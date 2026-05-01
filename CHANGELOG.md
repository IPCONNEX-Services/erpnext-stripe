# Changelog

## v1.1.0 — 2026-05-01
### Added
- **Per-customer payment trigger override** — each Stripe Customer record can now override the company-level trigger with its own policy (Use Company Default / On Invoice Submission / On Due Date / After X Days / Manual Only), including a customer-specific "days after due date" value
- **"Charge via Stripe" button** on the Sales Invoice form — manually charge any submitted, unpaid invoice using the customer's default card
- **"Process Pending Invoices" button** on the Customer form — bulk-enqueues Stripe charges for all outstanding invoices for that customer; supports multi-company selection

### Changed
- Hourly payment scheduler now resolves the effective trigger per customer rather than per company, allowing mixed policies within the same company
- `on_invoice_submit` hook respects the customer-level override when deciding whether to auto-charge on submission

## v1.0.0 — 2026-04-19
### Added
- Multi-company Stripe payment processing
- Customer sync between ERPNext and Stripe
- Card management with PCI-compliant tokenization
- Automatic payment trigger on Sales Invoice submit
- Hourly payment scheduler with retry logic
- Stripe webhook handling (signature-verified)
- Customer self-service portal for card management
- GitHub Actions CI workflow
