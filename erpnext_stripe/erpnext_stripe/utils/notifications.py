import frappe


def desk_alert(title: str, message: str, doc_type: str = None, doc_name: str = None):
    """Create a Frappe desk notification for the billing team."""
    users = _get_billing_users()
    for user in users:
        notification = frappe.new_doc("Notification Log")
        notification.subject = title
        notification.email_content = message
        notification.for_user = user
        notification.type = "Alert"
        if doc_type and doc_name:
            notification.document_type = doc_type
            notification.document_name = doc_name
        notification.insert(ignore_permissions=True)


def send_customer_failure_email(customer: str, sales_invoice: str, attempt_number: int):
    """Send a payment failure notification email to the customer's primary contact."""
    contact_email = _get_customer_email(customer)
    if not contact_email:
        return

    frappe.sendmail(
        recipients=[contact_email],
        subject=f"Payment attempt failed for invoice {sales_invoice}",
        template="stripe_payment_failure",
        args={
            "customer": customer,
            "sales_invoice": sales_invoice,
            "attempt_number": attempt_number,
        },
        now=False,
    )


def send_card_setup_email(customer: str, setup_url: str):
    """Send an email inviting the customer to add their card."""
    contact_email = _get_customer_email(customer)
    if not contact_email:
        frappe.throw(f"No email found for customer '{customer}'")

    frappe.sendmail(
        recipients=[contact_email],
        subject="Add your payment card",
        template="stripe_card_setup_invite",
        args={"customer": customer, "setup_url": setup_url},
        now=False,
    )


def _get_customer_email(customer: str) -> str | None:
    return frappe.db.get_value("Customer", customer, "email_id") or frappe.db.get_value(
        "Contact",
        {"link_doctype": "Customer", "link_name": customer, "is_primary_contact": 1},
        "email_id",
    )


def _get_billing_users() -> list[str]:
    """Return users with Accounts Manager role."""
    return frappe.db.get_all(
        "Has Role",
        filters={"role": ["in", ["Accounts Manager", "System Manager"]], "parenttype": "User"},
        pluck="parent",
        distinct=True,
    )
