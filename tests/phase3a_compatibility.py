#!/usr/bin/env python3
"""Serial application proof that no retired inventory mode survives anywhere.

Checkpoint 4B deleted the replaced migration files, so the migration-level half
of this proof — driving `0009_inventory_mode_compatibility` forwards and
backwards through the real executor, and its fail-closed negative cases —
retired with the migration it tested. Its file name is kept because several
contract-pinned CI wiring points reference it.

What remains is the part that is still true and still worth proving on a live
stack: a serial company can be created, administered and used end to end while
no retired mode exists in the model API, the admin, the database, or any SQL the
application emits.

Disposable stacks only.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import time

if os.environ.get("PHASE3A_TEST_DISPOSABLE") != "1":
    raise SystemExit("Use the compatibility disposable-stack gate; never production.")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django
django.setup()

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from tenancy.admin import CompanyAdminForm
from tenancy.models import Company, Membership
from tenancy.schema_verification import verify_company_schema
from tests.serial_api_compat import (
    no_retired_mode_attribute,
    retired_mode_rejected,
)

RESULTS = []


def check(name, ok):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}", flush=True)


def sql(statement, params=None):
    with connection.cursor() as cursor:
        cursor.execute(statement, params)
        return cursor.fetchall() if cursor.description else []


def main():
    check(
        "the retired column is absent from the registry",
        sql(
            """SELECT count(*) FROM information_schema.columns
                WHERE table_schema='public' AND table_name='tenancy_company'
                  AND column_name='inventory_mode'"""
        )[0][0] == 0,
    )
    check(
        "the retired serial-only constraint is absent",
        sql(
            """SELECT count(*) FROM pg_constraint
                WHERE conname='tenancy_company_valid_inventory_mode'"""
        )[0][0] == 0,
    )
    check("Company has no concrete inventory-mode field",
          "inventory_mode" not in {f.name for f in Company._meta.get_fields()})
    for value in ("quantity", "unknown", "", None, "serial"):
        check(f"construction rejects retired mode keyword {value!r} without inserting",
              retired_mode_rejected(f"Phase3A rejected {time.time_ns()}", value))
    check("retired mode is absent from the model API entirely",
          not hasattr(Company, "inventory_mode")
          and not hasattr(Company, "get_inventory_mode_display"))

    tag = str(time.time_ns())
    company = None
    user = None
    try:
        with CaptureQueriesContext(connection) as queries:
            company = Company.objects.create(name=f"Phase3A serial {tag}")
            company.refresh_from_db()
            company.full_clean()
            verification = verify_company_schema(company, use_cache=False)
            check("new company provisions serial v6 without any retired column",
                  company.provisioning_state == "ready"
                  and verification.ok and verification.family == "serial")
            check("no retired mode attribute survives on a live company",
                  no_retired_mode_attribute(company))
            form = CompanyAdminForm(instance=company)
            check("company administration and shared setup remain available",
                  "inventory_mode" not in form.fields
                  and "base_currency" in form.fields
                  and "tax_environment" in form.fields)
            user = get_user_model().objects.create_superuser(
                username=f"phase3a_{tag}", email="phase3a@example.com",
                password="test-only")
            Membership.objects.create(user=user, company=company)
            client = Client(HTTP_HOST="localhost")
            client.force_login(user)
            for path in ("/", "/purchase/purchasing/", "/sale/sales/",
                         "/items/items-dash/", "/admin/tenancy/company/"):
                response = client.get(path, follow=True)
                check(f"authenticated serial page works: {path}",
                      response.status_code == 200
                      and response.wsgi_request.user.is_authenticated
                      and not any("/authentication/login/" in location
                                  for location, _ in response.redirect_chain))
            company.disabled_features = ["stock_reports"]
            company.save(update_fields=["disabled_features"])
            company.refresh_from_db()
            check("shared feature settings still persist",
                  not company.feature_enabled("stock_reports")
                  and company.feature_enabled("sales_reports"))
            call_command("apply_sql_all_tenants", "tenancy/sql/tenant_indexes.sql",
                         dry_run=True, stdout=io.StringIO())
            call_command("release_preflight", stdout=io.StringIO())
            call_command("production_foundation_audit", stdout=io.StringIO())
        check("application reads/writes and operational commands emit no legacy-column SQL",
              not any("inventory_mode" in query["sql"]
                      for query in queries.captured_queries))

        output = io.StringIO()
        call_command("serial_only_phase0_audit", include_continuity=True, stdout=output)
        report = json.loads(output.getvalue())
        check("continuity inventory remains available and serial-only",
              not report["non_serial_companies"] and not report["missing_schemas"]
              and not report["unbalanced_schemas"]
              and not report["continuity_missing_schemas"])
    finally:
        if user is not None:
            user.delete()
        if company is not None:
            schema = company.schema_name
            Company.objects.filter(pk=company.pk).delete()
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")
                cursor.execute(
                    f"DROP SCHEMA IF EXISTS "
                    f"{connection.ops.quote_name(schema)} CASCADE"
                )

    passed = sum(ok for _name, ok in RESULTS)
    print(f"{passed}/{len(RESULTS)} serial no-retired-mode checks passed", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
