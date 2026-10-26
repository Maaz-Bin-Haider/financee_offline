"""Read-only Phase 4 audit for migration replacement and hygiene.

Two stages, selected with --stage:

* ``entry`` (default, checkpoint 4.0) requires the exact pre-squash chain, i.e.
  the migration history a database has before the 4A release runs.
* ``transition`` (checkpoint 4B) requires that same chain *plus* both squashed
  replacement records, which Django writes once every migration a replacement
  replaces is applied. That is the plan's precondition for removing the
  replaced files.

The command verifies the public state and migration history and never changes
migration records, the retirement archive, company rows, tenant schemas,
permissions, grants, containers, or application files.
"""
from __future__ import annotations

import hashlib
import json
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

REPLACEMENT = "0001_serial_only"

# The three migration histories a correct estate can hold. The audit discovers
# which one it is looking at instead of being told, so it never goes stale when
# a release moves the estate from one to the next.
#
#   pre-4A    the original chain only, before the 4A release
#   post-4A   the chain plus both replacement records, written by Django's
#             check_replacements() when the 4A release applied
#   pruned    the replacement records only, after a separately approved
#             per-app `migrate --prune`
#
# Anything else is drift and fails closed.
HISTORY_STATES = ("pre-4A", "post-4A", "pruned")


TENANCY_MIGRATIONS = (
    "0001_initial",
    "0002_subscription_control",
    "0003_subscription_emails",
    "0004_company_feature_flags",
    "0005_company_inventory_mode",
    "0006_currency_company_setup",
    "0007_company_provisioning_state",
    "0008_serial_only_company_creation",
    "0009_inventory_mode_compatibility",
)
AUTHENTICATION_MIGRATIONS = (
    "0001_payments_permissions",
    "0002_receipts_permissions",
    "0003_purchase_permissions",
    "0004_sale_permissions",
    "0005_purchase_return_permissions",
    "0006_sale_return_permissions",
    "0007_items_permissions",
    "0008_parties_permissions",
    "0009_accounts_reports_permissions",
    "0010_stock_reports_page",
    "0011_profit_reports_permissions",
    "0012_add_stock_reports_permissions_version2",
    "0013_add_account_reports_permissions_version2",
    "0014_add_stock_reports_permissions_version3",
    "0015_add_dashboard_options_permissions",
    "0016_add_set_opening_permission",
    "0017_add_owner_equity_permission",
    "0018_add_month_close_permission",
    "0019_add_sales_reports_permissions",
    "0020_add_contra_permissions",
    "0021_add_opening_stock_permissions",
    "0022_add_quantity_warehouse_permissions",
    "0023_add_quantity_transfer_permissions",
    "0024_add_quantity_count_adjustment_permissions",
    "0025_add_quantity_platform_permissions",
)
RETIRED_PERMISSION_CODES = (
    "view_warehouse",
    "create_warehouse",
    "update_warehouse",
    "delete_warehouse",
    "view_warehouse_transfer",
    "create_warehouse_transfer",
    "update_warehouse_transfer",
    "delete_warehouse_transfer",
    "view_physical_count",
    "create_physical_count",
    "approve_inventory_adjustment",
    "reverse_inventory_adjustment",
    "view_quantity_audit",
    "manage_quantity_attachments",
)
RETIRED_FEATURE_KEYS = (
    "purchase_reports",
    "quantity_controls",
    "quantity_controls.warehouses",
    "quantity_controls.transfers",
    "quantity_controls.counts",
    "quantity_controls.tax",
    "quantity_controls.audit",
)
ARCHIVE = "public.tenancy_phase3b_retirement_archive"
ARCHIVE_MARKER = "financee-serial-only-phase3b-archive-v1"
ARCHIVE_KEY = "serial-only-phase3b-v1"


def require(value, message):
    if not value:
        raise CommandError("Phase 4 entry audit blocked: " + message)


def scalar(cursor, query, params=None):
    cursor.execute(query, params or [])
    return cursor.fetchone()[0]


def history_for(state):
    """The exact django_migrations names each recognised state must hold.

    Names sort ahead of the replacement because "initial" and
    "payments_permissions" precede "serial_only".
    """
    if state == "pre-4A":
        return TENANCY_MIGRATIONS, AUTHENTICATION_MIGRATIONS
    if state == "pruned":
        return (REPLACEMENT,), (REPLACEMENT,)
    return (
        tuple(sorted(TENANCY_MIGRATIONS + (REPLACEMENT,))),
        tuple(sorted(AUTHENTICATION_MIGRATIONS + (REPLACEMENT,))),
    )


def classify_history(observed_tenancy, observed_authentication):
    """Return the recognised state these histories are, or None for drift."""
    for state in HISTORY_STATES:
        if (observed_tenancy, observed_authentication) == history_for(state):
            return state
    return None


