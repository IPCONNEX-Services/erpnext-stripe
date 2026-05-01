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
    ]
}

# Load Stripe.js only on pages that need it (portal card pages)
web_include_js = []

# DocType JS overrides for Customer form dashboard
doctype_js = {
    "Customer": "public/js/customer_stripe_dashboard.js",
    "Sales Invoice": "public/js/sales_invoice_stripe.js",
}

# On Sales Invoice submit — send card invite if no default card
doc_events = {
    "Sales Invoice": {
        "on_submit": "erpnext_stripe.api.payment_intent.on_invoice_submit",
    }
}
