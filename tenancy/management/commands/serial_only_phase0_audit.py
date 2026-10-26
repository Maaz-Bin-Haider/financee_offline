"""Read-only discovery audit for the serial-only consolidation project."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from tenancy.models import Company, PROVISIONING_READY
from tenancy.schema_families import SERIAL_SCHEMA_FAMILY


TENANT_SCHEMA_PATTERN = r"^tenant_company_[0-9]+$"
KNOWN_LEGACY_SERIAL_OBJECTS = {
    "item_history_view": "documented_bootstrap_debug_artifact",
}


def _digest(value) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _canonicalize_schema_references(value, schema_name):
    """Remove the physical tenant name from otherwise identical DDL text."""
    if isinstance(value, str):
        return value.replace(schema_name, "<tenant_schema>")
    if isinstance(value, tuple):
        return tuple(
            _canonicalize_schema_references(item, schema_name) for item in value
        )
    if isinstance(value, list):
        return [
            _canonicalize_schema_references(item, schema_name) for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _canonicalize_schema_references(item, schema_name)
            for key, item in value.items()
        }
    return value


def _physical_schema_names(cursor):
    cursor.execute(
        """
        SELECT schema_name
          FROM information_schema.schemata
         WHERE schema_name ~ %s
         ORDER BY schema_name
        """,
        [TENANT_SCHEMA_PATTERN],
    )
    return [row[0] for row in cursor.fetchall()]


def _schema_tables(cursor, schema_name):
    cursor.execute(
        """
        SELECT table_name
          FROM information_schema.tables
         WHERE table_schema = %s
           AND table_type = 'BASE TABLE'
         ORDER BY table_name
        """,
        [schema_name],
    )
    return [row[0] for row in cursor.fetchall()]


def _schema_classification(tables):
    has_serial = "tenant_schema_version" in tables
    has_quantity = "tenant_schema_metadata" in tables
    if has_serial and has_quantity:
        return "mixed"
    if has_serial:
        return "serial"
    if has_quantity:
        return "quantity"
    return "unknown"


def _schema_structure(cursor, schema_name):
    cursor.execute(
        """
        SELECT c.relname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = %s
           AND c.relkind = 'v'
           AND c.relname = %s
        """,
        [schema_name, "item_history_view"],
    )
    known_legacy_objects = [
        {
            "name": row[0],
            "reason": KNOWN_LEGACY_SERIAL_OBJECTS[row[0]],
        }
        for row in cursor.fetchall()
    ]
    cursor.execute(
        """
        SELECT c.table_name, c.column_name, c.ordinal_position, c.data_type,
               c.is_nullable, COALESCE(c.column_default, '')
          FROM information_schema.columns c
          JOIN information_schema.tables t
            ON t.table_schema = c.table_schema
           AND t.table_name = c.table_name
         WHERE c.table_schema = %s
           AND t.table_type = 'BASE TABLE'
         ORDER BY c.table_name, c.ordinal_position
        """,
        [schema_name],
    )
    columns = cursor.fetchall()
    cursor.execute(
        """
        SELECT p.proname,
               pg_get_function_identity_arguments(p.oid),
               pg_get_function_result(p.oid),
               p.provolatile,
               p.prosrc
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = %s
         ORDER BY p.proname, 2
        """,
        [schema_name],
    )
    functions = cursor.fetchall()
    cursor.execute(
        """
        SELECT c.relname, c.relkind
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = %s
           AND c.relkind IN ('S', 'v')
           AND c.relname <> %s
         ORDER BY c.relkind, c.relname
        """,
        [schema_name, "item_history_view"],
    )
    sequences_and_views = cursor.fetchall()
    cursor.execute(
        """
        SELECT indexname, indexdef
          FROM pg_indexes
         WHERE schemaname = %s
         ORDER BY indexname
        """,
        [schema_name],
    )
    indexes = cursor.fetchall()
    cursor.execute(
        """
        SELECT trigger_name, event_manipulation, event_object_table,
               action_timing, action_statement
          FROM information_schema.triggers
         WHERE trigger_schema = %s
         ORDER BY trigger_name, event_manipulation
        """,
        [schema_name],
    )
    triggers = cursor.fetchall()
    cursor.execute(
        """
        SELECT viewname, definition
         FROM pg_views
         WHERE schemaname = %s
           AND viewname <> %s
         ORDER BY viewname
        """,
        [schema_name, "item_history_view"],
    )
    views = cursor.fetchall()
    manifest = _canonicalize_schema_references({
        "columns": columns,
        "functions": functions,
        "sequences_and_views": sequences_and_views,
        "indexes": indexes,
        "triggers": triggers,
        "views": views,
    }, schema_name)
    return {
        "column_count": len(columns),
        "function_count": len(functions),
        "sequence_and_view_count": len(sequences_and_views),
        "index_count": len(indexes),
        "trigger_count": len(triggers),
        "view_count": len(views),
        "ignored_known_legacy_objects": known_legacy_objects,
        "component_fingerprints": {
            component: _digest(definition)
            for component, definition in manifest.items()
        },
        "fingerprint": _digest(manifest),
    }


def _schema_version(cursor, schema_name, classification):
    quoted = connection.ops.quote_name(schema_name)
    if classification == "serial":
        cursor.execute(
            f"SELECT version FROM {quoted}.tenant_schema_version WHERE id = true"
        )
        row = cursor.fetchone()
        return {"family": "serial", "version": int(row[0]) if row else None}
    if classification == "quantity":
        cursor.execute(
            f"""
            SELECT family, version, base_currency_code, tax_environment
              FROM {quoted}.tenant_schema_metadata
             WHERE id = true
            """
        )
        row = cursor.fetchone()
        return {
            "family": row[0] if row else None,
            "version": int(row[1]) if row else None,
            "base_currency": row[2] if row else None,
            "tax_environment": row[3] if row else None,
        }
    return {"family": classification, "version": None}


def _serial_continuity(cursor, schema_name, tables):
    required = {"journallines", "purchaseunits", "soldunits"}
    if not required.issubset(tables):
        return {
            "available": False,
            "journal_balanced": False,
            "reason": "required_serial_tables_missing",
        }
    quoted = connection.ops.quote_name(schema_name)
    cursor.execute(
        f"""
        SELECT count(*), COALESCE(sum(debit), 0), COALESCE(sum(credit), 0)
          FROM {quoted}.journallines
        """
    )
    journal_count, debit, credit = cursor.fetchone()
    cursor.execute(
        f"""
        SELECT
          (SELECT count(*) FROM {quoted}.purchaseunits WHERE in_stock),
          (SELECT count(*) FROM {quoted}.soldunits WHERE status = 'Sold'),
          (SELECT count(*) FROM {quoted}.soldunits WHERE status = 'Returned')
        """
    )
    serial_state = cursor.fetchone()
    evidence = {
        "journal_line_count": journal_count,
        "journal_totals": [str(debit), str(credit)],
        "serial_state": list(serial_state),
    }
    return {
        "available": True,
        "journal_balanced": debit == credit,
        "fingerprint": _digest(evidence),
    }


class Command(BaseCommand):
    help = (
        "Read-only Phase 0 inventory of company rows and physical tenant schemas. "
        "It never changes public or tenant data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-continuity",
            action="store_true",
            help=(
                "Also scan serial journal/inventory totals and emit only a "
                "privacy-safe fingerprint plus the balanced/unbalanced result."
            ),
        )
        parser.add_argument(
            "--strict-serial",
            action="store_true",
            help="Return non-zero unless the complete discovered estate is serial-only and healthy.",
        )
        parser.add_argument(
            "--statement-timeout-seconds",
            type=int,
            default=60,
            help="Abort a query rather than place sustained load on production (default: 60).",
        )

    def handle(self, *args, **options):
        timeout_seconds = options["statement_timeout_seconds"]
        if timeout_seconds < 1 or timeout_seconds > 600:
            raise CommandError("statement timeout must be between 1 and 600 seconds")

        # The transaction-level read-only flag is the database-enforced safety
        # boundary. Any accidental INSERT/UPDATE/DELETE/DDL would be rejected by
        # PostgreSQL before it could affect production.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    [f"{timeout_seconds}s"],
                )
                cursor.execute("SHOW server_version")
                postgres_version = cursor.fetchone()[0]
                cursor.execute("SELECT current_database(), pg_database_size(current_database())")
                database_name, database_bytes = cursor.fetchone()

                companies = list(
                    Company.objects.order_by("id").values(
                        "id",
                        "schema_name",
                        "is_active",
                        "provisioning_state",
                    )
                )
                # Inspect a retained legacy column when present, but do not
                # require it. The 3A image must also operate after the later,
                # separately approved contraction. Never mask a conflicting
                # value while the physical column still exists.
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                         WHERE table_schema='public' AND table_name='tenancy_company'
                           AND column_name='inventory_mode'
                    )
                """)
                has_legacy_mode = cursor.fetchone()[0]
                legacy_modes = {}
                if has_legacy_mode:
                    cursor.execute("SELECT id, inventory_mode FROM public.tenancy_company")
                    legacy_modes = dict(cursor.fetchall())
                for company in companies:
                    company["inventory_mode"] = (
                        legacy_modes.get(company["id"]) if has_legacy_mode
                        else SERIAL_SCHEMA_FAMILY
                    )
                registered = {
                    row["schema_name"]: row
                    for row in companies
                    if row["schema_name"]
                }
                physical = _physical_schema_names(cursor)
                schemas = []
                for schema_name in physical:
                    tables = _schema_tables(cursor, schema_name)
                    classification = _schema_classification(tables)
                    registry = registered.get(schema_name)
                    version = _schema_version(cursor, schema_name, classification)
                    row = {
                        "schema": schema_name,
                        "registered": registry is not None,
                        "company_id": registry["id"] if registry else None,
                        "company_active": registry["is_active"] if registry else None,
                        "registered_inventory_mode": (
                            registry["inventory_mode"] if registry else None
                        ),
                        "provisioning_state": (
                            registry["provisioning_state"] if registry else None
                        ),
                        "classification": classification,
                        "family": version["family"],
                        "version": version["version"],
                        "table_count": len(tables),
                        "structure": _schema_structure(cursor, schema_name),
                    }
                    if options["include_continuity"] and classification == "serial":
                        row["continuity"] = _serial_continuity(
                            cursor, schema_name, set(tables)
                        )
                    schemas.append(row)

        physical_set = set(physical)
        registered_set = set(registered)
        blank_schema_companies = [
            {
                "company_id": row["id"],
                "inventory_mode": row["inventory_mode"],
                "active": row["is_active"],
                "provisioning_state": row["provisioning_state"],
            }
            for row in companies
            if not row["schema_name"]
        ]
        non_serial_companies = [
            {
                "company_id": row["id"],
                "schema": row["schema_name"],
                "inventory_mode": row["inventory_mode"],
                "active": row["is_active"],
            }
            for row in companies
            if row["inventory_mode"] != SERIAL_SCHEMA_FAMILY
        ]
        orphan_schemas = sorted(physical_set - registered_set)
        missing_schemas = sorted(registered_set - physical_set)
        invalid_schemas = [
            row["schema"]
            for row in schemas
            if row["classification"] != "serial"
            or row["registered_inventory_mode"] != SERIAL_SCHEMA_FAMILY
            or row["provisioning_state"] != PROVISIONING_READY
            or row["version"] != settings.TENANT_SCHEMA_VERSION
        ]
        unbalanced_schemas = [
            row["schema"]
            for row in schemas
            if row.get("continuity")
            and not row["continuity"]["journal_balanced"]
        ]
        continuity_missing_schemas = [
            row["schema"]
            for row in schemas
            if row["classification"] == "serial"
            and not row.get("continuity", {}).get("available", False)
        ]
        serial_structure_groups = {}
        for row in schemas:
            if row["classification"] == "serial":
                serial_structure_groups.setdefault(
                    row["structure"]["fingerprint"], []
                ).append(row["schema"])
        serial_structure_groups = {
            fingerprint: sorted(schema_names)
            for fingerprint, schema_names in sorted(serial_structure_groups.items())
        }
        serial_structures_consistent = len(serial_structure_groups) <= 1
        ready = bool(companies) and not any(
            (
                blank_schema_companies,
                non_serial_companies,
                orphan_schemas,
                missing_schemas,
                invalid_schemas,
                unbalanced_schemas,
                continuity_missing_schemas,
            )
        ) and serial_structures_consistent
        result = {
            "phase": 0,
            "audit": "serial-only-discovery",
            "mode": "database-enforced-read-only",
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "database": {
                "name": database_name,
                "bytes": database_bytes,
                "postgres_version": postgres_version,
                "statement_timeout_seconds": timeout_seconds,
            },
            "company_count": len(companies),
            "active_company_count": sum(1 for row in companies if row["is_active"]),
            "inactive_company_count": sum(
                1 for row in companies if not row["is_active"]
            ),
            "registered_schema_count": len(registered_set),
            "physical_schema_count": len(physical_set),
            "blank_schema_companies": blank_schema_companies,
            "non_serial_companies": non_serial_companies,
            "orphan_schemas": orphan_schemas,
            "missing_schemas": missing_schemas,
            "invalid_schemas": invalid_schemas,
            "unbalanced_schemas": unbalanced_schemas,
            "continuity_missing_schemas": continuity_missing_schemas,
            "serial_structure_groups": serial_structure_groups,
            "serial_structures_consistent": serial_structures_consistent,
            "schemas": schemas,
            "ready_for_phase_1": ready,
        }
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        if options["strict_serial"] and not ready:
            raise CommandError("Phase 0 serial-only discovery did not pass")
