#!/usr/bin/env python3
"""Phase 24: execute the unchanged serial baseline on two fresh tenants."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402

from tenancy.models import (  # noqa: E402
    Company, Currency, Membership, PROVISIONING_READY,
)
from tenancy.schema_families import schema_family  # noqa: E402
from tests.serial_api_compat import SERIAL_SCHEMA_FAMILY  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []
LEGACY_MODULES = (
    "test_parties.py", "test_items.py", "test_purchases.py", "test_sales.py",
    "test_returns.py", "test_cash_movement.py", "test_opening.py",
    "test_owner_equity.py", "test_month_close.py", "test_reports.py",
    "test_attachments.py", "test_http.py",
)
QUANTITY_TABLES = {
    "tenant_schema_metadata", "quantity_seed_registry", "units_of_measure",
    "products", "product_variants", "warehouses", "stock_movements",
    "stock_balances", "fifo_layers", "fifo_allocations", "warehouse_transfers",
    "physical_counts", "tax_codes", "foreign_payments", "quantity_audit_events",
}
QUANTITY_FUNCTIONS = {
    "quantity_create_purchase", "quantity_create_sale",
    "quantity_create_sale_return", "quantity_create_purchase_return",
    "quantity_create_transfer", "quantity_create_physical_count",
    "quantity_run_report", "quantity_dashboard",
}


def _build_has_draft_invoices():
    """Whether the RUNNING build's own tenant template creates the four draft
    invoice tables. The Phase 3B rehearsal runs these tests inside an older
    image, whose template (and so every schema it serves) predates them."""
    template = ROOT / "tenancy/sql/tenant_template.sql"
    try:
        return "CREATE TABLE IF NOT EXISTS DraftInvoices" in template.read_text(encoding="utf-8")
    except OSError:
        return False


# The Phase 1 table baseline, plus draftinvoices, draftitems, draftunits and
# draftreturns on builds that carry the draft invoice feature, plus the three
# additive report-mail configuration/recipient/log tables where installed.
HAS_REPORT_EMAIL = (ROOT / "reportmailer").is_dir() and "CREATE TABLE IF NOT EXISTS report_email_settings" in (ROOT / "tenancy/sql/tenant_template.sql").read_text()
HAS_TEAM_ACTIVITY = (ROOT / "activity").is_dir() and "CREATE TABLE IF NOT EXISTS activity_events" in (ROOT / "tenancy/sql/tenant_template.sql").read_text()
BASELINE_TABLES = 24 + (4 if _build_has_draft_invoices() else 0) + (3 if HAS_REPORT_EMAIL else 0) + (1 if HAS_TEAM_ACTIVITY else 0)


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))


def q(schema, sql, params=None):
    quoted = connection.ops.quote_name(schema)
    with connection.cursor() as cursor:
        cursor.execute(f"SET search_path TO {quoted}, public")
        try:
            cursor.execute(sql, params or [])
            return cursor.fetchall() if cursor.description else []
        finally:
            cursor.execute("SET search_path TO public")


def catalog(schema):
    return {
        "tables": tuple(row[0] for row in q(schema, """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema=current_schema() AND table_type='BASE TABLE'
            ORDER BY table_name
        """)),
        "functions": tuple(row[0] for row in q(schema, """
            SELECT routine_name FROM information_schema.routines
            WHERE routine_schema=current_schema() ORDER BY routine_name
        """)),
        "views": tuple(row[0] for row in q(schema, """
            SELECT table_name FROM information_schema.views
            WHERE table_schema=current_schema() ORDER BY table_name
        """)),
        "indexes": tuple(row[0] for row in q(schema, """
            SELECT indexname FROM pg_indexes WHERE schemaname=current_schema()
            ORDER BY indexname
        """)),
    }


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


def run_command(label, command, env):
    result = subprocess.run(
        command, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = result.stdout
    chk(label, result.returncode == 0, output[-4000:])
    chk(f"{label} has zero XFAIL",
        "XFAIL" not in output and "XPASS" not in output, output[-4000:])
    return output


def main():
    companies = []
    users = []
    try:
        currency = Currency.objects.get(pk="PKR")
        User = get_user_model()
        for suffix in ("A", "B"):
            company = Company.objects.create(
                name=f"PHASE24 SERIAL {TAG} {suffix}",
                base_currency=currency, tax_environment="non_tax",
            )
            companies.append(company)
            user = User.objects.create_superuser(
                username=f"phase24_{TAG}_{suffix.lower()}",
                email=f"phase24-{suffix.lower()}@example.com", password="pass",
            )
            users.append(user)
            Membership.objects.create(user=user, company=company)

        definition = schema_family(SERIAL_SCHEMA_FAMILY)
        chk("two fresh serial companies provisioned",
            len({company.schema_name for company in companies}) == 2
            and all(company.provisioning_state == PROVISIONING_READY
                    for company in companies))
        chk("fresh serial schemas reach baseline version",
            all(q(
                company.schema_name,
                "SELECT version FROM tenant_schema_version WHERE id"
            )[0][0] == definition.required_version for company in companies))
        chk("both fresh serial schemas verify",
            all(verify_company_schema(company, use_cache=False).ok
                for company in companies))

        call_command(
            "apply_sql_all_tenants", str(definition.hardening_path),
            family=SERIAL_SCHEMA_FAMILY, stdout=open(os.devnull, "w"),
        )
        indexes_path = ROOT / "tenancy/sql/tenant_indexes.sql"
        call_command(
            "apply_sql_all_tenants", str(indexes_path),
            family=SERIAL_SCHEMA_FAMILY, stdout=open(os.devnull, "w"),
        )
        chk("serial hardening and index rollout are idempotent",
            all(verify_company_schema(company, use_cache=False).ok
                for company in companies))

        env = dict(os.environ)
        env["RUN_TAG"] = f"PHASE24_{TAG}"
        for module in LEGACY_MODULES:
            run_command(
                f"legacy {module}",
                [sys.executable, str(ROOT / "tests/suite" / module)], env,
            )
        system_output = run_command(
            "serial system-function harness",
            [sys.executable, str(ROOT / "tests/test_system.py")], env,
        )
        deep_output = run_command(
            "serial deep lifecycle harness",
            [sys.executable, str(ROOT / "tests/test_transaction_lifecycle_deep.py")],
            env,
        )
        for company in companies:
            chk(f"{company.name} system baseline is 111/111",
                f"{company.schema_name}: 111/111 passed" in system_output)
            chk(f"{company.name} deep baseline is 2702/2702",
                f"{company.schema_name}: 2702/2702 real checks passed"
                in deep_output)

        catalogs = [catalog(company.schema_name) for company in companies]
        chk("fresh serial required object fingerprints are identical",
            catalogs[0] == catalogs[1])
        for company, schema_catalog in zip(companies, catalogs):
            chk(f"{company.name} has no quantity tables",
                not QUANTITY_TABLES.intersection(schema_catalog["tables"]),
                QUANTITY_TABLES.intersection(schema_catalog["tables"]))
            chk(f"{company.name} has no quantity functions or reports",
                not QUANTITY_FUNCTIONS.intersection(schema_catalog["functions"]),
                QUANTITY_FUNCTIONS.intersection(schema_catalog["functions"]))
            chk(f"{company.name} retains Phase 1 table/index baseline",
                len(schema_catalog["tables"]) == BASELINE_TABLES
                and len(schema_catalog["indexes"]) >= 86
                and {"report_email_settings", "report_email_recipients", "report_email_log"}.intersection(schema_catalog["tables"])
                    == ({"report_email_settings", "report_email_recipients", "report_email_log"} if HAS_REPORT_EMAIL else set())
                and ("activity_events" in schema_catalog["tables"]) == HAS_TEAM_ACTIVITY,
                (len(schema_catalog["tables"]), len(schema_catalog["indexes"])))
            chk(f"{company.name} trial balance remains balanced",
                q(company.schema_name, """
                    SELECT COALESCE(sum(debit-credit),0) FROM journallines
                """)[0][0] == 0)
            chk(f"{company.name} has no orphan journal lines",
                q(company.schema_name, """
                    SELECT count(*) FROM journallines l LEFT JOIN journalentries j
                    USING(journal_id) WHERE j.journal_id IS NULL
                """)[0][0] == 0)
            chk(f"{company.name} report response contracts remain available",
                q(company.schema_name, "SELECT get_trial_balance_json()")[0][0]
                is not None
                and q(company.schema_name, "SELECT sales_summary_json(NULL,NULL)")[0][0]
                is not None)

        client = Client(SERVER_NAME="localhost")
        client.force_login(users[0])
        sidebar = client.get("/home/")
        chk("serial UI keeps legacy reports and hides quantity controls",
            sidebar.status_code == 200
            and b"Accounts Reports" in sidebar.content
            and b"Stock Reports" in sidebar.content
            and b"Sales Reports" in sidebar.content
            and b"Quantity Reports" not in sidebar.content
            and b"Physical Counts" not in sidebar.content)
        quantity_paths = (
            "/quantity-reports/", "/warehouses/quantity/", "/transfers/",
            "/physical-counts/", "/quantity-audit/",
        )
        responses = [client.get(path) for path in quantity_paths]
        chk("serial backend blocks every quantity-only route",
            all(response.status_code in (403, 404) for response in responses),
            [response.status_code for response in responses])
    finally:
        for company in reversed(companies):
            drop(company)
        # Do not delete the public users here. The legacy SQL harness exercises
        # cross-schema foreign keys to auth_user, and PostgreSQL can correctly
        # reject that deletion while another exercised schema still references
        # the ID. Usernames are run-tagged and the CI database is disposable.

    failed = [result for result in RESULTS if not result[1]]
    for name, ok, detail in RESULTS:
        print(("PASS" if ok else "FAIL") + ":", name,
              "" if ok or not detail else f"— {detail}")
    print(f"{len(RESULTS)-len(failed)}/{len(RESULTS)} Phase 24 checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
