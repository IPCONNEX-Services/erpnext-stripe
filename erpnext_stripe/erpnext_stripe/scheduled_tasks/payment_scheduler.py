import frappe
from frappe.utils import now


def run_due_payments():
    """
    Called hourly. Charges invoices whose payment trigger condition is met
    and which have no succeeded Stripe Payment Log.
    """
    settings_list = frappe.get_all(
        "Stripe Settings",
        filters={"is_default": 1, "default_payment_trigger": ["!=", "Manual Only"]},
        fields=["name", "company", "default_payment_trigger", "payment_trigger_days"],
    )

    for settings in settings_list:
        invoices = _get_due_invoices(settings)
        for inv_name in invoices:
            frappe.enqueue(
                "erpnext_stripe.api.payment_intent.charge_invoice",
                sales_invoice=inv_name,
                stripe_settings=settings.name,
                queue="default",
                now=False,
                job_id=f"stripe_charge_{inv_name}",
                deduplicate=True,
            )


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
        return  # Already resolved

    charge_invoice(
        sales_invoice=log.sales_invoice,
        stripe_settings=log.stripe_settings,
    )


def _get_due_invoices(settings: dict) -> list[str]:
    """Return invoice names that match the payment trigger for the given Stripe Settings."""
    from frappe.utils import add_days, today

    base_filters = {
        "company": settings.company,
        "docstatus": 1,
        "outstanding_amount": [">", 0],
        "status": ["not in", ["Paid", "Cancelled", "Return"]],
    }

    already_charged = frappe.db.get_all(
        "Stripe Payment Log",
        filters={"status": ["in", ["succeeded", "processing"]]},
        pluck="sales_invoice",
    )
    if already_charged:
        base_filters["name"] = ["not in", already_charged]

    trigger = settings.default_payment_trigger

    if trigger == "On Due Date":
        base_filters["due_date"] = ["<=", today()]

    elif trigger == "After X Days":
        days = settings.payment_trigger_days or 0
        cutoff = add_days(today(), -days)
        base_filters["due_date"] = ["<=", cutoff]

    # "On Invoice Submission" is handled by the on_submit hook, not here

    return frappe.db.get_all("Sales Invoice", filters=base_filters, pluck="name")
