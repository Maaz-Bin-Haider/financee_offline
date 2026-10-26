#!/usr/bin/env python3
"""Certify concurrent isolation across four serial-only tenants."""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

import psycopg2  # noqa: E402
from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client, RequestFactory  # noqa: E402

from financee.security import rate_limit_response  # noqa: E402
from tenancy.middleware import TenantSchemaMiddleware  # noqa: E402
from tenancy.models import (  # noqa: E402
    Company, Currency, Membership, PROVISIONING_READY,
)
from tests.serial_api_compat import SERIAL_SCHEMA_FAMILY  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402
from tenancy.utils import set_search_path  # noqa: E402

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []
DSN = {
    "dbname": os.environ.get("DB_NAME", "financee"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
}


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))


def decoded(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def django_schema():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_schema()")
        return cursor.fetchone()[0]


def sql_conn(schema):
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f'SET search_path TO "{schema}", public')
    cur.close()
    return conn


def scalar(conn, statement, params=None):
    with conn.cursor() as cursor:
        cursor.execute(statement, params or [])
        return cursor.fetchone()[0]


def call(conn, function, payload):
    return decoded(scalar(
        conn, f"SELECT {function}(%s::jsonb)", [json.dumps(payload)]
    ))


def serial_lifecycle(company, user, suffix):
    conn = sql_conn(company.schema_name)
    try:
        vendor = f"P25 Vendor {TAG} {suffix}"
        customer = f"P25 Customer {TAG} {suffix}"
        item = f"P25 Item {TAG} {suffix}"
        call(conn, "add_party_from_json", {
            "party_name": vendor, "party_type": "Vendor",
            "opening_balance": 0, "balance_type": "Debit",
            "created_by_id": str(user.pk),
        })
        call(conn, "add_party_from_json", {
            "party_name": customer, "party_type": "Customer",
            "opening_balance": 0, "balance_type": "Debit",
            "created_by_id": str(user.pk),
        })
        call(conn, "add_item_from_json", {
            "item_name": item, "sale_price": 180, "storage": "WH",
            "created_by_id": str(user.pk),
        })
        serials = [f"P25-{TAG}-{suffix}-{number}" for number in range(1, 5)]
        purchase_id = scalar(
            conn, "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
            [scalar(conn, "SELECT party_id FROM parties WHERE party_name=%s", [vendor]),
             "2026-07-20", json.dumps([{
                 "item_name": item, "qty": 4, "unit_price": 100,
                 "serials": [{"serial": serial, "comment": ""} for serial in serials],
             }]), user.pk],
        )
        sale_id = scalar(
            conn, "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [scalar(conn, "SELECT party_id FROM parties WHERE party_name=%s", [customer]),
             "2026-07-21", json.dumps([{
                 "item_name": item, "qty": 2, "unit_price": 180,
                 "serials": serials[:2],
             }]), user.pk],
        )
        scalar(conn, "SELECT create_sale_return(%s,%s::jsonb,%s)",
               [customer, json.dumps([serials[0]]), user.pk])
        scalar(conn, "SELECT create_purchase_return(%s,%s::jsonb,%s)",
               [vendor, json.dumps([serials[2]]), user.pk])
        report = scalar(conn, "SELECT get_trial_balance_json()")
        trial = scalar(
            conn, "SELECT COALESCE(sum(debit-credit),0) FROM journallines"
        )
        stock = scalar(
            conn, "SELECT count(*) FROM purchaseunits WHERE in_stock=true "
                  "AND serial_number=ANY(%s)", [serials],
        )
        conn.cursor().execute("SET search_path TO public")
        path = scalar(conn, "SELECT current_schema()")
        return {
            "mode": "serial", "suffix": suffix, "stock": stock,
            "trial": str(trial), "report": report is not None,
            "schema_after": path, "purchase_id": purchase_id,
            "sale_id": sale_id, "marker": f"P25-{TAG}-{suffix}",
        }
    finally:
        conn.close()


