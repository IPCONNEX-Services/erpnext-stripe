import frappe
from frappe import _

from erpnext_stripe.utils.stripe_client import get_stripe_client


def _check_desk_permission(stripe_customer: str):
    if not frappe.has_permission("Stripe Customer", "write", doc=stripe_customer):
        frappe.throw(_("Not permitted to manage cards for this customer."), frappe.PermissionError)


def get_publishable_key(stripe_settings: str) -> str:
    """Return the publishable key, failing loudly when it is missing or malformed.

    Stripe.js silently refuses to initialise on a bad key and the card form just
    never appears, so the shape is checked here instead.
    """
    key = frappe.db.get_value("Stripe Settings", stripe_settings, "publishable_key") or ""
    if not key.startswith("pk_"):
        frappe.throw(
            _("Stripe Settings '{0}' has no valid Publishable Key (it must start with 'pk_'). "
              "Copy it from the Stripe dashboard under Developers → API keys.").format(stripe_settings)
        )
    return key


def build_setup_intent(sc) -> dict:
    """Create a SetupIntent for a Stripe Customer doc. No permission check — the
    callers (desk endpoint, tokenised portal page) each do their own."""
    stripe = get_stripe_client(sc.stripe_settings)

    intent = stripe.SetupIntent.create(
        customer=sc.stripe_customer_id,
        usage="off_session",
        payment_method_types=["card"],
    )
    return {
        "client_secret": intent.client_secret,
        "publishable_key": get_publishable_key(sc.stripe_settings),
        "stripe_customer": sc.name,
    }


@frappe.whitelist()
def create_setup_intent(stripe_customer: str) -> dict:
    """Create a Stripe SetupIntent for adding a new card from the desk.

    Returns the client_secret plus the publishable key so the desk dialog can
    mount Stripe Elements without a second round trip.
    """
    _check_desk_permission(stripe_customer)
    return build_setup_intent(frappe.get_doc("Stripe Customer", stripe_customer))


@frappe.whitelist()
def get_card_setup_link(stripe_customer: str) -> dict:
    """Return a shareable, expiring card-setup URL for this Stripe Customer."""
    from erpnext_stripe.utils.setup_links import DEFAULT_EXPIRY_SECONDS, get_setup_url

    _check_desk_permission(stripe_customer)
    return {
        "url": get_setup_url(stripe_customer),
        "expires_in_hours": DEFAULT_EXPIRY_SECONDS // 3600,
    }


@frappe.whitelist()
def refresh_payment_methods(stripe_customer: str):
    """Re-fetch payment methods from Stripe and update the Stripe Customer record."""
    _check_desk_permission(stripe_customer)
    frappe.get_doc("Stripe Customer", stripe_customer).refresh_payment_methods()
    return {"status": "ok"}


@frappe.whitelist(allow_guest=True)
def confirm_card_added(token: str):
    """Called by the public add-card page once Stripe confirms the SetupIntent.

    Pulls the new card into the Stripe Customer child table so the billing team
    sees it without hitting "Refresh Cards", and alerts them that it landed.
    Guarded by the same signed token that granted access to the page.
    """
    from erpnext_stripe.utils.notifications import desk_alert
    from erpnext_stripe.utils.setup_links import verify_setup_token

    sc_name = verify_setup_token(token)["sc"]

    frappe.set_user("Administrator")
    sc = frappe.get_doc("Stripe Customer", sc_name)
    sc.refresh_payment_methods()

    desk_alert(
        _("Card added by customer"),
        _("{0} added a payment card via the card setup link.").format(sc.customer or sc.name),
        "Stripe Customer",
        sc.name,
    )
    frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def set_default_card(stripe_customer: str, stripe_pm_id: str):
    """Set a card as the default payment method for a Stripe customer."""
    _check_desk_permission(stripe_customer)
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
    _check_desk_permission(stripe_customer)
    sc = frappe.get_doc("Stripe Customer", stripe_customer)
    stripe = get_stripe_client(sc.stripe_settings)

    stripe.PaymentMethod.detach(stripe_pm_id)

    sc.payment_methods = [pm for pm in sc.payment_methods if pm.stripe_pm_id != stripe_pm_id]
    sc.save(ignore_permissions=True)
    return {"status": "ok"}


def send_card_setup_link(customer: str, stripe_settings: str) -> list[str]:
    """Email the customer a time-limited link to add their own card.

    No permission check — on_invoice_submit calls this as whoever submitted the
    invoice, and that user should not need Stripe Customer write rights. The
    desk endpoint below is the one that checks.
    """
    from erpnext_stripe.utils.notifications import send_card_setup_email as _send
    from erpnext_stripe.utils.setup_links import get_setup_url

    sc_name = frappe.db.get_value(
        "Stripe Customer",
        {"customer": customer, "stripe_settings": stripe_settings},
        "name",
    )
    if not sc_name:
        frappe.throw(
            _("No Stripe Customer record for {0} on {1}. Run a Stripe sync first.").format(
                customer, stripe_settings
            )
        )
    return _send(customer, get_setup_url(sc_name))


@frappe.whitelist()
def send_card_setup_email(customer: str, stripe_settings: str):
    """Desk action behind the "Email Setup Link to Customer" buttons."""
    sc_name = frappe.db.get_value(
        "Stripe Customer", {"customer": customer, "stripe_settings": stripe_settings}, "name"
    )
    if sc_name:
        _check_desk_permission(sc_name)
    return {"status": "ok", "recipients": send_card_setup_link(customer, stripe_settings)}
