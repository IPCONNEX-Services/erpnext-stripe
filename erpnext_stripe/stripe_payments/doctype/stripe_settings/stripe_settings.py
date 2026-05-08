import frappe
from frappe.model.document import Document


class StripeSettings(Document):
    def validate(self):
        if self.is_default:
            self._clear_other_defaults()

    def _clear_other_defaults(self):
        frappe.db.set_value(
            "Stripe Settings",
            {
                "company": self.company,
                "mode": self.mode,
                "name": ("!=", self.name),
                "is_default": 1,
            },
            "is_default",
            0,
        )

    def get_stripe_client(self):
        import stripe

        stripe.api_key = self.get_password("secret_key")
        return stripe

    @frappe.whitelist()
    def sync_payouts_now(self):
        """Manual trigger of the Stripe payout sync for this row."""
        from erpnext_stripe.utils.sync_payouts import sync_payouts
        return sync_payouts(self)
