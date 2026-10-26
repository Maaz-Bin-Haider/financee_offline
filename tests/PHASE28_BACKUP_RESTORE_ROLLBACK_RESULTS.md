# Phase 28 — Backup, Restore, Migration, and Rollback Results

Date completed: 2026-07-27
Status: **PASSED — PHASE 28 COMPLETE**

## Recovery implementation

- `deploy/backup_encrypted.sh` captures PostgreSQL in custom format and the
  complete media volume, records source SHA and UTC recovery time, checksums
  every member, and encrypts the single bundle with AES-256-CBC/PBKDF2.
- The encrypted object and portable SHA-256 sidecar are written to an explicit
  absolute `BACKUP_DEST`; the passphrase remains separate.
- `deploy/restore_rehearsal.sh` rejects production-like project names, decrypts
  and verifies every member before starting restore work, restores PostgreSQL
  and media into a disposable `phase28_*` Compose project, waits for health,
  verifies every active tenant, verifies a media sentinel, and reports RTO.
- `.github/workflows/ci.yml` now treats the recovery rehearsal as a mandatory
  publication dependency and retains its encrypted off-runner evidence
  artifact for 14 days.
- `PHASE28_RECOVERY_RUNBOOK.md` documents production/off-server operation,
  isolation, RPO/RTO, passphrase handling, and rollback constraints.

## Executed T8 rehearsal

- Static recovery contracts: **14/14 passed**.
- Encrypted bundle size: **1,003,552 bytes**.
- Portable encrypted-bundle SHA-256 verification: passed.
- Deliberately corrupted encrypted bundle: rejected before restore.
- Declared synthetic recovery-point RPO: **0 seconds**.
- Restore RTO through health, all-tenant preflight, and media verification:
  **43 seconds**.
- Complete rehearsal duration: **163 seconds**.
- Restored serial tenants:
  - `tenant_company_1`, serial v6, fingerprint `808e73deb5fbb472`;
  - `tenant_company_2`, serial v6, fingerprint `808e73deb5fbb472`.
- Restored media sentinel: passed.
- Public migrations after restore: no drift and no unapplied migration.
- Serial-family tenant index rollout: 2/2 passed idempotently.
- Quantity tenant provisioned after restore:
  `tenant_company_3`, quantity v22, fingerprint `d0c8ea47e0161104`.
- Previous production image:
  `4474d2a99be089c8d97c6640ffa29698577f3ff6`.
- Previous image health and Django system check against the forward-applied
  database: passed.
- Previous image observed both families (`serial:2`, `quantity:1`).
- Return to current image and final mixed-family preflight: passed.
- Failed-health rollback simulation selected and recreated the previous image.
- All source and restore containers, networks, and volumes were disposable and
  removed after the run.
- Final aggregate production-stack regression: **all 38 modules passed**,
  including Phase 24 serial **51/51**, Phase 25 isolation **17/17**, Phase 23
  quantity certification **20/20**, and HTTP **70/70**.

## Defects found and fixed

1. Compose `--env-file` controls substitution but does not replace the web
   service's fixed `deploy/.env`. Explicit per-rehearsal service `env_file`
   overrides now keep source and restore credentials isolated.
2. Reusing a constant local Compose project name could retain volumes if an
   attended run was interrupted. Local runs now include the process ID; CI
   runs use the unique GitHub run ID.
3. The first encrypted sidecar recorded a temporary absolute path. It now
   records only the bundle basename and verifies after relocation.

## Exit gate

**PASSED.** Encrypted database/media recovery, isolated restore, restored
serial verification, forward migration, post-restore quantity provisioning,
old-image compatibility, current-image recovery, corruption rejection,
RPO/RTO measurement, and failed-health rollback are repeatable. Phase 29 —
Staging Acceptance and Security Review — is next.
