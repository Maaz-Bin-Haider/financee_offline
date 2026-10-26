#!/usr/bin/env python3
"""Database-free contracts for the Phase 4 entry gate and transition plan."""
import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


audit = read("tenancy/management/commands/serial_only_phase4_audit.py")
wrapper = read("deploy/phase4_inventory_remote.sh")
workflow = read(".github/workflows/phase4-migration-leaf-inspection.yml")
plan = read("SERIAL_ONLY_REMOVAL_PLAN.md")
postgres_fixture = read("tests/phase3b_cleanup.py")
compat = read("tests/serial_api_compat.py")
recovery_local = read("tests/phase3_recovery_local.py")
suite_runner = read("tests/suite/run_all.py")
ci = read(".github/workflows/ci.yml")
project_context = read("PROJECT_CONTEXT.md")
readme = read("README.md")
claude_md = read("CLAUDE.md")
transition_proof = read("tests/phase4b_migration_transition.sh")
bootstrap_sql = read("build_multitenant_db.sql")
entrypoint_sh = read("deploy/entrypoint.sh")
bootstrap_command = read(
    "tenancy/management/commands/register_bootstrap_tenant.py")

RETIRED_PATHS = (
    "deploy/retire_quantity_static.py",
    "tests/test_phase2_static_retirement.py",
    "tests/phase26_performance_capacity.py",
    "ARCHITECTURE_QUANTITY_COMPANY.md",
    "SRS_QUANTITY_BASED_COMPANY.md",
    "IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md",
    "REQUIREMENTS_TRACEABILITY_QUANTITY_COMPANY.md",
)
PRESERVED_PATHS = (
    "tenancy/management/commands/serial_only_phase3_cleanup.py",
    "tenancy/management/commands/serial_only_phase3_audit.py",
    "PHASE3B_MAINTENANCE_RUNBOOK.md",
    ".github/workflows/phase3b-controlled-cleanup.yml",
    "tenancy/sql/tenant_template.sql",
    "tenancy/sql/production_hardening.sql",
    "tests/phase26_capacity_preflight.py",
)
# Modules the Phase 3 recovery gate runs inside the *previously published*
# image; each must tolerate both application shapes.
DUAL_IMAGE_MODULES = (
    "tests/suite/test_company_metadata.py",
    "tests/phase1_serial_only_creation.py",
    "tests/phase2_serial_runtime_removal.py",
    "tests/phase24_serial_matrix.py",
    "tests/phase25_four_company_isolation.py",
)
audit_tree = ast.parse(audit)
audit_sql = []
for node in ast.walk(audit_tree):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        continue
    if node.func.attr != "execute" or not node.args:
        continue
    value = node.args[0]
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        audit_sql.append(value.value)
    elif isinstance(value, ast.JoinedStr):
        audit_sql.append("".join(
            part.value for part in value.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        ))

