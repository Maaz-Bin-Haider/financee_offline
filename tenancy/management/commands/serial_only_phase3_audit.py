"""Read-only metadata inventory; also runnable via stdin in the Phase 2 image.

No ORM model import is needed: inventory the physical database, not an assumed
migration state. Output contains identifiers/counts/hashes, never account names,
permission assignees, company names, emails, or financial records.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


# Exact auth.user permissions introduced by authentication migrations 0022–0025.
# A matching codename on any other content type is NOT a deletion candidate.
RETIRED_PERMISSIONS = {
    "view_warehouse": "Can view quantity warehouses",
    "create_warehouse": "Can create quantity warehouses",
    "update_warehouse": "Can update quantity warehouses",
    "delete_warehouse": "Can delete unreferenced quantity warehouses",
    "view_warehouse_transfer": "Can view quantity warehouse transfers",
    "create_warehouse_transfer": "Can create quantity warehouse transfers",
    "update_warehouse_transfer": "Can update quantity warehouse transfers",
    "delete_warehouse_transfer": "Can reverse quantity warehouse transfers",
    "view_physical_count": "Can view quantity physical counts",
    "create_physical_count": "Can create quantity physical counts",
    "approve_inventory_adjustment": "Can approve and post inventory adjustments",
    "reverse_inventory_adjustment": "Can reverse posted inventory adjustments",
    "view_quantity_audit": "Can view quantity audit events",
    "manage_quantity_attachments": "Can manage quantity document attachments",
}
RETIRED_FEATURE_KEYS = frozenset({
    "purchase_reports", "quantity_controls", "quantity_controls.warehouses",
    "quantity_controls.transfers", "quantity_controls.counts",
    "quantity_controls.tax", "quantity_controls.audit",
})
COMPANY_COLUMNS = (
    "id", "schema_name", "is_active", "inventory_mode", "base_currency_id",
    "tax_environment", "provisioning_state", "disabled_features",
)
SCHEMA_PATTERN = re.compile(r"tenant_company_[0-9]+\Z")


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()).hexdigest()


def classify(tables):
    serial = "tenant_schema_version" in tables
    quantity = "tenant_schema_metadata" in tables
    if serial and quantity:
        return "mixed"
    if serial:
        return "serial"
    if quantity:
        return "quantity"
    return "unknown"


def feature_inventory(raw):
    # psycopg can return JSONField values as text when no ORM converter runs.
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            pass
    valid = isinstance(raw, list) and all(isinstance(key, str) for key in raw)
    keys = raw if valid else []
    retired = sorted(set(keys) & RETIRED_FEATURE_KEYS)
    unknown = [key for key in keys if key not in RETIRED_FEATURE_KEYS
               and key.startswith(("quantity", "purchase_reports."))]
    return {
        "valid_list_of_strings": valid,
        "retired_keys": retired,
        "retired_occurrences": sum(key in RETIRED_FEATURE_KEYS for key in keys),
        "preserved_key_count": sum(key not in RETIRED_FEATURE_KEYS for key in keys),
        "unclassified_legacy_key_count": len(unknown),
        "original_fingerprint": digest(raw),
        "preserved_fingerprint": digest([key for key in keys if key not in RETIRED_FEATURE_KEYS]),
    }


def inventory(cursor):
    cursor.execute("SHOW transaction_read_only")
    if cursor.fetchone()[0] != "on":
        raise CommandError("Phase 3 audit requires a read-only transaction")
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
          FROM information_schema.columns
         WHERE table_schema='public' AND table_name='tenancy_company'
         ORDER BY ordinal_position
    """)
    columns = {name: {"data_type": dtype, "nullable": nullable == "YES",
                      "has_database_default": default is not None,
                      "default_fingerprint": digest(default)}
               for name, dtype, nullable, default in cursor.fetchall()}
    missing_columns = sorted(set(COMPANY_COLUMNS) - set(columns))
    # This first inventory targets the verified Phase 2 image/schema, not the
    # future compatibility release. Unexpected schema state must stop review.
    if missing_columns:
        raise CommandError("Phase 3 inventory blocked by missing expected columns: "
                           + ", ".join(missing_columns))
    cursor.execute("""
        SELECT id, schema_name, is_active, inventory_mode, base_currency_id,
               tax_environment, provisioning_state, disabled_features
          FROM public.tenancy_company ORDER BY id
    """)
    companies = []
    setup = []
    for pk, schema, active, mode, currency, tax, state, features in cursor.fetchall():
        canonical = bool(SCHEMA_PATTERN.fullmatch(schema or ""))
        companies.append({
            "company_id": pk, "schema": schema if canonical else None,
            "canonical_schema_name": canonical,
            "noncanonical_schema_fingerprint": None if canonical else digest(schema),
            "active": active, "inventory_mode_is_serial": mode == "serial",
            "provisioning_ready": state == "ready",
            "features": feature_inventory(features),
        })
        setup.append((pk, currency, tax))
    cursor.execute("""
        SELECT nspname FROM pg_namespace
         WHERE nspname ~ '^tenant_company_' ORDER BY nspname
    """)
    physical = [row[0] for row in cursor.fetchall()]
    registered = {row["schema"] for row in companies if row["schema"]}
    schemas = []
    for schema in physical:
        canonical = bool(SCHEMA_PATTERN.fullmatch(schema))
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
             WHERE table_schema=%s AND table_type='BASE TABLE'
             ORDER BY table_name
        """, [schema])
        tables = [row[0] for row in cursor.fetchall()]
        family = classify(tables)
        version = None
        if canonical and family == "serial":
            quoted = connection.ops.quote_name(schema)
            cursor.execute(f"SELECT version FROM {quoted}.tenant_schema_version WHERE id=true")
            row = cursor.fetchone()
            version = row[0] if row else None
        schemas.append({
            "schema": schema if canonical else None,
            "noncanonical_schema_fingerprint": None if canonical else digest(schema),
            "registered": schema in registered, "classification": family,
            "serial_version": version, "table_count": len(tables),
        })
    cursor.execute("""
        SELECT p.id, p.codename, p.name, ct.app_label, ct.model,
               (SELECT count(*) FROM public.auth_user_user_permissions u
                 WHERE u.permission_id=p.id),
               (SELECT count(*) FROM public.auth_group_permissions g
                 WHERE g.permission_id=p.id)
          FROM public.auth_permission p
          JOIN public.django_content_type ct ON ct.id=p.content_type_id
         WHERE p.codename=ANY(%s) ORDER BY p.codename, p.id
    """, [list(RETIRED_PERMISSIONS)])
    permissions, other_content_types = [], 0
    for pk, code, name, app, model, users, groups in cursor.fetchall():
        if (app, model) != ("auth", "user"):
            other_content_types += 1
            continue
        permissions.append({
            "permission_id": pk, "codename": code,
            "seed_label_matches": name == RETIRED_PERMISSIONS[code],
            "direct_user_grant_count": users, "group_grant_count": groups,
        })
    cursor.execute("""
        SELECT d.classid::regclass::text, d.deptype,
               pg_describe_object(d.classid, d.objid, d.objsubid),
               (d.classid='pg_constraint'::regclass
                AND c.conname='tenancy_company_valid_inventory_mode') IS TRUE,
               d.classid='pg_attrdef'::regclass
          FROM pg_depend d
          JOIN pg_attribute a ON a.attrelid=d.refobjid AND a.attnum=d.refobjsubid
          LEFT JOIN pg_constraint c ON d.classid='pg_constraint'::regclass AND c.oid=d.objid
         WHERE d.refclassid='pg_class'::regclass
           AND a.attrelid='public.tenancy_company'::regclass
           AND a.attname='inventory_mode' AND NOT a.attisdropped
         ORDER BY 1, 2, 3
    """)
    dependencies = [{"catalog": catalog, "dependency_type": dtype,
                     "identity_fingerprint": digest(identity),
                     "expected_serial_constraint": constraint,
                     "column_default": default}
                    for catalog, dtype, identity, constraint, default in cursor.fetchall()]
    checks = {
        "nonempty_registry": bool(companies),
        "all_registry_rows_serial_and_ready": all(
            row["inventory_mode_is_serial"] and row["provisioning_ready"]
            and row["canonical_schema_name"] for row in companies),
        "registered_schemas_exist": registered.issubset(set(physical)),
        # Read the expected version from settings, as the Phase 0 audit does.
        # A hardcoded literal silently desynced this check when the tenant
        # schema version moved to 7 for the dashboard receivables fix.
        "no_orphan_noncanonical_or_nonserial_schema": all(
            row["schema"] and row["registered"]
            and row["classification"] == "serial"
            and row["serial_version"] == settings.TENANT_SCHEMA_VERSION
            for row in schemas),
        "feature_metadata_is_classified": all(
            row["features"]["valid_list_of_strings"]
            and not row["features"]["unclassified_legacy_key_count"] for row in companies),
        "permission_labels_match_historical_seeds": all(
            row["seed_label_matches"] for row in permissions),
        "column_dependencies_are_classified": all(
            row["expected_serial_constraint"] or row["column_default"] for row in dependencies),
    }
    return {
        "phase": 3, "stage": "inventory-only",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "database-enforced-read-only", "checks": checks,
        "inventory_review_ready": all(checks.values()),
        "authorizes_cleanup": False,
        "requires_compatibility_release_before_column_drop": True,
        "company_count": len(companies),
        "active_company_count": sum(row["active"] for row in companies),
        "shared_setup_fingerprint": digest(setup),
        "shared_setup_columns_preserved": ["base_currency_id", "tax_environment"],
        "company_column_contracts": {key: columns[key] for key in COMPANY_COLUMNS},
        "inventory_mode_dependencies": dependencies,
        "companies": companies, "physical_schemas": schemas,
        "missing_registered_schemas": sorted(registered - set(physical)),
        "retired_permission_candidates": permissions,
        "same_codenames_on_other_content_types_preserved": other_content_types,
        "missing_retired_permission_codenames": sorted(
            set(RETIRED_PERMISSIONS) - {row["codename"] for row in permissions}),
    }


class Command(BaseCommand):
    help = "Inventory Phase 3 public metadata and tenant schemas without changing data."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--statement-timeout-seconds", type=int, default=60)

    def handle(self, *args, **options):
        timeout = options["statement_timeout_seconds"]
        if not 1 <= timeout <= 120:
            raise CommandError("statement timeout must be between 1 and 120 seconds")
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SELECT set_config('statement_timeout', %s, true)", [f"{timeout}s"])
                cursor.execute("SELECT set_config('lock_timeout', '2s', true)")
                result = inventory(cursor)
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        if options["strict"] and not result["inventory_review_ready"]:
            raise CommandError("Phase 3 inventory requires review; no cleanup is authorized")


if __name__ == "__main__":
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
    django.setup()
    Command().run_from_argv(["manage.py", "serial_only_phase3_audit", *sys.argv[1:]])
