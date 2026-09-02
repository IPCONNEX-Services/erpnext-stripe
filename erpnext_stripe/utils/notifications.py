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


def send_card_setup_email(customer: str, setup_url: str) -> list[str]:
    """Email the customer a link to add their own card. Returns the recipients.

    Routed to the billing-flagged Contacts when this site has ipconnex_telecom's
    recipient resolver (billing mail must not land on a random contact), falling
    back to the customer's own email otherwise. The send is logged as a
    Communication on the Customer so the timeline shows who was invited and when.
    """
    recipients = _get_billing_recipients(customer)
    if not recipients:
        frappe.throw(f"No email found for customer '{customer}'")

    subject = "Add your payment card"
    message = frappe.render_template(
        "erpnext_stripe/templates/emails/stripe_card_setup_invite.html",
        {"customer": customer, "setup_url": setup_url},
    )

    comm = frappe.get_doc({
        "doctype": "Communication",
        "communication_type": "Communication",
        "communication_medium": "Email",
        "sent_or_received": "Sent",
        "subject": subject,
        "content": message,
        "recipients": ", ".join(recipients),
        "reference_doctype": "Customer",
        "reference_name": customer,
        "status": "Linked",
    })
    comm.insert(ignore_permissions=True)

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        now=True,
        reference_doctype="Customer",
        reference_name=customer,
        communication=comm.name,
    )
    return recipients


def _get_billing_recipients(customer: str) -> list[str]:
    """Billing-tagged contacts when ipconnex_telecom is installed, else the
    customer's primary email. erpnext_stripe must keep working without it."""
    try:
        from ipconnex_telecom.utils.billing_recipients import get_billing_recipients

        recipients = get_billing_recipients(customer, prefer_billing=True)
        if recipients:
            return recipients
    except ImportError:
        pass

    email = _get_customer_email(customer)
    return [email] if email else []


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
