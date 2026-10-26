#!/usr/bin/env python3
"""Cash movement: payments (to vendors), receipts (from customers), and
contra (party-to-party), with accounting, balances, navigation and history."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "cash_movement"


def run(t: Tester):
    g = GROUP
    vend = t.add_party("Vendor", opening_balance=1000, balance_type="Credit")   # AP balance -1000
    cust = t.add_party("Customer", opening_balance=1000, balance_type="Debit")  # AR balance +1000
    t.assert_tb(g, "opening balances")

    # ---- PAYMENT (to vendor) --------------------------------------------
    v0 = t.party_balance(vend)
    res = t.payment(vend, 300, ref=t.name("PMT"))
    t.check(g, "make_payment succeeds", isinstance(res, dict) and res.get("status") == "success", f"{res}")
    t.assert_tb(g, "payment")
    v1 = t.party_balance(vend)
    # Payment debits vendor AP -> balance rises by 300 (toward zero).
    t.check(g, "payment raises vendor balance by 300", abs((v1 or 0) - (v0 or 0) - 300) < 0.005, f"{v0}->{v1}")
    pid = t.one("SELECT payment_id FROM payments ORDER BY payment_id DESC LIMIT 1")
    t.ok(g, "get_payment_details runs", "SELECT get_payment_details(%s)", [pid])
    t.ok(g, "payments navigation (previous)", "SELECT get_previous_payment(%s)", [pid])
    t.ok(g, "get_last_20_payments_json runs", "SELECT get_last_20_payments_json(%s::jsonb)", [json.dumps({})])

    # update payment amount -> journal rebuilt, balance reflects new amount
    t.ok(g, "update_payment amount to 500",
         "SELECT update_payment(%s,%s::jsonb)", [pid, json.dumps({"amount": 500, "method": "Cash", "payment_date": "2025-07-03"})])
    t.assert_tb(g, "payment update")
    v2 = t.party_balance(vend)
    t.check(g, "updated payment reflects 500 total", abs((v2 or 0) - (v0 or 0) - 500) < 0.005, f"{v0}->{v2}")

    # delete payment -> reverses
    t.ok(g, "delete_payment", "SELECT delete_payment(%s)", [pid])
    t.assert_tb(g, "payment delete")
    t.check(g, "vendor balance restored after payment delete", abs((t.party_balance(vend) or 0) - (v0 or 0)) < 0.005)

    # invalid payment amount rejected
    t.err(g, "payment amount <= 0 rejected",
          "SELECT make_payment(%s::jsonb)", [json.dumps({"party_name": vend, "amount": 0, "created_by_id": str(t.user_id)})],
          contains="amount")

    # ---- RECEIPT (from customer) ----------------------------------------
    c0 = t.party_balance(cust)
    res = t.receipt(cust, 400, ref=t.name("RCT"))
    t.check(g, "make_receipt succeeds", isinstance(res, dict) and res.get("status") == "success", f"{res}")
    t.assert_tb(g, "receipt")
    c1 = t.party_balance(cust)
    # Receipt credits customer AR -> balance falls by 400.
    t.check(g, "receipt lowers customer balance by 400", abs((c0 or 0) - (c1 or 0) - 400) < 0.005, f"{c0}->{c1}")
    rid = t.one("SELECT receipt_id FROM receipts ORDER BY receipt_id DESC LIMIT 1")
    t.ok(g, "get_receipt_details runs", "SELECT get_receipt_details(%s)", [rid])
    t.ok(g, "get_last_20_receipts_json runs", "SELECT get_last_20_receipts_json(%s::jsonb)", [json.dumps({})])
    t.ok(g, "delete_receipt", "SELECT delete_receipt(%s)", [rid])
    t.check(g, "customer balance restored after receipt delete", abs((t.party_balance(cust) or 0) - (c0 or 0)) < 0.005)

    # ---- CONTRA (party-to-party) ----------------------------------------
    a = t.add_party("Both")
    b = t.add_party("Both")
    res = t.contra(a, b, 250, ref=t.name("CON"))
    t.check(g, "make_contra succeeds", isinstance(res, dict) and res.get("status") == "success", f"{res}")
    t.assert_tb(g, "contra")
    cid = t.one("SELECT contra_id FROM contra_entries ORDER BY contra_id DESC LIMIT 1")
    t.ok(g, "get_contra_details runs", "SELECT get_contra_details(%s)", [cid])
    t.ok(g, "get_last_20_contras_json runs", "SELECT get_last_20_contras_json(%s::jsonb)", [json.dumps({})])
    # same-party contra is rejected
    t.err(g, "contra with same from/to rejected",
          "SELECT make_contra(%s::jsonb)",
          [json.dumps({"from_party_name": a, "to_party_name": a, "amount": 10, "created_by_id": str(t.user_id)})],
          contains="same")
    t.ok(g, "update_contra amount", "SELECT update_contra(%s,%s::jsonb)", [cid, json.dumps({"amount": 275})])
    t.assert_tb(g, "contra update")
    t.ok(g, "delete_contra", "SELECT delete_contra(%s)", [cid])
    t.assert_tb(g, "contra delete")

    t.no_empty_journals(g, "end of cash movement")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
