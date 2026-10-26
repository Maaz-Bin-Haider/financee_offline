# Prompt for the new Financee_Offline project agent

Build a separate offline desktop-distributed edition of Financee in a new repository named `Financee_Offline`. These requirements have already been clarified with me; do not ask me to answer them again. Read the complete implementation plan supplied with this prompt, inspect the source read-only, and begin the isolated work described below.

The full plan is currently saved at:
`/Users/swisstech/.codex/visualizations/2026/10/23/01a168ee-b423-7770-8815-bfceffb2596d/Financee_Offline_Planning/IMPLEMENTATION_PLAN.md`

Copy the approved planning requirements into the new repository's own documents before implementation. This prompt is self-contained on the essential boundaries and product decisions.

## Existing systems are read-only

Reference application:
`/Users/swisstech/Development/Financee_Multitenant_Production`

Optional comparison reference:
`/Users/swisstech/Development/Accounting-Plus-Inventory-System`

The multitenant application is deployed with paying clients. Do not change a file, branch, Git configuration, migration, database, container, environment, workflow, backup or production resource belonging to either source system. Do not update their PROJECT_CONTEXT.md files either. Do not fetch into them, run their mutating tests/setup/deployment commands, use their secrets, or connect to their live databases. Read-only inspection is permitted.

All new work, Git history and product documents belong in:
`/Users/swisstech/Development/Financee_Offline`

Create an independent repository there if it does not exist. If it already exists, inspect and preserve its current work instead of replacing/resetting it. Do not create a linked source worktree or copy a source `.git` directory. Do not create a GitHub remote, push or publish a release without my explicit instruction.

The last owner-confirmed source application release is `96fd8b9dc4105870bc76cbb2b443bf5c36da2d66`, from successful workflow `40122187390`. It includes dark mode, Spotlight, Team Activity and the purchase-page sizing correction. Documentation-only source checkpoint `0ea97a2` records the production confirmation. Verify the intended source snapshot through read-only inspection and record provenance; never assume a dirty working directory is the production release.

## Confirmed product

- One company on one personal device. No multitenant structure is required or wanted.
- Retain the existing username/password login, local users, groups and permissions.
- One-time purchase. Remove SaaS subscriptions, payment/expiry/suspension locks, billing reminders and online activation/remote licence checks.
- Internet is allowed during installation and later manual updates. All normal business operations must work without internet after installation.
- Support Windows 10 x64 and Windows 11 x64, and Apple M-series Macs. No Intel Mac or Windows ARM package in v1.
- A desktop icon starts everything needed and opens Financee in the default browser. Customers should not need a terminal, Git, Python, Node or technical Docker knowledge.
- Start as an empty business. No hosted-client migration/import feature in v1; no demo transactions, stock or customer records in the delivered system.
- Admin → General Settings must include company identity and currency selection with the required symbol. Use a currency code plus optional local display-symbol override. Preserve financial numeric precision/calculations. No automatic FX conversion. Preserve the existing base-currency lock after financial activity; allow cosmetic symbol changes separately.
- Remove Report Email entirely, including its worker/scheduler, SMTP settings, permissions, navigation and endpoints. Remove subscription email as part of removing subscriptions. Ordinary email contact text on invoices can remain.
- Keep all other applicable existing features, including serial accounting/inventory, drafts, reports, attachments, dark mode, Spotlight, Team Activity and the corrected purchase layout. Dark mode stays globally available.
- Daily automatic backups, keeping the latest 30 completed normal backup ZIPs. Catch up on next startup when the device was off/asleep. Provide Backup Now, Restore Backup and Open Backups Folder controls.
- Each backup is one ZIP containing the database, uploaded attachments and recovery metadata/configuration. Customers manage their own local backup folder and additional copies. No cloud backup, GitHub upload, telemetry, vendor monitoring or remote recovery service.
- Customers install later versions manually using a new installer. Preserve their database, attachments, users, settings and backups.
- No additional DRM or enterprise security project is requested. Retain the application's login/permission checks, basic localhost isolation, accounting constraints and protections against corrupting/deleting data.

## Required architecture

