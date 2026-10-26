#!/usr/bin/env python3
"""Static safety contracts for the DB-only GitHub backup implementation."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "deploy" / "backup_database_encrypted.sh"


def main():
    text = BACKUP.read_text(encoding="utf-8")
    checks = {
        "DB-only backup script exists": BACKUP.is_file(),
        "existing Phase 28 script is not called":
            "bash backup_encrypted.sh" not in text,
        "custom PostgreSQL archive": "pg_dump" in text and "--format=custom" in text,
        "public and tenant schemas included":
            "information_schema.schemata" in text and "tenant_company_%" in text,
        "application preflight required": "manage.py release_preflight" in text,
        "exclusive nonblocking lock": "flock -n" in text,
        "portable atomic lock fallback":
            "fallback_lock_dir" in text and 'mkdir "$fallback_lock_dir"' in text,
        "restrictive output permissions":
            "umask 077" in text and text.count("install -m 600") >= 2,
        "plaintext temp cleanup":
            "mktemp -d" in text and "rm -rf -- \"$work_dir\"" in text,
        "encrypted output only":
            "aes-256-cbc" in text and ".dump.tar.enc" in text,
        "passphrase read from separate file":
            'BACKUP_PASSPHRASE_FILE' in text and '-pass "file:' in text,
        "internal checksums": "sha256sum database.dump manifest.txt" in text,
        "ciphertext sidecar": 'sha256sum "$backup_name"' in text,
        "decrypt verification": "openssl enc -d" in text,
        "internal checksum verification": "sha256sum -c SHA256SUMS" in text,
        "PostgreSQL catalogue verification": "pg_restore --list" in text,
        "UTC recovery point": "date -u +%Y%m%dT%H%M%SZ" in text,
        "no application restart":
            "compose up" not in text and "compose restart" not in text,
    }
    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"{len(checks) - len(failed)}/{len(checks)} backup contracts passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
