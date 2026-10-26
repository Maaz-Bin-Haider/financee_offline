#!/usr/bin/env python3
"""Purchase cycle: create, accounting (Inventory/AP), stock, invoice fetch,
navigation, summary, validated updates, and the delete guard."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "purchases"


def run(t: Tester):
    g = GROUP
    vend = t.add_party("Vendor")
    item = t.add_item()
    serials = t.serials("PU", 4)

    # --- create -----------------------------------------------------------
    pid, _ = t.purchase(vend, serials, unit_price=100, item_name=item)
    t.check(g, "purchase created", pid is not None)
    for s in serials:
        t.assert_stock(g, s, True)
    t.check(g, "invoice total = qty*price (400)",
            abs(float(t.one("SELECT total_amount FROM purchaseinvoices WHERE purchase_invoice_id=%s", [pid])) - 400) < 0.005)
    t.assert_tb(g, "purchase")
    # Credit purchase -> vendor AP carries the 400 as a credit balance.
    bal = t.party_balance(vend)
    t.check(g, "vendor AP balance = -400 after credit purchase", abs((bal or 0) + 400) < 0.005, f"balance={bal}")
    # Journal posts to Inventory (debit) and Accounts Payable (credit).
    inv_dr = float(t.one(
        "SELECT COALESCE(SUM(jl.debit),0) FROM purchaseinvoices p JOIN journallines jl ON jl.journal_id=p.journal_id "
        "JOIN chartofaccounts c ON c.account_id=jl.account_id WHERE p.purchase_invoice_id=%s AND c.account_name='Inventory'", [pid]))
    t.check(g, "inventory debited 400", abs(inv_dr - 400) < 0.005, f"inv_dr={inv_dr}")

    # --- fetch / navigation ----------------------------------------------
    cur = t.call_json("SELECT get_current_purchase(%s)", [pid])
    t.check(g, "get_current_purchase returns the invoice", isinstance(cur, dict) and cur, f"{type(cur)}")
    t.check(g, "get_last_purchase_id matches", t.one("SELECT get_last_purchase_id() >= %s", [pid]))
    for fn in ("get_last_purchase()", f"get_previous_purchase({pid})", f"get_next_purchase({pid})"):
        t.ok(g, f"navigation {fn.split('(')[0]}", f"SELECT {fn}")

    # --- summary ----------------------------------------------------------
    summ = t.call_json("SELECT get_purchase_summary(%s,%s)", ["2025-07-01", "2025-07-31"])
    t.check(g, "get_purchase_summary runs", summ is not None)

    # --- validated update: price-only, then replace an unsold serial ------
    price_payload = [{"item_name": item, "qty": 4, "unit_price": 125,
                      "serials": [{"serial": s, "comment": ""} for s in serials]}]
    v = t.call_json("SELECT validate_purchase_update2(%s,%s::jsonb)", [pid, json.dumps(price_payload)])
    t.check(g, "validate price-only update -> valid", isinstance(v, dict) and v.get("is_valid") is True, f"{v}")
    t.ok(g, "apply price-only update",
         "SELECT update_purchase_invoice(%s,%s::jsonb,%s,%s,%s)",
         [pid, json.dumps(price_payload), vend, "2025-07-01", t.user_id])
    t.check(g, "invoice total now 500", abs(float(t.one("SELECT total_amount FROM purchaseinvoices WHERE purchase_invoice_id=%s", [pid])) - 500) < 0.005)
    t.assert_tb(g, "purchase price update")

    # replace one unsold serial with a fresh one
    repl = t.serials("PUX", 1)[0]
    repl_payload = [{"item_name": item, "qty": 4, "unit_price": 125,
                     "serials": [{"serial": s, "comment": ""} for s in serials[:3] + [repl]]}]
    t.ok(g, "replace an unsold serial",
         "SELECT update_purchase_invoice(%s,%s::jsonb,%s,%s,%s)",
         [pid, json.dumps(repl_payload), vend, "2025-07-01", t.user_id])
    t.assert_stock(g, repl, True)
    t.check(g, "removed serial no longer exists", t.in_stock(serials[3]) is None)

    # --- delete guard -----------------------------------------------------
    # Sell one serial, then removing it via update and deleting the invoice must be blocked.
    cust = t.add_party("Customer")
    t.sale(cust, [serials[0]], unit_price=200, item_name=item)
    remove_sold = [{"item_name": item, "qty": 3, "unit_price": 125,
                    "serials": [{"serial": s, "comment": ""} for s in [serials[1], serials[2], repl]]}]
    vbad = t.call_json("SELECT validate_purchase_update2(%s,%s::jsonb)", [pid, json.dumps(remove_sold)])
    t.check(g, "removing a sold serial -> invalid", isinstance(vbad, dict) and vbad.get("is_valid") is False, f"{vbad}")
    t.err(g, "delete_purchase blocked when a serial is sold", "SELECT delete_purchase(%s)", [pid], contains="sale history")
    t.check(g, "purchase invoice survives blocked delete",
            t.one("SELECT count(*) FROM purchaseinvoices WHERE purchase_invoice_id=%s", [pid]) == 1)

    # A clean (untouched) purchase can still be deleted.
    clean_serials = t.serials("PUC", 1)
    clean_pid, _ = t.purchase(vend, clean_serials, unit_price=50, item_name=item)
    t.ok(g, "delete_purchase of untouched invoice", "SELECT delete_purchase(%s)", [clean_pid])
    t.check(g, "clean purchase removed", t.one("SELECT count(*) FROM purchaseinvoices WHERE purchase_invoice_id=%s", [clean_pid]) == 0)

    t.assert_tb(g, "end of purchases")
    t.no_empty_journals(g, "end of purchases")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
