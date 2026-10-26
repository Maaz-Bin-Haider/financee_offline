#!/usr/bin/env python3
"""Draft sale invoices (proforma): the reservation guard, the lifecycle, the
proof that a draft cannot move the books, conversion into a real credit sale,
the Confirmed Draft Return document, the reports, and the HTTP layer
(permissions, the deployment switch, the per-company flag, and the Sale /
Sale Return / Purchase Return lookups that name a reservation).

SQL checks run on every active tenant through the suite harness; the HTTP
checks run against the first active company as a temporary, non-superuser
member with explicitly granted permissions (superusers bypass has_perm).

Skips cleanly (exit 0) on a build without the draft feature: the Phase 3B
rehearsal runs the current tests/ inside an older image.

Run inside the web container:
    docker compose -f deploy/docker-compose.yml exec -e PYTHONPATH=/app web \
        python tests/suite/test_drafts.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

GROUP = "drafts"


def build_has_drafts():
    """Whether the RUNNING build carries the draft feature (its own template
    and its own Django app), not whether a given tenant happens to."""
    template = ROOT / "tenancy/sql/tenant_template.sql"
    try:
        in_template = "CREATE TABLE IF NOT EXISTS DraftInvoices" in template.read_text(encoding="utf-8")
    except OSError:
        in_template = False
    return in_template and importlib.util.find_spec("draft") is not None


# ── SQL layer, per tenant ─────────────────────────────────────────────────────

BOOKS_SQL = """
SELECT json_build_object(
  'journal_lines', (SELECT json_build_array(count(*), COALESCE(sum(debit),0), COALESCE(sum(credit),0)) FROM journallines),
  'journal_entries', (SELECT count(*) FROM journalentries),
  'sales_invoices', (SELECT count(*) FROM salesinvoices),
  'sold_units', (SELECT json_build_array(count(*), count(*) FILTER (WHERE status='Sold')) FROM soldunits),
  'purchase_units', (SELECT json_build_array(count(*), count(*) FILTER (WHERE in_stock)) FROM purchaseunits),
  'stock_movements', (SELECT count(*) FROM stockmovements),
  'sales_returns', (SELECT count(*) FROM salesreturns),
  'payments', (SELECT count(*) FROM payments),
  'receipts', (SELECT count(*) FROM receipts),
  'parties', (SELECT count(*) FROM parties),
  'trial_balance', get_trial_balance_json()::text
)::text
"""


def books(t):
    return t.one(BOOKS_SQL)


def draft_json(t, draft_id):
    return t.call_json("SELECT get_current_draft(%s)", [draft_id]) or {}


def reservation(t, serial):
    rows = t.q("SELECT is_reserved, reserved_for, reserved_draft_id, in_stock "
               "FROM get_serial_number_details(%s)", [serial])
    return rows[0] if rows else None


def create_draft(t, party, items, date="2025-07-04"):
    return t.exec("SELECT create_draft(%s,%s,%s::jsonb,%s)",
                  [t.party_id(party), date, json.dumps(items), t.user_id])


def run(t):
    g = GROUP
    if not t.has_function("create_draft"):
        t.check(g, "tenant carries the draft invoice schema", False,
                "create_draft() is missing: production_hardening.sql / the template did not apply it")
        return

    vendor = t.add_party("Vendor")
    customer = t.add_party("Customer")
    other = t.add_party("Customer")
    expense = t.add_party("Expense")
    item_a, item_b = t.add_item(sale_price=900), t.add_item(sale_price=700)
    a = t.serials("DA", 6)
    b = t.serials("DB", 2)
    _, item_a = t.purchase(vendor, a, unit_price=600, item_name=item_a)
    p_b, item_b = t.purchase(vendor, b, unit_price=400, item_name=item_b)
    t.ensure_cash_sale_party()

    before = books(t)

    # 1. Create --------------------------------------------------------------
    d1 = create_draft(t, customer, [
        {"item_name": item_a, "qty": 3, "unit_price": None, "serials": a[:3]},
        {"item_name": item_b, "qty": 1, "unit_price": 500, "serials": b[:1]},
    ])
    t.check(g, "create_draft returns a draft number", d1 is not None, d1)
    d = draft_json(t, d1)
    t.check(g, "a new draft is Open with 4 reserved units",
            d.get("status") == "Open" and d.get("reserved_units") == 4, d)
    lines = {line["item_name"]: line for line in (d.get("items") or [])}
    t.check(g, "a blank expected rate is stored as no rate, not 0.00",
            lines.get(item_a, {}).get("unit_price") is None
            and float(lines.get(item_b, {}).get("unit_price") or 0) == 500, lines)
    t.check(g, "reserved_details carries each serial's own cost",
            {r["serial"]: float(r["unit_cost"]) for r in lines.get(item_a, {}).get("reserved_details") or []}
            == {s: 600.0 for s in a[:3]}, lines.get(item_a))
    res = reservation(t, a[0])
    t.check(g, "the serial names the customer and draft it is held for",
            res is not None and res[0] is True and res[1] == customer and res[2] == d1 and res[3] is True, res)

    # 2. The guard: nothing can consume a reserved unit ------------------------
    t.err(g, "a reserved serial cannot be sold",
          "SELECT create_sale(%s,%s,%s::jsonb,%s)",
          [t.party_id(other), "2025-07-05",
           json.dumps([{"item_name": item_a, "qty": 1, "unit_price": 900, "serials": [a[0]]}]), t.user_id],
          contains="is reserved for customer")
    t.err(g, "a reserved serial cannot be returned to the vendor",
          "SELECT create_purchase_return(%s,%s::jsonb,%s)",
          [vendor, json.dumps([b[0]]), t.user_id], contains="is reserved for customer")
    t.err(g, "a purchase holding a reserved serial cannot be deleted",
          "SELECT delete_purchase(%s)", [p_b], contains="is reserved for customer")
    vd = t.call_json("SELECT validate_purchase_delete(%s)", [p_b]) or {}
    t.check(g, "validate_purchase_delete reports the reserved serial first",
            vd.get("is_valid") is False and b[0] in (vd.get("reserved_serials") or []), vd)
    t.err(g, "a sale return of a reserved (never sold) serial says so",
          "SELECT create_sale_return(%s,%s::jsonb,%s)",
          [customer, json.dumps([a[0]]), t.user_id], contains="not sold, so there is nothing to return")
    t.err(g, "a serial cannot be reserved twice",
          "SELECT create_draft(%s,%s,%s::jsonb,%s)",
          [t.party_id(other), "2025-07-04",
           json.dumps([{"item_name": item_a, "qty": 1, "serials": [a[0]]}]), t.user_id],
          contains="already reserved")
    for kind, party, text in (("vendor", vendor, "is not a customer"),
                              ("expense", expense, "is not a customer"),
                              ("cash", "Cash Sale", "reserved cash account")):
        t.err(g, f"a {kind} party cannot hold a draft",
              "SELECT create_draft(%s,%s,%s::jsonb,%s)",
              [t.party_id(party), "2025-07-04",
               json.dumps([{"item_name": item_a, "qty": 1, "serials": [a[5]]}]), t.user_id],
              contains=text)
    t.err(g, "qty must equal the number of serials",
          "SELECT create_draft(%s,%s,%s::jsonb,%s)",
          [t.party_id(other), "2025-07-04",
           json.dumps([{"item_name": item_a, "qty": 2, "serials": [a[5]]}]), t.user_id],
          contains="does not match")
    t.err(g, "a serial must belong to the line's item",
          "SELECT create_draft(%s,%s,%s::jsonb,%s)",
          [t.party_id(other), "2025-07-04",
           json.dumps([{"item_name": item_a, "qty": 1, "serials": [b[1]]}]), t.user_id],
          contains="does not belong")

    # 3. Edit, release, cancel ---------------------------------------------------
    t.ok(g, "an open draft can be rewritten",
         "SELECT update_draft(%s,%s::jsonb,NULL,NULL,%s)",
         [d1, json.dumps([
             {"item_name": item_a, "qty": 4, "unit_price": 850, "serials": a[:4]},
             {"item_name": item_b, "qty": 1, "unit_price": 500, "serials": b[:1]},
         ]), t.user_id])
    t.check(g, "the rewrite reserves the new line", draft_json(t, d1).get("reserved_units") == 5)

    released = t.exec("SELECT release_draft_units(%s,%s::jsonb,%s)", [d1, json.dumps([a[3]]), t.user_id])
    t.check(g, "release_draft_units reports what it released", released == 1, released)
    res = reservation(t, a[3])
    t.check(g, "a released serial is back in free stock", res is not None and res[0] is False and res[3] is True, res)

    d2 = create_draft(t, other, [{"item_name": item_a, "qty": 1, "serials": [a[3]]}])
    cancelled = t.exec("SELECT cancel_draft(%s,%s)", [d2, t.user_id])
    t.check(g, "cancel_draft releases everything and closes the draft",
            cancelled == 1 and draft_json(t, d2).get("status") == "Cancelled", draft_json(t, d2))
    released_row = [line for line in draft_json(t, d2).get("items") or []]
    t.check(g, "released serials are kept as history, never deleted",
            released_row and (released_row[0].get("released_serials") or []) == [a[3]], released_row)

    t.check(g, "no draft operation moved the books (journal, stock, invoices, balances)",
            books(t) == before, "books changed during draft operations")

    # 4. Conversion ----------------------------------------------------------------
    t.err(g, "conversion requires a final rate",
          "SELECT convert_draft_tranche(%s,%s::jsonb,%s,%s)",
          [d1, json.dumps([{"item_name": item_a, "qty": 1, "unit_price": "", "serials": [a[0]]}]),
           "2025-07-06", t.user_id], contains="final rate is required")
    t.err(g, "conversion refuses a serial that is not on the draft",
          "SELECT convert_draft_tranche(%s,%s::jsonb,%s,%s)",
          [d1, json.dumps([{"item_name": item_a, "qty": 1, "unit_price": 800, "serials": [a[5]]}]),
           "2025-07-06", t.user_id], contains="not on any draft")
    t.err(g, "conversion refuses a serial filed under another item",
          "SELECT convert_draft_tranche(%s,%s::jsonb,%s,%s)",
          [d1, json.dumps([{"item_name": item_b, "qty": 1, "unit_price": 800, "serials": [a[0]]}]),
           "2025-07-06", t.user_id], contains="under item")
    t.err(g, "conversion refuses a released serial",
          "SELECT convert_draft_tranche(%s,%s::jsonb,%s,%s)",
          [d1, json.dumps([{"item_name": item_a, "qty": 1, "unit_price": 800, "serials": [a[3]]}]),
           "2025-07-06", t.user_id], contains="belongs to draft invoice")

    bal_before = t.party_balance(customer) or 0.0
    inv = t.ok(g, "a tranche converts into a sale invoice",
               "SELECT convert_draft_tranche(%s,%s::jsonb,%s,%s)",
               [d1, json.dumps([{"item_name": item_a, "qty": 2, "unit_price": 800, "serials": a[:2]}]),
                "2025-07-06", t.user_id])
    if inv is None:
        return
    t.check(g, "the invoice is stamped with its draft",
            t.one("SELECT draft_invoice_id FROM salesinvoices WHERE sales_invoice_id=%s", [inv]) == d1)
    t.check(g, "converted serials left stock",
            t.in_stock(a[0]) is False and t.in_stock(a[1]) is False and t.active_sold(a[0]) == 1)
    t.check(g, "the customer's balance moved by the tranche (credit sale)",
            abs((t.party_balance(customer) or 0.0) - bal_before - 1600) < 0.005,
            (bal_before, t.party_balance(customer)))
    t.assert_tb(g, "conversion")
    d = draft_json(t, d1)
    t.check(g, "a part-converted draft reads Partially Converted and keeps the rest reserved",
            d.get("status_label") == "Partially Converted" and d.get("reserved_units") == 2
            and inv in (d.get("invoices") or []), d)
    t.err(g, "a draft with an invoiced tranche can no longer be edited",
          "SELECT update_draft(%s,%s::jsonb,NULL,NULL,%s)",
          [d1, json.dumps([{"item_name": item_a, "qty": 1, "serials": [a[2]]}]), t.user_id],
          contains="can no longer be edited")
    t.err(g, "a draft with an invoiced tranche can no longer be deleted",
          "SELECT delete_draft(%s)", [d1], contains="cannot be deleted")

    # 5. The Confirmed Draft Return -------------------------------------------------
    t.err(g, "the ordinary Sale Return refuses a draft-sold serial",
          "SELECT create_sale_return(%s,%s::jsonb,%s)",
          [customer, json.dumps([a[0]]), t.user_id], contains="Confirmed Draft Return")
    plain = t.serials("DP", 1)
    t.purchase(vendor, plain, unit_price=600, item_name=item_a)
    t.sale(customer, plain, unit_price=900, item_name=item_a, date="2025-07-06")
    t.err(g, "the draft return refuses an ordinary-sold serial",
          "SELECT create_draft_return(%s,%s::jsonb,%s,%s)",
          [customer, json.dumps(plain), "2025-07-07", t.user_id], contains="ordinary sale invoice")
    t.err(g, "a draft return cannot be dated before the sale",
          "SELECT create_draft_return(%s,%s::jsonb,%s,%s)",
          [customer, json.dumps([a[0]]), "2025-07-01", t.user_id], contains="before serial")
    t.err(g, "a draft return cannot be dated in the future",
          "SELECT create_draft_return(%s,%s::jsonb,CURRENT_DATE + 1,%s)",
          [customer, json.dumps([a[0]]), t.user_id], contains="future")

    dr = t.ok(g, "a draft-sold serial comes back on a Confirmed Draft Return",
              "SELECT create_draft_return(%s,%s::jsonb,%s,%s)",
              [customer, json.dumps([a[0]]), "2025-07-10", t.user_id])
    if dr is not None:
        sr_id = t.one("SELECT sales_return_id FROM draftreturns WHERE draft_return_id=%s", [dr])
        t.check(g, "the return is booked on the date picked, journal included",
                str(t.one("SELECT return_date FROM salesreturns WHERE sales_return_id=%s", [sr_id])) == "2025-07-10"
                and str(t.one("SELECT je.entry_date FROM salesreturns sr JOIN journalentries je "
                              "ON je.journal_id=sr.journal_id WHERE sr.sales_return_id=%s", [sr_id])) == "2025-07-10")
        t.check(g, "the returned unit goes to free stock, not back to the reservation",
                t.in_stock(a[0]) is True and reservation(t, a[0])[0] is False)
        t.check(g, "the ordinary sale-return history leaves the draft return out",
                sr_id not in [r["sales_return_id"] for r in
                              (t.call_json("SELECT get_sales_return_summary(%s,%s)",
                                           ["2025-07-01", "2025-07-31"]) or [])])
        t.err(g, "the ordinary delete refuses a draft return's underlying row",
              "SELECT delete_sale_return(%s)", [sr_id], contains="Confirmed Draft Return")
        t.ok(g, "a draft return can be edited, re-dated and re-priced",
             "SELECT update_draft_return(%s,%s::jsonb,%s,%s)",
             [dr, json.dumps([a[0], a[1]]), "2025-07-12", t.user_id])
        t.check(g, "the edit re-dates the journal too",
                str(t.one("SELECT je.entry_date FROM salesreturns sr JOIN journalentries je "
                          "ON je.journal_id=sr.journal_id WHERE sr.sales_return_id=%s", [sr_id])) == "2025-07-12"
                and float(t.one("SELECT total_amount FROM salesreturns WHERE sales_return_id=%s", [sr_id])) == 1600)
        t.err(g, "a draft-return edit refuses an ordinary-sold serial",
              "SELECT update_draft_return(%s,%s::jsonb,NULL,%s)",
              [dr, json.dumps([a[0]] + plain), t.user_id], contains="ordinary sale invoice")
        cur = t.call_json("SELECT get_current_draft_return(%s)", [dr]) or {}
        t.check(g, "get_current_draft_return carries its draft, date and lines",
                cur.get("draft_invoice_id") == d1 and cur.get("return_date") == "2025-07-12"
                and len(cur.get("items") or []) == 2, cur)
        t.assert_tb(g, "draft return")
        t.ok(g, "a draft return can be deleted", "SELECT delete_draft_return(%s)", [dr])
        t.check(g, "deleting it restores the sale",
                t.active_sold(a[0]) == 1 and t.in_stock(a[0]) is False
                and t.one("SELECT count(*) FROM salesreturns WHERE sales_return_id=%s", [sr_id]) == 0)

    # 6. Converting the rest closes the draft ---------------------------------------
    t.ok(g, "the remaining reserved units convert",
         "SELECT convert_draft_tranche(%s,%s::jsonb,%s,%s)",
         [d1, json.dumps([{"item_name": item_a, "qty": 1, "unit_price": 820, "serials": [a[2]]},
                          {"item_name": item_b, "qty": 1, "unit_price": 510, "serials": [b[0]]}]),
          "2025-07-08", t.user_id])
    t.check(g, "a fully invoiced draft reads Converted", draft_json(t, d1).get("status") == "Converted")
    t.assert_tb(g, "second tranche")

    # 7. Reports ---------------------------------------------------------------------
    d3 = create_draft(t, other, [{"item_name": item_a, "qty": 1, "unit_price": None, "serials": [a[4]]}],
                      date="2025-01-01")
    report = t.call_json("SELECT draft_pending_report(NULL,NULL,%s)", [30]) or {}
    row = next((r for r in report.get("rows") or [] if r.get("draft_invoice_id") == d3), None)
    t.check(g, "the pending report lists the open draft, unpriced and ageing",
            row is not None and row.get("unpriced_units") == 1 and row.get("is_aged") is True
            and (report.get("summary") or {}).get("unpriced_units", 0) >= 1, row)
    dash = t.call_json("SELECT fn_dash_draft_reservations(%s,%s)", [5, 30]) or {}
    t.check(g, "the dashboard card counts open drafts and ageing ones",
            dash.get("open_drafts", 0) >= 1 and dash.get("aged_drafts", 0) >= 1, dash)
    stock = t.q("SELECT reserved_for, reserved_on_draft FROM stock_report WHERE serial_number=%s", [a[4]])
    t.check(g, "Serial Wise Stock shows who a unit is held for",
            stock and stock[0][0] == other and int(stock[0][1]) == d3, stock)
    summary = t.q("SELECT quantity_in_stock, reserved_on_drafts FROM stock_summary() WHERE item_name=%s", [item_a])
    t.check(g, "the Stock Report counts reserved units without removing them from stock",
            summary and summary[0][1] == 1 and summary[0][0] >= 1, summary)
    ledger = t.q("SELECT particulars, qty_in, qty_out FROM get_serial_ledger(%s)", [a[2]])
    events = [r[0] for r in ledger or []]
    t.check(g, "the serial ledger shows the reservation and its conversion",
            "Reserved on Draft" in events and "Converted from Draft" in events
            and all(r[1] == 0 and r[2] == 0 for r in ledger if "Draft" in r[0]), ledger)
    t.check(g, "the sale-side serial ledger shows them too",
            "Reserved on Draft" in [r[0] for r in t.q(
                "SELECT particulars FROM get_serial_ledger_sales(%s)", [a[2]]) or []])

    # 8. A unit that was only ever released can still be deleted with its purchase ----
    x = t.serials("DX", 1)
    p_x, _ = t.purchase(vendor, x, unit_price=600, item_name=item_a)
    d4 = create_draft(t, other, [{"item_name": item_a, "qty": 1, "serials": x}])
    t.exec("SELECT release_draft_units(%s,%s::jsonb,%s)", [d4, json.dumps(x), t.user_id])
    t.ok(g, "a purchase whose serial was only released from a draft can be deleted",
         "SELECT delete_purchase(%s)", [p_x])

    # 9. A reservation and a sale of the same serial serialise on one row lock --------
    y = t.serials("DY", 1)
    t.purchase(vendor, y, unit_price=600, item_name=item_a)
    import psycopg2
    from _harness import DSN
    other_conn = psycopg2.connect(**DSN)
    other_conn.autocommit = True
    # Resolve everything BEFORE the transaction opens: any harness query on
    # t.conn (party_id and friends) rolls back an open transaction first.
    other_id, customer_id = t.party_id(other), t.party_id(customer)
    sale_items = json.dumps([{"item_name": item_a, "qty": 1, "unit_price": 900, "serials": y}])
    holder = t.cur()
    try:
        holder.execute("BEGIN")
        holder.execute("SELECT create_draft(%s,%s,%s::jsonb,%s)",
                       [other_id, "2025-07-04",
                        json.dumps([{"item_name": item_a, "qty": 1, "serials": y}]), t.user_id])
        seller = other_conn.cursor()
        seller.execute(f'SET search_path TO "{t.schema}", public')
        seller.execute("SET lock_timeout = '700ms'")
        outcome = "sold"
        try:
            seller.execute("SELECT create_sale(%s,%s,%s::jsonb,%s)",
                           [customer_id, "2025-07-05", sale_items, t.user_id])
        except psycopg2.Error as exc:
            outcome = str(exc).splitlines()[0]
        t.check(g, "a sale waits on the reservation's row lock", "lock" in outcome.lower(), outcome)
        holder.execute("COMMIT")
        outcome = "sold"
        try:
            seller.execute("SELECT create_sale(%s,%s,%s::jsonb,%s)",
                           [customer_id, "2025-07-05", sale_items, t.user_id])
        except psycopg2.Error as exc:
            outcome = str(exc).splitlines()[0]
        t.check(g, "once the reservation commits, the sale is refused", "reserved" in outcome.lower(), outcome)
    finally:
        try:
            holder.execute("ROLLBACK")
        except Exception:
            pass
        other_conn.close()

    # Leave nothing reserved behind for the other modules.
    for draft_id in t.q("SELECT draft_invoice_id FROM draftinvoices di JOIN parties p "
                        "ON p.party_id=di.customer_id WHERE di.status='Open' AND p.party_name IN (%s,%s)",
                        [customer, other]) or []:
        t.exec("SELECT cancel_draft(%s,%s)", [draft_id[0], t.user_id])
    t.check(g, "cleanup leaves no live reservation for this run's parties",
            t.one("SELECT count(*) FROM draftunits du JOIN draftitems di ON di.draft_item_id=du.draft_item_id "
                  "JOIN draftinvoices d ON d.draft_invoice_id=di.draft_invoice_id JOIN parties p "
                  "ON p.party_id=d.customer_id WHERE du.status='Reserved' AND p.party_name IN (%s,%s)",
                  [customer, other]) == 0)
    t.no_empty_journals(g, "draft invoices")


# ── HTTP layer, first active company ─────────────────────────────────────────

if __name__ == '__main__':
    from _harness import standalone
    sys.exit(standalone(run, GROUP))
