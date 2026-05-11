import frappe
from frappe.model.document import Document


class StripeCustomer(Document):
    def get_effective_trigger(self) -> tuple:
        """Return (trigger, days) for this customer, respecting the override."""
        override = self.payment_trigger_override
        if override and override != "Use Company Default":
            return override, self.payment_trigger_days_override or 0
        settings = frappe.get_doc("Stripe Settings", self.stripe_settings)
        return settings.default_payment_trigger or "Manual Only", settings.payment_trigger_days or 0

    def _get_explicit_default(self):
        for pm in self.payment_methods:
            if pm.is_default:
                return pm
        return None

    def get_default_payment_method(self):
        """Return the explicitly-flagged default PM; fall back to the first row when none is flagged."""
        explicit = self._get_explicit_default()
        if explicit:
            return explicit
        return self.payment_methods[0] if self.payment_methods else None

    def validate(self):
        """Allow at most one row with is_default=1. When the user toggles a new row on while
        another was already set, prefer the newly-toggled row."""
        defaults = [pm for pm in self.payment_methods if pm.is_default]
        if len(defaults) <= 1:
            return
        prev_id = self._previous_default_id()
        for pm in self.payment_methods:
            pm.is_default = 0
        keeper = next((pm for pm in defaults if pm.stripe_pm_id != prev_id), defaults[-1])
        keeper.is_default = 1

    def on_update(self):
        """When the desk-side explicit default changes, push it to Stripe so future charges
        and Stripe-rendered invoices use the same card. Skipped when the change came from
        refresh_payment_methods (Stripe -> ERPNext sync) to avoid a no-op loop."""
        if self.flags.get("from_stripe_sync"):
            return
        current = self._get_explicit_default()
        if not current:
            return
        if self._previous_default_id() == current.stripe_pm_id:
            return
        from erpnext_stripe.utils.stripe_client import get_stripe_client

        stripe = get_stripe_client(self.stripe_settings)
        stripe.Customer.modify(
            self.stripe_customer_id,
            invoice_settings={"default_payment_method": current.stripe_pm_id},
        )

    def _previous_default_id(self):
        previous = self.get_doc_before_save()
        if not previous:
            return None
        for pm in previous.payment_methods:
            if pm.is_default:
                return pm.stripe_pm_id
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

        # Mark default from Stripe customer default_source / invoice_settings (v15 SDK: use getattr)
        stripe_cus = stripe.Customer.retrieve(self.stripe_customer_id)
        invoice_settings = getattr(stripe_cus, "invoice_settings", None)
        default_pm_id = (
            getattr(invoice_settings, "default_payment_method", None) if invoice_settings else None
        ) or getattr(stripe_cus, "default_source", None)
        if default_pm_id:
            for pm in self.payment_methods:
                pm.is_default = 1 if pm.stripe_pm_id == default_pm_id else 0

        self.synced_at = frappe.utils.now()
        self.flags.from_stripe_sync = True
        self.save()
