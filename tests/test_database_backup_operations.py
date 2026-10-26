#!/usr/bin/env python3
"""Static contracts for scheduling and operating DB backups."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


def main():
    runner = (DEPLOY / "run_database_backup.sh").read_text()
    service = (DEPLOY / "financee-db-backup.service.example").read_text()
    timer = (DEPLOY / "financee-db-backup.timer.example").read_text()
    installer = (DEPLOY / "install_database_backup_timer.sh").read_text()
    status = (DEPLOY / "database_backup_status.sh").read_text()
    checks = {
        "runner requires encrypted backup then upload":
            runner.index("backup_database_encrypted.sh") <
            runner.index("upload_database_backup_github.sh"),
        "runner requires remote verification before state":
            runner.index("GITHUB_BACKUP_REMOTE_VERIFIED=true") <
            runner.index("LAST_SUCCESS_UTC"),
        "runner retains only one local encrypted copy":
            runner.count("find \"$BACKUP_DEST\"") == 2 and "-delete" in runner,
        "service is one-shot": "Type=oneshot" in service,
        "service references protected environment":
            "EnvironmentFile=/etc/financee-backup/github.env" in service,
        "service never restarts application":
            "docker compose" not in service and "restart" not in service.lower(),
        "service has bounded runtime and low priority":
            "TimeoutStartSec=4h" in service and "Nice=10" in service,
        "timer runs daily in UTC":
            "OnCalendar=*-*-* 02:15:00 UTC" in timer,
        "timer catches missed runs": "Persistent=true" in timer,
        "timer has randomized delay": "RandomizedDelaySec=15m" in timer,
        "installer requires explicit absolute app path":
            "FINANCEE_APP_DIR" in installer and '= /*' in installer,
        "installer does not start timer":
            "systemctl start" not in installer and
            "systemctl enable --now" not in installer,
        "credentials forced to 0600": "chmod 0600" in installer,
        "status uses exact repository allowlist":
            "Maaz-Bin-Haider/financee_pk_backup" in status,
        "status exports sourced GitHub token":
            "set -a" in status and "source \"$env_file\"" in status and
            "set +a" in status,
        "status enforces 26-hour freshness":
            "26 * 3600" in status and "REMOTE_BACKUP_STATUS=STALE" in status,
    }
    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"{len(checks) - len(failed)}/{len(checks)} operations checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
