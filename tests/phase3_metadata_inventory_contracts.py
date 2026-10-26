#!/usr/bin/env python3
"""Database-free safety contracts for Phase 3's inventory-only release."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "tenancy/management/commands/serial_only_phase3_audit.py").read_text()
remote = (ROOT / "deploy/phase3_inventory_remote.sh").read_text()
workflow = (ROOT / ".github/workflows/phase3-production-inventory.yml").read_text()
ci = (ROOT / ".github/workflows/ci.yml").read_text()
stack = (ROOT / "tests/ci_phase27_stack.sh").read_text()
tree = ast.parse(source)
# Inspect executable SQL arguments, not labels such as "Can update quantity
# warehouses" in the immutable historical permission catalogue.
literals = "\n".join(part.value.upper()
                     for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                     and node.func.attr == "execute" and node.args
                     for part in ast.walk(node.args[0])
                     if isinstance(part, ast.Constant) and isinstance(part.value, str))
calls = {node.func.attr for node in ast.walk(tree)
         if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
catalogue = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "RETIRED_PERMISSIONS"
                         for target in node.targets))
# Checkpoint 4B deleted authentication migrations 0022-0025. Their exact
# catalogue is preserved in a frozen reference so this stays an independent
# cross-check rather than the audit tooling agreeing with itself.
import json as _json
historical = _json.loads(
    (ROOT / "tests/retired_permissions_reference.json").read_text()
)["permissions"]

checks = {
    "repeatable consistent snapshot is forced read-only":
        'cursor.execute("SET TRANSACTION READ ONLY")' in source
        and "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" in source,
    "read-only status is verified before inventory":
        'cursor.execute("SHOW transaction_read_only")' in source,
    "no ORM mutator calls or mutation SQL":
        not calls.intersection({"save", "create", "update", "delete", "bulk_create"})
        and not any(token in literals for token in (
            "INSERT INTO", "UPDATE ", "DELETE FROM", "DROP ", "ALTER ", "TRUNCATE ",
            "CREATE TABLE", "CREATE SCHEMA",
        )),
    "statement and lock waits are bounded":
        "1 <= timeout <= 120" in source and "lock_timeout', '2s'" in source,
    "all companies and physical schemas are independently inspected":
        "FROM public.tenancy_company ORDER BY id" in source
        and "FROM pg_namespace" in source,
    "public metadata reads do not depend on ORM migration state":
        "from tenancy.models" not in source and "information_schema.columns" in source,
    "permission allowlist exactly matches all 14 historical quantity seeds":
        catalogue == historical and len(catalogue) == 14,
    "other content types are preserved and direct/group grant counts are inventoried":
        '(app, model) != ("auth", "user")' in source
        and "public.auth_user_user_permissions" in source
        and "public.auth_group_permissions" in source,
    "custom permission labels and unknown legacy feature keys require review":
        "seed_label_matches" in source and "unclassified_legacy_key_count" in source,
    "shared setup is preserved and represented by a digest":
        '"shared_setup_fingerprint": digest(setup)' in source
        and '"shared_setup_columns_preserved": ["base_currency_id", "tax_environment"]' in source,
    "column dependencies are inventoried without exporting definitions":
        "FROM pg_depend" in source and '"identity_fingerprint": digest(identity)' in source,
    "audit success never authorizes cleanup or direct column removal":
        '"authorizes_cleanup": False' in source
        and '"requires_compatibility_release_before_column_drop": True' in source,
    "production wrapper accepts explicitly empty optional app directory":
        'app_dir=${1?' in remote and 'app_dir=${1:?' not in remote,
    "production wrapper pins expected image and ARM64 before executing audit":
        '[[ "$actual_image" == "$expected_image" ]]' in remote
        and "{{.Architecture}}" in remote and "== arm64" in remote,
    "production wrapper checks unchanged container/image and health afterward":
        'ps -q web)" == "$web_id"' in remote
        and '== "$image_id"' in remote and 'PHASE3_PRODUCTION_CONTAINER_UNCHANGED=yes' in remote,
    "production wrapper uses read-only sessions for inventory and continuity":
        remote.count("PGOPTIONS=-c default_transaction_read_only=on") == 2
        and "--include-continuity" in remote and "--strict-serial" in remote,
    "production operation does not mutate checkout or Docker resources":
        not any(token in remote for token in (
            "git pull", "git checkout", "docker pull", "docker run", "docker cp",
            " up ", " down ", " restart ", " prune ", " migrate", "rm ", "mkdir ",
        )),
    "protected manual-only workflow shares production deploy concurrency":
        "workflow_dispatch:" in workflow and "  push:" not in workflow
        and "environment: production" in workflow and "group: production-deploy" in workflow
        and "contents: read" in workflow,
    "audit source is streamed from the exact workflow checkout":
        '"$GITHUB_SHA"' in workflow and "< tenancy/management/commands/serial_only_phase3_audit.py" in workflow,
    "new inventory checks are wired into mandatory CI":
        "phase3_metadata_inventory_contracts.py" in ci
        and "metadata-inventory-gate:" in ci
        and "phase3_metadata_inventory.py" in stack,
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
print(f"{sum(checks.values())}/{len(checks)} Phase 3 inventory contracts passed")
raise SystemExit(0 if all(checks.values()) else 1)
