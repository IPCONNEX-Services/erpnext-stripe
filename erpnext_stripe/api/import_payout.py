"""Per-payout import — fetch from Stripe, build JE, persist."""
import frappe


@frappe.whitelist()
def import_payout(payout_id: str, triggered_by: str = "manual", stripe_settings: str | None = None) -> str | None:
    """Fetch + build + insert JE for one Stripe payout. Returns the JE name on success."""
    if not stripe_settings:
        from erpnext_stripe.utils.stripe_client import get_default_stripe_settings
        stripe_settings = get_default_stripe_settings("IPCONNEX Services Inc.", "Production")
    settings = frappe.get_doc("Stripe Settings", stripe_settings)

    # Idempotency
    existing = frappe.db.get_value(
        "Stripe Payout Log",
        {"payout_id": payout_id, "status": "completed"},
        ["name", "journal_entry"],
        as_dict=True,
    )
    if existing:
        log = frappe.get_doc({
            "doctype": "Stripe Payout Log",
            "payout_id": payout_id,
            "status": "skipped_duplicate",
            "triggered_by": triggered_by,
            "journal_entry": existing["journal_entry"],
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return existing["journal_entry"]

    log = frappe.get_doc({
        "doctype": "Stripe Payout Log",
        "payout_id": payout_id,
        "status": "running",
        "triggered_by": triggered_by,
    })
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    sp = frappe.db.savepoint("stripe_build_je")
    try:
        from erpnext_stripe.utils.stripe_client import get_stripe_client
        stripe_lib = get_stripe_client(settings.name)

        payout = stripe_lib.Payout.retrieve(payout_id)
        # Paginate balance_transactions
        txns = []
        starting_after = None
        while True:
            params = {"payout": payout_id, "limit": 100}
            if starting_after:
                params["starting_after"] = starting_after
            page = stripe_lib.BalanceTransaction.list(**params)
            txns.extend(page.data)
            if not page.has_more:
                break
            if len(txns) >= 1000:
                raise ValueError(f"Payout {payout_id} has > 1000 txns; refusing to paginate further")
            starting_after = page.data[-1].id

        # Convert Stripe objects to plain dicts for the pure builder
        payout_dict = {
            "id": payout.id, "amount": payout.amount, "arrival_date": payout.arrival_date,
            "currency": payout.currency, "status": payout.status,
        }
        txn_dicts = [{"type": t.type, "amount": t.amount, "fee": t.fee} for t in txns]

        from erpnext_stripe.utils.journal_builder import build_settlement_je
        je_dict = build_settlement_je(payout_dict, txn_dicts, settings)
        meta = je_dict.pop("_meta")
        je_dict["currency"] = (payout.currency or "cad").upper()

        je = frappe.get_doc(je_dict)
        je.insert(ignore_permissions=True)
        if settings.default_je_status == "Submitted":
            je.submit()

        log.reload()
        log.status = "completed"
        log.arrival_date = je_dict["posting_date"]
        log.currency = payout.currency
        log.journal_entry = je.name
        log.gross_amount = meta["gross_amount"]
        log.fee_amount = meta["fee_amount"]
        log.net_amount = meta["net_amount"]
        log.txn_count = meta["txn_count"]
        log.save(ignore_permissions=True)
        frappe.db.commit()
        return je.name

    except Exception:
        frappe.db.rollback(save_point="stripe_build_je")
        log.reload()
        log.status = "failed"
        log.error_log = frappe.get_traceback()
        log.save(ignore_permissions=True)
        frappe.db.commit()
        return None
