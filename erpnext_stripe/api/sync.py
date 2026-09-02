import frappe
from frappe import _


@frappe.whitelist()
def sync_from_stripe(stripe_settings: str) -> dict:
    """
    Sync all customers and payment methods from a Stripe account into ERPNext.
    Returns counts: matched, unmatched.
    """
    from erpnext_stripe.utils.stripe_client import get_stripe_client

    stripe = get_stripe_client(stripe_settings)

    matched = 0
    unmatched = 0
    starting_after = None

    while True:
        params = {"limit": 100}
        if starting_after:
            params["starting_after"] = starting_after

        response = stripe.Customer.list(**params)
        customers = response.data

        if not customers:
            break

        for stripe_cus in customers:
            erpnext_customer = _match_customer(stripe_cus)
            _upsert_stripe_customer(stripe_cus, erpnext_customer, stripe_settings, stripe)

            if erpnext_customer:
                matched += 1
            else:
                unmatched += 1

        if not response.has_more:
            break
        starting_after = customers[-1].id

    frappe.db.set_value("Stripe Settings", stripe_settings, "last_synced_at", frappe.utils.now())

    return {"matched": matched, "unmatched": unmatched}


def _match_customer(stripe_cus) -> str | None:
    """Try to find an ERPNext customer matching this Stripe customer. Returns name or None."""
    # 1. Match by Stripe Customer ID stored on existing Stripe Customer doc
    existing = frappe.db.get_value(
        "Stripe Customer", {"stripe_customer_id": stripe_cus.id}, "customer"
    )
    if existing:
        return existing

    # 2. Match by metadata.erpnext_customer (v15 SDK: use getattr, not .get())
    meta_name = getattr(stripe_cus.metadata, "erpnext_customer", None) if stripe_cus.metadata else None
    if meta_name and frappe.db.exists("Customer", meta_name):
        return meta_name

    # 3. Match by email
    if stripe_cus.email:
        customer_name = frappe.db.get_value("Customer", {"email_id": stripe_cus.email}, "name")
        if customer_name:
            return customer_name
        # Also check Contact
        contact = frappe.db.get_value(
            "Contact",
            {"email_id": stripe_cus.email},
            "name",
        )
        if contact:
            linked = frappe.db.get_value(
                "Dynamic Link",
                {"parent": contact, "link_doctype": "Customer"},
                "link_name",
            )
            if linked:
                return linked

    return None


def _upsert_stripe_customer(stripe_cus, erpnext_customer: str | None, stripe_settings: str, stripe):
    """Create or update a Stripe Customer doc and its payment methods."""
    existing_name = frappe.db.get_value(
        "Stripe Customer",
        {"stripe_customer_id": stripe_cus.id, "stripe_settings": stripe_settings},
        "name",
    )

    if existing_name:
        doc = frappe.get_doc("Stripe Customer", existing_name)
    else:
        doc = frappe.new_doc("Stripe Customer")
        doc.stripe_customer_id = stripe_cus.id
        doc.stripe_settings = stripe_settings

    doc.customer = erpnext_customer
    doc.unmatched_flag = 0 if erpnext_customer else 1
    doc.synced_at = frappe.utils.now()

    # Sync payment methods
    pms = stripe.PaymentMethod.list(customer=stripe_cus.id, type="card")
    invoice_settings = getattr(stripe_cus, "invoice_settings", None)
    default_pm_id = getattr(invoice_settings, "default_payment_method", None) if invoice_settings else None

    existing_pm_ids = {pm.stripe_pm_id for pm in doc.payment_methods}
    for pm_data in pms.data:
        if pm_data.id not in existing_pm_ids:
            doc.append("payment_methods", {
                "stripe_pm_id": pm_data.id,
                "brand": pm_data.card.brand,
                "last4": pm_data.card.last4,
                "exp_month": pm_data.card.exp_month,
                "exp_year": pm_data.card.exp_year,
                "is_default": 1 if pm_data.id == default_pm_id else 0,
            })

    # Update default flag on existing rows
    if default_pm_id:
        for pm in doc.payment_methods:
            pm.is_default = 1 if pm.stripe_pm_id == default_pm_id else 0

    if existing_name:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    return doc.name


