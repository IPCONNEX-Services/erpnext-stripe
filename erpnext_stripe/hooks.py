app_name = "erpnext_stripe"
app_title = "Stripe Payments for ERPNext"
app_publisher = "IPCONNEX"
app_description = "Full Stripe integration for ERPNext — multi-company, PCI-compliant, with automated invoice collection and retry scheduling"
app_email = "dev@ipconnex.com"
app_license = "MIT"
app_version = "1.0.0"

required_apps = ["frappe", "erpnext"]

# Scheduled jobs
scheduler_events = {
    "hourly": [
        "erpnext_stripe.scheduled_tasks.payment_scheduler.run_due_payments",
        "erpnext_stripe.scheduled_tasks.payment_scheduler.process_retries",
    ],
    "cron": {
        # Daily 2:30am Montreal — offset from Pax8 (1:00) and OVH (1:30)
        "30 2 * * *": [
            "erpnext_stripe.scheduled_tasks.payout_scheduler.run_if_due",
        ],
        # Every 10 minutes — safety net for failed webhook deliveries
        "*/10 * * * *": [
            "erpnext_stripe.scheduled_tasks.reconciler.reconcile_stuck_payments",
        ],
    },
}

# Load Stripe.js only on pages that need it (portal card pages)
web_include_js = []

# Connections tab: surface Stripe Customer on the Customer form.
# Chains with the other apps' Customer dashboard overrides (frappe applies every hook).
override_doctype_dashboards = {
    "Customer": "erpnext_stripe.customer_dashboard_overrides.add_stripe",
}

# DocType JS overrides for Customer form dashboard
doctype_js = {
    "Customer": "public/js/customer_stripe_dashboard.js",
    "Sales Invoice": "public/js/sales_invoice_stripe.js",
}

# On Sales Invoice submit — send card invite if no default card
# DISABLED 2026-04-29 during v15→v16 recurring cutover (user direction). The hook
# attempts get_default_stripe_settings, which uses frappe.throw and leaks an error
# toast even when caught (upstream bug). With Stripe Settings is_default=0 on both
# records, no auto-charge/email fires either way; commenting this out makes the
# disable explicit and silences the toast. Re-enable when ready.
# doc_events = {
#     "Sales Invoice": {
#         "on_submit": "erpnext_stripe.api.payment_intent.on_invoice_submit",
#     }
# }
