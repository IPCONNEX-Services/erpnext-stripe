# Stripe Payments for ERPNext

## Purpose
Full Stripe integration for ERPNext: multi-company payment processing, customer sync,
card management, payment triggers on invoice submit, automated retry scheduling,
webhook handling, and a customer self-service portal for card management.
Published on the Frappe Cloud marketplace. Version: 1.0.0.

## Paid Tier
FREE — all features included at no cost.

## Tech Stack
- Frappe v15+ / ERPNext v15+
- Python 3.10+
- Stripe REST API + Stripe.js (webhooks, PaymentIntents, Customers, Cards)
- ruff for linting

## Key Files
- `erpnext_stripe/hooks.py` — scheduler (hourly payments + retries), doc_events (Sales Invoice on_submit), doctype_js (Customer dashboard)
- `erpnext_stripe/api/payment_intent.py` — `on_invoice_submit()` handler, PaymentIntent creation
- `erpnext_stripe/api/` — Stripe API client, webhook handlers, customer sync
- `erpnext_stripe/stripe_payments/` — Payment DocTypes and processing logic
- `erpnext_stripe/scheduled_tasks/payment_scheduler.py` — `run_due_payments()`, `process_retries()`
- `erpnext_stripe/templates/` — customer portal templates
- `erpnext_stripe/public/js/customer_stripe_dashboard.js` — Customer form dashboard
- `erpnext_stripe/utils/` — helpers, encryption utilities
- `.github/workflows/ci.yml` — CI: lint + import-check

## Common Tasks

### Add a new webhook event handler
1. Add handler function in `erpnext_stripe/api/` (webhook module)
2. Register event type in the webhook router
3. ALWAYS verify Stripe webhook signature before processing:
   ```python
   import stripe
   event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
   ```
4. Use idempotency — check if event was already processed before acting

### Modify payment retry logic
- Entry point: `erpnext_stripe/scheduled_tasks/payment_scheduler.py` → `process_retries()`
- Retry state is tracked in a DocType — check the existing retry fields before modifying

### Add a multi-company setting
- Company-specific Stripe keys live in a Settings DocType — look in `erpnext_stripe/stripe_payments/`
- Never use a single global Stripe key; always resolve per-company

### Test webhook locally (on bench server)
```bash
# Use Stripe CLI to forward webhooks
stripe listen --forward-to https://site_name/api/method/erpnext_stripe.api.webhook.handle
```

### Cut a release
1. Bump version in `setup.py` and `erpnext_stripe/hooks.py` (app_version)
2. Follow Release Procedure in the Frappe/ERPNext skill.

## Gotchas
- Stripe webhook signature MUST be verified before trusting the payload — never skip `stripe.Webhook.construct_event()`
- PaymentIntents are idempotent via `idempotency_key` — always pass one for retry safety
- Multi-company: each company needs its own Stripe account keys; mixing keys causes payments to go to the wrong Stripe account
- Customer portal templates in `templates/` are served by Frappe's web server — changes require `bench build`
- `setup.py` hardcodes version `"1.0.0"` — update both setup.py and hooks.py when releasing
- Hourly scheduled tasks run even when no payments are due — keep `run_due_payments()` fast with an early exit if nothing to process

## Secrets
Stripe secret key, publishable key, webhook signing secret — to be provided for testing. Store in Stripe Settings DocType (encrypted field), never hardcoded.
