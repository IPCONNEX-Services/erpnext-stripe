from frappe.model.document import Document


class StripePaymentLog(Document):
    def is_final(self) -> bool:
        return self.status in ("succeeded", "failed", "cancelled")
