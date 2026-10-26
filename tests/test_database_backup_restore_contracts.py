#!/usr/bin/env python3
"""Static restore and runbook contracts for daily DB backups."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    restore = (
        ROOT / "deploy/restore_database_backup_rehearsal.sh"
    ).read_text()
    runbook = (ROOT / "DATABASE_BACKUP_GITHUB_RUNBOOK.md").read_text()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    compose = (ROOT / "deploy/docker-compose.yml").read_text()
    checks = {
        "unsafe production projects rejected":
            "deploy|financee|production|prod|financee_production" in restore,
        "isolated project prefix required": "dbbackup_rehearsal_" in restore,
        "isolated web receives restore credentials":
            'export WEB_ENV_FILE="$RESTORE_ENV_FILE"' in restore and
            "env_file: ${WEB_ENV_FILE:-.env}" in compose,
        "inherited database credentials cannot override the isolated restore":
            "unset DB_NAME DB_USER DB_PASSWORD DB_HOST DB_PORT" in restore,
        "ciphertext sidecar verified": "sha256sum -c" in restore,
        "bundle decrypted": "openssl enc -d" in restore,
        "internal checksums verified": "sha256sum -c SHA256SUMS" in restore,
        "DB-only format enforced": "financee-db-backup-v1" in restore,
        "archive catalogue checked": "pg_restore --list" in restore,
        "clean isolated restore":
            "--clean --if-exists --no-owner --no-acl" in restore,
        "schema count compared":
            "restored_schema_count" in restore and "expected_schema_count" in restore,
        "all tenants preflighted": "manage.py release_preflight" in restore,
        "restored report worker is muted and health checked":
            'REPORT_EMAIL_ENABLED: "False"' in restore
            and 'manage.py run_report_scheduler --health' in restore,
        "restore RTO recorded": "RESTORE_RTO_SECONDS" in restore,
        "isolated volumes removed by default": 'down -v' in restore,
        "runbook names exact private repository":
            "Maaz-Bin-Haider/financee_pk_backup" in runbook,
        "runbook distinguishes DB-only from media": "does not include uploaded" in runbook,
        "runbook gates timer on restore": "Do not enable the timer until" in runbook,
        "CI includes DB backup contracts":
            "tests/database_backup_contracts.py" in workflow and
            "tests/test_database_backup_retention.py" in workflow and
            "tests/test_database_backup_operations.py" in workflow and
            "tests/test_database_backup_restore_contracts.py" in workflow,
    }
    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"{len(checks) - len(failed)}/{len(checks)} restore checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