Preserve Django + PostgreSQL and the existing SQL-based financial engine. Do not switch to SQLite, rewrite accounting in Python or import GST behavior from the other reference system.

Convert to one application database and one business dataset in `public`, alongside Django auth/local settings, after checking SQL object dependencies/name collisions. Remove the Company/Membership tenant registry, tenant schemas, provisioning, schema-family selection and request-driven tenant search-path switching. Leaving the old tenant system enabled with one fixed company is not the requested end state.

Replace business identity/configuration with a singleton local General Settings profile, enforced in both database and admin. Necessary system seeds such as chart of accounts, currency reference data, permissions and special cash parties are allowed. Create the first owner through local onboarding; do not ship a universal admin password.

Tenant middleware currently also performs permission/feature/rate checks. Preserve the applicable checks explicitly when removing tenancy; do not accidentally expose every screen/action. Convert company feature availability, if retained, to installation-level settings and make retained modules available by default while user permissions remain authoritative.

Refactor all dependent paths: attachments/media, permission seeding, context processors, Spotlight capability/recents/session scope, Team Activity actor snapshots/append-only recording, backups and admin. Establish a fresh, versioned single-company schema/migration path rather than shipping the old production tenant-retirement/reversal history.

Create a completely separate local Compose runtime with owned names/volumes/ports: PostgreSQL 16, Django/Gunicorn, Nginx, Redis initially if needed by existing behavior, and a backup scheduler. Remove the email worker. Tune for personal computers. Only the web entry point listens on loopback; DB/cache have no published host ports. Never mount a Docker socket into the web application.

Build native amd64 and arm64 Linux image payloads. Release installers download/import tested image archives with version/checksum manifests; no customer registry credentials or developer tools. Use pinned release images, not floating latest. Normal startup is entirely local and never pulls images.

Recommended packaging starting point: a small Python setup/launcher controller with a simple GUI, frozen with PyInstaller; a Windows setup EXE around it and a native ARM64 Mac app/setup bundle in a DMG. Prototype before committing to the packaging details. Build launchers on their actual target OS/architecture. Document any evidence-based alternative without changing the required customer experience.

Install prerequisites from official locations with required user consent. Detect compatible existing Docker installations, handle unavailable virtualization/WSL/reboot resumption, and do not replace or remove unrelated Docker/WSL installations. Customers may need to accept OS/Docker prompts; do not promise a completely unattended prerequisite install or accept third-party terms for them.

Windows 10 is an explicit target that needs a real tested OS/runtime strategy. Re-check current Docker/Microsoft support constraints. Do not silently discard Windows 10, claim universal support or pin an obsolete unsupported Desktop build without review. Evaluate an appropriate maintained Docker Engine/WSL path if necessary. Missing target hardware is a release-verification limitation, not a reason to invent passing results or to stop unrelated core implementation.

Mac distribution needs a proper Developer ID/signing/notarization path. Keep signing credentials as owner-provided release inputs. Label unsigned development builds honestly and never bypass Gatekeeper. Respect Docker and packaging dependency distribution/licensing terms.

## Local data, backup and recovery

Separate installed program files from a writable customer folder named `Financee_Offline`, normally under Documents or another location chosen during setup. It contains Config, Data/media, Backups, Logs and Cache. PostgreSQL live files can use a stable Financee-owned Docker volume identified in local configuration. Updates/uninstall must not mistake that volume for a disposable test database.

The development repository can contain a Backups placeholder, but ignore real ZIPs, customer data/media, logs, runtime secrets and generated installer payloads. Frequent commits apply to source, configuration templates, tests and documentation, not customer records.

Each ZIP must include a versioned manifest, a PostgreSQL custom-format logical dump, media files, required portable configuration and member hashes/sizes. No backup password/encryption workflow is required for v1. Use a PostgreSQL-compatible dump client; do not archive live PostgreSQL volume files. Logical recovery must be tested across the x64/ARM64 targets.

Coordinate a bounded write pause/drain so the database and media represent the same recovery point. Use cross-process locking; publish a ZIP only after verification, using atomic staging/finalization. Support large ZIPs. Rotate only after success. Keep rescue copies until an upgrade/restore is verified. Missed days trigger one catch-up backup when the runtime next starts; never claim backups run while a computer is off.

