"""Guarded, reversible prune of the replaced migration records.

Checkpoint 4B left production carrying the 34 historical `django_migrations`
rows the squashed replacements superseded. Django keeps working with them; they
are bookkeeping only. Removing them is the last piece of the serial-only
consolidation.

Pruning is normally a one-way door: Django drops a replacement from
``applied_migrations`` when the migrations it replaces are absent, so once the
rows are gone every ``replaces``-carrying image believes nothing is applied and
refuses to start. That is why this command **archives the exact rows it removes**
before removing them. Restoring the archive restores the rows, and with them the
rollback path, so the operation is reversible in the same way the Phase 3B
retirement is.

Actions:

* ``inspect`` -- read-only. Reports the exact current state and its digest.
* ``apply``   -- archives the replaced rows, runs Django's own per-app
                 ``migrate --prune``, and verifies precisely those rows and no
                 others were removed.
* ``restore`` -- puts the archived rows back and marks the archive restored.

``apply`` and ``restore`` require the typed confirmation, the exact digest from
a fresh ``inspect``, and a managed backup reference created within the last
30 minutes.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from tenancy.management.commands.serial_only_phase4_audit import (
    AUTHENTICATION_MIGRATIONS,
    REPLACEMENT,
    TENANCY_MIGRATIONS,
    classify_history,
)

ARCHIVE = "public.tenancy_phase4c_migration_archive"
KEY = "serial-only-phase4c-v1"
MARKER = "Serial-only checkpoint 4C: archived replaced migration records."
APPS = ("tenancy", "authentication")
REPLACED = {
    "tenancy": TENANCY_MIGRATIONS,
    "authentication": AUTHENTICATION_MIGRATIONS,
}
CONFIRMATIONS = {
    "apply": "PRUNE-REPLACED-MIGRATION-RECORDS",
    "restore": "RESTORE-REPLACED-MIGRATION-RECORDS",
}


def require(ok, message):
    if not ok:
        raise CommandError(f"Phase 4C prune stopped: {message}")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def history(cursor):
    """Every tenancy/authentication migration row, ordered deterministically."""
    cursor.execute(
        """SELECT app, name, applied FROM django_migrations
            WHERE app IN ('tenancy','authentication')
            ORDER BY app, name"""
    )
    return [(app, name, applied.isoformat()) for app, name, applied in cursor.fetchall()]


def stored_archive(cursor):
    cursor.execute("SELECT to_regclass(%s)", [ARCHIVE])
    if cursor.fetchone()[0] is None:
        return None
    cursor.execute(
        f"SELECT payload, payload_sha256, state FROM {ARCHIVE} WHERE operation_key=%s",
        [KEY],
    )
    row = cursor.fetchone()
    if row is None:
        return None
    payload = row[0] if isinstance(row[0], (list, dict)) else json.loads(row[0])
    require(digest(payload) == row[1], "archive checksum does not match its payload")
    return {"payload": payload, "sha256": row[1], "state": row[2]}


def state(cursor):
    rows = history(cursor)
    observed = {app: tuple(n for a, n, _ in rows if a == app) for app in APPS}
    history_state = classify_history(observed["tenancy"], observed["authentication"])
    replacement_applied = next(
        (applied for app, name, applied in rows if name == REPLACEMENT),
        datetime.now(timezone.utc).isoformat(),
    )
    return {
        "history_state": history_state,
        "applied_at": replacement_applied,
        "rows": rows,
        "replaced_row_count": sum(
            1 for app, name, _ in rows if name in REPLACED[app]
        ),
    }, stored_archive(cursor)


def summary(value, stored):
    return {
        "history_state": value["history_state"],
        "replaced_row_count": value["replaced_row_count"],
        "total_row_count": len(value["rows"]),
        "archive_state": None if stored is None else stored["state"],
        "archive_payload_sha256": None if stored is None else stored["sha256"],
        "state_sha256": digest(value),
    }


def expected_replaced(value):
    return [row for row in value["rows"] if row[1] in REPLACED[row[0]]]


def make_archive(cursor, payload):
    cursor.execute("SELECT to_regclass(%s)", [ARCHIVE])
    if cursor.fetchone()[0] is None:
        cursor.execute(
            f"""CREATE TABLE {ARCHIVE} (
                operation_key text PRIMARY KEY,
                payload jsonb NOT NULL,
                payload_sha256 text NOT NULL,
                state text NOT NULL CHECK (state IN ('applied','restored')),
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
        )
        cursor.execute(f"COMMENT ON TABLE {ARCHIVE} IS %s", [MARKER])
        cursor.execute(f"REVOKE ALL ON TABLE {ARCHIVE} FROM PUBLIC")
    cursor.execute(
        f"""INSERT INTO {ARCHIVE} (operation_key,payload,payload_sha256,state)
             VALUES (%s,%s::jsonb,%s,'applied')
             ON CONFLICT (operation_key) DO UPDATE
                SET state='applied', payload=EXCLUDED.payload,
                    payload_sha256=EXCLUDED.payload_sha256""",
        [KEY, json.dumps(payload), digest(payload)],
    )