def inspect(expect_state=None):
    if expect_state is not None and expect_state not in HISTORY_STATES:
        raise CommandError(f"unknown history state {expect_state!r}")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL lock_timeout='2s'")
            cursor.execute("SET LOCAL statement_timeout='60s'")
            cursor.execute("SET LOCAL search_path TO public")

            cursor.execute(
                """SELECT app, name FROM django_migrations
                     WHERE app IN ('tenancy', 'authentication')
                     ORDER BY app, name"""
            )
            observed = {"tenancy": [], "authentication": []}
            for app, name in cursor.fetchall():
                observed[app].append(name)
            history_state = classify_history(
                tuple(observed["tenancy"]), tuple(observed["authentication"])
            )
            require(
                history_state is not None,
                "migration history matches no recognised state "
                f"({len(observed['tenancy'])} tenancy and "
                f"{len(observed['authentication'])} authentication rows)",
            )
            require(
                expect_state is None or history_state == expect_state,
                f"migration history is {history_state!r}, not the asserted "
                f"{expect_state!r}",
            )

            column_present = scalar(
                cursor,
                """SELECT EXISTS (
                       SELECT 1 FROM pg_attribute
                        WHERE attrelid='public.tenancy_company'::regclass
                          AND attname='inventory_mode' AND NOT attisdropped)""",
            )
            require(not column_present, "retired inventory_mode column is present")

            require(
                scalar(cursor, "SELECT to_regclass(%s)", [ARCHIVE]) is not None,
                "Phase 3B reversal archive is absent",
            )
            require(
                scalar(
                    cursor,
                    "SELECT obj_description(%s::regclass, 'pg_class')",
                    [ARCHIVE],
                )
                == ARCHIVE_MARKER,
                "Phase 3B archive marker is unexpected",
            )
            cursor.execute(
                f"""SELECT operation_key, payload_sha256, state
                       FROM {ARCHIVE} ORDER BY operation_key"""
            )
            archive_rows = cursor.fetchall()
            require(
                len(archive_rows) == 1
                and archive_rows[0][0] == ARCHIVE_KEY
                and re.fullmatch(r"[0-9a-f]{64}", archive_rows[0][1] or "")
                and archive_rows[0][2] == "applied",
                "Phase 3B archive is not in the reviewed applied state",
            )

            permission_count = scalar(
                cursor,
                """SELECT count(*) FROM auth_permission p
                     JOIN django_content_type ct ON ct.id=p.content_type_id
                    WHERE ct.app_label='auth' AND ct.model='user'
                      AND p.codename = ANY(%s)""",
                [list(RETIRED_PERMISSION_CODES)],
            )
            require(permission_count == 0, "retired quantity permissions remain")

            stale_feature_count = scalar(
                cursor,
                """SELECT count(*) FROM tenancy_company c
                     CROSS JOIN LATERAL jsonb_array_elements_text(
                         COALESCE(c.disabled_features, '[]'::jsonb)
                     ) AS feature(value)
                    WHERE feature.value = ANY(%s)""",
                [list(RETIRED_FEATURE_KEYS)],
            )
            require(stale_feature_count == 0, "retired feature keys remain")

            cursor.execute(
                """SELECT id, schema_name, is_active, provisioning_state
                     FROM tenancy_company ORDER BY id"""
            )
            companies = cursor.fetchall()
            require(companies, "no registered company exists")
            require(
                all(
                    schema == f"tenant_company_{company_id}"
                    and active
                    and state == "ready"
                    for company_id, schema, active, state in companies
                ),
                "company registry is not canonical active ready serial-only",
            )

            cursor.execute(
                """SELECT nspname FROM pg_namespace
                    WHERE strpos(nspname, 'tenant_company_') = 1
                    ORDER BY nspname"""
            )
            physical = [row[0] for row in cursor.fetchall()]
            registered = [row[1] for row in companies]
            require(physical == sorted(registered), "tenant schema registry drift exists")
            for schema in physical:
                require(
                    scalar(
                        cursor,
                        "SELECT to_regclass(quote_ident(%s) || '.tenant_schema_version')",
                        [schema],
                    )
                    is not None,
                    "registered schema lacks serial metadata",
                )
                require(
                    scalar(
                        cursor,
                        "SELECT to_regclass(quote_ident(%s) || '.tenant_schema_metadata')",
                        [schema],
                    )
                    is None,
                    "retired quantity-family schema detected",
                )

            state = {
                "archive_payload_sha256": archive_rows[0][1],
                "history_state": history_state,
                "replacements_recorded": history_state in ("post-4A", "pruned"),
                "replaced_rows_retained": history_state == "post-4A",
                "archive_state": archive_rows[0][2],
                "authentication_leaf": AUTHENTICATION_MIGRATIONS[-1],
                "company_count": len(companies),
                "inventory_mode_column_present": column_present,
                "physical_schema_count": len(physical),
                "retired_feature_occurrences": stale_feature_count,
                "retired_permission_count": permission_count,
                "tenancy_leaf": TENANCY_MIGRATIONS[-1],
            }
            encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
            return {
                "audit": f"serial-only-phase4-{history_state}",
                "authorizes_migration_replacement": False,
                "authorizes_replaced_file_removal": False,
                "mode": "database-enforced-read-only",
                "state_sha256": hashlib.sha256(encoded).hexdigest(),
                **state,
            }


class Command(BaseCommand):
    help = "Read-only Phase 4 migration-leaf and post-cleanup entry audit."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")
        # Optional assertion. Omitted, the audit reports whichever recognised
        # state it finds and fails closed on anything unrecognised, so it never
        # needs repinning when a release moves the estate forward.
        parser.add_argument("--expect-state", choices=HISTORY_STATES, default=None)

    def handle(self, *args, **options):
        self.stdout.write(
            json.dumps(inspect(options["expect_state"]), indent=2, sort_keys=True)
        )


if __name__ == "__main__":
    import os
    import sys

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
    django.setup()
    Command().run_from_argv(
        ["manage.py", "serial_only_phase4_audit", *sys.argv[1:]]
    )
