"""Transactional serial-tenant provisioning."""

from django.db import connection, transaction

from .models import (
    PROVISIONING_FAILED,
    PROVISIONING_PROVISIONING,
    PROVISIONING_READY,
    Company,
)
from .schema_families import SERIAL_SCHEMA_FAMILY, schema_family
from .utils import (
    PUBLIC_SCHEMA,
    schema_has_tables,
    search_path_for,
    validate_schema_name,
)


def _read_template() -> str:
    definition = schema_family()
    return definition.template_path.read_text(encoding="utf-8")


def _assert_provisioned(cur, definition):
    """Raise inside the provisioning transaction if the family is incomplete."""
    for table in definition.required_tables:
        cur.execute("SELECT to_regclass(%s)", [table])
        if cur.fetchone()[0] is None:
            raise RuntimeError("required_table_missing")
    for sequence in definition.required_sequences:
        cur.execute("SELECT to_regclass(%s)", [sequence])
        if cur.fetchone()[0] is None:
            raise RuntimeError("required_sequence_missing")
    for function in definition.required_functions:
        cur.execute(
            """
            SELECT 1 FROM information_schema.routines
             WHERE routine_schema = current_schema()
               AND routine_name = %s
             LIMIT 1
            """,
            [function],
        )
        if cur.fetchone() is None:
            raise RuntimeError("required_function_missing")

    cur.execute("SELECT version FROM tenant_schema_version WHERE id = true")
    row = cur.fetchone()
    if not row or int(row[0]) < definition.required_version:
        raise RuntimeError("metadata_verification_failed")


def provision_schema(
    schema_name: str,
    force: bool = False,
    *,
    family: str = SERIAL_SCHEMA_FAMILY,
) -> bool:
    """Create one physical tenant schema from the serial template."""
    validate_schema_name(schema_name)
    if family != SERIAL_SCHEMA_FAMILY:
        raise ValueError("only serial tenant provisioning is supported")
    definition = schema_family()

    if not force and schema_has_tables(schema_name):
        return False

    template_sql = _read_template()
    quoted = connection.ops.quote_name(schema_name)
    tenant_path = search_path_for(schema_name)

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted}")
            cur.execute("SET check_function_bodies = false")
            cur.execute(f"SET search_path TO {tenant_path}")
            try:
                cur.execute(template_sql)
                _assert_provisioned(cur, definition)
            finally:
                cur.execute(f"SET search_path TO {PUBLIC_SCHEMA}")
    return True


def provision_company(company: Company) -> bool:
    """Provision a company and persist a sanitized operational state."""
    if not company.schema_name:
        return False
    Company.objects.filter(pk=company.pk).update(
        provisioning_state=PROVISIONING_PROVISIONING,
        provisioning_error_code="",
    )
    try:
        created = provision_schema(
            company.schema_name,
        )
    except Exception:
        Company.objects.filter(pk=company.pk).update(
            provisioning_state=PROVISIONING_FAILED,
            provisioning_error_code="schema_build_failed",
            is_active=False,
        )
        company.provisioning_state = PROVISIONING_FAILED
        company.provisioning_error_code = "schema_build_failed"
        company.is_active = False
        return False

    Company.objects.filter(pk=company.pk).update(
        provisioning_state=PROVISIONING_READY,
        provisioning_error_code="",
        is_active=True,
    )
    company.provisioning_state = PROVISIONING_READY
    company.provisioning_error_code = ""
    company.is_active = True
    return created
