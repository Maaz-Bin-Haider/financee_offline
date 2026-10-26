#!/usr/bin/env python3
"""
Regression test for the fixed Financee copy.

Purpose
-------
This script checks that the hardened copy still behaves like the original
business system for normal tenant users:

* tenant schema can be activated
* master data can be created
* purchase creates stock serials
* sale consumes purchased stock
* payments and receipts post successfully
* sale return and purchase return work
* common reports/functions still execute
* hardening blocks duplicate serial abuse instead of changing business results

Run inside the Docker web container:

    docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec web \
      python tests/test_fixed_behavior_regression.py

Optional:

    RUN_TAG=manual1 python tests/test_fixed_behavior_regression.py

The script creates uniquely named test parties/items/serials. It does not delete
the full transaction trail because this is an accounting system and reports must
be tested against real posted entries.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from decimal import Decimal

import psycopg2


RUN_TAG = os.environ.get("RUN_TAG") or time.strftime("%Y%m%d%H%M%S")

DSN = {
    "dbname": os.environ.get("DB_NAME", "financee"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
}


@dataclass
class Result:
    section: str
    name: str
    ok: bool
    detail: str = ""


class RegressionRunner:
    def __init__(self, conn, schema: str, user_id: int):
        self.conn = conn
        self.schema = schema
        self.user_id = user_id
        self.results: list[Result] = []
        self.ctx: dict[str, object] = {}
        suffix = f"{schema}_{RUN_TAG}".upper()
        self.customer = f"REG CUST {suffix}"
        self.vendor = f"REG VEND {suffix}"
        self.expense = f"REG EXPENSE {suffix}"
        self.item_a = f"REG ITEM A {suffix}"
        self.item_b = f"REG ITEM B {suffix}"
        self.serials = [f"{suffix}-SN-{i:04d}" for i in range(1, 7)]
        self.days = ["2025-06-01", "2025-06-02", "2025-06-03", "2025-06-04"]

    def cursor(self):
        cur = self.conn.cursor()
        cur.execute(f'SET search_path TO "{self.schema}", public')
        return cur

    def step(self, section, name, sql, params=None, expect_error=False, parser=None):
        cur = None
        try:
            cur = self.cursor()
            cur.execute(sql, params or [])
            row = cur.fetchone()
            value = row[0] if row else None
            if parser:
                parser(value)
            if expect_error:
                self.results.append(Result(section, name, False, "Expected an error, but query succeeded."))
            else:
                self.results.append(Result(section, name, True))
            return value
        except Exception as exc:
            self.conn.rollback()
            if expect_error:
                self.results.append(Result(section, name, True, f"Blocked as expected: {exc}"))
            else:
                self.results.append(Result(section, name, False, f"{type(exc).__name__}: {exc}"))
            return None
        finally:
            if cur is not None:
                cur.close()

    def assert_true(self, section, name, condition, detail=""):
        self.results.append(Result(section, name, bool(condition), "" if condition else detail))

    def fetch_one(self, sql, params=None):
        cur = self.cursor()
        try:
            cur.execute(sql, params or [])
            return cur.fetchone()
        finally:
            cur.close()

    def parse_success_json(self, value):
        if value is None:
            raise AssertionError("No JSON returned.")
        data = json.loads(value) if isinstance(value, str) else value
        if isinstance(data, dict) and data.get("status") == "error":
            raise AssertionError(data.get("message") or data)
        return data

    def accept_legacy_success(self, value):
        """
        Some original stored functions return plain text or scalar values instead
        of JSON. That is valid legacy behavior; this parser only rejects explicit
        JSON error objects.
        """
        if value is None:
            return value
        if isinstance(value, str):
            try:
                data = json.loads(value)
            except json.JSONDecodeError:
                return value
        else:
            data = value
        if isinstance(data, dict) and data.get("status") == "error":
            raise AssertionError(data.get("message") or data)
        return data

    def add_master_data(self):
        section = "01 master data"
        for party_type, name in (
            ("Customer", self.customer),
            ("Vendor", self.vendor),
            ("Expense", self.expense),
        ):
            payload = {
                "party_name": name,
                "party_type": party_type,
                "opening_balance": 0,
                "balance_type": "Debit",
                "created_by_id": str(self.user_id),
            }
            self.step(section, f"add {party_type.lower()} party", "SELECT add_party_from_json(%s::jsonb)", [json.dumps(payload)], parser=self.accept_legacy_success)

        for item, price in ((self.item_a, 1000), (self.item_b, 1500)):
            payload = {
                "item_name": item,
                "sale_price": price,
                "storage": "REG-WH",
                "created_by_id": str(self.user_id),
            }
            self.step(section, f"add item {item}", "SELECT add_item_from_json(%s::jsonb)", [json.dumps(payload)], parser=self.accept_legacy_success)

        row = self.fetch_one("SELECT count(*) FROM parties WHERE party_name IN (%s,%s,%s)", [self.customer, self.vendor, self.expense])
        self.assert_true(section, "parties persisted", row and row[0] == 3, f"Expected 3 parties, got {row}.")

    def party_id(self, name):
        row = self.fetch_one("SELECT party_id FROM parties WHERE party_name=%s", [name])
        return row[0] if row else None

    def purchase_stock(self):
        section = "02 purchase"
        vendor_id = self.party_id(self.vendor)
        items = [
            {
                "item_name": self.item_a,
                "qty": 4,
                "unit_price": 700,
                "serials": [{"serial": s, "comment": "regression"} for s in self.serials[:4]],
            },
            {
                "item_name": self.item_b,
                "qty": 2,
                "unit_price": 900,
                "serials": [{"serial": s, "comment": "regression"} for s in self.serials[4:]],
            },
        ]
        purchase_id = self.step(
            section,
            "create purchase invoice",
            "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
            [vendor_id, self.days[0], json.dumps(items), self.user_id],
        )
        self.ctx["purchase_id"] = purchase_id
        row = self.fetch_one("SELECT count(*) FROM purchaseunits WHERE serial_number = ANY(%s)", [self.serials])
        self.assert_true(section, "serial stock inserted", row and row[0] == 6, f"Expected 6 serials, got {row}.")

    def sale_stock(self):
        section = "03 sale"
        customer_id = self.party_id(self.customer)
        sale_items = [
            {"item_name": self.item_a, "qty": 2, "unit_price": 1000, "serials": self.serials[:2]},
            {"item_name": self.item_b, "qty": 1, "unit_price": 1500, "serials": [self.serials[4]]},
        ]
        sale_id = self.step(
            section,
            "create sale invoice",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[1], json.dumps(sale_items), self.user_id],
        )
        self.ctx["sale_id"] = sale_id
        row = self.fetch_one("SELECT count(*) FROM purchaseunits WHERE serial_number = ANY(%s) AND in_stock = false", [self.serials[:2] + [self.serials[4]]])
        self.assert_true(section, "sold serials marked out of stock", row and row[0] == 3, f"Expected 3 out-of-stock serials, got {row}.")

        self.step(
            section,
            "duplicate sale of same serial blocked",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[1], json.dumps([{"item_name": self.item_a, "qty": 1, "unit_price": 1000, "serials": [self.serials[0]]}]), self.user_id],
            expect_error=True,
        )

    def cash_movements(self):
        section = "04 payments receipts"
        payment_payload = {
            "party_name": self.vendor,
            "amount": 1200,
            "method": "Cash",
            "payment_date": self.days[2],
            "description": "regression payment",
            "created_by_id": self.user_id,
        }
        receipt_payload = {
            "party_name": self.customer,
            "amount": 1800,
            "method": "Cash",
            "receipt_date": self.days[2],
            "description": "regression receipt",
            "created_by_id": self.user_id,
        }
        pay = self.step(section, "make payment", "SELECT make_payment(%s::jsonb)", [json.dumps(payment_payload)], parser=self.parse_success_json)
        rec = self.step(section, "make receipt", "SELECT make_receipt(%s::jsonb)", [json.dumps(receipt_payload)], parser=self.parse_success_json)
        self.ctx["payment"] = pay
        self.ctx["receipt"] = rec

    def returns(self):
        section = "05 returns"
        sale_return_id = self.step(
            section,
            "create sale return",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps([self.serials[0]]), self.user_id],
        )
        self.ctx["sale_return_id"] = sale_return_id
        row = self.fetch_one("SELECT in_stock FROM purchaseunits WHERE serial_number=%s", [self.serials[0]])
        self.assert_true(section, "sale return restores stock", row and row[0] is True, f"Expected returned serial in stock, got {row}.")

        purchase_return_id = self.step(
            section,
            "create purchase return",
            "SELECT create_purchase_return(%s,%s::jsonb,%s)",
            [self.vendor, json.dumps([self.serials[3]]), self.user_id],
        )
        self.ctx["purchase_return_id"] = purchase_return_id
        row = self.fetch_one("SELECT in_stock FROM purchaseunits WHERE serial_number=%s", [self.serials[3]])
        self.assert_true(section, "purchase return removes stock", row and row[0] is False, f"Expected purchase-return serial out of stock, got {row}.")

    def reports(self):
        section = "06 reports"
        report_calls = [
            ("parties json", "SELECT get_parties_json()", []),
            ("items json", "SELECT get_items_json()", []),
            ("sales summary", "SELECT get_sales_summary(%s,%s)", [self.days[0], self.days[-1]]),
            ("purchase summary", "SELECT get_purchase_summary(%s,%s)", [self.days[0], self.days[-1]]),
            ("trial balance view", "SELECT count(*) FROM vw_trial_balance", []),
            ("stock summary", "SELECT count(*) FROM stock_summary()", []),
            ("serial details", "SELECT count(*) FROM get_serial_number_details(%s)", [self.serials[0]]),
            ("detailed ledger", "SELECT count(*) FROM detailed_ledger(%s,%s,%s)", [self.customer, self.days[0], self.days[-1]]),
            ("monthly position", "SELECT monthly_company_position(%s)", [self.days[-1]]),
            ("sales report summary", "SELECT sales_summary_json(%s,%s)", [self.days[0], self.days[-1]]),
            ("dashboard stock kpi", "SELECT fn_dash_stock_kpi()", []),
            ("dashboard recent transactions", "SELECT fn_dash_recent_transactions(%s)", [10]),
        ]
        for name, sql, params in report_calls:
            self.step(section, name, sql, params)

    def tenant_version(self):
        section = "00 tenant hardening"
        row = self.fetch_one("SELECT version FROM tenant_schema_version WHERE id = true")
        self.assert_true(section, "tenant schema version exists", row and int(row[0]) >= 1, f"Missing tenant_schema_version row: {row}. Run production_hardening.sql.")

    def run(self):
        self.tenant_version()
        self.add_master_data()
        self.purchase_stock()
        self.sale_stock()
        self.cash_movements()
        self.returns()
        self.reports()
        return self.results


def discover_tenants(conn):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT c.schema_name, m.user_id
            FROM public.tenancy_company c
            JOIN public.tenancy_membership m ON m.company_id = c.id
            WHERE c.is_active = true AND c.schema_name IS NOT NULL
            ORDER BY c.id, m.user_id
            """
        )
        rows = cur.fetchall()
        if rows:
            return rows
        cur.execute(
            """
            SELECT schema_name, 1
            FROM information_schema.schemata
            WHERE schema_name LIKE 'tenant\\_%' ESCAPE '\\'
            ORDER BY schema_name
            """
        )
        return cur.fetchall()
    finally:
        cur.close()


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    tenants = discover_tenants(conn)
    if not tenants:
        print("No tenant schemas found. Create a Company/Membership first.")
        return 2

    all_results: list[tuple[str, Result]] = []
    for schema, user_id in tenants:
        runner = RegressionRunner(conn, schema, user_id)
        results = runner.run()
        all_results.extend((schema, result) for result in results)

    by_schema = {}
    for schema, result in all_results:
        by_schema.setdefault(schema, []).append(result)

    print("\nFinancee fixed-copy regression results")
    print("=" * 72)
    for schema, results in by_schema.items():
        passed = sum(1 for r in results if r.ok)
        print(f"\n{schema}: {passed}/{len(results)} passed")
        current_section = None
        for result in results:
            if result.section != current_section:
                current_section = result.section
                print(f"  {current_section}")
            mark = "OK " if result.ok else "FAIL"
            suffix = f" - {result.detail}" if result.detail else ""
            print(f"    [{mark}] {result.name}{suffix}")

    failures = [(schema, r) for schema, r in all_results if not r.ok]
    print("\n" + "=" * 72)
    if failures:
        print(f"FAILED: {len(failures)} regression checks failed.")
        for schema, result in failures:
            print(f"- {schema} / {result.section} / {result.name}: {result.detail}")
        return 1

    print("PASSED: all regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
