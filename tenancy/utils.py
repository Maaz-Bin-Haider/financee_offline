"""
tenancy.utils
=============
Low-level, request-safe helpers for PostgreSQL schema switching.

Design notes
------------
* A schema name can NEVER be passed as a bound parameter to ``SET search_path``
  (identifiers are not parameterizable), so every schema name is validated
  against a strict pattern and double-quoted before interpolation. Schema names
  in this system are machine-generated (``tenant_company_<id>``), so the pattern
  is intentionally narrow.
* ``set_search_path`` / ``reset_search_path`` act on the *current request's*
  database connection only. Under Gunicorn sync workers each worker handles one
  request at a time on its own thread-local connection, so there is no shared,
  process-wide, or global tenant state and therefore no cross-request leakage.
"""
import re

from django.conf import settings
from django.core.cache import cache
from django.db import connection

PUBLIC_SCHEMA = "public"

# tenant_company_1 ... and 'public'. Max 63 chars (PostgreSQL identifier limit).
SCHEMA_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def validate_schema_name(schema_name: str) -> str:
    """Return the schema name if it is a safe SQL identifier, else raise."""
    if not schema_name or not SCHEMA_NAME_RE.match(schema_name):
        raise ValueError(f"Unsafe / invalid schema name: {schema_name!r}")
    return schema_name


def _quote_ident(name: str) -> str:
    return '"%s"' % validate_schema_name(name)


def search_path_for(schema_name: str) -> str:
    """
    Build the search_path string for a tenant.

    Tenants always include ``public`` as a fallback so that the SHARED tables
    (auth_user, django_session, tenancy_company, ...) remain reachable while
    business tables resolve to the tenant schema first.
    """
    if not schema_name or schema_name == PUBLIC_SCHEMA:
        return PUBLIC_SCHEMA
    return f"{_quote_ident(schema_name)}, {PUBLIC_SCHEMA}"


def set_search_path(schema_name: str) -> None:
    """Set search_path on the current connection for this request only."""
    path = search_path_for(schema_name)
    with connection.cursor() as cur:
        cur.execute(f"SET search_path TO {path}")


def reset_search_path() -> None:
    """Reset the current connection back to the shared schema. Defensive."""
    with connection.cursor() as cur:
        cur.execute(f"SET search_path TO {PUBLIC_SCHEMA}")


def schema_exists(schema_name: str) -> bool:
    validate_schema_name(schema_name)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name],
        )
        return cur.fetchone() is not None


def schema_has_tables(schema_name: str) -> bool:
    validate_schema_name(schema_name)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_type = 'BASE TABLE' LIMIT 1",
            [schema_name],
        )
        return cur.fetchone() is not None


def tenant_table_has_rows(schema_name: str, table_name: str) -> bool:
    """Return whether a validated tenant table exists and contains any row."""
    validate_schema_name(schema_name)
    if not table_name or not re.match(r"^[a-z_][a-z0-9_]{0,62}$", table_name):
        raise ValueError(f"Unsafe / invalid table name: {table_name!r}")
    quoted_schema = connection.ops.quote_name(schema_name)
    quoted_table = connection.ops.quote_name(table_name)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s LIMIT 1",
            [schema_name, table_name],
        )
        if cur.fetchone() is None:
            return False
        cur.execute(
            f"SELECT EXISTS (SELECT 1 FROM {quoted_schema}.{quoted_table} LIMIT 1)"
        )
        return bool(cur.fetchone()[0])


def list_tenant_schemas():
    """All provisioned tenant schemas (named tenant_%), ordered."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'tenant\\_%' ESCAPE '\\' "
            "ORDER BY schema_name"
        )
        return [r[0] for r in cur.fetchall()]


def tenant_schema_version_ok(schema_name: str) -> bool:
    """Return True when a tenant schema has the expected business schema version."""
    if not schema_name or schema_name == PUBLIC_SCHEMA:
        return True
    validate_schema_name(schema_name)
    expected = getattr(settings, "TENANT_SCHEMA_VERSION", 1)
    cache_key = f"tenant_schema_version_ok:{schema_name}:{expected}"
    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT version FROM tenant_schema_version WHERE id = true LIMIT 1")
            row = cur.fetchone()
    except Exception:
        cache.set(cache_key, False, timeout=30)
        return False
    ok = bool(row and int(row[0]) >= expected)
    cache.set(cache_key, ok, timeout=300 if ok else 30)
    return ok