def apply(cursor, value, stored):
    require(value["history_state"] == "post-4A",
            f"expected the post-4A history, found {value['history_state']!r}")
    payload = expected_replaced(value)
    require(len(payload) == len(TENANCY_MIGRATIONS) + len(AUTHENTICATION_MIGRATIONS),
            "unexpected number of replaced rows to archive")
    if stored is not None:
        require(stored["state"] == "restored",
                "an applied archive already exists; restore it before reapplying")
    make_archive(cursor, payload)
    # Use Django's own sanctioned mechanism, per application, then verify that
    # precisely the archived rows and nothing else were removed.
    for app in APPS:
        call_command("migrate", app, prune=True, no_input=True,
                     verbosity=0, stdout=io.StringIO())
    return payload


def restore(cursor, value, stored):
    """Reset the history to exactly the archived set plus the replacements.

    This is a reset rather than an insert on purpose. A rollback attempted
    against a pruned database does not fail cleanly: the authentication
    replacement is pure RunPython, so it re-applies and re-records its 26 rows
    before the tenancy replacement dies on CREATE TABLE. That leaves a
    half-applied history which a plain insert would compound instead of repair.
    Deleting first makes the restore idempotent and correct from any damaged
    state, not only from the clean pruned one.
    """
    require(stored is not None and stored["state"] == "applied",
            "no applied archive is available to restore")
    cursor.execute(
        "DELETE FROM django_migrations WHERE app IN ('tenancy','authentication')")
    rows = [(app, name, applied) for app, name, applied in stored["payload"]]
    rows += [(app, REPLACEMENT, value["applied_at"]) for app in APPS]
    cursor.executemany(
        "INSERT INTO django_migrations (app, name, applied) VALUES (%s,%s,%s)", rows)
    cursor.execute(f"UPDATE {ARCHIVE} SET state='restored' WHERE operation_key=%s", [KEY])


def operate(action="inspect", expected="", confirmation="", backup_release=""):
    require(action in ("inspect", "apply", "restore"), "unsupported action")
    if action != "inspect":
        require(confirmation == CONFIRMATIONS[action]
                and re.fullmatch(r"[0-9a-f]{64}", expected),
                "typed confirmation and exact inspected-state SHA-256 required")
        require(re.fullmatch(r"db-backup-[0-9]{8}T[0-9]{6}Z", backup_release),
                "managed backup reference required")
        created = datetime.strptime(backup_release[10:], "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc)
        require(0 <= (datetime.now(timezone.utc) - created).total_seconds() <= 1800,
                "backup reference is not within 30 minutes")
    with transaction.atomic():
        with connection.cursor() as cursor:
            if action == "inspect":
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL lock_timeout='2s'")
            cursor.execute("SET LOCAL statement_timeout='30s'")
            cursor.execute("SET LOCAL search_path TO public")
            if action != "inspect":
                cursor.execute("SELECT pg_try_advisory_xact_lock(731303, 4)")
                require(cursor.fetchone()[0], "another prune operation holds the lock")
                cursor.execute(
                    "LOCK TABLE public.django_migrations IN ACCESS EXCLUSIVE MODE")
            value, stored = state(cursor)
            # A damaged history is exactly when inspecting and restoring matter
            # most, so neither refuses one. Only `apply` insists on the exact
            # post-4A history, and it does so below.
            if action == "inspect":
                return {"action": action, "mode": "database-enforced-read-only",
                        "authorizes_prune": False, **summary(value, stored)}
            require(digest(value) == expected,
                    "inspected state changed; re-inspect and obtain new approval")
            if action == "apply":
                require(value["history_state"] == "post-4A",
                        f"expected the post-4A history, found "
                        f"{value['history_state']!r}")
            if action == "apply":
                removed = apply(cursor, value, stored)
            else:
                restore(cursor, value, stored)
                removed = []
            after, after_stored = state(cursor)
            if action == "apply":
                require(after["history_state"] == "pruned",
                        "history is not the pruned state after the prune")
                gone = [row for row in removed if row not in after["rows"]]
                require(len(gone) == len(removed),
                        "the prune did not remove exactly the archived rows")
                require(after["replaced_row_count"] == 0,
                        "replaced rows survived the prune")
            else:
                require(after["history_state"] == "post-4A",
                        "history is not the post-4A state after the restore")
            return {"action": action, "result": "PASS",
                    "rows_affected": len(removed) if action == "apply"
                    else len(stored["payload"]),
                    **summary(after, after_stored)}


class Command(BaseCommand):
    help = "Guarded, reversible prune of the replaced migration records."

    def add_arguments(self, parser):
        parser.add_argument("--action", default="inspect",
                            choices=("inspect", "apply", "restore"))
        parser.add_argument("--expected", default="")
        parser.add_argument("--confirmation", default="")
        parser.add_argument("--backup-release", default="")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(operate(
            options["action"], options["expected"],
            options["confirmation"], options["backup_release"],
        ), indent=2, sort_keys=True))
