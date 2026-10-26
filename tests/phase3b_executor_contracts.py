#!/usr/bin/env python3
"""Database-free wiring and safety contracts for attended Phase 3B execution."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
read = lambda p: (ROOT / p).read_text()
source = read("deploy/phase3b_cleanup_remote.py")
bundle = read("deploy/phase3b_cleanup_bundle.py")
recovery = read("deploy/phase3_recovery_remote.py")
workflow = read(".github/workflows/phase3b-controlled-cleanup.yml")
ci = read(".github/workflows/ci.yml")
execute = source.split("def execute(", 1)[1].split("def main(", 1)[0]
remote_step = workflow.split("      - name: Stream approved operation", 1)[1]
checks = {
    "guarded metadata core is pinned to the exact candidate requiring new inspection":
        hashlib.sha256((ROOT / "tenancy/management/commands/serial_only_phase3_cleanup.py").read_bytes()).hexdigest()
        == "9699731c843b02c213c99cb4efaa8c79d75dcd6c7fb3752d0b03816b876a1a00"
        and "unexpected permission/assignment table columns" in read("tenancy/management/commands/serial_only_phase3_cleanup.py")
        and "unexpected assignment/archive foreign-key dependency" in read("tenancy/management/commands/serial_only_phase3_cleanup.py")
        and "unexpected feature-list foreign-key dependency" in read("tenancy/management/commands/serial_only_phase3_cleanup.py"),
    "core checksum and exact source/image identities are required": "CORE_SHA256" in source
        and "expected_sha == recovery.ROLLBACK_SHA" in source and "Invocation/source SHA mismatch" in bundle,
    "operation requires exact action confirmation and state digest":
        'confirmation == CONFIRMATIONS[action]' in source and 'initial["state_sha256"] == expected_state' in source,
    "reviewed state input has no workflow default": 'expected_state_sha256:' in workflow
        and "default:" not in workflow.split("      expected_state_sha256:")[1].split("      expected_deployed_sha:")[0],
    "one-hour UTC window and attending recovery owner required": "<= 3600" in source
        and "remaining=120" in source and "Named attended rollback owner required" in source,
    "root and shared recovery host lock required": "os.geteuid() == 0" in source
        and "recovery.LOCK_FILE.open" in source and "fcntl.LOCK_EX | fcntl.LOCK_NB" in source,
    "existing host helper checksums and capacity checks retained": "recovery.HOST_HASHES.items()" in source
        and execute.count("recovery.capacity()") == 2,
    "new remotely verified backup precedes disposable rehearsal":
        execute.index("recovery.fresh_backup(evidence)") < execute.index("recovery.restore("),
    "rehearsal finishes and resources are removed before production mutation":
        execute.index("recovery.restore(") < execute.index('"production-mutation"')
        and "no_resources(project)" in recovery,
    "real restored data exercises action reverse action and actual image startup":
        "enumerate((action, reverse, action))" in source and '"--force-recreate"' in source
        and "Published image startup changed cleanup state" in source,
    "rehearsal explicitly rejects production project and container":
        "Rehearsal project is not uniquely isolated" in source and "Refusing production container as rehearsal target" in source,
    "unchanged and healthy production identity rechecked before mutation":
        'recovery.snapshot(compose, expected_sha) == before' in execute,
    "state is rechecked after rehearsal and by core under transaction locks":
        'immediate["state_sha256"] == expected_state' in source
        and 'expected=expected_state, release=release' in source,
    "write worker deadline is inside container and connections close":
        "signal.alarm(90)" in source and "connections.close_all()" in source and '"PGCONNECT_TIMEOUT=10"' in source,
    "uncertain write status is durable before sending mutation":
        execute.index('status["mutation_outcome"] = "unknown"') < execute.index('"production-mutation"')
        and "os.fsync" in source,
    "no automatic reversal or mutation retry in production orchestration":
        execute.count('"production-mutation"') == 1 and 'action="restore"' not in execute,
    "metadata continuity container and HTTP checks attempted after failure":
        "finally:\n        checks = final_review" in source
        and all('("'+name+'", lambda:' in source for name in ("containers", "metadata", "continuity", "http")),
    "business-balance equality is required only on isolated restored data":
        "include_balances=True" in source.split("def rehearse(")[1].split("def http_check(")[0]
        and "include_balances=True" not in execute,
    "raw logs and attending owner remain private on host": 'log=evidence /' in source
        and 'evidence.mkdir(mode=0o700' in source and '"rollback_owner": owner' not in source.split('status = {')[1].split('record(')[0],
    "bundle streams source without host checkout or container file copy":
        '"sources": payload' in bundle and 'types.ModuleType' in bundle
        and not any(s in remote_step for s in ("git pull", "docker pull", "docker cp", "deploy_pull")),
    "manual protected workflow shares deploy concurrency":
        "workflow_dispatch:" in workflow and "  push:" not in workflow
        and "environment: production" in workflow and "group: production-deploy" in workflow,
    "runner rehearsal gates protected production maintenance":
        "needs: rehearsal" in workflow and "tests/phase3_recovery_local.py --executor-test" in workflow
        and "tests/phase3_recovery_local.py --cleanup-test" in workflow,
    "executor unit and static checks are mandatory in CI":
        "tests.test_phase3b_cleanup_remote" in ci and "tests/phase3b_executor_contracts.py" in ci,
    "CI rehearses cleanup executor before existing publication gate":
        "python3 tests/phase3_recovery_local.py --executor-test" in ci
        and ci.count("compatibility-gate, cleanup-rehearsal-gate,") == 2,
    "legacy recovery keeps its original default audit path":
        "if verifier is None:" in recovery and '"serial_only_phase3_audit", ["--strict"]' in recovery,
    "success requires owner manual verification and no phase auto-advance":
        "PHASE3B_OWNER_MANUAL_CHECK_REQUIRED=yes" in source,
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
print(f"{sum(checks.values())}/{len(checks)} Phase 3B executor contracts passed")
raise SystemExit(0 if all(checks.values()) else 1)
