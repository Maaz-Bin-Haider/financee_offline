#!/usr/bin/env python3
"""Real-PostgreSQL proof of the guarded, reversible migration-record prune.

Runs only inside a disposable stack. Exercises the happy path, every refusal,
and the full apply -> restore -> reapply round trip, proving the operation is
reversible and that a rollback-capable image works again after a restore.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if os.environ.get("PHASE4C_TEST_DISPOSABLE") != "1":
    raise SystemExit("Use the disposable prune gate; never production.")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django
django.setup()

from django.core.management.base import CommandError
from django.db import connection
from tenancy.management.commands import serial_only_phase4c_prune as prune

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" - {detail}" if not ok else ""),
          flush=True)


def refused(**kwargs):
    try:
        prune.operate(**kwargs)
    except CommandError:
        return True
    return False


def rows():
    with connection.cursor() as cursor:
        return prune.history(cursor)


def fresh_backup():
    return "db-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_post_4a():
    """Give this disposable database the exact production history."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM django_migrations "
            "WHERE app='tenancy' AND name='0001_initial'")
        if cursor.fetchone()[0]:
            return
        payload = [("tenancy", n) for n in prune.TENANCY_MIGRATIONS]
        payload += [("authentication", n) for n in prune.AUTHENTICATION_MIGRATIONS]
        cursor.executemany(
            "INSERT INTO django_migrations (app,name,applied) VALUES (%s,%s,now())",
            payload)


def main():
    ensure_post_4a()
    before = rows()

    inspected = prune.operate()
    check("inspect is read-only and authorizes nothing",
          inspected["mode"] == "database-enforced-read-only"
          and inspected["authorizes_prune"] is False
          and inspected["history_state"] == "post-4A"
          and inspected["replaced_row_count"] == 34,
          str(inspected))
    state_sha = inspected["state_sha256"]

    check("apply without a confirmation is refused",
          refused(action="apply", expected=state_sha, backup_release=fresh_backup()))
    check("apply with the wrong confirmation is refused",
          refused(action="apply", expected=state_sha, confirmation="RESTORE-REPLACED-MIGRATION-RECORDS",
                  backup_release=fresh_backup()))
    check("apply with a stale state digest is refused",
          refused(action="apply", expected="0" * 64,
                  confirmation=prune.CONFIRMATIONS["apply"],
                  backup_release=fresh_backup()))
    check("apply without a managed backup reference is refused",
          refused(action="apply", expected=state_sha,
                  confirmation=prune.CONFIRMATIONS["apply"], backup_release=""))
    check("apply with an expired backup reference is refused",
          refused(action="apply", expected=state_sha,
                  confirmation=prune.CONFIRMATIONS["apply"],
                  backup_release="db-backup-20200101T000000Z"))
    check("every refusal left the history untouched", rows() == before)

    applied = prune.operate(action="apply", expected=state_sha,
                            confirmation=prune.CONFIRMATIONS["apply"],
                            backup_release=fresh_backup())
    check("apply prunes exactly the 34 replaced rows",
          applied["result"] == "PASS" and applied["rows_affected"] == 34
          and applied["history_state"] == "pruned"
          and applied["replaced_row_count"] == 0
          and applied["total_row_count"] == 2, str(applied))
    check("the archive records the removal", applied["archive_state"] == "applied")
    check("only the replacement records remain",
          {(a, n) for a, n, _ in rows()}
          == {("tenancy", prune.REPLACEMENT), ("authentication", prune.REPLACEMENT)})

    pruned_state = prune.operate()
    check("a second apply against the pruned state is refused",
          refused(action="apply", expected=pruned_state["state_sha256"],
                  confirmation=prune.CONFIRMATIONS["apply"],
                  backup_release=fresh_backup()))

    restored = prune.operate(action="restore", expected=pruned_state["state_sha256"],
                             confirmation=prune.CONFIRMATIONS["restore"],
                             backup_release=fresh_backup())
    check("restore puts every archived row back",
          restored["result"] == "PASS" and restored["history_state"] == "post-4A"
          and restored["replaced_row_count"] == 34, str(restored))
    check("the restored history is byte-identical to the original",
          {(a, n) for a, n, _ in rows()} == {(a, n) for a, n, _ in before})
    check("the archive is marked restored", restored["archive_state"] == "restored")

    reinspected = prune.operate()
    check("reapply is possible after a restore",
          prune.operate(action="apply", expected=reinspected["state_sha256"],
                        confirmation=prune.CONFIRMATIONS["apply"],
                        backup_release=fresh_backup())["history_state"] == "pruned")
    final = prune.operate()
    check("restore is available again after the reapply",
          prune.operate(action="restore", expected=final["state_sha256"],
                        confirmation=prune.CONFIRMATIONS["restore"],
                        backup_release=fresh_backup())["history_state"] == "post-4A")
    check("the estate ends exactly where it started",
          {(a, n) for a, n, _ in rows()} == {(a, n) for a, n, _ in before})

    passed = sum(RESULTS)
    print(f"{passed}/{len(RESULTS)} Phase 4C prune checks passed", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
