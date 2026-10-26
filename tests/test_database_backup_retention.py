#!/usr/bin/env python3

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "deploy" / "database_backup_retention.py"
spec = importlib.util.spec_from_file_location("backup_retention", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def release(stamp, **extra):
    row = {"tag_name": f"db-backup-{stamp}", "draft": False}
    row.update(extra)
    return row


def stamp(day):
    return day.strftime("%Y%m%dT%H%M%SZ")


def main():
    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))

    rows = [
        release("20260701T010000Z"),
        release("20260702T010000Z"),
        {"tag_name": "v1.0.0", "draft": False},
        {"tag_name": "db-backup-malformed", "draft": False},
        release("20260703T010000Z", draft=True),
    ]
    expired = module.expired_tags(rows, keep_daily=1, keep_monthly=0)
    check("newest daily retained", "db-backup-20260702T010000Z" not in expired)
    check("old daily expires", "db-backup-20260701T010000Z" in expired)
    check("unrelated release untouched", "v1.0.0" not in expired)
    check("malformed managed-like tag untouched", "db-backup-malformed" not in expired)
    check("draft release untouched", "db-backup-20260703T010000Z" not in expired)

    monthly = [
        release("20260401T010000Z"),
        release("20260420T010000Z"),
        release("20260502T010000Z"),
        release("20260529T010000Z"),
        release("20260603T010000Z"),
        release("20260628T010000Z"),
    ]
    expired = module.expired_tags(monthly, keep_daily=1, keep_monthly=2)
    check("first backup of newest month retained", "db-backup-20260603T010000Z" not in expired)
    check("first backup of previous month retained", "db-backup-20260502T010000Z" not in expired)
    check("monthly window expires old month", "db-backup-20260401T010000Z" in expired)
    check("newest daily retained alongside monthly", "db-backup-20260628T010000Z" not in expired)

    protected = module.expired_tags(
        [release("20260101T000000Z"), release("20260701T000000Z")],
        keep_daily=1,
        keep_monthly=0,
        protect=["db-backup-20260101T000000Z"],
    )
    check("explicit current release protection works", "db-backup-20260101T000000Z" not in protected)

    upload = (ROOT / "deploy/upload_database_backup_github.sh").read_text()
    check("exact repository allowlist", 'Maaz-Bin-Haider/financee_pk_backup' in upload)
    check("private repository verified", "repo_private" in upload and '.private' in upload)
    check("release assets used", "gh release create" in upload)
    check("remote assets re-downloaded", "gh release download" in upload)
    check("remote ciphertext checksum verified", 'sha256sum -c "$checksum_basename"' in upload)
    check("remote bundle decrypted", "openssl enc -d" in upload)
    check("remote dump catalogue verified", "pg_restore --list" in upload)
    check("failed release cleanup", "gh release delete \"$tag\"" in upload)
    check("retention runs only after verification", upload.index("verified=1") < upload.index("Applying pattern-safe retention"))
    check("1.9 GiB fail threshold", "2040109465" in upload)

    failed = [name for name, passed in checks if not passed]
    for name, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"{len(checks) - len(failed)}/{len(checks)} upload/retention checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
