import frappe
from frappe import _

from erpnext_stripe.utils.stripe_client import get_default_stripe_settings, get_stripe_client, get_stripe_customer


@frappe.whitelist()
def charge_invoice(sales_invoice: str, stripe_settings: str = None) -> dict:
    """
    Initiate a payment for a Sales Invoice. Uses the customer's default card.
    If stripe_settings is not provided, uses the company's default.
    Returns the Stripe Payment Log name.
    """
    invoice = frappe.get_doc("Sales Invoice", sales_invoice)

    if not stripe_settings:
        stripe_settings = get_default_stripe_settings(invoice.company)

    sc = get_stripe_customer(invoice.customer, stripe_settings)
    if not sc:
        frappe.throw(_(f"No Stripe customer found for '{invoice.customer}'. Please sync or create one."))

    default_pm = sc.get_default_payment_method()
    if not default_pm:
        frappe.throw(_(f"No default payment method for customer '{invoice.customer}'."))

    stripe = get_stripe_client(stripe_settings)

    existing_log = frappe.db.get_value(
        "Stripe Payment Log",
        {"sales_invoice": sales_invoice, "status": "succeeded"},
        "name",
    )
    if existing_log:
        frappe.throw(_(f"Invoice {sales_invoice} has already been paid via Stripe."))

    last_attempt = frappe.db.get_value(
        "Stripe Payment Log",
        {"sales_invoice": sales_invoice},
        ["name", "attempt_number"],
        as_dict=True,
        order_by="creation desc",
    )
    attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1

    amount_cents = int(invoice.outstanding_amount * 100)
    currency = (invoice.currency or "usd").lower()

    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency=currency,
        customer=sc.stripe_customer_id,
        payment_method=default_pm.stripe_pm_id,
        confirm=True,
        off_session=True,
        metadata={"sales_invoice": sales_invoice, "erpnext_customer": invoice.customer},
    )

    log = frappe.new_doc("Stripe Payment Log")
    log.sales_invoice = sales_invoice
    log.stripe_customer = sc.name
    log.stripe_settings = stripe_settings
    log.stripe_payment_intent_id = intent.id
    log.stripe_pm_id = default_pm.stripe_pm_id
    log.amount = invoice.outstanding_amount
    log.currency = invoice.currency
    log.status = "processing"
    log.attempt_number = attempt_number
    log.triggered_by = "manual"
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"log": log.name, "intent_id": intent.id, "status": intent.status}


@frappe.whitelist()
def create_payment_intent_for_portal(sales_invoice: str) -> dict:
    """
    Create a PaymentIntent for customer-initiated payment via the portal.
    Returns client_secret for the Stripe Payment Element.
    """
    invoice = frappe.get_doc("Sales Invoice", sales_invoice)

    # Verify requesting user is the customer
    customer = frappe.db.get_value("Customer", {"email_id": frappe.session.user}, "name")
    if invoice.customer != customer:
        frappe.throw(_("Not authorized"), frappe.PermissionError)

    stripe_settings = get_default_stripe_settings(invoice.company)
    sc = get_stripe_customer(invoice.customer, stripe_settings)
    if not sc:
        frappe.throw(_("No Stripe customer record found."))

    stripe = get_stripe_client(stripe_settings)

    intent = stripe.PaymentIntent.create(
        amount=int(invoice.outstanding_amount * 100),
        currency=(invoice.currency or "usd").lower(),
        customer=sc.stripe_customer_id,
        setup_future_usage="off_session",
        metadata={"sales_invoice": sales_invoice},
    )

    log = frappe.new_doc("Stripe Payment Log")
    log.sales_invoice = sales_invoice
    log.stripe_customer = sc.name
    log.stripe_settings = stripe_settings
    log.stripe_payment_intent_id = intent.id
    log.amount = invoice.outstanding_amount
    log.currency = invoice.currency
    log.status = "processing"
    log.attempt_number = 1
    log.triggered_by = "customer_portal"
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    settings_doc = frappe.get_doc("Stripe Settings", stripe_settings)
    return {
        "client_secret": intent.client_secret,
        "publishable_key": settings_doc.publishable_key,
    }


def on_invoice_submit(doc, method):
    """
    Hook called on Sales Invoice submit.
    Sends card setup email if customer has no default card and trigger is configured.
    Also auto-charges if trigger is 'On Invoice Submission'.
    """
    try:
        stripe_settings_name = get_default_stripe_settings(doc.company, mode="Production")
    except Exception:
        return  # No Stripe configured for this company

    settings = frappe.get_doc("Stripe Settings", stripe_settings_name)
    sc = get_stripe_customer(doc.customer, stripe_settings_name)

    if not sc or not sc.get_default_payment_method():
        from erpnext_stripe.api.setup_intent import send_card_setup_email
        try:
            send_card_setup_email(doc.customer, stripe_settings_name)
        except Exception:
            pass  # Don't fail submission if email fails
        return

    if settings.default_payment_trigger == "On Invoice Submission":
        frappe.enqueue(
            "erpnext_stripe.api.payment_intent.charge_invoice",
            sales_invoice=doc.name,
            stripe_settings=stripe_settings_name,
            queue="default",
            now=False,
        )
