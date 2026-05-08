"""Stripe payout sync — list payouts since cutoff, enqueue per-payout import jobs."""
import frappe
from frappe.utils import add_days, getdate, now


def sync_payouts(settings) -> dict:
    """Fetch payouts since (last_synced - 7 days) for one Stripe Settings row,
    enqueue import_payout for each payout that is not already completed or in-flight."""
    if not settings.payout_bank_account or not settings.payout_fee_account or not settings.payout_clearing_account:
        frappe.throw(
            f"Stripe Settings '{settings.name}' is missing payout account configuration. "
            "Set payout_bank_account, payout_fee_account, and payout_clearing_account."
        )

    cutoff = settings.last_payout_synced_at or "2026-04-01"
    fetch_from_date = add_days(getdate(cutoff), -7)
    fetch_from_unix = int(frappe.utils.get_datetime(fetch_from_date).timestamp())

    from erpnext_stripe.utils.stripe_client import get_stripe_client
    stripe_lib = get_stripe_client(settings.name)

    payouts = []
    starting_after = None
    while True:
        params = {"arrival_date": {"gte": fetch_from_unix}, "limit": 100, "status": "paid"}
        if starting_after:
            params["starting_after"] = starting_after
        page = stripe_lib.Payout.list(**params)
        payouts.extend(page.data)
        if not page.has_more:
            break
        starting_after = page.data[-1].id

    enqueued = 0
    for p in payouts:
        if frappe.db.exists("Stripe Payout Log",
                            {"payout_id": p.id, "status": ["in", ["completed", "running"]]}):
            continue
        frappe.enqueue(
            "erpnext_stripe.api.import_payout.import_payout",
            queue="default", timeout=300,
            payout_id=p.id, triggered_by="scheduler", stripe_settings=settings.name,
        )
        enqueued += 1

    # Per-row write — bypasses optimistic-lock check, safe for parallel callers
    frappe.db.set_value("Stripe Settings", settings.name, "last_payout_synced_at", now())
    frappe.db.commit()
    return {"enqueued": enqueued, "scanned": len(payouts)}
