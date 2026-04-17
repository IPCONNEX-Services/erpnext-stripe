import frappe
from frappe.model.document import Document


class StripeCustomer(Document):
    def get_default_payment_method(self):
        for pm in self.payment_methods:
            if pm.is_default:
                return pm
        return None

    def refresh_payment_methods(self):
        from erpnext_stripe.utils.stripe_client import get_stripe_client

        stripe = get_stripe_client(self.stripe_settings)
        pms = stripe.PaymentMethod.list(customer=self.stripe_customer_id, type="card")

        existing_ids = {pm.stripe_pm_id for pm in self.payment_methods}
        for pm_data in pms.data:
            if pm_data.id not in existing_ids:
                self.append(
                    "payment_methods",
                    {
                        "stripe_pm_id": pm_data.id,
                        "brand": pm_data.card.brand,
                        "last4": pm_data.card.last4,
                        "exp_month": pm_data.card.exp_month,
                        "exp_year": pm_data.card.exp_year,
                        "is_default": 0,
                    },
                )

        # Mark default from Stripe customer default_source / invoice_settings
        stripe_cus = stripe.Customer.retrieve(self.stripe_customer_id)
        default_pm_id = (
            stripe_cus.get("invoice_settings", {}).get("default_payment_method")
            or stripe_cus.get("default_source")
        )
        if default_pm_id:
            for pm in self.payment_methods:
                pm.is_default = 1 if pm.stripe_pm_id == default_pm_id else 0

        self.synced_at = frappe.utils.now()
        self.save()
