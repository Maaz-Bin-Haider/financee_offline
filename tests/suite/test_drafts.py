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

RESULTS = []


def hchk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)[:300]))
    return bool(ok)


def run_http():
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    from django.db import connection
    from django.test import Client, override_settings

    from _harness import DSN, RUN_TAG, Tester
    from tenancy.models import Company, Membership
    import psycopg2

    company = Company.objects.filter(is_active=True).exclude(schema_name="").order_by("id").first()
    if company is None:
        hchk("an active company exists", False, "no active tenant companies")
        return

    User = get_user_model()
    user = User.objects.create_user(f"draft_http_{RUN_TAG.lower()}", password=None)
    Membership.objects.create(user=user, company=company)
    snapshot = list(company.disabled_features or [])
    # The run needs drafts and the screens they touch (Sales, returns, the
    # dashboard card) on, whatever plan the company has; restored in finally.
    Company.objects.filter(pk=company.pk).update(disabled_features=[])
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    t = Tester(conn, company.schema_name, user.id, f"{RUN_TAG}H")

    def grant(*codenames):
        for code in codenames:
            user.user_permissions.add(Permission.objects.get(
                codename=code, content_type__app_label="auth", content_type__model="user"))

    server = next((h.lstrip(".") for h in (settings.ALLOWED_HOSTS or []) if h not in ("*", "")), "localhost")
    client = Client(SERVER_NAME=server)
    client.force_login(user)
    ajax = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

    def post(path, body):
        return client.post(path, data=json.dumps(body), content_type="application/json", **ajax)

    try:
        vendor, customer = t.add_party("Vendor"), t.add_party("Customer")
        item = t.add_item(sale_price=900)
        s = t.serials("DH", 3)
        t.purchase(vendor, s, unit_price=600, item_name=item)

        missing = [c for c, _ in __import__("draft.apps", fromlist=["x"]).DRAFT_PERMISSIONS
                   if not Permission.objects.filter(codename=c).exists()]
        hchk("all eleven draft permissions exist after migrate", not missing, missing)

        r = client.get("/draft/")
        hchk("the draft screen turns away a user without view_draft_invoice",
             r.status_code == 302, r.status_code)
        # Sidebar entries are asserted by their link, not their label: turning
        # a user away flashes "...Draft Invoices!" onto the next page.
        home = client.get("/home/").content.decode()
        hchk("no draft sidebar entry without the permission", 'href="/draft/' not in home)

        grant("view_draft_invoice")
        r = client.get("/draft/")
        hchk("the draft screen renders with view_draft_invoice",
             r.status_code == 200 and b"Draft Invoice" in r.content, r.status_code)
        home = client.get("/home/").content.decode()
        hchk("the sidebar offers Draft Invoices with the permission",
             'href="/draft/"' in home and 'href="/draft/convert/screen/"' not in home)

        body = {"party_name": customer, "draft_date": "2025-07-04", "description": "held for pricing",
                "items": [{"item_name": item, "qty": 2, "unit_price": None, "serials": s[:2]}]}
        r = post("/draft/save/", body)
        hchk("saving needs create_draft_invoice", r.status_code == 403, r.status_code)
        grant("create_draft_invoice")
        r = post("/draft/save/", body)
        data = r.json()
        hchk("a draft saves over HTTP", r.status_code == 200 and data.get("success") is True, data)
        draft_id = data.get("draft_invoice_id")

        got = client.get(f"/draft/get/?nav=current&draft_invoice_id={draft_id}", **ajax).json()
        hchk("the saved draft loads with its customer and description",
             got.get("success") and (got.get("draft") or {}).get("Party") == customer
             and (got.get("draft") or {}).get("description") == "held for pricing", got)

        look = post("/draft/serial/lookup/", {"serial": s[0]}).json()
        hchk("the draft serial lookup names the reservation",
             look.get("success") is False and look.get("reserved") is True
             and look.get("reserved_draft_id") == draft_id, look)
        look = post("/draft/serial/lookup/", {"serial": s[2]}).json()
        hchk("a free serial looks up with its item", look.get("success") and look.get("item_name") == item, look)

        grant("view_sale", "view_purchase_return", "view_sale_return")
        sale_look = client.get(f"/sale/lookup/{s[0]}/", **ajax).json()
        hchk("the Sale screen's lookup refuses a reserved serial and says why",
             sale_look.get("success") is False and sale_look.get("reserved") is True
             and customer in sale_look.get("message", ""), sale_look)
        bulk = post("/sale/bulk-lookup/", {"serials": [s[0], s[2]]}).json()
        hchk("bulk paste on the Sale screen files a reserved serial as invalid",
             [i["serial"] for i in bulk.get("invalid") or []] == [s[0]], bulk)
        pr_look = client.get(f"/purchaseReturn/lookup/{s[0]}/", **ajax).json()
        hchk("the Purchase Return lookup refuses a reserved serial",
             pr_look.get("success") is False and pr_look.get("reserved") is True, pr_look)
        sr_look = client.get(f"/saleReturn/lookup/{s[0]}/", **ajax).json()
        hchk("the Sale Return lookup points a reserved serial at Release Serials",
             sr_look.get("success") is False and "Release Serials" in sr_look.get("message", ""), sr_look)

        tranche = {"draft_invoice_id": draft_id, "invoice_date": "2025-07-06",
                   "items": [{"item_name": item, "qty": 1, "unit_price": 950, "serials": [s[0]]}]}
        r = post("/draft/convert/", tranche)
        hchk("conversion needs confirm_draft_invoice, not create", r.status_code == 403, r.status_code)
        r = client.get("/draft/convert/screen/")
        hchk("the Confirm Draft screen turns away a user without confirm_draft_invoice",
             r.status_code == 302, r.status_code)
        grant("confirm_draft_invoice")
        hchk("the Confirm Draft screen renders with the permission",
             client.get("/draft/convert/screen/").status_code == 200)
        data = post("/draft/convert/", tranche).json()
        hchk("a tranche converts over HTTP and names its invoice",
             data.get("success") and data.get("sales_invoice_id"), data)

        sr_look = client.get(f"/saleReturn/lookup/{s[0]}/", **ajax).json()
        hchk("the Sale Return lookup sends a draft-sold serial to the draft return",
             sr_look.get("success") is False and sr_look.get("from_draft") is True, sr_look)

        grant("view_draft_return", "create_draft_return")
        hchk("the Confirmed Draft Return screen renders", client.get("/draft/return/screen/").status_code == 200)
        look = post("/draft/return/serial/lookup/", {"serial": s[0]}).json()
        hchk("the draft return lookup prices the serial at its converted rate",
             look.get("success") and float(look.get("sold_price") or 0) == 950
             and look.get("draft_invoice_id") == draft_id, look)
        data = post("/draft/return/save/", {"party_name": customer, "return_date": "2025-07-09",
                                            "serials": [s[0]], "description": "returned unopened"}).json()
        hchk("a confirmed draft return saves over HTTP", data.get("success"), data)
        got = client.get(f"/draft/return/get/?nav=current&draft_return_id={data.get('draft_return_id')}",
                         **ajax).json()
        hchk("the draft return keeps its description and date",
             (got.get("draft_return") or {}).get("description") == "returned unopened"
             and (got.get("draft_return") or {}).get("return_date") == "2025-07-09", got)

        grant("view_pending_drafts_report")
        hchk("the Pending Drafts screen renders", client.get("/draft/pending/screen/").status_code == 200)
        rep = post("/draft/pending/", {}).json()
        hchk("the pending report returns rows and a summary",
             isinstance(rep.get("rows"), list) and "unpriced_units" in (rep.get("summary") or {}), rep)

        r = client.get("/home/api/dash/drafts/", **ajax)
        hchk("the dashboard card endpoint needs its permission", r.status_code == 403, r.status_code)
        grant("view_dash_draft_reservations")
        card = client.get("/home/api/dash/drafts/", **ajax).json()
        hchk("the dashboard card endpoint answers in the dashboard envelope",
             card.get("status") == "ok" and "open_drafts" in (card.get("data") or {}), card)
        hchk("the dashboard renders the Stock Reserved on Drafts card",
             "Stock Reserved on Drafts" in client.get("/home/").content.decode())

        with override_settings(DRAFT_SALES_ENABLED=False):
            r = post("/draft/save/", body)
            hchk("the deployment switch makes every draft endpoint a 404", r.status_code == 404, r.status_code)
            hchk("the deployment switch turns the screen away",
                 client.get("/draft/").status_code == 302)
            hchk("the deployment switch hides the sidebar entries and the card",
                 'href="/draft/' not in (home := client.get("/home/").content.decode())
                 and "Stock Reserved on Drafts" not in home)

        Company.objects.filter(pk=company.pk).update(disabled_features=["draft_invoices"])
        r = post("/draft/save/", body)
        hchk("the company flag blocks draft endpoints", r.status_code == 403, r.status_code)
        hchk("the company flag turns the screen away", client.get("/draft/").status_code == 302)
        hchk("the company flag hides the sidebar entries and the card",
             'href="/draft/' not in (home := client.get("/home/").content.decode())
             and "Stock Reserved on Drafts" not in home)
        Company.objects.filter(pk=company.pk).update(disabled_features=[])

        viewers, _ = Group.objects.get_or_create(name="view_only_users")
        user.groups.add(viewers)
        r = client.get(f"/draft/get/?nav=current&draft_invoice_id={draft_id}", **ajax)
        hchk("the read-only group is refused every draft action", r.status_code == 403, r.status_code)
        user.groups.remove(viewers)

        grant("delete_draft_invoice")
        data = post("/draft/cancel/", {"draft_invoice_id": draft_id}).json()
        hchk("the rest of the draft can be cancelled", data.get("success") and data.get("released") == 1, data)
    finally:
        Company.objects.filter(pk=company.pk).update(disabled_features=snapshot)
        conn.close()
        connection.close()
        Membership.objects.filter(user=user).delete()
        user.delete()


def main():
    if not build_has_drafts():
        print("SKIP: this build does not carry the draft invoice feature.")
        return 0

    from _harness import standalone
    sql_rc = standalone(run, GROUP)

    try:
        run_http()
    except Exception as exc:  # a crashing HTTP half is itself a failure
        import traceback
        hchk("HTTP checks crashed", False, f"{type(exc).__name__}: {exc} | {traceback.format_exc()[-400:]}")
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"draft HTTP: {passed}/{len(RESULTS)} checks passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    http_rc = 0 if passed == len(RESULTS) else 1
    return 1 if (sql_rc or http_rc) else 0


if __name__ == "__main__":
    sys.exit(main())
