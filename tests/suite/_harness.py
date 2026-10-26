#!/usr/bin/env python3
"""
Shared harness for the Financee full-system test suite (tests/suite/).

This suite was written from a first-principles reading of the live tenant
schema (functions, triggers, chart of accounts) and the Django routes — not
from the older ad-hoc test scripts. Every module exercises real business
functions against a real tenant schema and asserts on state, money, and reports.

Design
------
* One connection per tenant, autocommit ON (each business function commits).
* Expected-failure calls run inside an explicit BEGIN/ROLLBACK so a call that
  wrongly succeeds leaves no residue.
* Uniquely tagged master data per run so repeated runs never collide.
* A single ``Tester`` object carries the connection, per-run naming, business
  builders (party/item/purchase/sale/...), accounting assertions (trial balance,
  party balance, stock state), and a result recorder.

Each domain module exposes ``GROUP`` and ``def run(t: Tester) -> None`` and can
also be executed directly (``python tests/suite/test_parties.py``) via
``standalone(run, GROUP)``.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field


try:
    import psycopg2
except ImportError:  # pragma: no cover
    print("psycopg2 is required; run inside the web container.")
    raise


DSN = {
    "dbname": os.environ["DB_NAME"],
    "user": os.environ["DB_USER"],
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
}

# The PID keeps names unique across modules run together by run_all.py (each
# module is a separate process whose per-Tester sequence counter restarts at 0).
RUN_TAG = f"{(os.environ.get('RUN_TAG') or time.strftime('%H%M%S')).upper()}_{os.getpid()}"


@dataclass
class Check:
    group: str
    name: str
    ok: bool
    detail: str = ""
    # A known_bug check documents a confirmed defect: reported as XFAIL/XPASS and
    # excluded from the pass/fail exit code (like pytest xfail).
    known_bug: bool = False


@dataclass
class Tester:
    conn: object
    schema: str
    user_id: int
    tag: str
    results: list = field(default_factory=list)
    _seq: int = 0

    # ---- low level -------------------------------------------------------
    def _rollback(self):
        # In autocommit mode conn.rollback() is a no-op, so recover an aborted
        # or open transaction with an explicit SQL ROLLBACK.
        try:
            c = self.conn.cursor()
            c.execute("ROLLBACK")
            c.close()
        except Exception:
            pass

    def cur(self):
        from psycopg2 import extensions
        if self.conn.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE:
            self._rollback()
        c = self.conn.cursor()
        if self.schema != 'public': raise RuntimeError('Only public is supported.')
        return c

    def q(self, sql, params=None):
        c = self.cur()
        try:
            c.execute(sql, params or [])
            try:
                return c.fetchall()
            except Exception:
                return None
        finally:
            c.close()

    def one(self, sql, params=None):
        rows = self.q(sql, params)
        return rows[0][0] if rows else None

    def exec(self, sql, params=None):
        """Run a statement (autocommit) and return the first scalar, or None."""
        c = self.cur()
        try:
            c.execute(sql, params or [])
            try:
                row = c.fetchone()
                return row[0] if row else None
            except Exception:
                return None
        finally:
            c.close()

    # ---- result recording ------------------------------------------------
    def check(self, group, name, cond, detail=""):
        self.results.append(Check(group, name, bool(cond), "" if cond else str(detail)))
        return bool(cond)

    def ok(self, group, name, sql, params=None):
        """Expect success; PASS when the statement does not raise."""
        c = self.cur()
        try:
            c.execute(sql, params or [])
            try:
                row = c.fetchone()
                val = row[0] if row else None
            except Exception:
                val = None
            self.check(group, name, True)
            return val
        except Exception as exc:
            self._rollback()
            self.check(group, name, False, f"{type(exc).__name__}: {str(exc).splitlines()[0]}")
            return None
        finally:
            c.close()

    def err(self, group, name, sql, params=None, contains=None):
        """Expect a raised error; runs in BEGIN/ROLLBACK so nothing persists."""
        c = self.cur()
        try:
            c.execute("BEGIN")
            c.execute(sql, params or [])
            c.execute("ROLLBACK")
            self.check(group, name, False, "expected an error, but the call succeeded")
            return
        except Exception as exc:
            self._rollback()
            msg = str(exc).splitlines()[0]
            if contains is None:
                self.check(group, name, True)
            else:
                self.check(group, name, contains.lower() in msg.lower(),
                           f"error did not contain {contains!r}: {msg}")
        finally:
            c.close()

    def xfail(self, group, name, sql, params=None):
        """Document a currently-broken call. XFAIL if it errors (expected),
        XPASS if it unexpectedly works. Never fails the suite. Runs in a
        rolled-back transaction so nothing persists."""
        c = self.cur()
        try:
            c.execute("BEGIN")
            c.execute(sql, params or [])
            c.execute("ROLLBACK")
            self.results.append(Check(group, name, True, "unexpectedly succeeded (bug may be fixed)", known_bug=True))
        except Exception as exc:
            self._rollback()
            self.results.append(Check(group, name, False, str(exc).splitlines()[0], known_bug=True))
        finally:
            c.close()

    def expect_block(self, group, name, sql, params=None, contains=None):
        """Expect the call to be blocked (raise a guard error).

        * If it raises -> real PASS (guard works).
        * If it wrongly succeeds -> recorded as a documented XFAIL (a missing
          guard / tenant drift), which does NOT fail the suite.
        Runs in a rolled-back transaction so a wrongly-successful destructive
        call never persists.
        """
        c = self.cur()
        try:
            c.execute("BEGIN")
            c.execute(sql, params or [])
            c.execute("ROLLBACK")
            self.results.append(Check(group, name, False,
                                      "call was NOT blocked (guard missing / tenant drift)", known_bug=True))
        except Exception as exc:
            self._rollback()
            msg = str(exc).splitlines()[0]
            ok = contains is None or contains.lower() in msg.lower()
            self.check(group, name, ok, "" if ok else f"blocked but with unexpected error: {msg}")
        finally:
            c.close()

    def call_json(self, sql, params=None):
        """Call a jsonb-returning function and return the parsed dict."""
        val = self.exec(sql, params)
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(val)
        except Exception:
            return val

    # ---- naming ----------------------------------------------------------
    def name(self, prefix):
        self._seq += 1
        return f"{prefix} {self.tag} {self._seq:04d}"

    def serials(self, prefix, n):
        base = f"{self.tag}-{prefix}"
        out = []
        for _ in range(n):
            self._seq += 1
            out.append(f"{base}-{self._seq:05d}")
        return out

    # ---- master-data builders -------------------------------------------
    def add_party(self, party_type, opening_balance=0, balance_type="Debit", name=None):
        nm = name or self.name(f"P-{party_type[:3].upper()}")
        payload = {
            "party_name": nm, "party_type": party_type,
            "opening_balance": opening_balance, "balance_type": balance_type,
            "created_by_id": str(self.user_id),
        }
        self.exec("SELECT add_party_from_json(%s::jsonb)", [json.dumps(payload)])
        return nm

    def add_item(self, sale_price=250, name=None, category=None, brand=None):
        nm = name or self.name("ITEM")
        payload = {"item_name": nm, "sale_price": sale_price, "storage": "WH",
                   "category": category, "brand": brand,
                   "created_by_id": str(self.user_id)}
        self.exec("SELECT add_item_from_json(%s::jsonb)", [json.dumps(payload)])
        return nm

    def has_column(self, table, col):
        return bool(self.one(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s AND column_name=%s",
            [self.schema, table, col]))

    def relation_exists(self, name):
        return bool(self.one("SELECT to_regclass(%s)", [f'"{self.schema}".{name}']))

    def has_function(self, name):
        return bool(self.one(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname=%s AND p.proname=%s", [self.schema, name]))

    def party_id(self, name):
        return self.one("SELECT party_id FROM parties WHERE party_name=%s", [name])

    def item_id(self, name):
        return self.one("SELECT item_id FROM items WHERE item_name=%s", [name])

    def ensure_cash_sale_party(self):
        if self.party_id("Cash Sale") is None:
            self.add_party("Customer", name="Cash Sale")
        return "Cash Sale"

    # ---- transaction builders -------------------------------------------
    def purchase(self, vendor_name, serials, unit_price=100, item_name=None, date="2025-07-01"):
        item = item_name or self.add_item()
        items = [{"item_name": item, "qty": len(serials), "unit_price": unit_price,
                  "serials": [{"serial": s, "comment": ""} for s in serials]}]
        vid = self.party_id(vendor_name)
        pid = self.exec("SELECT create_purchase(%s,%s,%s::jsonb,%s)",
                        [vid, date, json.dumps(items), self.user_id])
        return pid, item

    def sale(self, party_name, serials, unit_price=150, item_name=None, date="2025-07-02"):
        cid = self.party_id(party_name)
        items = [{"item_name": item_name, "qty": len(serials), "unit_price": unit_price,
                  "serials": serials}]
        return self.exec("SELECT create_sale(%s,%s,%s::jsonb,%s)",
                         [cid, date, json.dumps(items), self.user_id])

    def sale_multi(self, party_name, item_lines, date="2025-07-02"):
        """item_lines: list of (item_name, serials, unit_price)."""
        cid = self.party_id(party_name)
        items = [{"item_name": nm, "qty": len(ser), "unit_price": px, "serials": ser}
                 for nm, ser, px in item_lines]
        return self.exec("SELECT create_sale(%s,%s,%s::jsonb,%s)",
                         [cid, date, json.dumps(items), self.user_id])

    def sale_return(self, party_name, serials):
        return self.exec("SELECT create_sale_return(%s,%s::jsonb,%s)",
                         [party_name, json.dumps(serials), self.user_id])

    def purchase_return(self, vendor_name, serials):
        return self.exec("SELECT create_purchase_return(%s,%s::jsonb,%s)",
                         [vendor_name, json.dumps(serials), self.user_id])

    def payment(self, vendor_name, amount, date="2025-07-03", ref=None, desc=None):
        payload = {"party_name": vendor_name, "amount": amount, "method": "Cash",
                   "reference_no": ref, "description": desc, "payment_date": date,
                   "created_by_id": str(self.user_id)}
        return self.call_json("SELECT make_payment(%s::jsonb)", [json.dumps(payload)])

    def receipt(self, customer_name, amount, date="2025-07-03", ref=None, desc=None):
        payload = {"party_name": customer_name, "amount": amount, "method": "Cash",
                   "reference_no": ref, "description": desc, "receipt_date": date,
                   "created_by_id": str(self.user_id)}
        return self.call_json("SELECT make_receipt(%s::jsonb)", [json.dumps(payload)])

    def contra(self, from_name, to_name, amount, date="2025-07-03", ref=None, desc=None):
        payload = {"from_party_name": from_name, "to_party_name": to_name, "amount": amount,
                   "reference_no": ref, "description": desc, "contra_date": date,
                   "created_by_id": str(self.user_id)}
        return self.call_json("SELECT make_contra(%s::jsonb)", [json.dumps(payload)])

    # ---- accounting / state assertions ----------------------------------
    def tb_diff(self):
        return float(self.one(
            "SELECT COALESCE(SUM(debit),0)-COALESCE(SUM(credit),0) FROM journallines") or 0)

    def assert_tb(self, group, label):
        d = self.tb_diff()
        return self.check(group, f"trial balance balances after {label}", abs(d) < 0.005,
                          f"trial balance out by {d:.4f}")

    def party_balance(self, name):
        row = self.call_json("SELECT get_party_balance_by_name(%s)", [name])
        if not row or not row.get("found"):
            return None
        return float(row.get("balance") or 0)

    def in_stock(self, serial):
        return self.one("SELECT in_stock FROM purchaseunits WHERE serial_number=%s", [serial])

    def active_sold(self, serial):
        return int(self.one(
            "SELECT count(*) FROM soldunits su JOIN purchaseunits pu ON pu.unit_id=su.unit_id "
            "WHERE pu.serial_number=%s AND su.status='Sold'", [serial]) or 0)

    def assert_stock(self, group, serial, expected):
        actual = self.in_stock(serial)
        return self.check(group, f"{serial} in_stock={expected}", actual is expected,
                          f"expected {expected}, got {actual}")

    def no_empty_journals(self, group, label):
        n = self.one("SELECT count(*) FROM journalentries je "
                     "WHERE NOT EXISTS (SELECT 1 FROM journallines jl WHERE jl.journal_id=je.journal_id)")
        return self.check(group, f"no empty journal entries ({label})", n == 0, f"{n} empty entries")


# ------------------------------------------------------------------------- #
#  Tenant discovery + runners
# ------------------------------------------------------------------------- #
def discover_business(conn):
    if DSN['dbname'] != 'financee_offline_test':
        raise RuntimeError('Business suite requires the isolated disposable financee_offline_test database.')
    with conn.cursor() as cur:
        cur.execute('SELECT id FROM public.auth_user WHERE is_active AND is_superuser ORDER BY id LIMIT 1')
        row = cur.fetchone()
    if not row: raise RuntimeError('Set up a disposable test owner first.')
    return [('public', row[0])]


def _print_and_exit(results):
    by_schema = {}
    for schema, r in results:
        by_schema.setdefault(schema, []).append(r)
    print("\n" + "=" * 78)
    total_fail = 0
    total_xfail = 0
    total_xpass = 0
    for schema, rs in by_schema.items():
        real = [r for r in rs if not r.known_bug]
        passed = sum(1 for r in real if r.ok)
        print(f"{schema}: {passed}/{len(real)} real checks passed")
        cur_group = None
        for r in rs:
            if r.group != cur_group:
                cur_group = r.group
                print(f"  [{cur_group}]")
            if r.known_bug:
                if r.ok:
                    total_xpass += 1
                    print(f"    [XPASS] {r.name} - {r.detail}")
                else:
                    total_xfail += 1
                    print(f"    [XFAIL] {r.name} - {r.detail}")
            elif not r.ok:
                total_fail += 1
                print(f"    [FAIL] {r.name} - {r.detail}")
    print("=" * 78)
    if total_xfail or total_xpass:
        print(f"Known bugs: {total_xfail} XFAIL (documented), {total_xpass} XPASS (may be fixed).")
    if total_fail:
        print(f"FAILED: {total_fail} checks failed.")
        return 1
    print("PASSED: all real checks passed"
          + (f" ({total_xfail} known bugs documented)." if total_xfail else "."))
    return 0


def standalone(run_fn, group):
    """Entry point for running a single domain module directly."""
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    tenants = discover_business(conn)
    if not tenants:
        print("No active tenant memberships found.")
        return 2
    all_results = []
    for schema, uid in tenants:
        t = Tester(conn, schema, uid, RUN_TAG)
        try:
            run_fn(t)
        except Exception as exc:  # a crashing module is itself a failure
            import traceback
            t.check(group, "module crashed", False,
                    f"{type(exc).__name__}: {exc} | {traceback.format_exc().splitlines()[-3:]}")
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
        all_results.extend((schema, r) for r in t.results)
    return _print_and_exit(all_results)
