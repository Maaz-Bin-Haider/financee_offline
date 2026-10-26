#!/usr/bin/env python3
"""Sale cycle: credit + cash sales, AR/Revenue/COGS accounting, stock,
invoice fetch/navigation/summary, updates, and post-return mutation guards.

The cash-party feature is required on every tenant (ported everywhere by
tenancy/sql/fix_cash_party_port.sql, tenant schema version 5), so the
cash-sale path is asserted unconditionally."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "sales"


def _cogs_of_sale(t, sale_id):
    return float(t.one(
        "SELECT COALESCE(SUM(jl.debit),0) FROM salesinvoices s "
        "JOIN journallines jl ON jl.journal_id=s.journal_id "
        "JOIN chartofaccounts c ON c.account_id=jl.account_id "
        "WHERE s.sales_invoice_id=%s AND c.account_name='Cost of Goods Sold'", [sale_id]) or 0)


def run(t: Tester):
    g = GROUP
    vend = t.add_party("Vendor")
    cust = t.add_party("Customer")
    item = t.add_item(sale_price=150)
    serials = t.serials("SL", 4)
    t.purchase(vend, serials, unit_price=100, item_name=item)

    # --- credit sale ------------------------------------------------------
    sid = t.sale(cust, serials[:2], unit_price=200, item_name=item)
    t.check(g, "credit sale created", sid is not None)
    for s in serials[:2]:
        t.assert_stock(g, s, False)
    t.check(g, "sale total = 400", abs(float(t.one("SELECT total_amount FROM salesinvoices WHERE sales_invoice_id=%s", [sid])) - 400) < 0.005)
    t.assert_tb(g, "credit sale")
    bal = t.party_balance(cust)
    t.check(g, "customer AR balance +400 after credit sale", abs((bal or 0) - 400) < 0.005, f"balance={bal}")
    t.check(g, "COGS posted at cost 200 (2*100)", abs(_cogs_of_sale(t, sid) - 200) < 0.005, f"cogs={_cogs_of_sale(t, sid)}")

    # duplicate sale of an already-sold serial is blocked
    t.err(g, "re-selling a sold serial is blocked",
          "SELECT create_sale(%s,%s,%s::jsonb,%s)",
          [t.party_id(cust), "2025-07-03", json.dumps([{"item_name": item, "qty": 1, "unit_price": 200, "serials": [serials[0]]}]), t.user_id],
          contains="already sold")

    # qty must equal the serial count (integrity guard)
    t.err(g, "qty != serial count is rejected",
          "SELECT create_sale(%s,%s,%s::jsonb,%s)",
          [t.party_id(cust), "2025-07-03", json.dumps([{"item_name": item, "qty": 5, "unit_price": 200, "serials": [serials[2]]}]), t.user_id],
          contains="does not match")

    # --- fetch / navigation / summary ------------------------------------
    cur = t.call_json("SELECT get_current_sale(%s)", [sid])
    t.check(g, "get_current_sale returns the invoice", isinstance(cur, dict) and cur)
    for fn in ("get_last_sale()", f"get_previous_sale({sid})", f"get_next_sale({sid})"):
        t.ok(g, f"navigation {fn.split('(')[0]}", f"SELECT {fn}")
    t.ok(g, "get_sales_summary runs", "SELECT get_sales_summary(%s,%s)", ["2025-07-01", "2025-07-31"])

    # --- update sale invoice (no returns yet) -----------------------------
    upd = [{"item_name": item, "qty": 2, "unit_price": 250, "serials": serials[:2]}]
    t.ok(g, "update sale invoice price",
         "SELECT update_sale_invoice(%s,%s::jsonb,%s,%s,%s)",
         [sid, json.dumps(upd), cust, "2025-07-02", t.user_id])
    t.check(g, "sale total now 500", abs(float(t.one("SELECT total_amount FROM salesinvoices WHERE sales_invoice_id=%s", [sid])) - 500) < 0.005)
    t.assert_tb(g, "sale update")

    # --- return then mutation guards --------------------------------------
    t.sale_return(cust, [serials[0]])
    t.assert_stock(g, serials[0], True)
    t.err(g, "update sale invoice blocked after a return exists",
          "SELECT update_sale_invoice(%s,%s::jsonb,%s,%s,%s)",
          [sid, json.dumps(upd), cust, "2025-07-02", t.user_id], contains="return history")
    t.err(g, "delete sale blocked after a return exists", "SELECT delete_sale(%s)", [sid], contains="return")

    # --- cash sale (required on every tenant since schema v5) -------------
    t.check(g, "cash-party feature present", t.has_column("parties", "is_cash"),
            "parties.is_cash missing; apply tenancy/sql/fix_cash_party_port.sql")
    cash_name = t.name("P-CASH")
    t.exec("SELECT add_party_from_json(%s::jsonb)",
            [json.dumps({"party_name": cash_name, "party_type": "Customer", "created_by_id": str(t.user_id)})])
    t.exec("UPDATE parties SET is_cash=true WHERE party_name=%s", [cash_name])
    cash_sid = t.sale(cash_name, [serials[2]], unit_price=300, item_name=item)
    t.check(g, "cash sale created", cash_sid is not None)
    t.assert_tb(g, "cash sale")
    # Cash sale debits Cash, not the party AR: party balance stays 0.
    cbal = t.party_balance(cash_name)
    t.check(g, "cash party accrues no AR balance", abs((cbal or 0)) < 0.005, f"balance={cbal}")
    cash_dr = float(t.one(
        "SELECT COALESCE(SUM(jl.debit),0) FROM salesinvoices s JOIN journallines jl ON jl.journal_id=s.journal_id "
        "JOIN chartofaccounts c ON c.account_id=jl.account_id WHERE s.sales_invoice_id=%s AND c.account_name='Cash'", [cash_sid]))
    t.check(g, "cash sale debits Cash 300", abs(cash_dr - 300) < 0.005, f"cash_dr={cash_dr}")
    # Seeded sentinel parties from the port migration.
    t.check(g, "sentinel cash parties seeded",
            int(t.one("SELECT COUNT(*) FROM parties WHERE COALESCE(is_cash,false) "
                      "AND party_name IN ('Cash Sale','Cash Purchase')")) == 2)
    t.ok(g, "get_cash_party_id('sale') resolves", "SELECT get_cash_party_id('sale')")
    t.ok(g, "get_cash_party_id('purchase') resolves", "SELECT get_cash_party_id('purchase')")

    t.assert_tb(g, "end of sales")
    t.no_empty_journals(g, "end of sales")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
