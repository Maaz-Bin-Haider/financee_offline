#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
backup = (ROOT / "deploy/backup_encrypted.sh").read_text()
restore = (ROOT / "deploy/restore_rehearsal.sh").read_text()
rehearsal = (ROOT / "tests/phase28_recovery_rehearsal.sh").read_text()
runbook = (ROOT / "PHASE28_RECOVERY_RUNBOOK.md").read_text()

checks = {
    "database custom dump": "pg_dump" in backup and "--format=custom" in backup,
    "database and media encrypted together":
        "database.dump media.tar" in backup and "aes-256-cbc" in backup,
    "bundle integrity recorded":
        "sha256sum database.dump media.tar manifest.txt" in backup,
    "corrupted bundle rejection rehearsed":
        "corrupted encrypted bundle rejected" in rehearsal,
    "unsafe restore projects rejected":
        "deploy|financee|production|prod" in restore,
    "restore checks bundle integrity": "sha256sum -c SHA256SUMS" in restore,
    "restore verifies all tenants": "release_preflight" in restore,
    "restore verifies media": "RESTORE_MEDIA_SENTINEL" in restore,
    "RTO measured": "RESTORE_RTO_SECONDS" in restore,
    "forward public migration rehearsed": "manage.py migrate --noinput" in rehearsal,
    "serial-only forward registry rehearsed":
        "Phase 28 Forward Serial" in rehearsal
        and "tenancy_company_valid_inventory_mode" in rehearsal,
    "old image compatibility rehearsed": "PHASE28_OLD_IMAGE" in rehearsal,
    "failed health rollback rehearsed": "phase27_rollback_simulation.sh" in rehearsal,
    "RPO documented": "RPO" in runbook and "created_at_utc" in runbook,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
print(f"{len(checks) - len(failed)}/{len(checks)} Phase 28 release gates passed")
raise SystemExit(1 if failed else 0)
