"""Read-only Phase 30 production foundation and tenant continuity audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.urls import resolve, reverse

from tenancy.admin import CompanyAdmin
from tenancy.models import Company, Membership
from tenancy.schema_families import SERIAL_SCHEMA_FAMILY
from tenancy.schema_verification import verify_company_schema
from tenancy.utils import reset_search_path, set_search_path


def _digest(value) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode()).hexdigest()


def _tenant_snapshot(company):
    verification = verify_company_schema(company, use_cache=False)
    if not verification.ok or verification.family != SERIAL_SCHEMA_FAMILY:
        raise CommandError(
            f"{company.schema_name}: serial schema verification failed "
            f"({verification.reason})"
        )
    set_search_path(company.schema_name)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name
              FROM information_schema.tables
             WHERE table_schema=current_schema() AND table_type='BASE TABLE'
             ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        counts = {}
        for table in tables:
            quoted = connection.ops.quote_name(table)
            cursor.execute(f"SELECT count(*) FROM {quoted}")
            count = cursor.fetchone()[0]
            # An empty table carries no continuity evidence. Leaving it out lets
            # a release add tables -- production_hardening.sql creates them at
            # container start, after the "before" snapshot was taken -- without
            # failing the comparison. A table that gains or loses rows still
            # changes this map.
            if count:
                counts[table] = count
        cursor.execute("""
            SELECT count(*),COALESCE(sum(debit),0),COALESCE(sum(credit),0)
              FROM journallines
        """)
        journal_count, debit, credit = cursor.fetchone()
        cursor.execute("SELECT get_trial_balance_json()")
        trial_balance = cursor.fetchone()[0]
        cursor.execute("""
            SELECT
              (SELECT count(*) FROM purchaseunits WHERE in_stock),
              (SELECT count(*) FROM soldunits WHERE status='Sold'),
              (SELECT count(*) FROM soldunits WHERE status='Returned')
        """)
        serial_state = cursor.fetchone()
    reset_search_path()
    continuity = {
        "table_counts": counts,
        "journal_line_count": journal_count,
        "journal_balanced": debit == credit,
        "journal_totals": [str(debit), str(credit)],
        "serial_state": list(serial_state),
        "trial_balance": trial_balance,
    }
    return {
        "company_id": company.pk,
        "schema": company.schema_name,
        "family": verification.family,
        "version": verification.version,
        "continuity_fingerprint": _digest(continuity),
        "table_count_fingerprint": _digest(counts),
        "journal_balanced": debit == credit,
    }


def _platform_contracts(existing_company):
    route_names = (
        "authentication:login",
        "admin:index",
        "attachments:metadata",
    )
    routes = {}
    for name in route_names:
        kwargs = (
            {"document_type": "purchase", "document_id": 1}
            if name == "attachments:metadata" else None
        )
        path = reverse(name, kwargs=kwargs)
        routes[name] = resolve(path).url_name is not None
    company_admin = CompanyAdmin(Company, admin.site)
    inventory_mode_hidden = (
        "inventory_mode" not in company_admin.form.base_fields
        and all(
            "inventory_mode" not in fieldset[1].get("fields", ())
            for fieldset in company_admin.fieldsets
        )
    )
    user_model = get_user_model()
    return {
        "routes": routes,
        # Preserve the evidence key consumed by the Phase 30 deployment
        # controller; hidden is stricter than the previous read-only field.
        "inventory_mode_admin_locked": inventory_mode_hidden,
        "active_user_count": user_model.objects.filter(is_active=True).count(),
        "membership_count": Membership.objects.count(),
        "subscription_states_valid": all(
            company.subscription_state() in {
                "suspended", "blocked", "grace", "expiring", "active",
                "unrestricted",
            }
            for company in Company.objects.filter(is_active=True)
        ),
    }


class Command(BaseCommand):
    help = "Capture or compare read-only Phase 30 production continuity evidence."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--serial-only", action="store_true")
        parser.add_argument("--compare", type=Path)

    def handle(self, *args, **options):
        companies = list(
            Company.objects.filter(is_active=True).exclude(schema_name="").order_by("id")
        )
        if not companies:
            raise CommandError("no active tenant exists")
        try:
            tenants = [_tenant_snapshot(company) for company in companies]
        finally:
            reset_search_path()
        # Checkpoint 4A retired the registry mode column, so "serial only" is
        # now proven by physical schema verification rather than by a metadata
        # value a caller could set. _tenant_snapshot already refuses any schema
        # that does not verify as the serial family; this re-asserts it on the
        # collected evidence so --serial-only stays a real, fail-closed gate.
        non_serial = [
            row["schema"] for row in tenants
            if row["family"] != SERIAL_SCHEMA_FAMILY
        ]
        if options["serial_only"] and non_serial:
            raise CommandError(
                "Phase 30 forbids quantity tenants: " + ", ".join(non_serial)
            )
        platform = _platform_contracts(companies[0])
        result = {
            "phase": 30,
            "mode": "read-only-production-safe",
            "serial_only": not non_serial,
            "tenant_count": len(tenants),
            "tenants": tenants,
            "platform": platform,
            "ok": (
                not non_serial
                and all(row["journal_balanced"] for row in tenants)
                and all(platform["routes"].values())
                and platform["inventory_mode_admin_locked"]
                and platform["subscription_states_valid"]
            ),
        }
        if options["compare"]:
            baseline = json.loads(options["compare"].read_text())
            before = {
                row["schema"]: row["continuity_fingerprint"]
                for row in baseline["tenants"]
            }
            after = {
                row["schema"]: row["continuity_fingerprint"]
                for row in result["tenants"]
            }
            result["comparison"] = {
                "tenant_set_unchanged": set(before) == set(after),
                "continuity_unchanged": before == after,
                "changed_schemas": sorted(
                    schema for schema in set(before) | set(after)
                    if before.get(schema) != after.get(schema)
                ),
            }
            result["ok"] = result["ok"] and all(
                value is True
                for key, value in result["comparison"].items()
                if key != "changed_schemas"
            )
        rendered = json.dumps(result, indent=2, sort_keys=True)
        self.stdout.write(rendered)
        if not result["ok"]:
            raise CommandError("Phase 30 production foundation audit failed")
