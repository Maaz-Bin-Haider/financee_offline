"""Fail-closed schema-family/version/fingerprint release gate."""
from __future__ import annotations

import hashlib
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenancy.models import Company, PROVISIONING_READY
from tenancy.schema_families import SERIAL_SCHEMA_FAMILY, schema_family
from tenancy.schema_verification import verify_company_schema
from tenancy.utils import reset_search_path, set_search_path


class Command(BaseCommand):
    help = "Verify every active tenant before or after a release."

    def add_arguments(self, parser):
        parser.add_argument(
            "--require-family", action="append", choices=("serial",),
            default=[], help="Fail unless at least one active tenant has this family.",
        )
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        rows, failed, families = [], [], set()
        family_fingerprints = {}
        companies = Company.objects.filter(is_active=True).exclude(
            schema_name=""
        ).order_by("id")
        try:
            for company in companies:
                definition = schema_family()
                verification = verify_company_schema(company, use_cache=False)
                families.add(SERIAL_SCHEMA_FAMILY)
                row = {
                    "company_id": company.pk,
                    "company": company.name,
                    "schema": company.schema_name,
                    "registered_family": SERIAL_SCHEMA_FAMILY,
                    "verified_family": verification.family,
                    "version": verification.version,
                    "required_version": definition.required_version,
                    "provisioning_state": company.provisioning_state,
                    "ok": bool(
                        verification.ok
                        and verification.family == SERIAL_SCHEMA_FAMILY
                        and verification.version >= definition.required_version
                        and company.provisioning_state == PROVISIONING_READY
                    ),
                    "reason": verification.reason,
                }
                if row["ok"]:
                    set_search_path(company.schema_name)
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT table_name,column_name,ordinal_position,
                                   data_type,is_nullable,COALESCE(column_default,'')
                              FROM information_schema.columns
                             WHERE table_schema=current_schema()
                               AND table_name=ANY(%s)
                             ORDER BY table_name,ordinal_position
                        """, [list(definition.required_tables)])
                        columns = cursor.fetchall()
                        cursor.execute("""
                            SELECT p.proname,
                                   pg_get_function_identity_arguments(p.oid),
                                   pg_get_function_result(p.oid),
                                   p.provolatile,p.prosrc
                              FROM pg_proc p
                              JOIN pg_namespace n ON n.oid=p.pronamespace
                             WHERE n.nspname=current_schema()
                               AND p.proname=ANY(%s)
                             ORDER BY p.proname,2
                        """, [list(definition.required_functions)])
                        functions = cursor.fetchall()
                        actual_contract = {
                            "columns": columns,
                            "functions": functions,
                            "sequences": sorted(definition.required_sequences),
                        }
                        row["fingerprint"] = hashlib.sha256(
                            json.dumps(
                                actual_contract, sort_keys=True, default=str
                            ).encode()
                        ).hexdigest()
                        cursor.execute("SELECT get_trial_balance_json()")
                        row["safe_probe"] = cursor.fetchone()[0] is not None
                    row["ok"] = row["ok"] and row["safe_probe"]
                    expected = family_fingerprints.setdefault(
                        SERIAL_SCHEMA_FAMILY, row["fingerprint"]
                    )
                    row["fingerprint_matches_family"] = (
                        row["fingerprint"] == expected
                    )
                    row["ok"] = (
                        row["ok"] and row["fingerprint_matches_family"]
                    )
                else:
                    row["safe_probe"] = False
                    row["fingerprint"] = ""
                    row["fingerprint_matches_family"] = False
                reset_search_path()
                rows.append(row)
                if not row["ok"]:
                    failed.append(company.schema_name)
        finally:
            reset_search_path()

        missing = sorted(set(options["require_family"]) - families)
        result = {
            "ok": not failed and not missing and bool(rows),
            "tenant_count": len(rows),
            "families": sorted(families),
            "missing_required_families": missing,
            "failed_schemas": failed,
            "tenants": rows,
        }
        if options["json"]:
            self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        else:
            for row in rows:
                self.stdout.write(
                    f"{'OK' if row['ok'] else 'FAIL'} "
                    f"{row['schema']} company={row['company']!r} "
                    f"family={row['registered_family']} "
                    f"version={row['version']}/{row['required_version']} "
                    f"fingerprint={row['fingerprint'][:16]}"
                )
            if missing:
                self.stderr.write("Missing required families: " + ", ".join(missing))
        if not result["ok"]:
            raise CommandError(
                "release preflight failed: "
                f"failed={failed or 'none'} missing={missing or 'none'}"
            )
