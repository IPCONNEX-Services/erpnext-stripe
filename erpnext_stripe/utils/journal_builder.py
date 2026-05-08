"""Stripe payout settlement — JE builder.

Pure function: takes a Stripe payout dict + list of balance_transactions + the
Stripe Settings doc, returns a dict ready for `frappe.get_doc(...).insert()`.
No DB writes. No frappe imports.
"""
import datetime


_ALLOWED_TXN_TYPES = ("charge", "refund", "adjustment", "stripe_fee")


def build_settlement_je(payout: dict, txns: list, settings) -> dict:
    if (payout.get("currency") or "").lower() != "cad":
        raise ValueError(f"Only CAD payouts supported in v1; got {payout.get('currency')}")
    if payout.get("status") != "paid":
        raise ValueError(f"Payout {payout.get('id')} status={payout.get('status')}, not paid")

    gross_cents = 0
    fee_cents = 0
    counted = 0
    for t in txns:
        if t.get("type") == "payout":
            continue  # would double-count
        if t.get("type") not in _ALLOWED_TXN_TYPES:
            continue
        gross_cents += int(t.get("amount") or 0)
        fee_cents += int(t.get("fee") or 0)
        counted += 1

    net_cents = gross_cents - fee_cents
    drift_cents = abs(net_cents - int(payout.get("amount") or 0))
    if drift_cents > 2:
        raise ValueError(
            f"Payout {payout.get('id')}: math drift {drift_cents} cents. "
            f"gross={gross_cents}, fees={fee_cents}, net={net_cents}, "
            f"payout.amount={payout.get('amount')}"
        )

    arrival = datetime.date.fromtimestamp(int(payout["arrival_date"]))
    arrival_iso = arrival.isoformat()

    return {
        "doctype": "Journal Entry",
        "company": settings.company,
        "posting_date": arrival_iso,
        "voucher_type": "Bank Entry",
        "cheque_no": payout["id"],
        "cheque_date": arrival_iso,
        "user_remark": f"Stripe payout {payout['id']} — {counted} txns, fees {fee_cents/100:.2f}",
        "accounts": [
            {"account": settings.payout_bank_account,
             "debit_in_account_currency": int(payout["amount"]) / 100.0},
            {"account": settings.payout_fee_account,
             "debit_in_account_currency": fee_cents / 100.0},
            {"account": settings.payout_clearing_account,
             "credit_in_account_currency": gross_cents / 100.0},
        ],
        "_meta": {
            "gross_amount": gross_cents / 100.0,
            "fee_amount": fee_cents / 100.0,
            "net_amount": int(payout["amount"]) / 100.0,
            "txn_count": counted,
        },
    }
