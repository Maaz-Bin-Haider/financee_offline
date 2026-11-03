# Phase 8 manual upgrades and failure recovery

2026-11-02; native acceptance completed 2026-11-03. The owner authorized “move forward and push”, then “continue”.
Phase 7 source checkpoint `9eb706f` and Phase 8 checkpoint `113887c` were pushed
to `origin/codex/single-company-core`; remote HEAD was independently verified.
Phase 8 now has a local manual-upgrade build verified headless and through
the final native Mac UI. Stop for review before Phase 9.
No installer publication, Apple upload or upgrade of the review business occurred.

## Review build and supported upgrade

Local artifact: `dist/Financee-Offline-Apple-Silicon-Development-b12e676.dmg`.
498,479,775 bytes; SHA-256:
`2561a5e5756cedb8638cf11872749f5b4aa724744f07cd0cfeb57d71c1012ab2`.
Frozen app source `b12e676ee93e40a3dfab2f3dafa76287bce5773e`;
engine source `8076287` (full revision and image identity in PHASE8_RESULTS.json).
Both are version `0.8.0-phase8`, schema 2. The engine predates host-only
recovery/UI corrections; its backup/upgrade-check implementation is unchanged.
Program staging provenance and final frozen-app provenance are recorded separately.

The first reviewed policy accepts **0.5.0-phase5 → 0.8.0-phase8** and
**0.7.0-phase7 → 0.8.0-phase8**, on schema 2 and the same native architecture.
PostgreSQL/cache/proxy identities remain pinned. It rejects downgrades, unknown
source versions, schema changes, pending Django migrations, altered financial
SQL and changed business fingerprints. Running an old image alone is never a
rollback. A future schema-changing release needs its own reviewed migration and
preservation policy; this build does not claim arbitrary future migration support.

## Customer update flow

1. Keep the previous app and an independent verified backup. For review, use a
   disposable business or a copy recovered with the previous release. Never use
   the original review business for automated upgrade tests.
2. Close the previous maintenance window. If optional sign-in startup is enabled,
   turn it off there first; enable it in the new app after verification. This
   build refuses an upgrade with the old sign-in hook still enabled.
3. Install the new **Financee Offline Mac 0.8 Development.app** beside the old
   app. Use Setup → **Upgrade Existing Business**. Select the existing business
   folder and previous Financee app. The common default old Mac app is recognized;
   another previous app can be selected with the native app chooser.
4. Choose **Verify / Prepare Upgrade**. Setup checks the exact policy, current
   identity/storage/runtime, archive hashes and native cached images. Windows
   development setup asks for the matching local runtime tar. No normal startup
   or upgrade pulls images, checks a licence, or changes the shared Docker runtime.
5. Choose **Apply Verified Upgrade**. The native confirmation names both versions
   and the exact business folder. Cancelling leaves the installation unchanged.
   Confirmed work revalidates the reviewed inputs and holds installation locks.
6. The installer retains immutable old/target program resources, stops only the
   verified business web/backup services, creates a protected rescue ZIP and
   restores a separate candidate database/media generation. It verifies all
   business/auth/permission/settings/history rows and sequences, all uploaded
   bytes and links, balances, constraints and 190 source financial SQL definitions.
   Sessions deliberately expire. It runs the declared repeatable migration/check
   sequence, starts the target web/proxy and verifies exact build/schema/identity/
   generation before committing and resuming daily backups.
7. Use the new app after success and sign in again. Previous apps, images,
   database/media generations, customer credentials and rescue ZIPs remain
   retained. Optional new desktop/sign-in integration remains an explicit choice.

If interrupted, reopen the matching new installer, select the same business,
and choose **Recover Interrupted Upgrade**. It validates its durable journal,
old/new program identities, credential hashes and strict container ownership,
stops only the recorded owned work and returns to the previous paired database,
media and runtime. It also stops a surviving named upgrade task before recovery.
No active database is destroyed, no inverse financial migration is attempted,
and no global Docker down/prune/reset command is used. Normal launch and same-build
repair refuse a pending upgrade. New-engine business requests remain gated until
commit; health remains available. Completed recovery is a read-only no-op.

## Actual verification

- **120 host checks pass**: 14 upgrade policy/ownership/interruption guards and
  the previous 106 installer/launcher checks.
