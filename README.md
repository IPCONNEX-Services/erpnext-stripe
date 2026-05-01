# Stripe Payments for ERPNext

A Frappe/ERPNext app for full Stripe payment integration — multi-company, PCI-compliant, with automated invoice collection, retry scheduling, and a hosted card management UI.

## Features

- **Multi-company:** each company can have multiple Stripe accounts (test + prod)
- **Customer sync:** import existing Stripe customers by ID or email; bi-directional sync
- **Card management:** list, add, remove, and set default cards per customer via Stripe's hosted Payment Element (PCI-compliant — no raw card data touches your server)
- **Flexible payment triggers:** company-level policy (on submission, on due date, after X days, or manual) with per-customer override
- **Manual charge controls:** "Charge via Stripe" button on any unpaid Sales Invoice; "Process Pending Invoices" on the Customer form to bulk-charge all outstanding invoices
- **Invoice activity trail:** every Stripe payment event (initiated, succeeded, failed, retried) is logged as a comment on the Sales Invoice timeline
- **Retry scheduling:** configurable retry delays (default 24h / 72h / 7d) with desk + customer email notifications
- **Customer portal:** add/manage cards from ERPNext's `/me` portal
- **Email card invite:** send a time-limited setup link to a customer to add their card
- **Automatic Payment Entry:** on payment success, a Payment Entry is created and reconciled against the invoice
- **Webhook-driven:** all payment outcomes confirmed via Stripe webhooks (idempotent handlers)

## Requirements

- ERPNext v15 or v16
- Python 3.10+
- A Stripe account (test + production keys)

## Installation

```bash
bench get-app https://github.com/ipconnex/erpnext-stripe
bench --site your-site.com install-app erpnext_stripe
bench --site your-site.com migrate
```

## Configuration

1. Go to **Stripe Settings** and create a new record
2. Select the Company, set mode to Test or Production
3. Enter your Stripe Publishable Key, Secret Key, and Webhook Secret
4. Check **Is Default** to make it the active account for that company + mode
5. Set **Default Payment Trigger** — this applies to all customers in that company
6. Click **Sync from Stripe** to import existing customers and payment methods

### Per-Customer Payment Policy

To override the company trigger for a specific customer, open their **Stripe Customer** record and set **Payment Trigger Override**:

| Override | Behavior |
|---|---|
| Use Company Default | Inherits from Stripe Settings |
| On Invoice Submission | Charges automatically when the Sales Invoice is submitted |
| On Due Date | Charged by the hourly scheduler when `due_date <= today` |
| After X Days | Charged X days after the due date (set the days field) |
| Manual Only | Never auto-charged — must be triggered from the invoice or customer form |

## Webhook Setup

In your Stripe dashboard, add a webhook endpoint pointing to:

```
https://your-erp-site.com/api/method/erpnext_stripe.api.webhook.handle
```

Subscribe to these events:
- `payment_intent.succeeded`
- `payment_intent.payment_failed`
- `setup_intent.succeeded`
- `customer.updated`

Copy the webhook signing secret into your **Stripe Settings** record.

## License

MIT
