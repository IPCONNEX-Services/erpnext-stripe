import frappe


def get_context(context):
    token = frappe.request.args.get("token")
    stripe_customer_param = frappe.request.args.get("stripe_customer")
    client_secret_param = frappe.request.args.get("client_secret")

    context.no_cache = 1

    # Direct link from Stripe Customer form (staff use)
    if stripe_customer_param and client_secret_param:
        sc = frappe.get_doc("Stripe Customer", stripe_customer_param)
        settings = frappe.get_doc("Stripe Settings", sc.stripe_settings)
        context.publishable_key = settings.publishable_key
        context.client_secret = client_secret_param
        context.stripe_customer = stripe_customer_param
        context.customer_name = frappe.db.get_value("Customer", sc.customer, "customer_name") or ""
        return

    # Email invite link (token-based)
    if not token:
        frappe.throw("Invalid or missing token", frappe.PermissionError)

    try:
        data = frappe.utils.verify_signed_url(token)
    except Exception:
        frappe.throw("This link has expired or is invalid.", frappe.PermissionError)

    customer = data.get("customer")
    stripe_settings = data.get("stripe_settings")

    if not customer or not stripe_settings:
        frappe.throw("Invalid link parameters.", frappe.PermissionError)

    sc_name = frappe.db.get_value(
        "Stripe Customer",
        {"customer": customer, "stripe_settings": stripe_settings},
        "name",
    )
    if not sc_name:
        frappe.throw("Stripe customer record not found.", frappe.DoesNotExistError)

    from erpnext_stripe.api.setup_intent import create_setup_intent

    result = create_setup_intent(sc_name)
    settings_doc = frappe.get_doc("Stripe Settings", stripe_settings)

    context.publishable_key = settings_doc.publishable_key
    context.client_secret = result["client_secret"]
    context.stripe_customer = sc_name
    context.customer_name = frappe.db.get_value("Customer", customer, "customer_name") or ""
