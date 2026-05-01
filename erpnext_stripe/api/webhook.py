import json

import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def handle():
    """Single webhook endpoint for all Stripe events."""
    payload = frappe.request.data
    sig_header = frappe.request.headers.get("Stripe-Signature")

    stripe_settings_name = frappe.request.args.get("settings")
    if not stripe_settings_name:
        frappe.throw(_("Missing 'settings' query parameter"), frappe.PermissionError)

    settings = frappe.get_doc("Stripe Settings", stripe_settings_name)
    webhook_secret = settings.get_password("webhook_secret")

    import stripe

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        frappe.throw(_("Invalid Stripe webhook signature"), frappe.PermissionError)

    event_type = event["type"]
    frappe.logger("erpnext_stripe").debug(f"Stripe webhook received: {event_type} ({event['id']})")

    routers = {
        "payment_intent.succeeded": _handle_payment_succeeded,
        "payment_intent.payment_failed": _handle_payment_failed,
        "setup_intent.succeeded": _handle_setup_succeeded,
        "customer.updated": _handle_customer_updated,
    }

    handler = routers.get(event_type)
    if handler:
        handler(event, stripe_settings_name)

    return {"status": "ok"}


def _handle_payment_succeeded(event: dict, stripe_settings: str):
    intent_id = event["data"]["object"]["id"]
    amount_received = event["data"]["object"]["amount_received"] / 100

    log = _get_log_by_intent(intent_id)
    if not log or log.status == "succeeded":
        return  # idempotent

    from erpnext_stripe.utils.payment_entry import create_and_reconcile
    from erpnext_stripe.utils.notifications import desk_alert

    pe_name = create_and_reconcile(log.sales_invoice, amount_received, stripe_settings)

    frappe.db.set_value("Stripe Payment Log", log.name, {
        "status": "succeeded",
        "payment_entry": pe_name,
        "event_data": json.dumps(event),
    })

    frappe.get_doc("Sales Invoice", log.sales_invoice).add_comment(
        "Comment",
        f"Stripe payment succeeded — {amount_received} | Payment Entry: {pe_name}",
    )

    desk_alert(
        title=f"Payment received for {log.sales_invoice}",
        message=f"Stripe payment of {amount_received} succeeded. Payment Entry: {pe_name}",
        doc_type="Sales Invoice",
        doc_name=log.sales_invoice,
    )


def _handle_payment_failed(event: dict, stripe_settings: str):
    from frappe.utils import add_to_date, now

    intent = event["data"]["object"]
    intent_id = intent["id"]
    # v15 SDK: last_payment_error is a StripeObject — use getattr, not .get()
    raw_error = getattr(intent, "last_payment_error", None)
    error_code = getattr(raw_error, "code", None) if raw_error else None
    error_message = getattr(raw_error, "message", None) if raw_error else None

    log = _get_log_by_intent(intent_id)
    if not log or log.status == "succeeded":
        return

    company = frappe.db.get_value("Sales Invoice", log.sales_invoice, "company")
    schedule = _get_retry_schedule(company)
    next_attempt = log.attempt_number + 1
    max_attempts = schedule.max_attempts if schedule else 3

    if next_attempt > max_attempts:
        frappe.db.set_value("Stripe Payment Log", log.name, {
            "status": "failed",
            "stripe_error_code": error_code,
            "stripe_error_message": error_message,
            "event_data": json.dumps(event),
        })
        frappe.get_doc("Sales Invoice", log.sales_invoice).add_comment(
            "Comment",
            f"Stripe payment failed (attempt #{log.attempt_number}) — "
            f"{error_message or error_code}. No more retries.",
        )
        _notify_failure(log, schedule, final=True)
        return

    delay_hours = schedule.get_delay_for_attempt(next_attempt) if schedule else 24
    next_retry_at = add_to_date(now(), hours=delay_hours)

    frappe.db.set_value("Stripe Payment Log", log.name, {
        "status": "failed",
        "stripe_error_code": error_code,
        "stripe_error_message": error_message,
        "next_retry_at": next_retry_at,
        "event_data": json.dumps(event),
    })

    frappe.get_doc("Sales Invoice", log.sales_invoice).add_comment(
        "Comment",
        f"Stripe payment failed (attempt #{log.attempt_number}) — "
        f"{error_message or error_code}. Next retry: {next_retry_at}.",
    )

    _notify_failure(log, schedule, final=False)


def _handle_setup_succeeded(event: dict, stripe_settings: str):
    setup_intent = event["data"]["object"]
    stripe_customer_id = getattr(setup_intent, "customer", None)
    pm_id = getattr(setup_intent, "payment_method", None)

    if not stripe_customer_id or not pm_id:
        return

    stripe_customer_name = frappe.db.get_value(
        "Stripe Customer",
        {"stripe_customer_id": stripe_customer_id, "stripe_settings": stripe_settings},
        "name",
    )
    if not stripe_customer_name:
        return

    stripe_customer = frappe.get_doc("Stripe Customer", stripe_customer_name)

    import stripe
    settings = frappe.get_doc("Stripe Settings", stripe_settings)
    stripe.api_key = settings.get_password("secret_key")

    pm_data = stripe.PaymentMethod.retrieve(pm_id)
    card = pm_data.card

    existing = next((p for p in stripe_customer.payment_methods if p.stripe_pm_id == pm_id), None)
    if not existing:
        stripe_customer.append("payment_methods", {
            "stripe_pm_id": pm_id,
            "brand": card.brand,
            "last4": card.last4,
            "exp_month": card.exp_month,
            "exp_year": card.exp_year,
            "is_default": 1 if not stripe_customer.payment_methods else 0,
        })
        stripe_customer.save(ignore_permissions=True)


def _handle_customer_updated(event: dict, stripe_settings: str):
    stripe_customer_id = event["data"]["object"]["id"]
    stripe_customer_name = frappe.db.get_value(
        "Stripe Customer",
        {"stripe_customer_id": stripe_customer_id, "stripe_settings": stripe_settings},
        "name",
    )
    if stripe_customer_name:
        frappe.get_doc("Stripe Customer", stripe_customer_name).refresh_payment_methods()


def _get_log_by_intent(intent_id: str):
    name = frappe.db.get_value(
        "Stripe Payment Log", {"stripe_payment_intent_id": intent_id}, "name"
    )
    return frappe.get_doc("Stripe Payment Log", name) if name else None


def _get_retry_schedule(company: str):
    name = frappe.db.get_value("Stripe Retry Schedule", {"company": company}, "name")
    return frappe.get_doc("Stripe Retry Schedule", name) if name else None


def _notify_failure(log, schedule, final: bool):
    from erpnext_stripe.utils.notifications import desk_alert, send_customer_failure_email

    customer = frappe.db.get_value("Sales Invoice", log.sales_invoice, "customer")
    notify_after = schedule.notify_customer_after_attempt if schedule else 2

    desk_alert(
        title=f"Payment failed for {log.sales_invoice} (attempt {log.attempt_number})",
        message=f"Error: {log.stripe_error_message or log.stripe_error_code}. "
                + ("No more retries." if final else "Next retry scheduled."),
        doc_type="Stripe Payment Log",
        doc_name=log.name,
    )

    if log.attempt_number >= notify_after:
        send_customer_failure_email(customer, log.sales_invoice, log.attempt_number)
