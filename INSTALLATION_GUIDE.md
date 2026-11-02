# Financee Offline development installation

These are development builds for owner review, not signed/customer-certified
releases. Keep existing business data and independent backups. There is no
universal administrator password or demo business.

## Apple Silicon Mac

The self-contained DMG is saved locally at:
`dist/Financee-Offline-Apple-Silicon-Development-352b538.dmg`.
It contains the native app, matching offline runtime images and instructions.
See [Phase 7 review](docs/PHASE7_REVIEW.md) for exact hashes, verification and gates.

Open the locally built development app normally if macOS allows it. If Gatekeeper
blocks it, wait for the Developer ID signed/notarized build; do not bypass macOS
protections. Choose Install to My Applications, check the Mac, and use the official
Docker requirements/download link to complete Docker's own setup and terms.
Then select Docker Setup Reviewed and Verify Included Runtime.

For a new business, select a new empty folder and create your company, currency,
timezone and owner account in the browser. The initial backup folder is Backups
inside the selected business folder. For same-build repair, explicitly select the
existing folder; setup preserves its accounts, credentials, data and backups.
Desktop icon creation and OS sign-in startup are optional. Daily use is through
the installed app/desktop icon; no terminal or developer tools are needed.

Prepare App Removal in Setup stops only the verified installation and disables
its own optional sign-in entry. Quit, then move the app to Trash yourself. The
business folder, backups and data volumes are retained. Data-changing upgrades
are a separate unfinished workflow; do not replace another program build blindly.

Native copy/setup/repair/frozen-health checks pass using private fixtures. Visible
self-copy, empty first startup, setup/maintenance handoff, chooser/removal
cancellation and data-retaining removal pass on this Mac. Developer ID,
notarization and real fresh-device/offline reboot/sign-in acceptance remain pending.

## Windows x64

The locally saved development ZIP is:
`dist/Financee-Offline-Windows-x64-Development-60dc9a3.zip`.
Extract it and keep the setup EXE and matching runtime tar together. Read the
included READ-ME-FIRST before testing on a disposable Windows device. It is
unsigned; compilation/bundle checks passed on a hosted Windows runner, while
customer install/UAC/WSL/reboot/repair/removal tests are deferred by the owner.
Windows 10 runtime/business setup is blocked until its maintained runtime path is
implemented and qualified. See [Phase 6 review](docs/PHASE6_REVIEW.md).

## Existing local review business

The original Phase 5 desktop shortcut and review business are preserved.
The development launcher can start it at http://127.0.0.1:18766/home/.
Company/currency are administered through General Settings. Keep its existing
owner credentials; new-account onboarding cannot replace an existing owner.
The review db/redis/web/nginx were stopped when Phase 7 testing began, and their
state was preserved. Automated tests never restore this review business.

Automatic daily/catch-up ZIPs, Backup Now and launcher recovery controls exist;
see [Phase 4 backup/recovery evidence](docs/PHASE4_REVIEW.md) and
[Phase 5 maintenance controls](docs/PHASE5_REVIEW.md). Earlier phase guides are
historical handoffs, not current installer release claims.
