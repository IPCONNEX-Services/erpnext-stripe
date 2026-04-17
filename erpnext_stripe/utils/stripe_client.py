import frappe


def get_stripe_client(stripe_settings_name: str):
    """Return a configured stripe module for the given Stripe Settings record."""
    import stripe

    settings = frappe.get_doc("Stripe Settings", stripe_settings_name)
    stripe.api_key = settings.get_password("secret_key")
    return stripe


def get_default_stripe_settings(company: str, mode: str = "Production") -> str:
    """Return the name of the default Stripe Settings for a company + mode."""
    name = frappe.db.get_value(
        "Stripe Settings",
        {"company": company, "mode": mode, "is_default": 1},
        "name",
    )
    if not name:
        frappe.throw(
            f"No default Stripe Settings found for company '{company}' in {mode} mode. "
            "Please configure one in Stripe Settings."
        )
    return name


def get_stripe_customer(customer: str, stripe_settings: str) -> "frappe.Document | None":
    """Return the Stripe Customer doc for an ERPNext customer + settings pair."""
    name = frappe.db.get_value(
        "Stripe Customer",
        {"customer": customer, "stripe_settings": stripe_settings},
        "name",
    )
    return frappe.get_doc("Stripe Customer", name) if name else None