@frappe.whitelist()
def get_customer_stripe_summary(customer: str) -> dict:
    """Return a summary of the Stripe state for a customer (used by Customer form dashboard)."""
    records = frappe.get_all(
        "Stripe Customer",
        filters={"customer": customer},
        fields=[
            "name",
            "stripe_customer_id",
            "stripe_settings",
            "synced_at",
            "payment_trigger_override",
            "payment_trigger_days_override",
            "unmatched_flag",
        ],
    )

    result = []
    for rec in records:
        settings = frappe.db.get_value(
            "Stripe Settings", rec.stripe_settings, ["mode", "company"], as_dict=True
        )
        pms = frappe.get_all(
            "Stripe Payment Method",
            filters={"parent": rec.name},
            fields=["stripe_pm_id", "brand", "last4", "exp_month", "exp_year", "is_default"],
        )
        result.append({
            **rec,
            "mode": settings.mode if settings else None,
            "company": settings.company if settings else None,
            "payment_methods": pms,
        })

    return result


@frappe.whitelist()
def get_stripe_account_options() -> list:
    """Stripe Settings a card can be set up against - default account first."""
    return frappe.get_all(
        "Stripe Settings",
        fields=["name", "company", "mode", "is_default"],
        order_by="is_default desc, mode asc, name asc",
    )


@frappe.whitelist()
def ensure_stripe_customer(customer: str, stripe_settings: str = None) -> dict:
    """Return a Stripe Customer for this ERPNext customer, creating one if needed.

    Lets the billing team start from a Customer that has never touched Stripe:
    the desk calls this, then opens the card dialog or emails a setup link
    against whatever comes back.

    An existing Stripe-side customer on the same email is adopted rather than
    duplicated, unless another ERPNext customer already claims it.
    """
    from erpnext_stripe.utils.stripe_client import get_stripe_client

    if not frappe.has_permission("Stripe Customer", "create"):
        frappe.throw(_("Not permitted to set up Stripe for this customer."), frappe.PermissionError)

    stripe_settings = stripe_settings or _default_stripe_settings()

    existing = frappe.db.get_value(
        "Stripe Customer", {"customer": customer, "stripe_settings": stripe_settings}, "name"
    )
    if existing:
        return {"stripe_customer": existing, "status": "existing", "stripe_settings": stripe_settings}

    cust = frappe.db.get_value("Customer", customer, ["customer_name", "email_id"], as_dict=True)
    if not cust:
        frappe.throw(_("Customer {0} not found.").format(customer))

    stripe = get_stripe_client(stripe_settings)
    email = cust.email_id or _primary_contact_email(customer)

    stripe_cus = _find_adoptable_stripe_customer(stripe, email) if email else None
    status = "adopted"

    if not stripe_cus:
        stripe_cus = stripe.Customer.create(
            name=cust.customer_name or customer,
            email=email or None,
            metadata={"erpnext_customer": customer},
        )
        status = "created"

    name = _upsert_stripe_customer(stripe_cus, customer, stripe_settings, stripe)
    frappe.db.commit()
    return {"stripe_customer": name, "status": status, "stripe_settings": stripe_settings}


def _default_stripe_settings() -> str:
    options = get_stripe_account_options()
    if not options:
        frappe.throw(_("No Stripe Settings configured."))
    default = [o for o in options if o.is_default]
    if default:
        return default[0].name
    if len(options) == 1:
        return options[0].name
    frappe.throw(_("More than one Stripe account and none marked default - pick the account to use."))


def _primary_contact_email(customer: str) -> str | None:
    return frappe.db.get_value(
        "Contact",
        {"link_doctype": "Customer", "link_name": customer, "is_primary_contact": 1},
        "email_id",
    )


def _find_adoptable_stripe_customer(stripe, email: str):
    """An existing Stripe customer on this email, unless another ERPNext customer
    already claims it - two ERPNext records must never share one Stripe id."""
    for candidate in stripe.Customer.list(email=email, limit=10).data:
        claimed_by = frappe.db.get_value(
            "Stripe Customer", {"stripe_customer_id": candidate.id}, "customer"
        )
        if not claimed_by:
            return candidate
    return None
