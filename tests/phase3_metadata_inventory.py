#!/usr/bin/env python3
"""Synthetic PostgreSQL tests for the read-only Phase 3 inventory.

Run only via the uniquely named disposable CI stack, never on production.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

if os.environ.get("PHASE3_TEST_DISPOSABLE") != "1":
    raise SystemExit("Use the metadata-inventory disposable-stack gate; not production.")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from tenancy.models import Company, Membership
from tenancy.management.commands import serial_only_phase3_audit as audit


RESULTS = []
TAG = str(time.time_ns())


def check(name, result):
    RESULTS.append((name, bool(result)))


def report(strict=False):
    output = io.StringIO()
    call_command("serial_only_phase3_audit", strict=strict, stdout=output)
    return json.loads(output.getvalue())


def strict_blocked():
    try:
        report(strict=True)
    except CommandError:
        return True
    return False


def snapshot():
    # Hash only; never print names, assignees or raw table contents.
    data = []
    with connection.cursor() as cursor:
        for table in ("tenancy_company", "auth_permission", "auth_user",
                      "auth_group", "auth_user_user_permissions", "auth_group_permissions"):
            cursor.execute(f'SELECT row_to_json(t) FROM public."{table}" t ORDER BY id')
            data.append(cursor.fetchall())
    return audit.digest(data)


def main():
    company = user = group = custom_type = None
    orphan = f"tenant_company_{TAG}"
    invalid_orphan = f"tenant_company_phase3_{TAG}"
    dependent_view = f"phase3_dependency_{TAG}"
    # Checkpoint 4A: the authentication squash correctly no longer creates the
    # retired permissions, so a fresh serial-only database has none. The Phase 3
    # inventory must still find them wherever they do exist -- that is the real
    # production case before the 3B cleanup -- so seed the exact retired set
    # here and remove only what this test created.
    # The Phase 3 inventory audits the *pre-3B* estate, so it requires the
    # retired column to exist. A fresh checkpoint 4A install never creates it
    # (that is the point of 4A), so reconstruct the exact contract the audit
    # expects on this disposable stack before exercising it.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='tenancy_company' "
            "AND column_name='inventory_mode')"
        )
        if not cursor.fetchone()[0]:
            cursor.execute(
                "ALTER TABLE public.tenancy_company "
                "ADD COLUMN inventory_mode varchar(16) NOT NULL DEFAULT 'serial'"
            )
            cursor.execute(
                "ALTER TABLE public.tenancy_company "
                "ADD CONSTRAINT tenancy_company_valid_inventory_mode "
                "CHECK (inventory_mode='serial')"
            )
            print("NOTE: fresh checkpoint 4A database; reconstructed the "
                  "retired column contract for the Phase 3 inventory.", flush=True)

    auth_user_type = ContentType.objects.get_for_model(get_user_model())
    seeded_permission_ids = []
    for codename, label in audit.RETIRED_PERMISSIONS.items():
        permission, created = Permission.objects.get_or_create(
            codename=codename, content_type=auth_user_type,
            defaults={"name": label},
        )
        if created:
            seeded_permission_ids.append(permission.pk)
    seed_permission = Permission.objects.get(
        codename="view_warehouse", content_type__app_label="auth", content_type__model="user"
    )
    original_label = seed_permission.name
    features = ["stock_reports", "quantity_controls", "quantity_controls.tax",
                "purchase_reports", "sales_reports.trend", "quantity_controls"]
    try:
        company = Company.objects.create(name=f"PRIVATE-COMPANY-{TAG}", disabled_features=features)
        # Inactive rows must be included in the inventory, not silently ignored.
        Company.objects.filter(pk=company.pk).update(is_active=False)
        user = get_user_model().objects.create_user(username=f"private-user-{TAG}")
        group = Group.objects.create(name=f"private-group-{TAG}")
        Membership.objects.create(company=company, user=user)
        user.user_permissions.add(seed_permission)
        group.permissions.add(seed_permission)
        custom_type = ContentType.objects.create(app_label=f"phase3_{TAG}", model="fixture")
        Permission.objects.create(codename="view_warehouse", name=f"PRIVATE-LABEL-{TAG}",
                                  content_type=custom_type)
        before = snapshot()
        value = report(strict=True)
        check("audit changes no public registry, permissions or assignments", snapshot() == before)
        check("healthy serial inventory passes without authorizing cleanup",
              value["inventory_review_ready"] and not value["authorizes_cleanup"])
        check("column removal remains behind a compatibility release",
              value["requires_compatibility_release_before_column_drop"])
        row = next(row for row in value["companies"] if row["company_id"] == company.pk)
        check("inactive company is inventoried", row["active"] is False)
        check("exact stale keys and duplicate occurrences are counted",
              row["features"]["retired_keys"] == ["purchase_reports", "quantity_controls", "quantity_controls.tax"]
              and row["features"]["retired_occurrences"] == 4)
        check("serial feature order and values have a preservation fingerprint",
              row["features"]["preserved_fingerprint"] == audit.digest(["stock_reports", "sales_reports.trend"]))
        check("all 14 seeded permission candidates are inventoried", len(value["retired_permission_candidates"]) == 14)
        permission = next(p for p in value["retired_permission_candidates"] if p["permission_id"] == seed_permission.pk)
        check("direct and group grants are counted without assignee identities",
              permission["direct_user_grant_count"] >= 1 and permission["group_grant_count"] >= 1)
        check("same codename on another content type is preserved",
              value["same_codenames_on_other_content_types_preserved"] >= 1
              and Permission.objects.filter(content_type=custom_type).exists())
        serialized = json.dumps(value)
        check("output excludes company/user/group names and custom permission labels",
              all(marker not in serialized for marker in (
                  company.name, user.username, group.name, f"PRIVATE-LABEL-{TAG}")))
        check("shared setup fields are preserved and fingerprinted",
              value["shared_setup_columns_preserved"] == ["base_currency_id", "tax_environment"]
              and len(value["shared_setup_fingerprint"]) == 64)
        check("inventory-mode column and dependency metadata are captured",
              "inventory_mode" in value["company_column_contracts"]
              and bool(value["inventory_mode_dependencies"]))

        # Standalone stdin execution is the exact transport used on production.
        standalone = subprocess.run(
            [sys.executable, "-", "--strict"], input=Path(audit.__file__).read_text(),
            text=True, capture_output=True,
            env={**os.environ, "PGOPTIONS": "-c default_transaction_read_only=on"},
        )
        check("standalone stdin transport works with session-enforced read-only",
              standalone.returncode == 0 and json.loads(standalone.stdout)["inventory_review_ready"])

        def forbidden_write(cursor):
            cursor.execute("UPDATE public.tenancy_company SET is_active=is_active WHERE false")
        rejected = False
        try:
            with patch.object(audit, "inventory", forbidden_write):
                report()
        except DatabaseError as exc:
            rejected = getattr(exc.__cause__, "pgcode", None) == "25006"
        check("PostgreSQL rejects an injected persistent-table write", rejected and snapshot() == before)

        for invalid_features in ({"PRIVATE": "invalid"}, ["quantity_controls.custom"]):
            Company.objects.filter(pk=company.pk).update(disabled_features=invalid_features)
            check("malformed or unclassified legacy features fail strict review", strict_blocked())
        Company.objects.filter(pk=company.pk).update(disabled_features=features)

        Permission.objects.filter(pk=seed_permission.pk).update(name=f"PRIVATE-CUSTOM-{TAG}")
        check("customized legacy permission label fails closed without exposing it",
              strict_blocked() and f"PRIVATE-CUSTOM-{TAG}" not in json.dumps(report()))
        Permission.objects.filter(pk=seed_permission.pk).update(name=original_label)

        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA "{orphan}"')
            cursor.execute(f'CREATE TABLE "{orphan}".tenant_schema_metadata (id boolean)')
        check("orphan quantity schema is detected and never removed", strict_blocked())
        orphan_row = next(s for s in report()["physical_schemas"] if s["schema"] == orphan)
        check("orphan classification remains explicit", orphan_row["classification"] == "quantity" and not orphan_row["registered"])
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA "{orphan}" CASCADE')
            cursor.execute(f'CREATE SCHEMA "{invalid_orphan}"')
        check("noncanonical tenant-prefixed schemas are not missed", strict_blocked())
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA "{invalid_orphan}" CASCADE')
        check("valid state still passes after negative cases", report(strict=True)["inventory_review_ready"])
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE VIEW public."{dependent_view}" AS SELECT inventory_mode FROM public.tenancy_company')
        check("unexpected inventory-mode dependency requires review", strict_blocked())
        with connection.cursor() as cursor:
            cursor.execute(f'DROP VIEW public."{dependent_view}"')
        for invalid_timeout in (0, 121):
            blocked = False
            try:
                call_command("serial_only_phase3_audit", statement_timeout_seconds=invalid_timeout, stdout=io.StringIO())
            except CommandError:
                blocked = True
            check("invalid statement timeout rejected", blocked)
    finally:
        Permission.objects.filter(pk=seed_permission.pk).update(name=original_label)
        with connection.cursor() as cursor:
            cursor.execute(f'DROP VIEW IF EXISTS public."{dependent_view}"')
            for schema in (orphan, invalid_orphan, company.schema_name if company else None):
                if schema:
                    cursor.execute(f'DROP SCHEMA IF EXISTS {connection.ops.quote_name(schema)} CASCADE')
        if user:
            user.delete()
        if group:
            group.delete()
        if custom_type:
            custom_type.delete()
        if company:
            Company.objects.filter(pk=company.pk).delete()
        # Remove only the retired permissions this test created.
        if seeded_permission_ids:
            Permission.objects.filter(pk__in=seeded_permission_ids).delete()
    for name, passed in RESULTS:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"{sum(passed for _, passed in RESULTS)}/{len(RESULTS)} Phase 3 live inventory checks passed")
    return 0 if all(passed for _, passed in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