checks = {
    "audit forces repeatable read-only transaction": (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" in audit
        and "SET TRANSACTION READ ONLY" in audit
    ),
    "audit SQL contains no write or DDL statement": (
        bool(audit_sql)
        and all(statement.lstrip().upper().startswith(("SELECT", "SET"))
                for statement in audit_sql)
    ),
    "the exact historical leaf names remain the basis of every state": (
        '"0009_inventory_mode_compatibility"' in audit
        and '"0025_add_quantity_platform_permissions"' in audit
        and 'if state == "pre-4A":\n        return TENANCY_MIGRATIONS, AUTHENTICATION_MIGRATIONS'
        in audit
        and "classify_history(" in audit
    ),
    "post-cleanup column permissions and features must be absent": (
        "retired inventory_mode column is present" in audit
        and "retired quantity permissions remain" in audit
        and "retired feature keys remain" in audit
    ),
    "reversal archive must remain applied and checksummed": (
        "Phase 3B reversal archive is absent" in audit
        and "archive_rows[0][2] == \"applied\"" in audit
        and 're.fullmatch(r"[0-9a-f]{64}"' in audit
        and "ARCHIVE_MARKER" in audit
    ),
    "only canonical active ready serial schemas pass": (
        "company registry is not canonical active ready serial-only" in audit
        and "tenant schema registry drift exists" in audit
        and "retired quantity-family schema detected" in audit
        and "strpos(nspname, 'tenant_company_') = 1" in audit
        and "to_regclass(quote_ident(%s)" in audit
    ),
    "audit output explicitly authorizes nothing": (
        '"authorizes_migration_replacement": False' in audit
        and "PHASE4_REPLACEMENT_AUTHORIZED=no" in wrapper
    ),
    "remote transport pins exact healthy ARM64 image": (
        "expected_deployed_sha" in wrapper
        and "deployed image mismatch" in wrapper
        and "web is not healthy" in wrapper
        and "image is not ARM64" in wrapper
    ),
    "remote database sessions are independently forced read-only": (
        wrapper.count("PGOPTIONS=-c default_transaction_read_only=on") == 2
        and "serial_only_phase0_audit --include-continuity" in wrapper
    ),
    "container and image are unchanged after inspection": (
        "web container changed during inspection" in wrapper
        and "web image changed during inspection" in wrapper
        and "PHASE4_PRODUCTION_CONTAINER_UNCHANGED=yes" in wrapper
    ),
    "workflow is manual protected and serialized with deployments": (
        "workflow_dispatch:" in workflow
        and "environment: production" in workflow
        and "group: production-deploy" in workflow
        and "contents: read" in workflow
    ),
    "workflow transports only read-only audit source": (
        "INSPECT-PHASE4-MIGRATION-LEAVES" in workflow
        and "serial_only_phase4_audit.py" in workflow
        and "phase4_inventory_remote.sh" in workflow
        and "--action apply" not in workflow
    ),
    "two-release Django migration transition is mandatory": (
        "Checkpoint 4A" in plan
        and "Checkpoint 4B" in plan
        and "old migration files remain" in plan
        and "remove `replaces`" in plan
    ),
    "4A: every retired quantity-family artifact is gone": (
        all(not (ROOT / path).exists() for path in RETIRED_PATHS)
        and not any((ROOT / "tenancy/sql").glob("quantity_*.sql"))
        and not any((ROOT / "tests/suite").glob("test_quantity_*.py"))
        and not any((ROOT / "tests").glob("PHASE*QUANTITY*_RESULTS.md"))
    ),
    "4A: the reversal path is preserved": (
        all((ROOT / path).exists() for path in PRESERVED_PATHS)
    ),
    "4B: the replaced migration files are removed and replaces is gone": (
        sorted(p.name for p in (ROOT / "tenancy/migrations").glob("*.py"))
        == ["0001_serial_only.py", "__init__.py"]
        and sorted(p.name for p in (ROOT / "authentication/migrations").glob("*.py"))
        == ["0001_serial_only.py", "__init__.py"]
        and "replaces = [" not in read("tenancy/migrations/0001_serial_only.py")
        and "replaces = [" not in read("authentication/migrations/0001_serial_only.py")
        and "initial = True" in read("tenancy/migrations/0001_serial_only.py")
        and "initial = True" in read("authentication/migrations/0001_serial_only.py")
    ),
    "4B: the retired permission catalogue keeps an independent cross-reference": (
        (ROOT / "tests/retired_permissions_reference.json").exists()
        and len(json.loads(
            read("tests/retired_permissions_reference.json"))["permissions"]) == 14
        and "retired_permissions_reference.json" in read(
            "tests/phase3b_cleanup_contracts.py")
        and "retired_permissions_reference.json" in read(
            "tests/phase3_metadata_inventory_contracts.py")
    ),
    "4A: no source or test references a deleted module or symbol": (
        "retire_quantity_static" not in read("deploy/entrypoint.sh")
        and "test_phase2_static_retirement" not in ci
        and "test_quantity_" not in suite_runner
        and "phase26_performance_capacity" not in ci
    ),
    "4A: dual-image modules use the version-adaptive compatibility shim": (
        all("serial_api_compat" in read(path) for path in DUAL_IMAGE_MODULES)
        and "tests/suite/run_all.py" in recovery_local
        and "RETIRED_API_PRESENT" in compat
        and "Delete this module in checkpoint 4B" in compat
    ),
    "4A: the shim covers both rejection shapes without weakening either": (
        "except TypeError:" in compat
        and "except ValidationError:" in compat
        and "return False" in compat
    ),
    "active documentation describes the completed serial-only system": (
        "Retired Quantity-Company Family" in project_context
        and "STATUS: COMPLETE" in project_context
        and "Do not reintroduce an inventory-mode concept" in claude_md
        and "There is no inventory-mode concept left to configure" in readme
    ),
    "the migration rules future work must know are documented": (
        # Not "one-way": checkpoint 4C proved the prune reversible via its
        # archive. The rule that matters is that a rollback attempted after a
        # prune corrupts the history rather than failing cleanly.
        "a rollback attempted afterwards corrupts the" in project_context
        and "Prune is per-app" in project_context
        and "no pre-4B rollback path" in project_context
        and "serial_only_phase4c_prune --action restore" in project_context
    ),
    "4A: documentation still warns that serial line quantities are not the family": (
        'ordinary word "quantity" is not by itself' in project_context
        and 'ordinary word "quantity" is *not* evidence' in claude_md
    ),
    "4B: the superseded 4A proof retired with the coexisting originals": (
        not (ROOT / "tests/phase4a_migration_proof.sh").exists()
        and "migration-replacement-gate:" not in ci
    ),
    "4B: the transition proof guards the unsupported skip-4A upgrade": (
        "a database on the original chain cannot skip the 4A release"
        in transition_proof
    ),
    "4A: the bootstrap no longer defeats the tenancy squash": (
        "CREATE TABLE IF NOT EXISTS public.tenancy_company" not in bootstrap_sql
        and "'tenancy', '0001_initial'" not in bootstrap_sql
        and "register_bootstrap_tenant" in entrypoint_sh
        and "Company.objects.exists()" in bootstrap_command
    ),
    "the audit discovers its migration history instead of being pinned": (
        'HISTORY_STATES = ("pre-4A", "post-4A", "pruned")' in audit
        and "def classify_history(" in audit
        and "check_replacements" in audit
        and '"--expect-state", choices=HISTORY_STATES, default=None' in audit
        and '"authorizes_replaced_file_removal": False,' in audit
    ),
    "the audit fails closed on any unrecognised migration history": (
        "history_state is not None," in audit
        and "matches no recognised state" in audit
        and "not the asserted" in audit
    ),
    "each recognised history state is defined exactly": (
        "TENANCY_MIGRATIONS + (REPLACEMENT,)" in audit
        and "AUTHENTICATION_MIGRATIONS + (REPLACEMENT,)" in audit
        and 'if state == "pruned":' in audit
    ),
    "the remote wrapper validates and forwards an optional assertion": (
        "expect_state=${4:-}" in wrapper
        and '""|pre-4A|post-4A|pruned) ;;' in wrapper
        and "invalid expected history state" in wrapper
        and '${expect_state:+--expect-state "$expect_state"}' in wrapper
        and "PHASE4_EXPECT_STATE=%s" in wrapper
    ),
    "the workflow derives the deployed SHA instead of hard-coding it": (
        "497b6650ed678bc462f85de6bff14692bffd6ace" not in workflow
        and "a4f915f3e771d0769f410a3d9ee0cdb7bbc1cd00" not in workflow
        and "inputs.expected_deployed_sha || github.sha" in workflow
        and "git merge-base --is-ancestor" in workflow
        and "fetch-depth: 0" in workflow
        and "%q %q %q %q" in workflow
    ),
    "the real PostgreSQL fixture proves all three states and drift": (
        'history_state"] == "pre-4A"' in postgres_fixture
        and 'history_state"] == "post-4A"' in postgres_fixture
        and 'history_state"] == "pruned"' in postgres_fixture
        and "_state_refused(" in postgres_fixture
        and "_discovery_refused()" in postgres_fixture
        and "all three recognised histories produce distinct digests" in postgres_fixture
    ),
    "4B: the transition proof exists and is a mandatory CI gate": (
        (ROOT / "tests/phase4b_migration_transition.sh").exists()
        and "migration-transition-gate:" in ci
        and "tests/phase4b_migration_transition.sh" in ci
    ),
    "4B: the transition proof covers prune and rollback safety fail-closed": (
        "fresh install creates no retired column" in transition_proof
        and "prune leaves only the two squashed migration records" in transition_proof
        and "before pruning, rolling back to 4A applies no migration" in transition_proof
        and "after pruning, rolling back to 4A is refused by the database" in transition_proof
        and 'exit "$FAILED"' in transition_proof
    ),
    "4B: pruning is never automated anywhere in the deployment path": (
        "--prune" not in read("deploy/entrypoint.sh")
        and "--prune" not in read("deploy/deploy_pull.sh")
        and "--prune" not in ci.split("migration-transition-gate:", 1)[0]
    ),
    "real PostgreSQL cleanup fixture executes the Phase 4 audit": (
        "phase4_audit.inspect()" in postgres_fixture
        and "Phase 4 entry audit accepts exact post-cleanup migration and serial state"
        in postgres_fixture
    ),
}

for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
raise SystemExit(0 if all(checks.values()) else 1)
