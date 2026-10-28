# Financee Offline context

2026-10-28, Asia/Karachi. Owner authorized Phase 5. **The local Apple Silicon
Phase 5 implementation is ready for owner review; stop before Phase 6.** Full
hardware acceptance remains pending for Windows, actual shared-runtime Docker-off
and OS reboot/sign-in. No push/publication authorized.

Independent repo /Users/swisstech/Development/Financee_Offline, branch
codex/single-company-core. Both source systems remain read-only and unchanged.
Confirmed application baseline 96fd8b9dc4105870bc76cbb2b443bf5c36da2d66, workflow
40122187390; source HEAD 0ea97a2253f0ed12213a24832393e223eed71e21 is documentation only.
Provenance and original imported hashes remain in SOURCE_PROVENANCE.md and
SOURCE_FILES_SHA256.json. Approved requirements/plan are preserved locally.

Current review build **0.5.0-phase5**, schema **2**. Engine core commit
f9b00f7163e18b218ab478e2d0471c74f65910d1; native launcher commit
a78b9a72c8cc4d37c57f54eba4b003cbc54705a9. The engine image is
sha256:40b14f234aaf0f41aa35341f47200ce1ba7a847997905ae0619bace283a6d94c
(linux/arm64). Native bundle checksum and exact evidence are in docs/PHASE5_RESULTS.json.
Desktop shortcut: /Users/swisstech/Desktop/Financee Offline Development.app →
.runtime/phase5-launcher/Financee Offline Review.app. This local ad-hoc signed
ARM64 app is not notarized or a customer installer.
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

Phase 5 adds a frozen Python/Tk desktop maintenance app, chosen-folder empty
setup and existing-install adoption, independent identity/credentials, explicit
local Docker context and cached-image checks, strict owned roots/volumes/loopback
ports, installation health, nonblocking operations, locks/second-launch handling,
start/open/status/stop, backup/folder/log controls, typed single-use restore consent,
rescue/candidate verification/rollback, desktop shortcut and opt-in sign-in hooks.
Stop never starts an unavailable Docker runtime. A verified Docker Desktop macOS
/host_mnt alias is normalized while foreign mounts remain refused. New empty
businesses wait quietly for setup before scheduling a backup.

36 launcher guards, 38 core tests, 18 recovery cases, 328 business assertions and
1530 HTTP checks pass. Real native first-run, backup, explicit restore and cancellation
were exercised on disposable data; zero seeded owners/company/journal rows and a
waiting backup worker were verified. Typing alone/cancellation preserve pointer
and journal. A copied ARM64 app verifies real health with developer paths removed;
program hashes, contained symlinks, native libraries and local signature validate.
Review AED/profile/users/permissions/business/media fingerprints remain equal;
no review restore occurred. Source Git HEAD/status remain unchanged. Actual global
Docker-off/reboot and Windows target tests are not claimed. See docs/PHASE5_REVIEW.md
and PHASE5_RESULTS.json. Generated apps/config/ZIPs/receipts remain ignored.

Remaining gates: owner Phase 5 review; Phases 6/7
real Windows10/11 x64 and signed/notarized Apple Silicon installers; Phase 8 safe
manual installer upgrades/recovery; Phase 9 release CI/distribution with explicit
owner authorization. No Intel Mac/Windows ARM package in v1. Current fonts cover
catalogue currency symbols, not every possible writing system. CSV is Excel-readable;
no new native XLSX writer or Excel-app verification is claimed. Keep customer data,
media, secrets, logs, ZIPs and installer payloads out of Git. Never operate sources.
