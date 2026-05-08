import frappe
from frappe.model.document import Document


class StripePayoutLog(Document):
    @frappe.whitelist()
    def retry(self):
        if self.status != "failed":
            frappe.throw(f"Retry valid only for status=failed (current: {self.status})")
        payout_id = self.payout_id
        frappe.delete_doc("Stripe Payout Log", self.name, ignore_permissions=True)
        frappe.db.commit()
        from erpnext_stripe.api.import_payout import import_payout
        return import_payout(payout_id=payout_id, triggered_by="retry")
