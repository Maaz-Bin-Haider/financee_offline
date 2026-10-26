#!/usr/bin/env python3
"""Fail-closed contracts for the production Phase 0 recovery rehearsal."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "deploy/phase0_post_cleanup_recovery_gate.sh").read_text()
RESTORE = (ROOT / "deploy/restore_database_backup_rehearsal.sh").read_text()
OVERRIDE = (ROOT / "deploy/docker-compose.phase0-recovery.yml").read_text()
WORKFLOW = (
    ROOT / ".github/workflows/verify-phase0-production-recovery.yml"
).read_text()

checks = {
    "manual workflow only": "workflow_dispatch:" in WORKFLOW and "push:" not in WORKFLOW,
    "production approval required": "environment: production" in WORKFLOW,
    "exact confirmation required": "VERIFY-PHASE0-POST-CLEANUP-RESTORE" in SCRIPT and "VERIFY-PHASE0-POST-CLEANUP-RESTORE" in WORKFLOW,
    "workflow source SHA pinned": "rev-parse HEAD" in WORKFLOW and "expected_sha" in WORKFLOW,
    "root required for protected backup files": '[[ "$(id -u)" == "0" ]]' in SCRIPT,
    "host capacity is gated": "MemAvailable" in SCRIPT and "disk_available_kb" in SCRIPT,
    "capacity values are evidenced": "PHASE0_RECOVERY_HOST_AVAILABLE_MEMORY_KB" in SCRIPT and "PHASE0_RECOVERY_DOCKER_AVAILABLE_KB" in SCRIPT,
    "recovery cannot pull missing images": 'docker image inspect "$required_image"' in SCRIPT,
    "one GiB disk margin remains": '"$disk_available_kb" -ge 1048576' in SCRIPT,
    "production strict before backup": SCRIPT.index("production-before.json") < SCRIPT.index("systemctl start financee-db-backup.service"),
    "new remote backup required": "Backup release predates this recovery operation" in SCRIPT,
    "restore project has safe prefix": "dbbackup_rehearsal_phase0_" in SCRIPT and "dbbackup_rehearsal_" in RESTORE,
    "ephemeral credentials generated": "openssl rand" in SCRIPT and "mktemp -d" in SCRIPT,
    "recovery is resource limited": 'memory: 768M' in OVERRIDE and 'memory: 512M' in OVERRIDE and 'memory: 64M' in OVERRIDE,
    "restore uses exact managed script": "bash restore_database_backup_rehearsal.sh" in SCRIPT,
    "restored strict audit required": SCRIPT.index("RESTORE_RESULT=PASS") < SCRIPT.index("restored-phase0.json"),
    "disposable volumes removed exactly": '"${restore_compose[@]}" down -v' in SCRIPT and "docker volume prune" not in SCRIPT,
    "production strict after cleanup": "production-after.json" in SCRIPT,
    "production env reset after restore": 'export WEB_ENV_FILE="$production_env_file"' in SCRIPT and SCRIPT.index('export WEB_ENV_FILE="$production_env_file"') > SCRIPT.index('"${restore_compose[@]}" down -v'),
    "production serial preflight required": "release_preflight" in SCRIPT and "--require-family serial" in SCRIPT,
    "production HTTP check required": "http://localhost/authentication/login/" in SCRIPT,
    "workflow retains evidence": "retention-days: 90" in WORKFLOW,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if failed:
    raise SystemExit(f"{len(failed)} recovery contract(s) failed")
print(f"Phase 0 recovery contracts: {len(checks)}/{len(checks)} passed")
