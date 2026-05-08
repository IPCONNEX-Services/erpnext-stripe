"""Daily cron entry — fires at 30 2 * * * Montreal."""
import frappe


def run_if_due():
    """Iterate Stripe Settings rows with payout_cron_enabled=1 and call sync_payouts on each."""
    rows = frappe.get_all("Stripe Settings", filters={"payout_cron_enabled": 1}, pluck="name")
    for name in rows:
        try:
            from erpnext_stripe.utils.sync_payouts import sync_payouts
            settings = frappe.get_doc("Stripe Settings", name)
            sync_payouts(settings)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Stripe payout_scheduler.run_if_due [{name}]")
