import unittest
from unittest.mock import MagicMock


def _settings():
    s = MagicMock()
    s.company = "IPCONNEX Services Inc."
    s.payout_bank_account = "BMO - IPX"
    s.payout_fee_account = "Intérêts et frais de banque - IPX"
    s.payout_clearing_account = "Stripe Clearing - IPX"
    return s


class TestBuildSettlementJE(unittest.TestCase):
    def test_simple_cad_payout(self):
        from erpnext_stripe.utils.journal_builder import build_settlement_je
        payout = {"id": "po_simple", "amount": 9700, "arrival_date": 1717891200,
                  "currency": "cad", "status": "paid"}
        txns = [
            {"type": "charge", "amount": 5000, "fee": 150},
            {"type": "charge", "amount": 5000, "fee": 150},
            {"type": "payout", "amount": -9700, "fee": 0},
        ]
        je = build_settlement_je(payout, txns, _settings())
        self.assertEqual(je["doctype"], "Journal Entry")
        self.assertEqual(je["voucher_type"], "Bank Entry")
        self.assertEqual(je["cheque_no"], "po_simple")
        self.assertEqual(je["company"], "IPCONNEX Services Inc.")
        self.assertEqual(len(je["accounts"]), 3)
        self.assertEqual(je["accounts"][0]["account"], "BMO - IPX")
        self.assertAlmostEqual(je["accounts"][0]["debit_in_account_currency"], 97.00)
        self.assertEqual(je["accounts"][1]["account"], "Intérêts et frais de banque - IPX")
        self.assertAlmostEqual(je["accounts"][1]["debit_in_account_currency"], 3.00)
        self.assertEqual(je["accounts"][2]["account"], "Stripe Clearing - IPX")
        self.assertAlmostEqual(je["accounts"][2]["credit_in_account_currency"], 100.00)
        self.assertEqual(je["_meta"]["txn_count"], 2)
        self.assertAlmostEqual(je["_meta"]["gross_amount"], 100.00)
        self.assertAlmostEqual(je["_meta"]["fee_amount"], 3.00)
        self.assertAlmostEqual(je["_meta"]["net_amount"], 97.00)

    def test_payout_with_refund(self):
        from erpnext_stripe.utils.journal_builder import build_settlement_je
        payout = {"id": "po_refund", "amount": 6700, "arrival_date": 1717891200,
                  "currency": "cad", "status": "paid"}
        txns = [
            {"type": "charge", "amount": 10000, "fee": 300},
            {"type": "refund", "amount": -3000, "fee": 0},
        ]
        je = build_settlement_je(payout, txns, _settings())
        self.assertAlmostEqual(je["accounts"][0]["debit_in_account_currency"], 67.00)
        self.assertAlmostEqual(je["accounts"][1]["debit_in_account_currency"], 3.00)
        self.assertAlmostEqual(je["accounts"][2]["credit_in_account_currency"], 70.00)

    def test_usd_payout_raises(self):
        from erpnext_stripe.utils.journal_builder import build_settlement_je
        payout = {"id": "po_usd", "amount": 9700, "arrival_date": 1717891200,
                  "currency": "usd", "status": "paid"}
        with self.assertRaises(ValueError) as cm:
            build_settlement_je(payout, [], _settings())
        self.assertIn("CAD", str(cm.exception))

    def test_unpaid_status_raises(self):
        from erpnext_stripe.utils.journal_builder import build_settlement_je
        payout = {"id": "po_pending", "amount": 9700, "arrival_date": 1717891200,
                  "currency": "cad", "status": "pending"}
        with self.assertRaises(ValueError) as cm:
            build_settlement_je(payout, [], _settings())
        self.assertIn("not paid", str(cm.exception).lower())

    def test_drift_raises(self):
        from erpnext_stripe.utils.journal_builder import build_settlement_je
        payout = {"id": "po_drift", "amount": 9700, "arrival_date": 1717891200,
                  "currency": "cad", "status": "paid"}
        txns = [{"type": "charge", "amount": 10000, "fee": 100}]
        with self.assertRaises(ValueError) as cm:
            build_settlement_je(payout, txns, _settings())
        self.assertIn("drift", str(cm.exception).lower())

    def test_unknown_txn_types_ignored(self):
        from erpnext_stripe.utils.journal_builder import build_settlement_je
        payout = {"id": "po_unknown", "amount": 4850, "arrival_date": 1717891200,
                  "currency": "cad", "status": "paid"}
        txns = [
            {"type": "charge", "amount": 5000, "fee": 150},
            {"type": "transfer", "amount": 100000, "fee": 0},
        ]
        je = build_settlement_je(payout, txns, _settings())
        self.assertAlmostEqual(je["accounts"][2]["credit_in_account_currency"], 50.00)


if __name__ == "__main__":
    unittest.main()
