#!/usr/bin/env python3
"""Static safety contracts for the Phase 0 read-only discovery command."""
import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# The CI known-drift assertion below pins the tenant schema version the two CI
# schemas must report. Read it from settings instead of hardcoding a literal:
# a hardcoded 6 silently desynced this gate when the version moved to 7.
EXPECTED_SCHEMA_VERSION = int(
    re.search(
        r'TENANT_SCHEMA_VERSION\s*=\s*env\.int\(\s*"TENANT_SCHEMA_VERSION"\s*,\s*default=(\d+)\s*\)',
        (ROOT / "financee/settings.py").read_text(encoding="utf-8"),
    ).group(1)
)

audit = (
    ROOT
    / "tenancy/management/commands/serial_only_phase0_audit.py"
).read_text(encoding="utf-8")
tree = ast.parse(audit)
called_attributes = {
    node.func.attr
    for node in ast.walk(tree)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
}
sql_literals = "\n".join(
    node.value.upper()
    for node in ast.walk(tree)
    if isinstance(node, ast.Constant) and isinstance(node.value, str)
)

checks = {
    "database transaction is forced read-only":
        'cursor.execute("SET TRANSACTION READ ONLY")' in audit,
    "command contains no ORM mutator calls":
        not ({"save", "create", "update", "delete", "bulk_create"}
             & called_attributes),
    "command contains no data or schema mutation SQL":
        not any(token in sql_literals for token in (
            "INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE ",
            "DROP ", "ALTER ", "CREATE TABLE", "CREATE SCHEMA",
        )),
    "query load is bounded by a local statement timeout":
        "statement_timeout" in audit and "set_config" in audit,
    "all company rows are inventoried":
        'Company.objects.order_by("id").values(' in audit,
    "physical tenant schemas are discovered independently":
        "information_schema.schemata" in audit
        and "TENANT_SCHEMA_PATTERN" in audit,
    "serial quantity mixed and unknown schemas are classified":
        all(f'return "{family}"' in audit for family in (
            "serial", "quantity", "mixed", "unknown"
        )),
    "orphan and missing schemas are reported":
        "orphan_schemas" in audit and "missing_schemas" in audit,
    "inactive and non-serial company rows are visible":
        "inactive_company_count" in audit and "non_serial_companies" in audit,
    "schema structure is fingerprinted without exposing function bodies":
        '"fingerprint": _digest(' in audit
        and '"functions": functions' in audit
        and '"indexes": indexes' in audit
        and '"triggers": triggers' in audit
        and '"views": views' in audit,
    "tenant schema names are removed before structural comparison":
        "_canonicalize_schema_references" in audit
        and 'value.replace(schema_name, "<tenant_schema>")' in audit,
    "only the documented bootstrap debug view is excluded from comparison":
        'KNOWN_LEGACY_SERIAL_OBJECTS = {\n    "item_history_view": '
        in audit
        and '"ignored_known_legacy_objects": known_legacy_objects' in audit,
    "privacy-safe component hashes localize structural drift":
        '"component_fingerprints": {' in audit
        and "component: _digest(definition)" in audit,
    "serial schema drift fails readiness":
        "serial_structure_groups" in audit
        and "serial_structures_consistent" in audit,
    "company rows without schema names are reported":
        "blank_schema_companies" in audit,
    "business totals are emitted only as a digest":
        '"fingerprint": _digest(evidence)' in audit
        and '"journal_totals": [str(debit), str(credit)]' in audit,
    "readiness requires continuity evidence for every serial schema":
        "continuity_missing_schemas" in audit
        and 'row.get("continuity", {}).get("available", False)' in audit,
    "strict mode fails closed":
        "--strict-serial" in audit
        and 'raise CommandError("Phase 0 serial-only discovery did not pass")' in audit,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
print(f"{len(checks) - len(failed)}/{len(checks)} Phase 0 contracts passed")

if len(sys.argv) == 3 and sys.argv[1] == "--assert-known-ci-drift":
    report = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    empty_exception_fields = (
        "blank_schema_companies",
        "non_serial_companies",
        "orphan_schemas",
        "missing_schemas",
        "invalid_schemas",
        "unbalanced_schemas",
        "continuity_missing_schemas",
    )
    report_checks = {
        "CI report contains two registered physical serial schemas":
            report["company_count"] == 2
            and report["registered_schema_count"] == 2
            and report["physical_schema_count"] == 2
            and len(report["schemas"]) == 2,
        "CI report contains no registry schema or continuity exception":
            all(not report[field] for field in empty_exception_fields),
        f"both CI schemas are ready balanced serial version {EXPECTED_SCHEMA_VERSION}":
            all(
                row["classification"] == "serial"
                and row["registered_inventory_mode"] == "serial"
                and row["provisioning_state"] == "ready"
                and row["version"] == EXPECTED_SCHEMA_VERSION
                and row["continuity"]["journal_balanced"]
                for row in report["schemas"]
            ),
        "known CI drift is limited to stored-function definitions":
            [
                component
                for component in report["schemas"][0]["structure"][
                    "component_fingerprints"
                ]
                if len({
                    row["structure"]["component_fingerprints"][component]
                    for row in report["schemas"]
                }) > 1
            ] == ["functions"],
        "strict readiness failed closed on the known CI drift":
            not report["serial_structures_consistent"]
            and not report["ready_for_phase_1"],
    }
    report_failed = [name for name, ok in report_checks.items() if not ok]
    for name, ok in report_checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    failed.extend(report_failed)
elif len(sys.argv) != 1:
    print("usage: phase0_serial_only_discovery_contracts.py [--assert-known-ci-drift REPORT]")
    failed.append("invalid arguments")

raise SystemExit(1 if failed else 0)
