# Financee Offline context

2026-11-02: The owner instructed “move forward and push”, then “continue”.
Phase 7 source/evidence was pushed to origin/codex/single-company-core at
9eb706f1492828b1f186cfdeb5a425a5b527cd02. Phase 8 manual upgrade/failure recovery
is authorized and headless-verified. Stop at its review gate before Phase 9;
no publication or live review upgrade is authorized. Current engine development
version is 0.8.0-phase8, schema 2. Final native Mac confirmation/cancellation/upgrade/login/stop/exit passed on 2026-11-03.
The policy accepts only 0.5.0-phase5/0.7.0-phase7 schema-2 sources, rejects any
pending migration/downgrade, and preserves all business rows/sequences/media
apart from deliberately expired sessions. This is not arbitrary schema-change
support. Paired candidates/rescues and immutable previous program snapshots
are retained. Side-by-side versioned apps preserve old executables. Windows
native upgrade builds/device tests and signing remain release gates.

2026-11-02, Asia/Karachi. The owner instructed “move forward” after the Windows
build handoff, authorizing Phase 7 Apple Silicon installer work. **Phase 7 native
Mac app/DMG development build is locally verified, including native UI; signing/
release acceptance remain pending. Phase 8 is authorized below.** Windows device
tests remain deferred by the owner, and the Windows 10 maintained runtime path
remains unfinished. The existing Apple Silicon review app remains the Phase 5
build. Actual shared-runtime Docker-off and OS reboot/sign-in acceptance remain
pending. No valid Developer ID identity was available for this build; development
builds are ad-hoc signed and not notarized.
The owner authorized committing and pushing the current
source state to https://github.com/Maaz-Bin-Haider/financee_offline.git on
2026-10-28. Remote `origin`, branch `codex/single-company-core`, tracks the same
remote branch. The Phase 5 handoff commit is 03a22c3f9755e9c805fe222c5795ee1985b7d3e3.
Generated apps/images, customer data, credentials, media, backups and logs remain
excluded. Installer releases/distribution still require separate owner authorization.

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

Phase 6 adds explicit Windows prerequisite diagnostics/WSL consent and update
requests, persistent setup state, verified image archive download/import, same-release
repair and conservative data-preserving uninstall preparation. Inno Setup/native
PyInstaller recipes and a clean-checkout staging/export path are present. Windows
10 is explicitly refused by this development prototype until a maintained runtime
pair is implemented/qualified; the dedicated Engine-in-WSL candidate is not yet
implemented. Hosted Windows PyInstaller/Inno compilation now passes; customer
UAC/reboot/installer acceptance remains pending. 47 installer/prerequisite checks
and 42 launcher guards pass (89 total); Windows passes 88 with one POSIX Mac path
fixture skipped. The AMD64 engine passes 38 Django tests and system/migration checks. A real Mac ARM64 shared-engine smoke verifies four exported native
images, empty setup, repeat setup/repair with unchanged identity/keys/generation/
container IDs, and data-retaining uninstall preparation. This does not certify
Windows. Review db/redis/web/nginx were already exited, backup running; tests
preserved those states, images/config/credentials/media. No stopped-review live
business fingerprint was queried. Temporary test containers/networks were removed,
volumes retained. See docs/PHASE6_REVIEW.md and PHASE6_RESULTS.json for exact local
payload/source evidence and build instructions. Core source commit 6cb2bc8.
The owner then confirmed that a Windows test machine is unavailable and instructed
building now with device tests deferred. A manual-only hosted Linux AMD64 payload + Windows x64 PyInstaller/Inno build
succeeded at source 60dc9a3f3d033b59f37441dcab3ab161683e7f2a, run 41422916045.
Both frozen programs pass native AMD64/Tcl/TLS/program-resource checks. Setup
verifies canonical image contents across classic/containerd stores and records
release-bound destination IDs; a real native zero-layer proof and repeated full
Mac disposable setup/repair/stop pass. Program startup retains exact local-ID
checks. Build source/workflow were pushed only to financee_offline; development
artifacts are temporary Actions outputs, not a release. No customer upload,
production action or Phase 7 work is part of this build. Local delivery paths and
hashes are in docs/PHASE6_RESULTS.json. Saved/verified complete local ZIP:
dist/Financee-Offline-Windows-x64-Development-60dc9a3.zip (931,227,330 bytes),
SHA-256 3bcf950b1e190a53508777a2fbd6379310f861a4b89a7c5c7704517aaac5464a.
It includes the setup EXE, matching AMD64 runtime tar and future test instructions;
all seven files, ZIP CRCs, source/bundle provenance and GitHub artifact digest pass.
The owner explicitly deferred real Windows device testing. Phase 6 is not complete;
Windows 10 maintained runtime implementation and all customer acceptance remain
pending. No signed/customer-certified release is claimed.

Remaining gates: Phase 6 native Windows10/11 x64 implementation/acceptance and
owner review; Phase 7 signed/notarized Apple Silicon installers; Phase 8 safe
manual installer upgrades/recovery; Phase 9 release CI/distribution with explicit
owner authorization. No Intel Mac/Windows ARM package in v1. Current fonts cover
catalogue currency symbols, not every possible writing system. CSV is Excel-readable;
no new native XLSX writer or Excel-app verification is claimed. Keep customer data,
media, secrets, logs, ZIPs and installer payloads out of Git. Never operate sources.


Phase 7 final local development build: source/engine commit
352b538d787677df94a7fd11c58d4c9853df139e, setup/engine 0.7.0-phase7, schema 2.
DMG: dist/Financee-Offline-Apple-Silicon-Development-352b538.dmg
(497,522,060 bytes), SHA-256
f9cbffd79758fadd9bde2b4913b4eb0179fa669771db4414dbc204dc4df722e8.
No customer profile, credentials, business data or Docker Desktop is bundled.
The old Phase 5 review app/image/customer remain unchanged.

