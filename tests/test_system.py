#!/usr/bin/env python3
"""
test_system.py  —  Full functional test harness for the Financee multi-tenant ERP.

It drives EVERY business operation (create / update / delete for sale, purchase,
sale-return, purchase-return, payment, receipt, contra; plus parties, items,
opening stock, opening cash, owner equity, month close) and then runs EVERY
report function and view — separately for two tenant schemas — recording the
outcome of each step. Failures are collected and printed at the end.

It talks straight to PostgreSQL (psycopg2) and switches `search_path` per tenant,
exactly like the app's middleware. Each operation runs in autocommit so one
failure never poisons the next.

Run locally against your Docker stack (DB exposed on localhost:5432 by the
override):  see the companion guide for the exact command.
"""
import json
import os
import sys
import traceback

import psycopg2
import time

RUN_TAG = os.environ.get("RUN_TAG") or time.strftime("%H%M%S")

DSN = dict(
    dbname=os.environ.get("DB_NAME", "financee"),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", ""),
    host=os.environ.get("DB_HOST", "localhost"),
    port=os.environ.get("DB_PORT", "5432"),
)

# A week of business dates.
DAYS = [f"2025-06-0{d}" for d in range(1, 8)]            # 2025-06-01 .. 2025-06-07
CUSTOMER = f"ALPHA TRADERS {RUN_TAG}"
VENDOR   = f"BETA SUPPLIES {RUN_TAG}"
BOTH     = f"GAMMA CO {RUN_TAG}"
EXPENSE  = f"OFFICE RENT {RUN_TAG}"
ITEMS = [f"LAPTOP X1 {RUN_TAG}", f"PHONE P10 {RUN_TAG}", f"MONITOR M24 {RUN_TAG}"]


