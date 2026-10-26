#!/usr/bin/env python3
"""Opening balances: opening cash (singleton), opening stock loads, and
reclassification of the Opening Balance account into Owner's Capital."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "opening"


def run(t: Tester):
    g = GROUP

    # ---- OPENING CASH (singleton) ---------------------------------------
    before = t.call_json("SELECT get_opening_cash_json()")
    orig_amt = 0
    if isinstance(before, dict):
        try:
            orig_amt = float(before.get("amount") or before.get("opening_cash") or 0)
        except Exception:
            orig_amt = 0

    res = t.call_json("SELECT set_opening_cash_from_json(%s::jsonb)",
                      [json.dumps({"amount": 5000, "created_by_id": str(t.user_id)})])
    t.check(g, "set_opening_cash succeeds", isinstance(res, dict), f"{res}")
    t.assert_tb(g, "opening cash set")
    cash_dr = float(t.one(
        "SELECT COALESCE(SUM(jl.debit),0) FROM journalentries je JOIN journallines jl ON jl.journal_id=je.journal_id "
        "JOIN chartofaccounts c ON c.account_id=jl.account_id "
        "WHERE je.description='Opening Cash in Hand' AND c.account_name='Cash'"))
    t.check(g, "opening cash debits Cash 5000", abs(cash_dr - 5000) < 0.005, f"cash_dr={cash_dr}")
    # negative opening cash rejected
    t.err(g, "negative opening cash rejected",
          "SELECT set_opening_cash_from_json(%s::jsonb)", [json.dumps({"amount": -1})], contains="negative")
    # restore original amount
    t.exec("SELECT set_opening_cash_from_json(%s::jsonb)", [json.dumps({"amount": orig_amt, "created_by_id": str(t.user_id)})])

    # ---- OPENING STOCK ---------------------------------------------------
    item = t.add_item()
    serials = t.serials("OS", 3)
    payload = {"as_of_date": "2025-01-01", "created_by_id": str(t.user_id),
               "items": [{"item_name": item, "unit_price": 90,
                          "serials": [{"serial": s, "comment": "opening"} for s in serials]}]}
    res = t.call_json("SELECT create_opening_stock(%s::jsonb)", [json.dumps(payload)])
    t.check(g, "create_opening_stock succeeds", isinstance(res, dict) and res.get("status") == "success", f"{res}")
    osid = res.get("opening_stock_id") if isinstance(res, dict) else None
    for s in serials:
        t.assert_stock(g, s, True)
    t.assert_tb(g, "opening stock")
    # Debit Inventory / Credit Opening Balance for 3*90 = 270.
    obe_cr = float(t.one(
        "SELECT COALESCE(SUM(jl.credit),0) FROM purchaseinvoices p JOIN journallines jl ON jl.journal_id=p.journal_id "
        "JOIN chartofaccounts c ON c.account_id=jl.account_id "
        "WHERE p.purchase_invoice_id=%s AND c.account_name='Opening Balance'", [osid]))
    t.check(g, "opening stock credits Opening Balance 270", abs(obe_cr - 270) < 0.005, f"obe_cr={obe_cr}")

    # guards: duplicate serial in payload, and serial already in system
    dup = {"items": [{"item_name": item, "unit_price": 10,
                      "serials": [{"serial": "DUPX", "comment": ""}, {"serial": "DUPX", "comment": ""}]}]}
    r = t.call_json("SELECT create_opening_stock(%s::jsonb)", [json.dumps(dup)])
    t.check(g, "duplicate serial in opening stock rejected", isinstance(r, dict) and r.get("status") == "error", f"{r}")
    exists = {"items": [{"item_name": item, "unit_price": 10, "serials": [{"serial": serials[0], "comment": ""}]}]}
    r = t.call_json("SELECT create_opening_stock(%s::jsonb)", [json.dumps(exists)])
    t.check(g, "existing serial in opening stock rejected", isinstance(r, dict) and r.get("status") == "error", f"{r}")

    # list + details + delete
    t.ok(g, "get_opening_stock_loads_json runs", "SELECT get_opening_stock_loads_json()")
    t.ok(g, "get_opening_stock_load_details runs", "SELECT get_opening_stock_load_details(%s)", [osid])
    r = t.call_json("SELECT delete_opening_stock(%s)", [osid])
    t.check(g, "delete_opening_stock succeeds", isinstance(r, dict), f"{r}")
    t.assert_tb(g, "opening stock delete")

    # ---- RECLASSIFY OPENING BALANCE -> CAPITAL --------------------------
    # Create a fresh opening stock so there is an Opening Balance to move.
    s2 = t.serials("OS2", 2)
    t.exec("SELECT create_opening_stock(%s::jsonb)",
           [json.dumps({"as_of_date": "2025-01-01", "created_by_id": str(t.user_id),
                        "items": [{"item_name": item, "unit_price": 50,
                                   "serials": [{"serial": s, "comment": ""} for s in s2]}]})])
    r = t.call_json("SELECT reclassify_opening_balance_to_capital(%s::jsonb)", [json.dumps({})])
    t.check(g, "reclassify runs (success or noop)", isinstance(r, dict) and r.get("status") in ("success", "noop"), f"{r}")
    t.assert_tb(g, "reclassify")
    obe_bal = float(t.one(
        "SELECT COALESCE(SUM(jl.debit)-SUM(jl.credit),0) FROM journallines jl "
        "JOIN chartofaccounts c ON c.account_id=jl.account_id WHERE c.account_name='Opening Balance'"))
    t.check(g, "Opening Balance account is zero after reclassify", abs(obe_bal) < 0.005, f"obe_bal={obe_bal}")

    t.no_empty_journals(g, "end of opening")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
