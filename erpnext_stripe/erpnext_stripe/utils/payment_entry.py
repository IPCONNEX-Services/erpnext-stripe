import frappe
from frappe.utils import flt


def create_and_reconcile(sales_invoice_name: str, amount: float, stripe_settings_name: str) -> str:
    """Create a submitted Payment Entry for the invoice and reconcile it. Returns PE name."""
    invoice = frappe.get_doc("Sales Invoice", sales_invoice_name)
    settings = frappe.get_doc("Stripe Settings", stripe_settings_name)

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = invoice.company
    pe.posting_date = frappe.utils.today()
    pe.mode_of_payment = _get_or_create_stripe_mode()
    pe.party_type = "Customer"
    pe.party = invoice.customer
    pe.paid_amount = flt(amount)
    pe.received_amount = flt(amount)
    pe.target_exchange_rate = 1
    pe.paid_from = _get_receivable_account(invoice.company)
    pe.paid_to = _get_stripe_bank_account(settings)
    pe.reference_no = f"stripe-{sales_invoice_name}"
    pe.reference_date = frappe.utils.today()

    pe.append(
        "references",
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": sales_invoice_name,
            "total_amount": invoice.grand_total,
            "outstanding_amount": invoice.outstanding_amount,
            "allocated_amount": flt(amount),
        },
    )

    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe.name


def _get_or_create_stripe_mode() -> str:
    if frappe.db.exists("Mode of Payment", "Stripe"):
        return "Stripe"
    mop = frappe.new_doc("Mode of Payment")
    mop.mode_of_payment = "Stripe"
    mop.type = "General"
    mop.insert(ignore_permissions=True)
    return "Stripe"


def _get_receivable_account(company: str) -> str:
    return frappe.db.get_value(
        "Company", company, "default_receivable_account"
    ) or frappe.throw(f"No default receivable account for company '{company}'")


def _get_stripe_bank_account(settings) -> str:
    """Return the bank/cash account configured on the Mode of Payment for this company."""
    mop_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": "Stripe", "company": settings.company},
        "default_account",
    )
    if not mop_account:
        frappe.throw(
            "Please configure a default account for the 'Stripe' Mode of Payment "
            f"for company '{settings.company}'."
        )
    return mop_account