def http_probe(company, user, state):
    client = Client(SERVER_NAME="localhost")
    client.force_login(user)
    home = client.get("/home/")
    report = client.get("/accountsReports/trial-balance/")
    export = client.get(
        "/sales-reports/api/summary/?from=2026-07-01&to=2026-07-31"
    )
    expected = (200, 200)
    missing = client.get("/attachments/sale/999999999/")
    logout = client.get("/authentication/logout/")
    return {
        "home": home.status_code, "report": report.status_code,
        "export": export.status_code, "expected": expected,
        "missing": missing.status_code, "logout": logout.status_code,
        "report_body": report.content[:300].decode("utf-8", "replace"),
        "export_body": export.content[:300].decode("utf-8", "replace"),
        "leaked": any(
            other.encode() in report.content + export.content
            for other in state["foreign_markers"]
        ),
    }


def persistent_connection_probe(companies):
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    observed = []
    try:
        for company in companies * 3:
            with conn.cursor() as cursor:
                cursor.execute(
                    f'SET search_path TO "{company.schema_name}", public'
                )
                cursor.execute("SELECT current_schema()")
                observed.append(cursor.fetchone()[0])
                cursor.execute("SET search_path TO public")
                cursor.execute("SELECT current_schema()")
                observed.append(cursor.fetchone()[0])
        return observed
    finally:
        conn.close()


def rate_limit_probe(companies):
    cache.clear()
    factory = RequestFactory()
    responses = []
    for company in (companies[0], companies[1], companies[0]):
        request = factory.get("/home/api/kpi/", REMOTE_ADDR="192.0.2.25")
        request.user = SimpleNamespace(pk=25)
        request.tenant_company = company
        request.tenant_schema = company.schema_name
        responses.append(rate_limit_response(
            request, "phase25", limit=1, window=60
        ))
    cache.clear()
    return [None if response is None else response.status_code
            for response in responses]


def exception_probe(company):
    middleware = TenantSchemaMiddleware(lambda request: None)
    request = RequestFactory().get("/home/api/failure/")
    request.tenant_schema = company.schema_name
    set_search_path(company.schema_name)
    with patch("tenancy.middleware.logger.error"):
        response = middleware.process_exception(
            request, RuntimeError(company.schema_name)
        )
    return (
        response.status_code,
        json.loads(response.content),
        django_schema(),
    )


def drop(company):
    if not company:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"DROP SCHEMA IF EXISTS "
            f"{connection.ops.quote_name(company.schema_name)} CASCADE"
        )
        cursor.execute("SET search_path TO public")
    Company.objects.filter(pk=company.pk).delete()


