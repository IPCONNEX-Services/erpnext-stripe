import frappe

from erpnext_stripe.api.setup_intent import build_setup_intent
from erpnext_stripe.utils.setup_links import verify_setup_token

no_cache = 1


def get_context(context):
    """Render the customer-facing card entry form for a signed token.

    Access is granted only by the signed `token` query param (see
    utils/setup_links). Desk users add cards from the Stripe Customer form
    dialog instead, so there is no staff branch here.
    """
    context.no_cache = 1

    payload = verify_setup_token(frappe.request.args.get("token"))

    # The token is the authorisation — read the record as Administrator so the
    # page works for a Guest (the customer clicking a link from their inbox).
    frappe.set_user("Administrator")

    sc_name = payload["sc"]
    if not frappe.db.exists("Stripe Customer", sc_name):
        frappe.throw("Stripe customer record not found.", frappe.DoesNotExistError)

    sc = frappe.get_doc("Stripe Customer", sc_name)
    intent = build_setup_intent(sc)

    context.publishable_key = intent["publishable_key"]
    context.client_secret = intent["client_secret"]
    context.stripe_customer = sc.name
    context.token = frappe.request.args.get("token")
    context.customer_name = frappe.db.get_value("Customer", sc.customer, "customer_name") or ""
