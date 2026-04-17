from frappe.model.document import Document


class StripeRetrySchedule(Document):
    def get_delay_for_attempt(self, attempt_number: int) -> int:
        """Return hours to wait before this attempt number (1-indexed)."""
        delays = [
            self.attempt_1_delay_hours or 24,
            self.attempt_2_delay_hours or 72,
            self.attempt_3_delay_hours or 168,
        ]
        idx = attempt_number - 2  # attempt 2 uses delays[0], etc.
        if idx < 0:
            return 0
        return delays[min(idx, len(delays) - 1)]