def main():
    companies, users = [], []
    try:
        currency = Currency.objects.get(pk="PKR")
        User = get_user_model()
        modes = (
            (SERIAL_SCHEMA_FAMILY, "SA"),
            (SERIAL_SCHEMA_FAMILY, "SB"),
            (SERIAL_SCHEMA_FAMILY, "SC"),
            (SERIAL_SCHEMA_FAMILY, "SD"),
        )
        for _mode, suffix in modes:
            company = Company.objects.create(
                name=f"PHASE25 {suffix} {TAG}",
                base_currency=currency, tax_environment="non_tax",
            )
            user = User.objects.create_superuser(
                username=f"phase25_{TAG}_{suffix.lower()}",
                email=f"phase25-{suffix.lower()}@example.com", password="pass",
            )
            Membership.objects.create(user=user, company=company)
            companies.append(company)
            users.append(user)

        chk("T6 provisions four serial companies",
            len(companies) == 4
            and all(verify_company_schema(c, use_cache=False).family
                    == SERIAL_SCHEMA_FAMILY for c in companies)
            and all(c.provisioning_state == PROVISIONING_READY for c in companies))
        chk("all four serial schemas verify before concurrency",
            all(verify_company_schema(c, use_cache=False).ok for c in companies))

        jobs = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for company, user, (_, suffix) in zip(companies, users, modes):
                jobs.append(pool.submit(serial_lifecycle, company, user, suffix))
            states = [future.result() for future in as_completed(jobs)]
        state_by_suffix = {state["suffix"]: state for state in states}
        chk("all four simultaneous business lifecycles complete", len(states) == 4)
        chk("every concurrent tenant journal remains balanced",
            all(state["trial"] in ("0", "0.00", "0.0000") for state in states),
            [(s["suffix"], s["trial"]) for s in states])
        chk("serial purchases, sales and returns retain independent stock",
            all(state["mode"] == "serial" and state["stock"] == 2
                and state["report"] for state in states), states)
        chk("independent worker connections reset to public",
            all(state["schema_after"] == "public" for state in states), states)

        markers = [state["marker"] for state in states]
        http_states = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = []
            for company, user, (_, suffix) in zip(companies, users, modes):
                state = state_by_suffix[suffix]
                state["foreign_markers"] = [m for m in markers if m != state["marker"]]
                futures.append(pool.submit(http_probe, company, user, state))
            http_states = [future.result() for future in futures]
        chk("concurrent report pages and exports stay available",
            all((s["report"], s["export"]) == s["expected"] for s in http_states),
            http_states)
        chk("guessed attachment IDs never disclose a document",
            all(s["missing"] == 404 for s in http_states), http_states)
        chk("report and export responses contain no foreign marker",
            all(not s["leaked"] for s in http_states), http_states)
        chk("four concurrent logouts complete safely",
            all(s["logout"] in (200, 302) for s in http_states), http_states)

        observed = persistent_connection_probe(companies)
        expected = []
        for company in companies * 3:
            expected.extend([company.schema_name, "public"])
        chk("persistent connection alternates tenants without path leakage",
            observed == expected, observed)

        limits = rate_limit_probe(companies)
        chk("rate-limit cache quotas are company isolated",
            limits == [None, None, 429], limits)

        status, payload, schema = exception_probe(companies[0])
        chk("exception path resets database context to public", schema == "public", schema)
        chk("exception response hides tenant schema and internal error",
            status == 500 and payload == {
                "status": "error", "message": "An unexpected error occurred."
            } and companies[0].schema_name not in json.dumps(payload), payload)

        # The retired registry mode can no longer be forged at all, so the
        # equivalent fail-closed guarantee is proven physically: a company
        # pointing at a schema without serial metadata must be rejected.
        stray_schema = f"tenant_company_stray_{TAG}".lower()
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            cursor.execute(f"CREATE SCHEMA {connection.ops.quote_name(stray_schema)}")
        try:
            mismatch = Company(
                pk=companies[2].pk, name=companies[2].name,
                schema_name=stray_schema,
                base_currency=companies[2].base_currency,
                tax_environment=companies[2].tax_environment,
            )
            verification = verify_company_schema(mismatch, use_cache=False)
            chk("non-serial schema shape is rejected without changing tenant data",
                not verification.ok
                and verification.reason in {"metadata_invalid", "metadata_missing"},
                verification)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")
                cursor.execute(
                    f"DROP SCHEMA IF EXISTS "
                    f"{connection.ops.quote_name(stray_schema)} CASCADE"
                )
        chk("verified serial companies are unaffected by the rejected probe",
            all(verify_company_schema(c, use_cache=False).ok for c in companies))
        chk("main Django connection finishes on public", django_schema() == "public",
            django_schema())
    finally:
        for user in users:
            user.delete()
        for company in reversed(companies):
            drop(company)

    failed = [result for result in RESULTS if not result[1]]
    for name, ok, detail in RESULTS:
        print(("PASS" if ok else "FAIL") + ":", name,
              "" if ok or not detail else f"— {detail}")
    print(f"{len(RESULTS)-len(failed)}/{len(RESULTS)} Phase 25 checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
