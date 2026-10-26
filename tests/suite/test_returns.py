#!/usr/bin/env python3
"""Sale returns and purchase returns: create/update/delete, accounting
reversal, stock restoration, and every lifecycle guard."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "returns"


def run(t: Tester):
    g = GROUP
    vend = t.add_party("Vendor")
    vend2 = t.add_party("Vendor")
    cust = t.add_party("Customer")
    cust2 = t.add_party("Customer")
    item = t.add_item()
    serials = t.serials("RT", 4)
    t.purchase(vend, serials, unit_price=100, item_name=item)

    # ---- SALE RETURN -----------------------------------------------------
    t.sale(cust, serials[:3], unit_price=200, item_name=item)
    bal_after_sale = t.party_balance(cust)
    t.check(g, "customer AR +600 after 3-serial sale", abs((bal_after_sale or 0) - 600) < 0.005, f"{bal_after_sale}")

    # wrong customer cannot return
    t.err(g, "wrong-customer sale return blocked",
          "SELECT create_sale_return(%s,%s::jsonb,%s)", [cust2, json.dumps([serials[0]]), t.user_id],
          contains="not sold to this customer")

    # partial return of 2 of 3
    rid = t.sale_return(cust, serials[:2])
    for s in serials[:2]:
        t.assert_stock(g, s, True)
    t.assert_stock(g, serials[2], False)
    t.assert_tb(g, "partial sale return")
    bal = t.party_balance(cust)
    t.check(g, "customer AR reduced to +200 after returning 2", abs((bal or 0) - 200) < 0.005, f"{bal}")

    # duplicate return blocked
    t.err(g, "duplicate sale return blocked",
          "SELECT create_sale_return(%s,%s::jsonb,%s)", [cust, json.dumps([serials[0]]), t.user_id],
          contains="")

    # update return: drop one serial back to sold
    t.ok(g, "update sale return to a single serial",
         "SELECT update_sale_return(%s,%s::jsonb,%s)", [rid, json.dumps([serials[0]]), t.user_id])
    t.assert_stock(g, serials[0], True)
    t.assert_stock(g, serials[1], False)
    t.assert_tb(g, "sale return update")

    # navigation + summary
    t.ok(g, "get_current_sales_return runs", "SELECT get_current_sales_return(%s)", [rid])
    t.ok(g, "get_sales_return_summary runs", "SELECT get_sales_return_summary(%s,%s)", ["2025-07-01", "2025-07-31"])

    # delete return: serial returns to sold
    t.ok(g, "delete sale return", "SELECT delete_sale_return(%s)", [rid])
    t.assert_stock(g, serials[0], False)
    t.check(g, "sale return header removed", t.one("SELECT count(*) FROM salesreturns WHERE sales_return_id=%s", [rid]) == 0)
    t.assert_tb(g, "sale return delete")

    # ---- PURCHASE RETURN -------------------------------------------------
    # serials[3] is unsold and in stock; serials[0..2] are sold.
    vbal_before = t.party_balance(vend) or 0
    t.err(g, "purchase return wrong vendor blocked",
          "SELECT create_purchase_return(%s,%s::jsonb,%s)", [vend2, json.dumps([serials[3]]), t.user_id],
          contains="")
    t.err(g, "purchase return of a SOLD serial blocked",
          "SELECT create_purchase_return(%s,%s::jsonb,%s)", [vend, json.dumps([serials[2]]), t.user_id],
          contains="stock")

    prid = t.purchase_return(vend, [serials[3]])
    t.check(g, "purchase return created", prid is not None)
    t.assert_stock(g, serials[3], False)
    t.assert_tb(g, "purchase return")
    vbal_after = t.party_balance(vend) or 0
    t.check(g, "vendor AP moves toward zero after purchase return", vbal_after > vbal_before,
            f"before={vbal_before} after={vbal_after}")

    t.err(g, "double purchase return blocked",
          "SELECT create_purchase_return(%s,%s::jsonb,%s)", [vend, json.dumps([serials[3]]), t.user_id],
          contains="stock")

    # navigation + summary + delete
    t.ok(g, "get_current_purchase_return runs", "SELECT get_current_purchase_return(%s)", [prid])
    t.ok(g, "get_purchase_return_summary runs", "SELECT get_purchase_return_summary(%s,%s)", ["2025-07-01", "2025-07-31"])
    t.ok(g, "delete purchase return", "SELECT delete_purchase_return(%s)", [prid])
    t.assert_stock(g, serials[3], True)
    t.assert_tb(g, "purchase return delete")

    t.no_empty_journals(g, "end of returns")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