class Runner:
    def __init__(self, conn, schema, uid):
        self.conn = conn
        self.schema = schema
        self.uid = uid
        self.results = []          # (name, ok, error)
        self.ctx = {}              # shared ids/serials between steps

    def cur(self):
        c = self.conn.cursor()
        c.execute(f'SET search_path TO "{self.schema}", public')
        return c

    def step(self, name, sql, params=None, fetch=True):
        """Run one operation; record pass/fail; return the first column or None.

        A function that RETURNS {"status":"error", ...} (instead of raising) is
        a *logical* failure and is recorded as such.
        """
        try:
            c = self.cur()
            c.execute(sql, params or [])
            val = c.fetchone() if fetch else None
            c.close()
            out = val[0] if val else None
            parsed = out
            if isinstance(out, str):
                try:
                    parsed = json.loads(out)
                except Exception:
                    parsed = out
            if isinstance(parsed, dict) and parsed.get("status") == "error":
                self.results.append((name, False, f"LOGIC: {parsed.get('message')}"))
            else:
                self.results.append((name, True, None))
            return out
        except Exception as e:
            self.conn.rollback()
            self.results.append((name, False, f"{type(e).__name__}: {e}".strip()))
            return None

    def serial(self, n):
        return f"{self.schema[-1]}-{RUN_TAG}-SN-{n:05d}"

    # ----------------------------------------------------------------- masters
    def setup_masters(self):
        for ptype, name in [("Customer", CUSTOMER), ("Vendor", VENDOR),
                             ("Both", BOTH), ("Expense", EXPENSE)]:
            self.step(
                f"add_party[{name}]",
                "SELECT add_party_from_json(%s::jsonb)",
                [json.dumps({"party_name": name, "party_type": ptype,
                             "opening_balance": 0, "balance_type": "Debit",
                             "created_by_id": str(self.uid)})],
            )
        for it in ITEMS:
            self.step(
                f"add_item[{it}]",
                "SELECT add_item_from_json(%s::jsonb)",
                [json.dumps({"item_name": it, "sale_price": 1000,
                             "created_by_id": str(self.uid)})],
            )

    # -------------------------------------------------------------- openings
    def setup_openings(self):
        self.step("set_opening_cash",
                  "SELECT set_opening_cash_from_json(%s::jsonb)",
                  [json.dumps({"amount": 100000, "created_by_id": self.uid})])

        # Opening stock for MONITOR (item must already exist).
        serials = [self.serial(900 + i) for i in range(3)]
        self.ctx["opening_serials"] = serials
        oid_raw = self.step(
            "create_opening_stock",
            "SELECT create_opening_stock(%s::jsonb)",
            [json.dumps({"as_of_date": DAYS[0], "vendor_name": VENDOR,
                         "created_by_id": self.uid,
                         "items": [{"item_name": ITEMS[2], "unit_price": 500,
                                    "serials": serials}]})],
        )
        _o = oid_raw if isinstance(oid_raw, dict) else (json.loads(oid_raw) if isinstance(oid_raw, str) else {})
        self.ctx["opening_load"] = (_o or {}).get("opening_stock_id")

        self.step("owner_equity[injection]",
                  "SELECT add_owner_equity_txn(%s::jsonb)",
                  [json.dumps({"direction": "injection", "amount": 50000,
                               "txn_date": DAYS[0], "equity_account": "Owner's Capital",
                               "description": "seed", "created_by_id": self.uid})])
        self.step("owner_equity[withdrawal]",
                  "SELECT add_owner_equity_txn(%s::jsonb)",
                  [json.dumps({"direction": "withdrawal", "amount": 10000,
                               "txn_date": DAYS[1], "equity_account": "Owner's Capital",
                               "description": "drawings", "created_by_id": self.uid})])

    # -------------------------------------------------------------- purchases
    def party_id(self, name):
        c = self.cur()
        c.execute("SELECT party_id FROM parties WHERE party_name=%s", [name])
        r = c.fetchone(); c.close()
        return r[0] if r else None

    def purchases(self):
        vid = self.party_id(VENDOR)
        self.ctx["purchase_invoices"] = []
        self.ctx["serials"] = []
        n = 1
        for day in DAYS:
            sers = [self.serial(n + k) for k in range(2)]
            n += 2
            items = [{"item_name": ITEMS[0], "qty": 2, "unit_price": 800,
                      "serials": [{"serial": s, "comment": ""} for s in sers]}]
            inv = self.step(
                f"create_purchase[{day}]",
                "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
                [vid, day, json.dumps(items), self.uid],
            )
            if inv:
                self.ctx["purchase_invoices"].append(inv)
                self.ctx["serials"].extend(sers)

    # ------------------------------------------------------------------ sales
    def sales(self):
        cid = self.party_id(CUSTOMER)
        self.ctx["sale_invoices"] = []
        self.ctx["sold_serials"] = []
        sers = self.ctx.get("serials", [])
        # sell two serials per day for the first few days
        idx = 0
        for day in DAYS:
            if idx + 1 >= len(sers):
                break
            chunk = [sers[idx], sers[idx + 1]]
            idx += 2
            items = [{"item_name": ITEMS[0], "qty": 2, "unit_price": 1000,
                      "serials": chunk}]
            inv = self.step(
                f"create_sale[{day}]",
                "SELECT create_sale(%s,%s,%s::jsonb,%s)",
                [cid, day, json.dumps(items), self.uid],
            )
            if inv:
                self.ctx["sale_invoices"].append(inv)
                self.ctx["sold_serials"].extend(chunk)

    # --------------------------------------------------------- payments/receipts
    def payments_receipts(self):
        self.ctx["payment_ids"] = []
        self.ctx["receipt_ids"] = []
        for i, day in enumerate(DAYS[:3]):
            r = self.step(
                f"make_payment[{day}]",
                "SELECT make_payment(%s::jsonb)",
                [json.dumps({"party_name": VENDOR, "amount": 1000 + i,
                             "method": "Cash", "payment_date": day,
                             "description": "settle", "created_by_id": self.uid})],
            )
            if r:
                pid = (r if isinstance(r, dict) else json.loads(r)).get("payment_id")
                if pid:
                    self.ctx["payment_ids"].append(pid)
            r = self.step(
                f"make_receipt[{day}]",
                "SELECT make_receipt(%s::jsonb)",
                [json.dumps({"party_name": CUSTOMER, "amount": 2000 + i,
                             "method": "Cash", "receipt_date": day,
                             "description": "collect", "created_by_id": self.uid})],
            )
            if r:
                rid = (r if isinstance(r, dict) else json.loads(r)).get("receipt_id")
                if rid:
                    self.ctx["receipt_ids"].append(rid)

    # ----------------------------------------------------------------- contra
    def contra(self):
        cid = self.step(
            "make_contra",
            "SELECT make_contra(%s::jsonb)",
            [json.dumps({"from_party_name": CUSTOMER, "to_party_name": VENDOR,
                         "amount": 500, "description": "transfer",
                         "contra_date": DAYS[2], "created_by_id": self.uid})],
        )
        # make_contra may return id or json; stash whatever we can use for update/delete
        try:
            c = self.cur()
            c.execute("SELECT contra_id FROM contra_entries ORDER BY contra_id DESC LIMIT 1")
            r = c.fetchone(); c.close()
            self.ctx["contra_id"] = r[0] if r else None
        except Exception:
            self.ctx["contra_id"] = None

    # ---------------------------------------------------------------- returns
    def returns(self):
        sold = self.ctx.get("sold_serials", [])
        purch = self.ctx.get("serials", [])
        # sale return: return one sold serial back from the customer
        if sold:
            self.ctx["sale_return_id"] = self.step(
                "create_sale_return",
                "SELECT create_sale_return(%s,%s::jsonb,%s)",
                [CUSTOMER, json.dumps([sold[0]]), self.uid],
            )
        # purchase return: return an unsold purchased serial to the vendor
        unsold = [s for s in purch if s not in sold]
        if unsold:
            self.ctx["purchase_return_id"] = self.step(
                "create_purchase_return",
                "SELECT create_purchase_return(%s,%s::jsonb,%s)",
                [VENDOR, json.dumps([unsold[-1]]), self.uid],
            )

    # ------------------------------------------------------------ month close
    def month_close(self):
        self.step("month_close[preview]",
                  "SELECT preview_period_close(%s,%s)", [2025, 6])
        self.step("month_close[close]",
                  "SELECT close_period_from_json(%s::jsonb)",
                  [json.dumps({"year": 2025, "month": 6, "created_by_id": self.uid})])
        self.step("month_close[reverse]",
                  "SELECT reverse_period_close(%s,%s)", [2025, 6])

    # ---------------------------------------------------------------- updates
    def updates(self):
        si = self.ctx.get("sale_invoices") or []
        pi = self.ctx.get("purchase_invoices") or []
        if pi:
            # update first purchase: change qty/price on its two serials
            inv = pi[0]
            c = self.cur()
            c.execute("""SELECT pu.serial_number FROM purchaseunits pu
                         JOIN purchaseitems pit ON pu.purchase_item_id=pit.purchase_item_id
                         WHERE pit.purchase_invoice_id=%s""", [inv])
            sers = [r[0] for r in c.fetchall()]; c.close()
            items = [{"item_name": ITEMS[0], "qty": len(sers), "unit_price": 850,
                      "serials": [{"serial": s, "comment": "upd"} for s in sers]}]
            self.step("update_purchase_invoice",
                      "SELECT update_purchase_invoice(%s,%s::jsonb,%s,%s,%s)",
                      [inv, json.dumps(items), VENDOR, DAYS[0], self.uid])
        if si:
            inv = si[-1]
            c = self.cur()
            c.execute("""SELECT pu.serial_number FROM soldunits su
                         JOIN salesitems sit ON su.sales_item_id=sit.sales_item_id
                         JOIN purchaseunits pu ON su.unit_id=pu.unit_id
                         WHERE sit.sales_invoice_id=%s AND su.status='Sold'""", [inv])
            sers = [r[0] for r in c.fetchall()]; c.close()
            if sers:
                items = [{"item_name": ITEMS[0], "qty": len(sers), "unit_price": 1100,
                          "serials": sers}]
                self.step("update_sale_invoice",
                          "SELECT update_sale_invoice(%s,%s::jsonb,%s,%s,%s)",
                          [inv, json.dumps(items), CUSTOMER, DAYS[6], self.uid])
        if self.ctx.get("payment_ids"):
            self.step("update_payment",
                      "SELECT update_payment(%s,%s::jsonb)",
                      [self.ctx["payment_ids"][0],
                       json.dumps({"party_name": VENDOR, "amount": 1234, "method": "Bank",
                                   "payment_date": DAYS[0], "description": "upd",
                                   "created_by_id": self.uid})])
        if self.ctx.get("receipt_ids"):
            self.step("update_receipt",
                      "SELECT update_receipt(%s,%s::jsonb)",
                      [self.ctx["receipt_ids"][0],
                       json.dumps({"party_name": CUSTOMER, "amount": 4321, "method": "Bank",
                                   "receipt_date": DAYS[0], "description": "upd",
                                   "created_by_id": self.uid})])
        if self.ctx.get("contra_id"):
            self.step("update_contra",
                      "SELECT update_contra(%s,%s::jsonb)",
                      [self.ctx["contra_id"],
                       json.dumps({"from_party_name": CUSTOMER, "to_party_name": VENDOR,
                                   "amount": 600, "description": "upd",
                                   "contra_date": DAYS[2], "created_by_id": self.uid})])
        # master updates
        pid = self.party_id(CUSTOMER)
        if pid:
            self.step("update_party_from_json",
                      "SELECT update_party_from_json(%s,%s::jsonb)",
                      [pid, json.dumps({"party_name": CUSTOMER, "party_type": "Customer",
                                        "contact_info": "0300", "address": "Karachi"})])
        self.step("update_item_from_json",
                  "SELECT update_item_from_json(%s::jsonb)",
                  [json.dumps({"item_name": ITEMS[0], "sale_price": 1300,
                               "storage": "WH2"})])

    # ---------------------------------------------------------------- deletes
    def deletes(self):
        if self.ctx.get("sale_return_id"):
            self.step("delete_sale_return",
                      "SELECT delete_sale_return(%s)", [self.ctx["sale_return_id"]])
        if self.ctx.get("purchase_return_id"):
            self.step("delete_purchase_return",
                      "SELECT delete_purchase_return(%s)", [self.ctx["purchase_return_id"]])
        if self.ctx.get("contra_id"):
            self.step("delete_contra", "SELECT delete_contra(%s)", [self.ctx["contra_id"]])
        if self.ctx.get("payment_ids"):
            self.step("delete_payment", "SELECT delete_payment(%s)", [self.ctx["payment_ids"][-1]])
        if self.ctx.get("receipt_ids"):
            self.step("delete_receipt", "SELECT delete_receipt(%s)", [self.ctx["receipt_ids"][-1]])
        # delete a sale that has NOT been returned, then a purchase whose serials are free
        if self.ctx.get("sale_invoices"):
            self.step("delete_sale", "SELECT delete_sale(%s)", [self.ctx["sale_invoices"][-1]])
        if self.ctx.get("purchase_invoices"):
            self.step("delete_purchase", "SELECT delete_purchase(%s)", [self.ctx["purchase_invoices"][-1]])
        if self.ctx.get("opening_load"):
            self.step("delete_opening_stock", "SELECT delete_opening_stock(%s)", [self.ctx["opening_load"]])

    # ---------------------------------------------------------------- reports
    def reports(self):
        f, t = DAYS[0], DAYS[6]
        scalar = [
            ("get_trial_balance_json", "SELECT get_trial_balance_json()", []),
            ("get_party_balances_json", "SELECT get_party_balances_json()", []),
            ("get_accounts_receivable", "SELECT get_accounts_receivable_json_excluding()", []),
            ("get_accounts_payable", "SELECT get_accounts_payable_json_excluding()", []),
            ("get_expense_party_balances", "SELECT get_expense_party_balances_json()", []),
            ("get_items_json", "SELECT get_items_json()", []),
            ("get_parties_json", "SELECT get_parties_json()", []),
            ("get_party_balance_by_name", "SELECT get_party_balance_by_name(%s)", [CUSTOMER]),
            ("get_item_stock_by_name", "SELECT get_item_stock_by_name(%s)", [ITEMS[0]]),
            ("get_sales_summary", "SELECT get_sales_summary(%s,%s)", [f, t]),
            ("get_purchase_summary", "SELECT get_purchase_summary(%s,%s)", [f, t]),
            ("get_sales_return_summary", "SELECT get_sales_return_summary(%s,%s)", [f, t]),
            ("get_purchase_return_summary", "SELECT get_purchase_return_summary(%s,%s)", [f, t]),
            ("monthly_company_position", "SELECT monthly_company_position(%s)", [t]),
            ("monthly_income_statement", "SELECT monthly_income_statement(%s,%s,%s,%s)", [f, t, 10000, 6000]),
            ("get_cash_ledger_with_party", "SELECT get_cash_ledger_with_party(%s,%s)", [f, t]),
            # sales_reports
            ("sales_summary_json", "SELECT sales_summary_json(%s,%s)", [f, t]),
            ("product_profitability_json", "SELECT product_profitability_json(%s,%s)", [f, t]),
            ("customer_profitability_json", "SELECT customer_profitability_json(%s,%s)", [f, t]),
            ("sales_by_product_json", "SELECT sales_by_product_json(%s,%s)", [f, t]),
            ("sales_by_customer_json", "SELECT sales_by_customer_json(%s,%s)", [f, t]),
            ("sale_wise_profit_json", "SELECT sale_wise_profit_json(%s,%s)", [f, t]),
            ("sales_trend_json", "SELECT sales_trend_json(%s,%s,%s)", [f, t, "day"]),
            ("invoice_register_json", "SELECT invoice_register_json(%s,%s)", [f, t]),
            # dashboard
            ("fn_dash_sales_today_kpi", "SELECT fn_dash_sales_today_kpi()", []),
            ("fn_dash_sales_last7days", "SELECT fn_dash_sales_last7days()", []),
            ("fn_dash_sales_range", "SELECT fn_dash_sales_range(%s,%s)", [f, t]),
            ("fn_dash_stock_kpi", "SELECT fn_dash_stock_kpi()", []),
            ("fn_dash_low_stock_items", "SELECT fn_dash_low_stock_items(%s)", [5]),
            ("fn_dash_fast_moving_items", "SELECT fn_dash_fast_moving_items(%s,%s)", [30, 10]),
            ("fn_dash_stale_stock", "SELECT fn_dash_stale_stock(%s)", [30]),
            ("fn_dash_top_customers", "SELECT fn_dash_top_customers(%s,%s,%s)", [5, f, t]),
            ("fn_dash_top_vendors", "SELECT fn_dash_top_vendors(%s,%s,%s)", [5, f, t]),
            ("fn_dash_receivables_aging", "SELECT fn_dash_receivables_aging()", []),
            ("fn_dash_recent_transactions", "SELECT fn_dash_recent_transactions(%s)", [10]),
            ("fn_dash_expense_kpi", "SELECT fn_dash_expense_kpi()", []),
            ("fn_dash_top_expense_categories", "SELECT fn_dash_top_expense_categories(%s,%s,%s)", [5, f, t]),
            ("fn_dash_top_expense_descriptions", "SELECT fn_dash_top_expense_descriptions(%s,%s,%s)", [5, f, t]),
            ("fn_dash_smart_alerts", "SELECT fn_dash_smart_alerts()", []),
            ("stock_summary", "SELECT * FROM stock_summary()", []),
            ("detailed_ledger", "SELECT * FROM detailed_ledger(%s,%s,%s)", [CUSTOMER, f, t]),
            ("detailed_ledger2", "SELECT * FROM detailed_ledger2(%s,%s,%s)", [CUSTOMER, f, t]),
            ("sale_wise_profit", "SELECT * FROM sale_wise_profit(%s,%s)", [f, t]),
            ("item_transaction_history", "SELECT * FROM item_transaction_history(%s::text,%s::date,%s::date)", [ITEMS[0], DAYS[0], DAYS[6]]),
            ("item_transaction_history2", "SELECT * FROM item_transaction_history(%s,%s,%s)", [ITEMS[0], f, t]),
        ]
        for name, sql, params in scalar:
            self.step(f"report:{name}", sql, params)

        # serial ledgers need a real serial
        ser = (self.ctx.get("serials") or [None])[0]
        if ser:
            for fn in ("get_serial_ledger", "get_serial_ledger_purchase",
                       "get_serial_ledger_sales", "get_serial_number_details"):
                self.step(f"report:{fn}", f"SELECT * FROM {fn}(%s)", [ser])

        # plain views
        for v in ["generalledger", "item_last_purchase_view",
                  "item_last_sale_view", "sale_wise_profit_view",
                  "standing_company_worth_view", "stock_report", "stock_worth_report",
                  "vw_dash_daily_sales", "vw_dash_expenses", "vw_dash_party_ar_balance",
                  "vw_dash_stock_overview", "vw_trial_balance"]:
            self.step(f"view:{v}", f"SELECT * FROM {v}", fetch=True)

    def run_all(self):
        self.setup_masters()
        self.setup_openings()
        self.purchases()
        self.sales()
        self.payments_receipts()
        self.contra()
        self.returns()
        self.month_close()
        self.updates()
        self.reports()
        self.deletes()
        return self.results


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    # discover tenant schemas
    c = conn.cursor()
    c.execute(
        """
        SELECT schema_name
          FROM public.tenancy_company
         WHERE is_active = true
           AND schema_name IS NOT NULL
         ORDER BY id
        """
    )
    schemas = [r[0] for r in c.fetchall()]
    c.execute("SELECT id FROM public.auth_user ORDER BY id LIMIT 1")
    row = c.fetchone()
    uid = row[0] if row else 1
    c.close()
    if not schemas:
        print("No tenant schemas found. Provision tenants first.")
        sys.exit(1)

    all_fail = []
    for sch in schemas:
        r = Runner(conn, sch, uid).run_all()
        ok = sum(1 for _, s, _ in r if s)
        fail = [(n, e) for n, s, e in r if not s]
        print(f"\n=== {sch}: {ok}/{len(r)} passed, {len(fail)} failed ===")
        for n, e in fail:
            print(f"  FAIL  {n}\n        {e}")
        all_fail.extend((sch, n, e) for n, e in fail)

    print("\n" + "=" * 70)
    print(f"TOTAL FAILURES: {len(all_fail)}")
    # de-duplicate error signatures across tenants
    seen = {}
    for sch, n, e in all_fail:
        seen.setdefault((n.split('[')[0], e), []).append(sch)
    print(f"DISTINCT FAILURE TYPES: {len(seen)}")
    for (n, e), schs in seen.items():
        print(f"  - {n}  ({len(schs)} tenant(s)): {e}")


if __name__ == "__main__":
    main()
