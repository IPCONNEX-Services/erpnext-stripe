import frappe
from frappe.utils import add_days, getdate, now, today


def run_due_payments():
    """
    Called hourly. For each company's default Stripe Settings, fetch all candidate
    invoices and charge those whose effective trigger (company or customer-level) is met.
    """
    settings_list = frappe.get_all(
        "Stripe Settings",
        filters={"is_default": 1},
        fields=["name", "company", "default_payment_trigger", "payment_trigger_days"],
    )

    for settings in settings_list:
        candidates = _get_candidate_invoices(settings)
        for inv in candidates:
            _maybe_enqueue(inv, settings)


def process_retries():
    """
    Called hourly. Re-attempts failed payments whose next_retry_at has passed.
    """
    due_retries = frappe.get_all(
        "Stripe Payment Log",
        filters={
            "status": "failed",
            "next_retry_at": ["<=", now()],
        },
        fields=["name", "sales_invoice", "stripe_settings", "attempt_number"],
    )

    for log in due_retries:
        frappe.enqueue(
            "erpnext_stripe.scheduled_tasks.payment_scheduler._retry_payment",
            log_name=log.name,
            queue="default",
            now=False,
            job_id=f"stripe_retry_{log.name}",
            deduplicate=True,
        )


def _retry_payment(log_name: str):
    from erpnext_stripe.api.payment_intent import charge_invoice

    log = frappe.get_doc("Stripe Payment Log", log_name)
    if log.status != "failed":
        return

    charge_invoice(
        sales_invoice=log.sales_invoice,
        stripe_settings=log.stripe_settings,
    )


def _maybe_enqueue(inv: dict, settings: dict):
    """Charge inv if its effective trigger condition is met."""
    from erpnext_stripe.utils.stripe_client import get_stripe_customer

    sc = get_stripe_customer(inv.customer, settings.name)
    if not sc or not sc.get_default_payment_method():
        return

    trigger, days = sc.get_effective_trigger()

    if trigger in ("Manual Only", "On Invoice Submission"):
        return

    due = getdate(inv.due_date)

    if trigger == "On Due Date":
        if due > getdate(today()):
            return
    elif trigger == "After X Days":
        cutoff = getdate(add_days(today(), -days))
        if due > cutoff:
            return

    frappe.enqueue(
        "erpnext_stripe.api.payment_intent.charge_invoice",
        sales_invoice=inv.name,
        stripe_settings=settings.name,
        queue="default",
        now=False,
        job_id=f"stripe_charge_{inv.name}",
        deduplicate=True,
    )


def _get_candidate_invoices(settings: dict) -> list:
    """Return all submitted, outstanding, not-yet-charged invoices for this company."""
    already_charged = frappe.db.get_all(
        "Stripe Payment Log",
        filters={"status": ["in", ["succeeded", "processing"]]},
        pluck="sales_invoice",
    )

    filters = {
        "company": settings.company,
        "docstatus": 1,
        "outstanding_amount": [">", 0],
        "status": ["not in", ["Paid", "Cancelled", "Return"]],
    }
    if already_charged:
        filters["name"] = ["not in", already_charged]

    return frappe.db.get_all(
        "Sales Invoice",
        filters=filters,
        fields=["name", "customer", "due_date"],
    )
