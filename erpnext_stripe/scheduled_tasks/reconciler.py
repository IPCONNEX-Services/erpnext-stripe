"""Safety net for Stripe Payment Logs that never received a webhook update.

If a `payment_intent.succeeded` webhook fails to deliver (network blip, signing
secret rotated out of sync, etc.), the local `Stripe Payment Log` row stays in
`processing` indefinitely while the actual charge succeeded upstream. This task
catches up by polling Stripe directly and re-running the same handler the
webhook would have called.

Runs every 10 minutes. Idempotent: the underlying `_handle_payment_succeeded`
short-circuits when the log is already `succeeded`.
"""

from datetime import datetime, timedelta, timezone

import frappe


def reconcile_stuck_payments(lookback_hours: int = 24, settle_age_minutes: int = 5):
    """Find Stripe Payment Logs stuck in `processing` and reconcile against
    Stripe's authoritative state.

    Args:
        lookback_hours: only consider logs created within this window — caps
            DB scan and stays inside Stripe's Event retention window.
        settle_age_minutes: ignore very recent logs — give the webhook a chance
            to deliver naturally first.
    """
    from erpnext_stripe.utils.stripe_client import get_stripe_client
    from erpnext_stripe.api.webhook import _handle_payment_succeeded, _handle_payment_failed

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    settle_cutoff = now_utc - timedelta(minutes=settle_age_minutes)
    lookback_cutoff = now_utc - timedelta(hours=lookback_hours)

    stuck = frappe.db.get_all(
        "Stripe Payment Log",
        filters=[
            ["status", "=", "processing"],
            ["stripe_payment_intent_id", "is", "set"],
            ["creation", "<=", settle_cutoff],
            ["creation", ">=", lookback_cutoff],
        ],
        fields=["name", "stripe_payment_intent_id", "stripe_settings", "sales_invoice"],
        order_by="creation asc",
    )

    if not stuck:
        return

    frappe.logger("erpnext_stripe").info(
        f"reconcile_stuck_payments: {len(stuck)} log(s) to check"
    )

    reconciled = errored = still_processing = 0
    for log in stuck:
        try:
            stripe = get_stripe_client(log.stripe_settings)
            pi = stripe.PaymentIntent.retrieve(log.stripe_payment_intent_id)
            if pi.status == "succeeded":
                synthetic = {
                    "type": "payment_intent.succeeded",
                    "id": f"reconcile_{log.stripe_payment_intent_id}",
                    "data": {"object": {
                        "id": pi.id,
                        "amount_received": pi.amount_received,
                    }},
                }
                _handle_payment_succeeded(synthetic, log.stripe_settings)
                reconciled += 1
            elif pi.status == "canceled":
                synthetic = {
                    "type": "payment_intent.payment_failed",
                    "id": f"reconcile_{log.stripe_payment_intent_id}",
                    "data": {"object": {
                        "id": pi.id,
                        "last_payment_error": pi.last_payment_error,
                    }},
                }
                _handle_payment_failed(synthetic, log.stripe_settings)
                reconciled += 1
            else:
                still_processing += 1
            frappe.db.commit()
        except Exception:
            errored += 1
            frappe.db.rollback()
            frappe.log_error(
                frappe.get_traceback(),
                f"reconcile_stuck_payments — {log.name} ({log.stripe_payment_intent_id})",
            )

    frappe.logger("erpnext_stripe").info(
        f"reconcile_stuck_payments done: reconciled={reconciled} "
        f"still_processing={still_processing} errored={errored}"
    )