- Actual populated 0.5 → 0.8 and 0.7 → 0.8 upgrades pass using the final packaged
  program. Synthetic fixtures include AED/Dubai settings, owner/viewer/inactive
  users, a group/action permission, serialized purchase/sale, balanced books,
  activity history, a linked PDF and binary media. Fixtures require an exact
  unique host-created marker and refuse unmarked/source/review installations.
- Five abrupt host exits were injected after rescue, candidate creation,
  target binding, candidate verification and startup health. Recovery returned
  to the exact old generation, rows/sequences/media and original credentials.
  The target health endpoint remained available while business routes returned
  HTTP 503 before commit.
- Real candidate company-data corruption was rejected and recovered; an injected
  target-start failure also recovered the original paired release. Both fault
  cases passed for both supported source versions. Success preserved every
  non-session table/sequence/media fingerprint and expired candidate sessions.
- **38 core tests pass** after each supported upgrade. SQL integrity verifies
  all 190 source definitions, balanced journals, validated constraints and
  attachment links. Runtime credentials and the old database/media/program/
  images/rescue ZIPs remain retained. Temporary test containers/networks were
  removed with volumes retained; the completed recovery action did not downgrade.
- The final frozen app and read-only DMG pass signature integrity, relocated
  program/payload hashes, five native ARM64 Mach-O files, contained symlinks,
  relocatable libraries and bundled Python/Tcl/TLS without developer paths.
  Final engine cleanliness and matching packaged VERSION/health were checked.
- On 2026-11-03 the final `b12e676` app self-copied into Applications beside
  the old app, verified the marked populated 0.7 business, and passed native
  cancellation with unchanged container IDs, health, configuration, generation
  and credential hashes. The single native Yes/No confirmation then applied the
  upgrade and opened the new maintenance window and default-browser login page.
  No credentials were entered through GUI automation. Independent comparison
  confirmed every non-session business/auth/permission/settings/history table,
  sequence and media hash matched; all 190 SQL definitions passed and old
  sessions expired. Protected rescue and old data/program generations remained.
- Native Stop affected only this test installation. Closing maintenance exited
  the app and released both program/customer locks. Its temporary containers and
  networks were removed with the database volume, app, files and rescue ZIPs
  retained. Test-only preferences were archived after checking the persisted
  upgraded-business selection, leaving the installed app ready for fresh setup.
  The prior redundant typed dialog was removed; explicit native confirmation
  remains bound to the reviewed source/target versions and exact folder.

Testing found and corrected a recovery-port check that mistook the deliberately
stopped web process behind the verified owned proxy for a foreign port collision.
Ownership remains strict: a foreign listener, image, project, customer mount,
volume or LAN binding is refused. A test cleanup initially omitted Docker Desktop
path detection and safely refused `/host_mnt` mounts. The test now initializes
runtime detection before inspecting ownership; the final runs clean up normally.
Source/financial SQL/migrations were not weakened to make tests pass.

Exact receipts: `docs/PHASE8_RESULTS.json` and ignored
`.runtime/phase8-delivery-build/{build-receipt,verification,upgrade-from-0.5,upgrade-from-0.7,distribution-checks,native-ui-results}.json` and `native-ui/` screenshots.
Earlier builds/failed-attempt data are retained as diagnostics. Both reference
repositories remain clean at their recorded HEADs; review container states/images,
configuration/credentials/media remain unchanged. No review restore/upgrade or
live business fingerprint query was performed.

## Remaining gates

Native Mac acceptance is complete for this existing-Docker host. Its retained
fixture is recorded in `.runtime/phase8-native-ui.json`, and its archived test
preferences are in `.runtime/phase8-delivery-build/native-ui/test-app-state`.
No review upgrade or company/owner credential entry through GUI automation took
place. Synthetic test account creation remained confined to marked fixtures.

The common Windows upgrade window and a separate development app identity/path
are implemented in source. No Phase 8 native Windows build or Windows customer
upgrade/UAC/reboot/uninstall certification is claimed. Windows 10 maintained
runtime implementation remains unfinished, as previously recorded.

The DMG is ad-hoc signed, not Developer ID signed/notarized. Gatekeeper rejects it
as expected (exit 3); the notary helper refuses it before upload. No bypass occurred.
Fresh-device, true offline OS reboot/sign-in, Windows target testing and owner
signing/notary inputs remain distribution gates. Phase 9 has not started.
