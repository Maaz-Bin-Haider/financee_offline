#!/usr/bin/env python3
"""Database-free preservation and release-wiring contracts for checkpoint 3A."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(path):
    return (ROOT / path).read_text()

model = read("tenancy/models.py")
squashed = read("tenancy/migrations/0001_serial_only.py")
workflow = read(".github/workflows/ci.yml")
stack = read("tests/ci_phase27_stack.sh")
live = read("tests/phase3a_compatibility.py")
# Checkpoint 4B retired tests/phase3a_old_image.py with the Phase 2 image it
# pinned: that image declares inventory_mode as a concrete ORM field and
# cannot run against a 4B database. Rollback compatibility is now proven
# against the actual rollback target by the 4B transition proof.
transition = read("tests/phase4b_migration_transition.sh")
recovery = read("tests/phase28_recovery_rehearsal.sh")
company = next(n for n in ast.parse(model).body if isinstance(n, ast.ClassDef) and n.name == "Company")
concrete = {t.id for n in company.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
query_dependencies = []
query_sources = [path for path in (ROOT / "tenancy").rglob("*.py") if "migrations" not in path.parts]
query_sources += [ROOT / path for path in (
    "tests/ci_bootstrap.py", "tests/test_http.py", "tests/suite/test_attachments.py",
    "tests/phase2_serial_runtime_removal.py",
)]
for path in query_sources:
    for node in ast.walk(ast.parse(path.read_text())):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"filter", "exclude", "update", "values", "values_list", "only", "defer", "order_by"}):
            names = [kw.arg for kw in node.keywords if kw.arg]
            names += [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
            if any(name.lstrip("-").split("__")[0] == "inventory_mode" for name in names):
                query_dependencies.append(f"{path.relative_to(ROOT)}:{node.lineno}")
checks = {
    "inventory mode is no longer a concrete Company field": "inventory_mode" not in concrete,
    "checkpoint 4B removed the replaced migrations and the replaces marker":
        sorted(p.name for p in (ROOT / "tenancy/migrations").glob("*.py"))
        == ["0001_serial_only.py", "__init__.py"]
        and sorted(p.name for p in (ROOT / "authentication/migrations").glob("*.py"))
        == ["0001_serial_only.py", "__init__.py"]
        and "initial = True" in squashed
        and "replaces = [" not in squashed,
    "the squashed migration cannot create the retired column":
        "inventory_mode" not in squashed.split("operations = [", 1)[1]
        and "quantity" not in squashed.split("operations = [", 1)[1].lower(),
    "temporary 3A compatibility API is fully retired":
        "def get_inventory_mode_display(self)" not in model
        and "_requested_inventory_mode" not in model
        and "class CompanyQuerySet" not in model,
    "no supported path can express a retired mode":
        "inventory_mode" not in model and "INVENTORY_MODE" not in model,
    "live test proves the retired keyword is rejected at construction":
        "retired_mode_rejected" in live and "construction rejects" in live,
    "shared currency tax and provisioning constraints remain":
        all(name in concrete for name in ("base_currency", "tax_environment", "provisioning_state", "disabled_features"))
        and "tenancy_company_valid_tax_environment" in model and "tenancy_company_valid_provisioning_state" in model,
    "existing serial SQL rollout no longer filters an ORM legacy column":
        "inventory_mode=" not in read("tenancy/management/commands/apply_sql_all_tenants.py"),
    "runtime and active test discovery have no legacy ORM-column query": not query_dependencies,
    "continuity audit handles legacy-column presence and absence explicitly":
        "has_legacy_mode" in read("tenancy/management/commands/serial_only_phase0_audit.py")
        and "legacy_modes.get" in read("tenancy/management/commands/serial_only_phase0_audit.py"),
    "the live proof is restricted to disposable stacks":
        'PHASE3A_TEST_DISPOSABLE' in live
        # The live proof no longer performs destructive DDL, so it cleans up its
        # own fixtures explicitly instead of relying on transaction rollback.
        and "DROP SCHEMA IF EXISTS" in live
        and "finally:" in live,
    "rollback compatibility is proven against the actual rollback target":
        not (ROOT / "tests/phase3a_old_image.py").exists()
        and "phase3a_old_image" not in stack
        and "before pruning, rolling back to 4A applies no migration" in transition
        and "before pruning, rolling back to 3A applies no migration" in transition,
    "live proof asserts no application SQL touches the retired column":
        "CaptureQueriesContext" in live
        and "queries.captured_queries" in live
        and "no_retired_mode_attribute(company)" in live
        and "the retired column is absent from the registry" in live,
    "compatibility is mandatory for staging and publication":
        workflow.count("metadata-inventory-gate, compatibility-gate,") == 2,
    "ARM64 executes new compatibility tests":
        "phase3a_compatibility.py" in stack.split("  arm64)", 1)[1].split("  full)", 1)[0],
    "recovery rollback targets the 4A release and rebuilds the real history":
        # Checkpoint 4B deleted the replaced migration files, so no pre-4A image
        # recognises a 4B database: Django drops a replacement from
        # applied_migrations when the migrations it replaces are absent. The
        # rollback target is therefore the 4A release, and the estate must be
        # seeded through 3A and 4A so it retains the replaced rows that make a
        # rollback possible at all.
        'old_image="${PHASE28_OLD_IMAGE:-ghcr.io/maaz-bin-haider/financee-web:a4f915f3e771d0769f410a3d9ee0cdb7bbc1cd00}"'
        in recovery
        and "seed_3a_image=" in recovery
        and "Seeding the estate through the 3A and 4A releases" in recovery
        and "tenant_schema_version" in recovery,
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if query_dependencies:
    print("Legacy query dependencies: " + ", ".join(query_dependencies))
print(f"{sum(checks.values())}/{len(checks)} Phase 3A contracts passed")
raise SystemExit(0 if all(checks.values()) else 1)