106 host guards, 38 core tests, system/migration checks, standalone/read-only DMG
verification and native copy/setup/repair/frozen-health/removal integration pass.
Five ARM64 Mach-O files and bundled Tcl/TLS work without developer paths. After
manual unlock, native UI self-copy, runtime verification, empty startup, chooser
cancellation, setup/maintenance handoff, removal cancellation and confirmation
pass. Counts 0|0|0 and setup incomplete; no company/owner/password submitted.
Final app processes exit normally and release their locks. An observer reused an
exited process handle once, triggering a duplicate-instance guard; the actual
handoff/setup window was healthy. Use a fresh CUA app binding after handoffs.

Testing corrected stale backup guidance, explicit Tk loop teardown/closed polling,
and a hard-coded health version. Health reads packaged VERSION. `.dockerignore`
now excludes generated installers/customer folders/developer environments; final
engine root/version checks pass. Original SQL/migrations/contract unchanged.
No 190-definition comparison repeated for these host/presentation/health changes.
Earlier builds and failed-attempt customer files/volumes are retained in ignored
.runtime diagnostics. The final native test app remains in ~/Applications with
its disposable preferences/customer preserved and stopped, no sign-in/desktop
hook enabled. Temporary test containers/networks, browser tabs and port reservations
were closed; volumes/data/apps retained. Review states/images/config/credentials/
media and both source repository HEADs/clean status match the baseline.

No valid Developer ID identity exists. Ad-hoc signatures verify; Gatekeeper rejects
the development artifact (exit 3), and the notary helper refuses it before upload.
No security bypass, Apple submission, artifact upload, public release or Phase 7
source push. Pending: owner signing/notary inputs, fresh supported Macs, absent
Docker setup, offline OS reboot/sign-in and customer reinstall acceptance. Windows
10 maintained runtime work/device acceptance remain pending. Stop before Phase 8.
Exact receipts: docs/PHASE7_REVIEW.md and docs/PHASE7_RESULTS.json; ignored build
receipts/screenshots in .runtime/phase7-final-build.

Current Phase 8 handoff (updated 2026-11-03): app source
b12e676ee93e40a3dfab2f3dafa76287bce5773e, engine source 8076287, version
0.8.0-phase8/schema 2. DMG dist/Financee-Offline-Apple-Silicon-Development-b12e676.dmg
(498,479,775 bytes), SHA256
2561a5e5756cedb8638cf11872749f5b4aa724744f07cd0cfeb57d71c1012ab2.
120 host checks, both populated 0.5/0.7→0.8 upgrades, 38 core tests per source,
190 SQL definitions, five abrupt host-exit checkpoints, candidate corruption and
startup failure recovery pass. Only reviewed same-schema upgrades are supported;
no arbitrary future migrations or image-only downgrade.

The final b12e676 Mac app has now passed native self-copy, verification, cancel
(no container/health/config/generation/credential changes), explicit Yes/No,
real populated upgrade and maintenance/default-browser login handoff. Full
independent post-upgrade fingerprints confirm business/auth/permission/settings/
history rows, sequences, all media and credentials match; sessions expired.
Protected rescue, old DB/media/program/images and the correct new selection were
verified. No GUI owner/password entry occurred. Native Stop, close and released
program/customer locks passed. Only its test containers/networks were removed;
volumes, data/files/rescues/apps retained. The old typed prompt was removed in
b12e676; the single native concrete confirmation works.

Native receipt: .runtime/phase8-delivery-build/native-ui-results.json. Evidence
screenshots in native-ui/ and the visualization folder. Fixture pointers and
pre-upgrade hashes in .runtime/phase8-native-ui.json; this marked fixture is now
UPGRADED and stopped. Do not repeat its original upgrade or select .runtime/review.
Default test-only app preferences were archived AFTER verifying the persisted
upgraded selection to .runtime/phase8-delivery-build/native-ui/test-app-state;
the installed ~/Applications/Financee Offline Mac 0.8 Development.app now opens
fresh setup for owner review. Test data remain recoverable using the saved state.
The old typed-dialog build/state remain preserved separately under
.runtime/phase8-native-previous-confirmation. Original Phase5 review and Phase7
app/state remain untouched. Review container IDs/states/images and configuration/
credential/media hashes still match the original baseline. Both source repos are
read-only and unchanged. The test browser tab was closed.

Windows Phase 8 source has separate install identity/paths but its native build/
device tests are still pending. Windows10 maintained runtime work, fresh-device/
offline OS reboot/sign-in, signing/notarization and owner review remain gates.
The GitHub repository is PUBLIC; the existing manual Windows build workflow
uploads development artifacts. No Phase8 workflow run or public installer upload
was performed in this native Mac validation. Phase9 has not started. Source push
authorization persists; previous remote checkpoint d3f118b was verified. Native evidence is recorded in this source checkpoint; no program change or
DMG rebuild was needed. Installers, customer records and runtime secrets remain
local and ignored. Exact handoff: docs/PHASE8_REVIEW.md and RESULTS.json.

2026-11-03 continuation: preparing Windows Phase8 validation. The existing public
repo workflow now defaults to native Windows guards/GUI imports ONLY, with no
artifact upload, Docker/WSL mutation or installer execution. Full Linux payload
and Windows packaging jobs require explicit upload_development_artifacts=true.
Owner's no-public-artifact rule still applies; source push permission persists.
Existing workflow action/dependency pins are retained. Package notices now
describe the 0.8 side-by-side upgrade/recovery flow. Source/CI validation is not
Windows customer install/UAC/reboot/upgrade acceptance. Stop before Phase9.
