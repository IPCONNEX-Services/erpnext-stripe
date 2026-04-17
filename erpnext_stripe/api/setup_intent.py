import frappe

from erpnext_stripe.utils.stripe_client import get_stripe_client


@frappe.whitelist()
def create_setup_intent(stripe_customer: str) -> dict:
    """Create a Stripe SetupIntent for adding a new card. Returns client_secret."""
    sc = frappe.get_doc("Stripe Customer", stripe_customer)
    stripe = get_stripe_client(sc.stripe_settings)

    intent = stripe.SetupIntent.create(
        customer=sc.stripe_customer_id,
        usage="off_session",
        payment_method_types=["card"],
    )
    return {"client_secret": intent.client_secret}


@frappe.whitelist()
def refresh_payment_methods(stripe_customer: str):
    """Re-fetch payment methods from Stripe and update the Stripe Customer record."""
    frappe.get_doc("Stripe Customer", stripe_customer).refresh_payment_methods()
    return {"status": "ok"}


@frappe.whitelist()
def set_default_card(stripe_customer: str, stripe_pm_id: str):
    """Set a card as the default payment method for a Stripe customer."""
    sc = frappe.get_doc("Stripe Customer", stripe_customer)
    stripe = get_stripe_client(sc.stripe_settings)

    stripe.Customer.modify(
        sc.stripe_customer_id,
        invoice_settings={"default_payment_method": stripe_pm_id},
    )

    for pm in sc.payment_methods:
        pm.is_default = 1 if pm.stripe_pm_id == stripe_pm_id else 0
    sc.save(ignore_permissions=True)
    return {"status": "ok"}


@frappe.whitelist()
def remove_card(stripe_customer: str, stripe_pm_id: str):
    """Detach a card from the Stripe customer."""
    sc = frappe.get_doc("Stripe Customer", stripe_customer)
    stripe = get_stripe_client(sc.stripe_settings)

    stripe.PaymentMethod.detach(stripe_pm_id)

    sc.payment_methods = [pm for pm in sc.payment_methods if pm.stripe_pm_id != stripe_pm_id]
    sc.save(ignore_permissions=True)
    return {"status": "ok"}


@frappe.whitelist()
def send_card_setup_email(customer: str, stripe_settings: str):
    """Send a time-limited card-setup link to the customer's primary email."""
    from frappe.utils import get_url
    from erpnext_stripe.utils.notifications import send_card_setup_email as _send

    token_data = {
        "customer": customer,
        "stripe_settings": stripe_settings,
    }
    # 48-hour expiry signed URL
    signed = frappe.utils.make_signed_url(
        "/add-card", token_data, expires_in=172800
    )
    setup_url = get_url(signed)
    _send(customer, setup_url)
    return {"status": "ok"}
