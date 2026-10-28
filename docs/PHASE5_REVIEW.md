# Phase 5 desktop launcher review

2026-10-28, Asia/Karachi. **0.5.0-phase5 / schema 2 / backup format 1.**
The local Apple Silicon implementation is ready for owner review. Stop before
Phase 6. The full target-machine acceptance matrix remains pending as listed below.

## Open the review build

Double-click **Financee Offline Development** on the Mac desktop. Its target is:

`/Users/swisstech/Development/Financee_Offline/.runtime/phase5-launcher/Financee Offline Review.app`

Choose **Start / Open Financee** if needed. The existing review business opens at
http://127.0.0.1:18766/home/ using its original owner login. Company settings,
**AED**, Asia/Karachi, users/permissions, business records and media are preserved.
No new owner, universal password or sample transactions were added to review.
Closing the maintenance window/browser leaves services running. **Stop Financee**
stops only this installation; it retains data and backups.

The window and native Financee menu offer Start/Open, Backup Now, Restore Backup,
Open Backups Folder, Choose Backup Folder, Stop, Refresh Status, local logs and a
desktop shortcut. Backup status shows the last filename/time, folder, next due
state and errors. Sign-in startup is optional and remains unchecked. It was tested
in private fixture directories; no real OS startup entry was enabled by the agent.

Restore selects and validates a ZIP, shows company/date/version/SHA-256 and waits
for **RESTORE** to be typed exactly. Restore remains disabled until that phrase;
typing alone does not start recovery. Confirming starts candidate recovery;
cancelling leaves the active dataset and restore journal unchanged. Native menus
also expose confirmation and cancellation. All actual restores in this phase used
the separate disposable test installation, never review.

## What was implemented

The frozen app includes Python/Tk and program resources. Normal use needs no
terminal, checkout, Python, Git or Node installation. This development build uses
already-cached tested images and the installed local Docker runtime. Installer
payload import/prerequisite handling belongs to Phases 6/7.

A new installation requires a chosen empty folder, creates independent random
runtime credentials and identity, and opens empty company/owner setup. Existing
folders retain their settings and credentials. The app records the owned
project, volume and loopback port; a moved folder requires repair.

Startup validates program hashes, local Docker context, native Linux image IDs,
owned mounts/volume/loopback binding and installation-specific health. It rejects
missing previously-owned volumes, foreign ports, unexpected services and other
image versions before mutation. A healthy matching build is reused. The desktop
controller never silently initializes replacement data or performs an upgrade.
Normal startup never builds/pulls images. Stop does not start an unavailable
Docker runtime. No global Docker stop, context switch or prune is used.

Host locks serialize operations, the maintenance window handles duplicate launch
requests, and long operations run outside the GUI thread. Backup/restore use the
shared Phase 4 engine, with rescue/previous data retained, candidate checks,
session expiry, health verification and rollback. The maintenance authority is
the owner of the local device, not an unauthenticated web endpoint.

Actual first-run testing found and fixed an empty-company scheduler query: it
now waits quietly for setup, clears a previous startup error, and becomes due
after a company is configured. A real PostgreSQL regression covers that transition.

## Verification

See [PHASE5_RESULTS.json](PHASE5_RESULTS.json) for exact revisions, image ID,
bundle checksum, review ZIP checksum and recorded results.

- 36 host launcher guards, 38 Django core tests and 18 real PostgreSQL/ZIP recovery cases pass.
- 328 business assertions and 1,530 HTTP checks across 43 screens/147 local resources pass.
- All 190 retained source SQL definitions match; no migration drift or system-check errors.
- Real reuse, cold stop/start, selected backup folder, manual ZIP/inspect, changed-digest refusal,
  candidate restore, retained rescue/old data, expired sessions and unchanged credentials pass.
- Real port collision refused before creating a volume. Empty setup with spaces/Unicode/dollar
  paths passes. Temporary installation containers/networks are removed with volumes retained.
- Native Start/Open, status, Backup Now, ZIP picker, typed consent/explicit approval, disabled
  confirmation and cancellation were exercised. Pointer/journal hashes prove waiting, typing
  alone and cancellation do not switch data. Native first-run chose an empty folder and
  reached ready/setup; it contains zero users, company profiles and journal entries.
- The real empty first-run worker now reports waiting for setup without an error.
- Docker Desktop's observed `/host_mnt` macOS alias is accepted only for a verified Desktop
  runtime. Foreign roots and aliases on other runtimes/platforms remain rejected.
- Repeated disposable tests exhausted the local address pool once. Only the test-created
  UUID projects were removed; data volumes were retained and the same first-run installation
  retried successfully. No global network cleanup or Docker configuration change occurred.
- The native ARM64 bundle passes deep code-signature/program-file verification. All recognized
  Mach-O files are ARM64, library paths are relocatable and symlinks remain within the bundle.
  A copied app ran diagnostics from a temporary directory with developer Python/PATH variables
  removed and verified real review health. It does not depend on the checkout interpreter.
- Review before/after fingerprints match for 35 business/configuration tables, user flags and
  permissions, profile and media. Session/activity timing is excluded from these comparison
  snapshots. Full backup validation separately fingerprints every public table and sequence.
- Both source repositories remain clean at their original HEADs. No remote/push/publication.

The native HTTP check uses direct fixed loopback HTTP, without proxy lookup,
redirects, cookies or unnecessary HTTPS certificate discovery. This fixed a
frozen-app health failure that source-only execution did not expose.

Representative native screenshots are stored locally in the task visualization
folder: `phase5-launcher-review.jpg` and `phase5-first-run-ready.jpg`. The latter
captures the first retry before the scheduler waiting-state fix; the final real
worker check and results JSON confirm that fix. Generated apps, data, secrets,
ZIPs, logs and machine-specific receipts remain ignored.

## Remaining acceptance and release gates

This is a local, **ad-hoc signed, not notarized** development app, tested on the
recorded Apple Silicon macOS host. It is not a customer installer or a public
release. An unbound first-run test app is also present in `.runtime/phase5-launcher`;
its private test preference path is intentionally separate from customer preferences.

Real Windows 10/11 x64 builds and device tests, actual Docker-off startup on a
dedicated machine, OS reboot/sign-in lifecycle, fresh-device prerequisites,
signed/notarized Mac distribution, installer repair/uninstall and upgrades remain
pending. Docker-off responses and OS-hook serialization were tested using mocks
and private fixtures; the shared host Docker runtime was never globally stopped.
Windows hooks in source are not native Windows certification. No Intel Mac or
Windows ARM package is provided in v1.

For owner review: open the desktop shortcut, check dashboard/General Settings AED,
inspect the backup folder and try Backup Now/status. Restore UI cancellation is
safe to inspect; completed restore testing has already used disposable data.
Do not proceed to Phase 6 or publish without the owner's next instruction.
