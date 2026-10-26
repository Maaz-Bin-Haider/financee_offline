#!/usr/bin/env python3
"""Phase 26 T7 capacity preflight for the production-shaped Docker stack.

This is intentionally non-destructive. It records the database/container
limits that must be correct before the large 100k-SKU/5m-movement benchmark is
allowed to run.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402


TARGET = {
    "active_sessions": 100,
    "skus_per_tenant": 100_000,
    "stock_movements": 5_000_000,
    "physical_units": 100_000,
    "normal_report_seconds": 3,
    "host_vcpu": 2,
    "host_memory_bytes": 4 * 1024**3,
}


def cgroup_limit(path: str) -> int | None:
    try:
        raw = Path(path).read_text().strip()
    except OSError:
        return None
    if raw == "max":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def pg_settings() -> dict[str, str]:
    names = (
        "max_connections",
        "shared_buffers",
        "effective_cache_size",
        "work_mem",
        "maintenance_work_mem",
        "wal_compression",
        "checkpoint_completion_target",
        "random_page_cost",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name, setting || COALESCE(unit, '') "
            "FROM pg_settings WHERE name = ANY(%s)",
            [list(names)],
        )
        values = dict(cursor.fetchall())
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"
        )
        values["current_connections"] = str(cursor.fetchone()[0])
        cursor.execute("SELECT current_setting('server_version')")
        values["server_version"] = cursor.fetchone()[0]
    return values


def main() -> int:
    pg = pg_settings()
    memory_limit = cgroup_limit("/sys/fs/cgroup/memory.max")
    cpu_limit = Path("/sys/fs/cgroup/cpu.max")
    cpu_quota = cpu_limit.read_text().strip() if cpu_limit.exists() else None
    max_connections = int(pg["max_connections"])
    current_connections = int(pg["current_connections"])

    # Keep headroom for Django/Gunicorn, migrations, deploy health checks, and
    # an operator connection. T7 needs 100 active sessions, not merely a
    # max_connections value of 100.
    required_connections = TARGET["active_sessions"] + 10
    checks = {
        "postgres_16_or_newer": int(pg["server_version"].split(".")[0]) >= 16,
        "redis_cache_configured": settings.CACHES["default"]["BACKEND"].endswith(
            "RedisCache"
        ),
        "persistent_connections_enabled":
            settings.DATABASES["default"]["CONN_MAX_AGE"] > 0,
        "connection_budget_supports_t7": max_connections >= required_connections,
        "connection_headroom_currently_available":
            max_connections - current_connections >= TARGET["active_sessions"],
        "runtime_memory_not_above_t4g_medium":
            memory_limit is None or memory_limit <= TARGET["host_memory_bytes"],
    }
    payload = {
        "phase": 26,
        "gate": "capacity_preflight",
        "target": TARGET,
        "runtime": {
            "memory_limit_bytes": memory_limit,
            "cpu_quota": cpu_quota,
            "django_conn_max_age": settings.DATABASES["default"]["CONN_MAX_AGE"],
            "cache_backend": settings.CACHES["default"]["BACKEND"],
        },
        "postgres": pg,
        "checks": checks,
        "passed": all(checks.values()),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["passed"]:
        failed = [name for name, ok in checks.items() if not ok]
        print("PREFLIGHT BLOCKED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("PREFLIGHT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
