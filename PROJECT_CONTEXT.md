# Financee Offline context

2026-10-26, Asia/Karachi. Owner authorized Phase 4 and later resumed after a
usage-limit interruption. **Phase 4 is complete; stop for owner review before
Phase 5.**
Later phases retain their individual review gates. No push/publication authorized.

Independent repo /Users/swisstech/Development/Financee_Offline, branch
codex/single-company-core. Both source systems remain read-only and unchanged.
Confirmed application baseline 96fd8b9dc4105870bc76cbb2b443bf5c36da2d66, workflow
40122187390; source HEAD 0ea97a2253f0ed12213a24832393e223eed71e21 is documentation only.
Provenance and original imported hashes remain in SOURCE_PROVENANCE.md and
SOURCE_FILES_SHA256.json. Approved requirements/plan are preserved locally.

Current review build **0.4.0-phase4**, schema **2**, core commit 36e77f93bf024d1c85e8030a4f25f8985429ee68.
Image sha256:49a9f3dc7e91ff12a07da8a8754b01706259019e857e9f277e087391edf5a75a (linux/arm64).
Review http://127.0.0.1:18766/home/; owner General Settings at
/admin/local/generalsettings/1/change/, Local Backups at /admin/local-backups/.
Existing company, AED, timezone, users, permissions, all business rows/media and
login preserved; all 24 local modules enabled. No review restore was executed.
No universal password or sample business data is installed in the review business.

Architecture: one public PostgreSQL business dataset beside Django auth and a
singleton local General Settings profile. No tenant registry/membership/routing,
provisioning, subscription/SMTP/report email, activation or cloud operations.
Local permissions remain authoritative. Module availability is stored locally;
dark mode and append-only attribution are retained. Attachments remain private.

Phase 2 adds owner-only identity/contact/currency/timezone/module editing, database
module-key validation, base-currency/posting serialization, company/currency-aware
PDF/CSV/print presentation and bundled currency-symbol fonts. Original arithmetic
and all 190 source SQL definitions remain unchanged. SQL/Python/browser business
dates use the chosen timezone. Offset-preserving PostgreSQL timestamp decoding
prevents audit instant shifts across timezone and DST changes.

Verification: 32 core tests, 328 business assertions, 3 real currency/posting race
cases, 17 currency JS checks, 18 export checks and 41 earlier frontend checks pass.
Four real PDF/CSV currency samples; company/code checked on all 20 PDF pages,
representative pages rendered/visually inspected. No migration drift/system errors.
See docs/PHASE2_REVIEW.md and docs/PHASE2_RESULTS.json for exact evidence and limits.
Earlier Phase 1/currency handoff documents are historical snapshots.

Owned stable project financee_offline_review, loopback 18766; customer folder
.runtime/review, database volume financee_offline_review_database. Test resources
financee_offline_test are disposable and separate. DB/cache have no host ports;
no app container mounts Docker's socket. Runtime credentials remain independent
and ignored. Developer pre-Phase2 rescue ZIP remains historical. Phase 4 now produces verified
format-1 ZIPs in .runtime/review/Backups; test restores use disposable data only.

Phase 3 bundles pinned libraries/fonts/icons with licenses and per-file hashes,
removes CDN includes and the unused eval-dependent ExcelJS global include, and
fixes multipart attachment transaction attribution in Team Activity. The private
application/DB/cache network denies internet connections; only Nginx joins the
entry bridge needed for loopback publishing. Browser CSP permits local resource
origins and required legacy inline code. 35 core tests, 328 business assertions,
76 JS checks, 1185 asset checks and 1530 HTTP checks across 43 screens/147 local
resources pass. Source SQL remains 190 unchanged definitions. Cold service restart
with pulls disabled and fresh local browser origin verified; host Wi-Fi and OS
reboot were not changed/tested. See docs/PHASE3_REVIEW.md and PHASE3_RESULTS.json.

Phase 4 adds local pg_dump/pg_restore 16 tools from the pinned server image,
ZIP64 database/media/config recovery points, full member hashes, bounded shared
request/stream draining plus SQL table locks, atomic publication, 30 normal-copy
retention, protected rescue/foreign ZIPs, daily/catch-up worker, owner status and
Backup Now. Config/active.json atomically couples database/media generations and
records the owned database volume. Restore validates a candidate against complete
row/sequence fingerprints and unchanged SQL, expires candidate sessions/cache,
and requires restart health verification. Startup rolls back incomplete switches.
The old DB/media and rescue ZIPs are retained. Worker/web never mount Docker's
socket. Backup-folder selection/inspect/confirmed restore/recover/open-folder are
available through runtime/maintenance.py; the packaged GUI belongs to Phase 5.

37 core tests, 17 recovery/fault cases, 328 business assertions and 1530 HTTP checks
pass, with 190 source SQL definitions unchanged. Actual restore/restart, preserved
credentials, selected-folder scheduling, no duplicate on same-day restart and
interrupted-switch startup rollback pass on the test installation. A real ARM64
→ emulated Linux AMD64 → ARM64 logical round trip matches every table/sequence
fingerprint. This does not certify native OS installers/reboots. Automatic and
owner-UI review ZIPs validate; the latest observed review pause was 0.097 seconds
on this small dataset. Review business/profile/user/media hashes remain equal.
See docs/PHASE4_REVIEW.md and PHASE4_RESULTS.json for commands, limits and evidence.

Remaining gates: Phase 5 native launcher; Phases 6/7
real Windows10/11 x64 and signed/notarized Apple Silicon installers; Phase 8 safe
manual installer upgrades/recovery; Phase 9 release CI/distribution with explicit
owner authorization. No Intel Mac/Windows ARM package in v1. Current fonts cover
catalogue currency symbols, not every possible writing system. CSV is Excel-readable;
no new native XLSX writer or Excel-app verification is claimed. Keep customer data,
media, secrets, logs, ZIPs and installer payloads out of Git. Never operate sources.
