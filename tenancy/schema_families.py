"""Authoritative serial tenant-schema definition and rollout registry."""

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


SQL_DIR = Path(__file__).resolve().parent / "sql"
SERIAL_SCHEMA_FAMILY = "serial"


@dataclass(frozen=True)
class SchemaFamily:
    key: str
    template_path: Path
    hardening_path: Path
    required_version: int
    metadata_table: str
    runtime_enabled: bool
    required_tables: tuple[str, ...]
    required_sequences: tuple[str, ...] = ()
    required_functions: tuple[str, ...] = ()
    rollout_files: tuple[str, ...] = ()
    enabled_path_prefixes: tuple[str, ...] = ()
    bootstrap_paths: tuple[Path, ...] = ()


def serial_schema_family() -> SchemaFamily:
    return SchemaFamily(
        key=SERIAL_SCHEMA_FAMILY,
        template_path=SQL_DIR / "tenant_template.sql",
        hardening_path=SQL_DIR / "production_hardening.sql",
        required_version=getattr(settings, "TENANT_SCHEMA_VERSION", 6),
        metadata_table="tenant_schema_version",
        runtime_enabled=True,
        required_tables=(
            "tenant_schema_version",
            "items",
            "parties",
            "journalentries",
            "journallines",
        ),
        rollout_files=(
            "production_hardening.sql",
            "tenant_indexes.sql",
            "fix_sale_return_lifecycle_guards.sql",
            "fix_transaction_integrity_guards.sql",
            "fix_tenant_drift.sql",
            "fix_cash_party_port.sql",
            "add_document_attachments.sql",
            "fix_dashboard_expense_receivables.sql",
            "add_draft_invoices.sql",
            "add_report_email.sql",
            "add_team_activity.sql",
        ),
    )


def schema_family(family_key: str = SERIAL_SCHEMA_FAMILY) -> SchemaFamily:
    """Return the only supported tenant schema definition."""
    if family_key != SERIAL_SCHEMA_FAMILY:
        raise ValueError(f"Unsupported schema family: {family_key!r}")
    return serial_schema_family()


def family_for_sql_file(sql_path: str) -> str:
    """Resolve a controlled serial rollout SQL filename."""
    name = Path(sql_path).name
    definition = serial_schema_family()
    if name not in definition.rollout_files:
        raise ValueError(
            f"SQL file {name!r} is not a registered serial rollout artifact."
        )
    return SERIAL_SCHEMA_FAMILY