Show local backup status and clear disk-full/permission/missing-folder errors. Backup Now can be offered in admin and the launcher; the launcher must provide Restore Backup and Open Backups Folder, including recovery when Django cannot start. Admin web controls remain permission-protected; local recovery is an explicit device-owner operation.

Restore must validate compatibility, checksums and archive paths, obtain explicit replacement confirmation, and preserve a rescue point. Restore into a candidate database/media generation, verify financial/data/attachment integrity, then switch the active installation and health-check. A failure must retain/reinstate the old installation. Do not destroy the only current database before validating the candidate. Expire old sessions/cache after recovery. Destination-generated runtime credentials should remain separate from restored business configuration.

Manual upgrades need version/schema compatibility, a verified rescue ZIP, staged replacement images/files, explicit repeatable migrations and post-upgrade verification. Data-changing rollback may require the paired backup; do not claim that an old image alone reverses incompatible SQL changes. Repair/reinstall must not initialize a blank database over existing customer data. Preserve data/backups on uninstall by default and never run global Docker prune/down/reset commands.

## Fully offline presentation

Bundle every runtime font, icon, CSS/JS library, PDF/Excel library and other CDN dependency with appropriate licence/version records. Existing source templates still load online resources, and some transaction/PDF labels hard-code PKR/AED. Audit all active screens and exports. A warm browser cache is not proof: verify after restart with internet disconnected and no external resource cache dependency.

Retain existing financial rounding/precision and test currency labels/symbols throughout reports, invoices, dashboards and PDF/CSV/Excel/print. Bundle fonts so supported Unicode symbols do not become missing-glyph boxes. Keep the purchase layout and both themes usable at desktop and phone widths.

## Work sequence and commits

Follow these phases, recording outcomes in the new repository:

0. Safe repository import, provenance, scope, runtime/platform decisions and isolated resource ownership.
1. Single-company core, fresh empty onboarding, local auth/permissions and removal of tenancy/subscriptions/email.
2. General Settings, company identity, currency/symbol/timezone and local module settings.
3. Fully local assets, offline behavior and final Spotlight/activity/attachment adaptation checks.
4. ZIP backup engine, daily/catch-up scheduler, retention/status and recoverable restore.
5. Packaged desktop launcher and maintenance controls.
6. Windows 10/11 x64 setup/downloader, prerequisite/reboot/repair/uninstall workflow.
7. Apple Silicon setup/DMG/app, desktop alias and signing/notarization pipeline.
8. Data-preserving manual upgrade and failure recovery.
9. Separate product CI, full platform matrix, customer instructions and owner-approved release artifacts.

Start now with Phase 0 preparation and Phase 1 implementation. Work through to a running isolated single-company core with meaningful verification, then stop for my manual review. Do not stop with only a proposed plan, and do not implement all remaining phases in one uninterrupted batch. Later phases each end in a reviewable local build and owner gate unless I explicitly combine them.

Make small meaningful commits throughout. Code plus related SQL/migrations/tests/version metadata is a coherent commit; do not leave a knowingly broken schema/contract pair merely to increase commit count. Never manufacture empty commits or alter dates. Update the new PROJECT_CONTEXT.md as decisions and results change.

Port relevant business tests to the single-company architecture, with independently checked financial SQL invariants. Remove/rewrite obsolete multitenant-specific assertions deliberately and explain the replacement coverage; do not weaken business tests or broadly re-pin SQL to hide accidental changes.

Use only new Financee_Offline-owned disposable resources for automated tests and a separate stable manual-review stack. Never run mutating tests against my existing source/review/production databases. Preserve other projects and all their Docker resources.

At each phase handoff provide the exact commit/build, local URL or installer artifact, safe test account/setup instructions, concise manual checklist, actual tests/results and remaining platform limits. Claims of Windows/Mac installation, signing, offline operation, backup restore or upgrade success require actual evidence. Missing machine access or credentials should be reported precisely at the affected release gate while completing other authorized work.

Do not push, create a remote repository, upload an artifact publicly, publish an installer or operate production until I explicitly instruct it. My local review approval alone is not push/publication permission. Keep code/source and backup responsibilities local as specified.
