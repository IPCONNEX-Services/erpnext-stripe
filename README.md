# Stripe Payments for ERPNext

A Frappe/ERPNext app for full Stripe payment integration — multi-company, PCI-compliant, with automated invoice collection, retry scheduling, and a hosted card management UI.

## Features

- **Multi-company:** each company can have multiple Stripe accounts (test + prod)
- **Customer sync:** import existing Stripe customers by ID or email; bi-directional sync
- **Card management:** list, add, remove, and set default cards per customer via Stripe's hosted Payment Element (PCI-compliant — no raw card data touches your server)
- **Invoice payment triggers:** on submission, on due date, after X days, or manual
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
5. Click **Sync from Stripe** to import existing customers and payment methods

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
