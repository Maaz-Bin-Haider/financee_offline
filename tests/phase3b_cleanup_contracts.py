#!/usr/bin/env python3
"""Database-free contracts for the explicitly invoked 3B maintenance candidate."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "tenancy/management/commands/serial_only_phase3_cleanup.py").read_text()
tree = ast.parse(source)
catalogue = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "PERMISSIONS" for t in n.targets))
# Checkpoint 4B deleted authentication migrations 0022-0025. Their exact
# catalogue is preserved in a frozen reference so this stays an independent
# cross-check rather than the cleanup tooling agreeing with itself.
import json as _json
historical = _json.loads(
    (ROOT / "tests/retired_permissions_reference.json").read_text()
)["permissions"]
apply = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply")
apply_source = ast.get_source_segment(source, apply)
summary = ast.get_source_segment(source, next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "summary"))
inspection = (ROOT / ".github/workflows/phase3b-cleanup-inspection.yml").read_text()
workflow = (ROOT / ".github/workflows/ci.yml").read_text()
checks = {
    "exact fourteen historical auth.user permissions": catalogue == historical and len(catalogue) == 14
        and "ct.app_label='auth' AND ct.model='user'" in source,
    "default command action is inspect": 'default="inspect"' in source,
    "inspection is repeatable-snapshot database read-only": "SET TRANSACTION READ ONLY" in source
        and "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" in source,
    "mutations need exact fingerprint and typed confirmation": "digest(value) == expected" in source
        and "confirmation == CONFIRMATIONS[action]" in source,
    "managed backup reference must be recent": "<= 1800" in source and "managed backup reference required" in source,
    "whole operation atomic with bounded SQL and lock waits": "with transaction.atomic():" in source
        and "lock_timeout='2s'" in source and "statement_timeout='30s'" in source,
    "lock and recheck targets before modifying them": "pg_try_advisory_xact_lock" in source
        and source.index("LOCK TABLE public.tenancy_company IN ACCESS EXCLUSIVE MODE") < source.index("value, stored = state(cursor)"),
    "guard full legacy column contract and exact dependencies":
        all(s in source for s in ('"character varying(16)"', "default_collation", "unexpected inventory-mode dependency", "pg_depend")),
    "reject side-effect triggers rules and row security": all(s in source for s in ("pg_trigger", "pg_rewrite", "relrowsecurity")),
    "reject unknown permission foreign-key dependencies": "unexpected permission foreign-key dependency" in source,
    "no tenant schema removal or cascading column removal": "DROP SCHEMA" not in source
        and "CASCADE" not in source and "DROP COLUMN inventory_mode RESTRICT" in source,
    "archive precedes deletion and is read back": apply_source.index("make_archive") < apply_source.index("DELETE FROM")
        and "archive round-trip mismatch" in source,
    "archive is private checksummed bounded and never dropped": "REVOKE ALL ON TABLE" in source
        and "archive checksum/state mismatch" in source and "1024 * 1024" in source and "DROP TABLE" not in source,
    "feature rewrite preserves order and skips unchanged lists": 'after = [k for k in original if k not in FEATURES]' in source
        and "if original != after:" in apply_source,
    "preservation checks cover unrelated metadata and serial feature values": 'data["preserved_features"]' in source
        and "preserved(cursor) == before" in source,
    "restore retains original permission and assignment IDs": "INSERT INTO public.auth_permission (id,content_type_id,codename,name)" in source
        and "grant[\"id\"]" in source and "SET CONSTRAINTS ALL IMMEDIATE" in source,
    "restore refuses to clobber changed feature settings": "changed/missing feature row would be overwritten by restore" in source,
    "inspection summary contains no grant assignees or company names": '"user_id"' not in summary and '"group_id"' not in summary
        and '"name"' not in summary and '"authorizes_cleanup": False' in summary,
    "startup never calls cleanup command": "serial_only_phase3_cleanup" not in (ROOT / "deploy/entrypoint.sh").read_text(),
    "standalone transport works in already-deployed Django image": 'if __name__ == "__main__":' in source
        and "django.setup()" in source and '"--strict"' in source,
    "inspection workflow is protected and cannot request a write action": "workflow_dispatch:" in inspection
        and "environment: production" in inspection and "group: production-deploy" in inspection
        and "< tenancy/management/commands/serial_only_phase3_cleanup.py" in inspection
        and "deploy/phase3_inventory_remote.sh" in inspection and "--confirmation APPLY" not in inspection,
    "contracted database regression is mandatory before publication": "cleanup-rehearsal-gate:" in workflow
        and workflow.count("compatibility-gate, cleanup-rehearsal-gate,") == 2
        and "python3 tests/phase3_recovery_local.py --cleanup-test" in workflow,
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
print(f"{sum(checks.values())}/{len(checks)} Phase 3B cleanup contracts passed")
raise SystemExit(0 if all(checks.values()) else 1)
