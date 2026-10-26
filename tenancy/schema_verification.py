"""Family/version/fingerprint verification before tenant activation."""

from dataclasses import dataclass

from django.core.cache import cache
from django.db import connection

from .models import Company
from .schema_families import SERIAL_SCHEMA_FAMILY, schema_family
from .utils import schema_exists, validate_schema_name


@dataclass(frozen=True)
class SchemaVerification:
    ok: bool
    reason: str
    family: str | None = None
    version: int | None = None


def _objects_exist(schema_name, kind, names):
    if not names:
        return True
    if kind == "sequence":
        # information_schema.sequences intentionally omits identity backing
        # sequences; pg_class is the complete PostgreSQL object catalogue.
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT c.relname
                  FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = %s
                   AND c.relkind = 'S'
                """,
                [schema_name],
            )
            found = {row[0] for row in cur.fetchall()}
        return set(names).issubset(found)
    catalog = {
        "table": ("information_schema.tables", "table_name"),
        "function": ("information_schema.routines", "routine_name"),
    }
    source, column = catalog[kind]
    with connection.cursor() as cur:
        cur.execute(
            f"SELECT {column} FROM {source} WHERE routine_schema = %s"
            if kind == "function"
            else f"SELECT {column} FROM {source} WHERE table_schema = %s",
            [schema_name],
        )
        found = {row[0] for row in cur.fetchall()}
    return set(names).issubset(found)


def verify_company_schema(company: Company, *, use_cache=True) -> SchemaVerification:
    schema_name = company.schema_name
    if not schema_name or not schema_exists(schema_name):
        return SchemaVerification(False, "schema_missing")
    validate_schema_name(schema_name)
    definition = schema_family()
    cache_key = (
        f"tenant_schema_compatible:{company.pk}:{schema_name}:"
        f"{SERIAL_SCHEMA_FAMILY}:{company.base_currency_id}:"
        f"{company.tax_environment}:"
        f"{definition.required_version}"
    )
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return SchemaVerification(**cached)

    quoted = connection.ops.quote_name(schema_name)
    try:
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT version FROM {quoted}.tenant_schema_version WHERE id = true"
            )
            row = cur.fetchone()
            if not row:
                result = SchemaVerification(False, "metadata_missing")
            elif int(row[0]) < definition.required_version:
                result = SchemaVerification(
                    False, "version_outdated", SERIAL_SCHEMA_FAMILY, row[0]
                )
            else:
                result = SchemaVerification(
                    True, "ok", SERIAL_SCHEMA_FAMILY, row[0]
                )
    except Exception:
        result = SchemaVerification(False, "metadata_invalid")

    if result.ok:
        if not _objects_exist(schema_name, "table", definition.required_tables):
            result = SchemaVerification(False, "fingerprint_tables")
        elif not _objects_exist(schema_name, "sequence", definition.required_sequences):
            result = SchemaVerification(False, "fingerprint_sequences")
        elif not _objects_exist(schema_name, "function", definition.required_functions):
            result = SchemaVerification(False, "fingerprint_functions")

    cache.set(cache_key, result.__dict__, timeout=300 if result.ok else 30)
    return result
