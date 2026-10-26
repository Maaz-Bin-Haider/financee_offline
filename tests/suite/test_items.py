#!/usr/bin/env python3
"""Item master: create/update, lookups, stock-by-name, and the item-name
autocomplete helper (documented broken)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "items"


def run(t: Tester):
    g = GROUP

    name = t.add_item(sale_price=250, category="CAT-A", brand="BR-A")
    iid = t.item_id(name)
    t.check(g, "item created", iid is not None)
    t.check(g, "item stored fields",
            t.one("SELECT sale_price=250 AND category='CAT-A' AND brand='BR-A' FROM items WHERE item_id=%s", [iid]))

    # update by item_id
    t.ok(g, "update item price/brand",
         "SELECT update_item_from_json(%s::jsonb)",
         [json.dumps({"item_id": str(iid), "sale_price": 400, "brand": "BR-B"})])
    t.check(g, "item price updated to 400", t.one("SELECT sale_price=400 FROM items WHERE item_id=%s", [iid]))

    # lookups
    by_name = t.call_json("SELECT get_item_by_name(%s)", [name])
    row = by_name[0] if isinstance(by_name, list) and by_name else by_name
    t.check(g, "get_item_by_name returns the item", isinstance(row, dict) and row.get("item_name") == name, f"{by_name}")

    items = t.call_json("SELECT get_items_json()")
    t.check(g, "get_items_json returns a list", isinstance(items, list) and len(items) >= 1)

    # stock-by-name reflects a purchase of two serials
    vend = t.add_party("Vendor")
    serials = t.serials("IT", 2)
    t.purchase(vend, serials, unit_price=100, item_name=name)
    stock = t.q("SELECT * FROM get_item_stock_by_name(%s)", [name])
    t.check(g, "get_item_stock_by_name lists purchased serials", stock is not None and len(stock) >= 2,
            f"rows={None if stock is None else len(stock)}")

    # active autocomplete path (as the view runs it) works
    hits = t.q("SELECT item_name FROM Items WHERE UPPER(item_name) LIKE %s LIMIT 10", [name.upper() + "%"])
    t.check(g, "item autocomplete (view query) finds the item", hits is not None and len(hits) >= 1)

    # get_item_names_like helper (ambiguous column fixed by fix_tenant_drift.sql).
    hits2 = t.q("SELECT * FROM get_item_names_like(%s)", [name[:6]])
    t.check(g, "get_item_names_like returns matches", hits2 is not None and len(hits2) >= 1,
            f"rows={None if hits2 is None else len(hits2)}")

    t.no_empty_journals(g, "end of items")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
