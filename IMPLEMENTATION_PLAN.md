# Financee_Offline — implementation and delivery plan

Prepared: 2026-10-26, Asia/Karachi. Status: planning only; implementation belongs in a new project and repository.

## 1. Confirmed product requirements

| Item | Decision |
| --- | --- |
| Product/repository | Financee_Offline, independent of both existing repositories |
| Business scope | One company per installation, one personal device; remove multitenancy |
| Users | Preserve login, local users, groups and existing action/report permissions |
| Commercial model | One-time purchase; no SaaS subscription expiry, online activation, vendor kill switch or remote licence check |
| Internet | Available for installation and optional manual updates; normal application use must work disconnected |
| Devices | Windows 10 x64, Windows 11 x64 and Apple Silicon Macs; no Intel Mac or Windows ARM delivery in v1 |
| Launch | Desktop icon starts the local services and opens the default browser after readiness |
| Initial data | Empty customer system; no migration from hosted customers in v1 |
| Settings | Company information and configurable currency/symbol in Admin → General Settings |
| Backups | Automatic daily ZIP; keep the latest 30 completed normal backups; Backup Now and Restore Backup controls |
| Backup contents | Database, uploaded attachments and the configuration/version metadata required for recovery |
| Backup ownership | Local customer responsibility; no vendor storage, upload, monitoring or remote recovery service |
| Updates | Customer runs a new installer manually; preserve their data and settings |
| Report Email | Remove it, its scheduler, SMTP configuration and related UI/endpoints |
| Source boundaries | Financee_Multitenant_Production and Accounting-Plus-Inventory-System are read-only; production must not be operated or modified |
| Delivery discipline | Frequent meaningful commits, local review gates, no pushes or publication without explicit owner authorization |

Retain all other applicable Financee features: serial purchases/sales/returns, cash flows, parties/items, drafts, opening balances/stock, owner equity, month close, reports, attachments, dark mode, Spotlight and Team Activity. No GST port, inventory-mode redesign, cloud synchronization or unrelated visual redesign.

## 2. Source baseline and repository boundary

Use the most recently owner-confirmed production application as the reference. The last confirmed release in this conversation is `96fd8b9dc4105870bc76cbb2b443bf5c36da2d66`, workflow `40122187390`, including the corrected purchase layout. The source checkout also has documentation-only confirmation commit `0ea97a2`. Verify the intended application snapshot read-only before copying; record the exact chosen SHA and file hashes in `SOURCE_PROVENANCE.md`.

Create `/Users/swisstech/Development/Financee_Offline` as a new independent Git repository in the new project. Copy a deliberate tracked-file snapshot, not an existing working checkout wholesale. Do not copy `.git`, local secrets, customer dumps, media, generated files, Docker volumes or environment files. Remove inherited production-deployment workflows and operational cloud/SSH/backup-upload tooling before the first push could run them. Keep financial SQL provenance without making the new product depend on source paths.

Do not edit either source checkout, change its branch, fetch into it, run its mutating tests, reuse its runtime credentials, or operate any existing deployment/review stack. Read-only Git/API inspection is allowed. Build/test only from the new repository, with Financee_Offline-owned resource names and loopback ports. Do not use a linked Git worktree from either source.

Initial repository documents: `README.md`, `PROJECT_CONTEXT.md`, `SOURCE_PROVENANCE.md`, `OFFLINE_PRODUCT_SPEC.md`, `IMPLEMENTATION_PLAN.md`, `BACKUP_RESTORE.md`, `INSTALLATION_GUIDE.md`, `RELEASE_CHECKLIST.md`, and focused architectural decisions. The first new-repository commit should capture the safe import and these boundaries.

## 3. Target architecture

### Application and database

- Keep Django and PostgreSQL, including the proven SQL accounting, serial/inventory and report functions. Do not replace PostgreSQL with SQLite or move accounting logic into Python.
- Use one application database with one business dataset in `public`, alongside Django auth and local settings. First check object names/dependencies for collisions. No company registry, Membership routing, tenant schemas, provisioning, schema-family selection or request-driven search-path switching remains.
- A singleton `GeneralSettings`/business profile stores name, contact/print details, currency, optional symbol override, timezone and applicable installation-level module switches. Prevent a second business profile in the database and admin.
- All local authenticated users belong to the same business. Preserve route/action/report permissions, active-user checks, groups, CSRF and escaping. Remove membership requirements without accidentally dropping the permission checks currently enforced by tenant middleware.
- Adapt attachments to one installation-local media root; preserve authenticated downloads and file validation. Adapt Spotlight permissions/session-scoped recents and Team Activity rosters/recording to local users. Keep activity append-only and retain existing accounting guards.
- Remove subscription models/guards/banners, billing administration, subscription email and Report Email. Remove their routes, settings, permissions, source references and report worker; do not merely hide their menus.
- Start with all retained business modules available, while keeping user permissions authoritative. If module switches remain, they belong to local General Settings, not a per-company plan. Dark mode stays globally available.
- Establish new, coherent offline migrations and a versioned single-company SQL bootstrap/upgrade path. Because this is a fresh product, do not ship the legacy multitenant retirement/reversal machinery as the offline installer database history.

Necessary system/reference data is allowed: chart of accounts, currency catalogue, permissions and required cash-party sentinels. Do not seed demo invoices, stock, financial journals, sample customers or universal default passwords.

### Runtime services

Use a Financee_Offline-only Compose definition: PostgreSQL 16, Django/Gunicorn, Nginx, Redis initially where needed by existing cache/permission/rate-limit behavior, and a local backup scheduler. The report-email worker is absent. Tune resources for a personal computer instead of copying the EC2 settings.

Build native `linux/amd64` app/dependency images for Windows x64 and `linux/arm64` for M-series Macs. Distribute tested image archives as installer payloads so customers need no Git, Python, Node, compiler, registry credentials or source checkout. Pin release tags/digests and checksums in an architecture-specific manifest; do not use floating `latest` at runtime.

Only Nginx publishes an HTTP port on `127.0.0.1`. PostgreSQL and Redis have no host ports. Use a stable, collision-checked local port. The launcher must never silently open a different product's service if the port is occupied. Do not mount the Docker socket into the web app. Keep locally generated runtime credentials across updates; never reuse production credentials.

### Launcher and installers

Recommended initial approach: a small Python launcher/setup controller with a simple packaged GUI, frozen with PyInstaller. It starts Docker when necessary, waits for readiness, starts only the product's services, shows progress/errors, and opens the browser. The same controller owns local maintenance and restore orchestration. Validate this packaging approach early before building both installers. PyInstaller packages its interpreter, but each OS/architecture needs its own build. [PyInstaller operating model](https://pyinstaller.org/en/stable/operating-mode.html).

Windows delivery: a conventional setup EXE, for example Inno Setup around the packaged controller, with desktop and Start Menu shortcuts. Mac delivery: an ARM64 app/setup bundle in a DMG, with an Applications installation and desktop alias. Upstream packaging/distribution terms must be reviewed before selecting release tooling. [Inno Setup capabilities and terms](https://jrsoftware.org/isinfo.php).

## 4. Customer installation and everyday flow

Installer flow:

1. Explain the local product, supported device requirements and customer-managed backups.
2. Detect OS/build/architecture, virtualization, RAM, disk space, existing Docker and an existing Financee_Offline installation. Do not modify another Docker project's containers/volumes.
3. On Windows, set up the required WSL/runtime path using a guided workflow, with resumable state if a reboot is necessary. Do not require a customer-created Linux account/terminal session when the selected runtime can avoid it.
4. Obtain prerequisite installers from official verified locations. Show required consent/OS prompts instead of accepting third-party terms on the customer's behalf. Reuse a compatible existing Docker installation.
5. Download the matching Financee release payload, verify checksums, import all required images, establish owned volumes/configuration, and initialize the empty single-company database once.
6. Persist an installation ID, paths, release/version metadata and the selected port. Re-running setup repairs/reuses this installation rather than resetting it.
7. Create the Financee Offline desktop icon and open first-run onboarding after service readiness.
8. Onboarding asks for company name, currency/symbol, local administrator credentials and confirms the local backup folder. It can resume after interruption and refuses a second business.

Daily use: double-click the icon → short starting/progress window → browser login page → existing Financee workflow. If services are already running, reuse them and open the existing installation. Normal launch never pulls images, checks an online licence or needs internet.

The launcher includes Open Financee, Backup Now, Restore Backup, Open Backups Folder, status/help and Stop Financee. Stopping Financee stops only its stack, never Docker globally. Closing a browser tab does not terminate the database. Offer a clear first-run choice for starting Financee at OS sign-in; reopening manually remains supported.

Runtime packages/images must already be cached after installation. Disconnecting the internet, restarting the computer and launching the application is an acceptance test.

## 5. Platform feasibility and distribution prerequisites

Target Windows 10/11 x64 with WSL 2 where applicable. Current Docker documentation lists build/edition, virtualization and memory prerequisites, and restricts Desktop support to Windows versions within Microsoft's servicing policy. Therefore Windows 10 compatibility needs an explicitly tested OS/runtime pair; do not promise every Windows 10 installation or silently pin an obsolete unsupported Desktop build. Phase 0 must establish the delivery path, including whether a maintained Docker Engine-in-WSL approach is needed for the intended Windows 10 machines. If no viable tested path exists, report that release blocker rather than silently dropping Windows 10. [Docker Windows requirements](https://docs.docker.com/desktop/setup/install/windows-install/).

WSL enablement can require elevated permission and a restart; installer state must survive it. BIOS virtualization changes may require customer action. [Microsoft WSL installation](https://learn.microsoft.com/en-us/windows/wsl/install).

Apple delivery is native ARM64, on macOS versions supported by the selected Docker release; do not depend on Intel emulation. [Docker Mac requirements](https://docs.docker.com/desktop/setup/install/mac-install/).

Provide a public-distribution signing/notarization path for the Mac app/installer, including a stapled ticket, and appropriate Windows signing. Signing credentials/accounts are owner-provided release inputs; unsigned development artifacts must be labelled as such. Do not bypass Gatekeeper, disable protections or describe an unsigned development artifact as a smooth customer-ready release. [Apple Developer ID and notarization](https://developer.apple.com/developer-id/).

Docker Desktop has its own commercial eligibility/terms, independent of the Financee one-time purchase. Prefer downloading Desktop from Docker during setup rather than assuming redistribution rights. Do not bake automatic agreement acceptance into the installer. [Docker Desktop licensing](https://docs.docker.com/subscription-billing/desktop-license/).

Initial engineering targets: 8GB total RAM minimum subject to measurements, 16GB recommended, and an SSD/free-space requirement measured with realistic data and backup/upgrade headroom. These are proposed product targets, not claims that every device at those limits has already been certified.

## 6. Currency and admin General Settings

Provide a currency catalogue selector and an optional custom display symbol (for example PKR/Rs, USD/$, AED, EUR/€). Store code and symbol separately; do not alter the global catalogue just to customize one installation's symbol. Use the local setting consistently in transaction totals, reports, dashboard, PDF/print and CSV/Excel labels. Remove hard-coded PKR/AED assumptions from active application presentation paths.

Keep existing financial numeric precision, arithmetic and rounding. This is one base accounting currency, not multi-currency bookkeeping or an FX conversion module. Choose/change the base currency before the first financial posting; retain the source system's base-currency lock after activity. A display-symbol override can remain editable without changing the underlying currency or amounts; make that distinction explicit in General Settings.

Bundle fonts capable of displaying supported symbols in the UI and PDF/print. Verify representative Unicode symbols, negative values, zero, large amounts and exports; avoid missing-glyph boxes. Preserve administrator-only settings and current permissions. Timezone defaults sensibly during setup and can be selected locally for backup/activity dates.

## 7. True offline assets and feature audit

Vendor all runtime JavaScript/CSS, fonts, icons, PDF/Excel dependencies and any other CDN resources with version/license metadata. Scan templates, CSS imports, JS and runtime requests. Core operations, login, settings, reports, exports, printing, Spotlight and Team Activity must make no external requests when disconnected. Installation and explicitly requested updates are separate network operations.

Remove Report Email entirely, including related settings, scheduler service, transport dependencies where unused, feature flags, permission seeds, navigation/search targets and tests. Printed company/customer email contact fields may remain as ordinary business information; they do not imply outbound messaging.

Retain the current purchase sizing fix and dark-mode behavior. Do not port the single-company reference project's different GST/lookup/accounting behavior incidentally.

## 8. Customer data and ZIP backups

Keep installed program files separate from a writable customer-data folder, conventionally `Documents/Financee_Offline` (or a folder selected during setup). This satisfies the requested separate Backups folder without requiring a Git checkout or writable Program Files/Applications directory.

Example customer layout:

```text
Financee_Offline/
  Config/       installation/version/path configuration
  Data/         uploaded media and active-generation metadata
  Backups/      completed ZIP recovery files
  Logs/         bounded local diagnostic logs
  Cache/        downloaded installer/image payloads
```

The live PostgreSQL files should reside in a product-owned Docker volume for filesystem compatibility/performance; they are not the customer's backup. Record the volume identity in the local installation configuration. Do not copy live PostgreSQL directories from Docker's internal disk as a backup.

Inside the development repository, keep a `Backups/` placeholder if desired but ignore its real contents, along with customer Data, Logs, runtime config/secrets and build output. Actual ZIPs are never committed or uploaded. Code/templates/scripts are what gets committed frequently.

Each recovery point is a single ZIP, for example:

```text
Financee_Offline_Backup_2026-10-26_183000_<unique-id>.zip
  manifest.json       backup format, product version, DB version, timestamp/timezone
  database.dump       pg_dump custom-format full application database
  media/              uploaded attachment files
  configuration.json  portable business/configuration values required for recovery
  checksums.json      hashes and sizes of archive members
```

Use a PostgreSQL-version-compatible `pg_dump`/`pg_restore` inside the controlled runtime. Logical archives support recovery across the x64/ARM64 targets; test that path rather than archiving raw Docker volumes. [PostgreSQL dump formats and portability](https://www.postgresql.org/docs/16/app-pgdump.html).

Daily scheduling:

- One scheduled successful backup per local calendar day while Financee is running; catch up on next launch if the device/services were off or asleep. No promise of a backup while the computer is off.
- A lightweight backup worker uses the same backup engine as Backup Now. Use a cross-process lock so startup, manual and scheduled jobs cannot collide.
- Keep the latest 30 completed normal ZIPs. An interrupted/failed backup never removes a previous valid backup. Protect pre-update/pre-restore rescue copies until their operation is verified.
- Write to staging, verify dump/archive integrity and member checksums, then atomically publish the final ZIP; rotate only after verified success. Support ZIP64 for large datasets.
- Coordinate a bounded write pause/drain with attachment changes to capture a mutually consistent database/media pair. Release maintenance state automatically on failure. Do not assume a database-consistent pg_dump alone makes filesystem media consistent.
- Show last success, filename, folder, next due state and actionable failure messages. Folder missing, disk full, access denied and partial writes must not be silent.

No encrypted-passphrase workflow is required for v1; deliver ordinary ZIPs as requested. Keep integrity checks, upload/path validation and safe archive extraction because corrupt or malformed files must not destroy customer data.

## 9. Restore, manual update and uninstall

Restore is a guided local-owner maintenance operation from the launcher. The admin can show backup status and Backup Now; the launcher supplies Restore Backup and Open Backups Folder so the customer can recover even when the web app cannot start. Web controls remain administrator-only; recovery assumes control of the customer's local device.

Restore sequence: choose ZIP → validate format/version/checksums/paths/available space → explain replacement and confirm → make a rescue backup when the current installation is healthy → pause owned services/writes → restore into a candidate database/media generation → check users, permissions, financial invariants and attachment links → switch the active installation configuration → health-check and reopen login. Retain the previous generation until success. A failed candidate must leave or reinstate the old installation. Expire sessions/cache/recents after restore.

Do not delete/replace the active database before the candidate is validated. Refuse incompatible future formats/versions and missing required members. Do not overwrite local Docker credentials from an old backup; restore business data using the destination installation's runtime configuration. Preserve any required application keys if future storage actually depends on them.

Manual update sequence: identify installed release → validate target manifest/compatibility → verify downloads → make ZIP rescue backup → stage new version/images → apply explicit, repeatable upgrades → run accounting/data/attachment checks → switch/restart and verify. A repair/reinstall must not rerun first-time customer initialization. Keep the previous release for recovery. Do not claim that running an old image reverses an incompatible database migration; restore a verified paired data/runtime generation when required.

No background auto-updater, telemetry, vendor backup upload or online licence heartbeat. Once a release is installed, starting it does not contact a registry. Uninstall removes only product-owned program/runtime resources selected for removal, preserves customer data/backups by default, and never removes shared Docker/WSL installations or other projects. Data deletion is an explicit separate customer action.

## 10. Phased implementation and review gates

| Phase | Work and concrete deliverable | Acceptance gate |
| --- | --- | --- |
| 0 — Foundation | New repository, safe source snapshot/provenance, product spec, platform/runtime feasibility and isolated resource layout | Sources unchanged; inherited production workflows absent; record viable Windows 10/11 and Mac runtime strategy |
| 1 — Single-company core | One database/business profile, empty bootstrap/onboarding, local users/permissions; remove tenancy/subscriptions/email | First working local app; no tenant switching/second company; core financial/serial regression passes; stop for owner review |
| 2 — General Settings | Company identity, currency/symbol, timezone and local module settings; all UI/export currency labels | Currency fixtures and permissions pass; no changed accounting math; owner reviews admin and exports |
| 3 — Offline completeness | Local assets/fonts, final email/online dependency removal, adapted Spotlight/activity/attachments | Restart and full workflow with internet disconnected; no external runtime requests; owner reviews |
| 4 — ZIP backup/recovery | Daily/catch-up worker, shared backup engine, retention/status, manual backup and candidate restore | Corrupt/missing/disk-full/interrupted cases; database/media round-trip; users/permissions/append-only history and books preserved |
| 5 — Desktop launcher | Packaged local controller, first-run flow, start/open/status/stop, maintenance controls and shortcuts | No terminal or developer tools; Docker-off/already-running/double-click/port-collision/reboot cases pass |
| 6 — Windows package | x64 setup/downloader, prerequisite workflow, reboot resume, desktop/Start shortcuts, repair/uninstall | Fresh real Windows 10 and 11 target tests, with and without Docker; no changes to other Docker projects |
| 7 — Apple Silicon package | Native ARM64 DMG/app, first-run installation, desktop alias, signing/notarization pipeline | Fresh supported M-series Mac tests; no Rosetta dependency; correct offline launch and preserved data |
| 8 — Manual upgrades | Installer update mode, paired rescue backup, version/schema checks, failure recovery and downgrade policy | Upgrade populated old release and interrupt it; balances, serials, users, settings, activity and attachments survive |
| 9 — Distribution | Separate CI/artifacts/manifests/notices, tested installer releases, plain customer instructions | Full release matrix and installation/recovery evidence; owner authorizes publication; no cloud-production deployment jobs |

Phase 0 is preparation and need not create a separate review delay. The new agent can proceed through Phase 1 to the first working isolated single-company build, then stop for manual review. Each later phase is a concrete review gate. The owner may explicitly authorize combining phases. Never infer permission to push/publish from a passed local review.

## 11. Verification matrix and release evidence

- Relevant SQL/business regression: purchases, sales, both returns, stock/reservations, drafts/conversions, cash/credit, opening stock/cash, owner equity, close/reverse, ledgers and all reports. Reconcile journal balance, party balances, cost/stock coherence and existing source function invariants.
- Auth: first owner setup, normal login/logout, groups, read-only users, denied actions/settings, inactive users and source-record link permissions. Removing tenancy must not accidentally make users superusers.
- Single-company proof: no Company/Membership registry, tenant schemas or tenant selection in supported runtime; one profile, one dataset, no report-email/subscription endpoints or worker.
- UI: both themes, current purchase layout, normal desktop/phone widths, Unicode currency labels, PDF/CSV/Excel exports and printing without internet.
- Backups: daily/catch-up, concurrency/locking, ZIP corruption, disk failure, media consistency, 30-copy retention, whole-install recovery and cross-architecture logical restore.
- Installer lifecycle: fresh install, interrupted/repeated install, prerequisite consent, reboot, upgrade, repair, uninstall, reinstall, changed paths with spaces/Unicode, full disk, occupied port, duplicate click and failed Docker startup.
- Network: disconnected first launch after completed install, cold reboot offline, no CDN/SMTP/registry/activation calls during normal use. No LAN listener for the application/DB/cache.
- Isolation: source Git/status unchanged; no existing Docker containers, networks, data, images or host configuration modified by test cleanup. Never use global prune commands.

Build Windows launchers/installers on Windows x64 and Mac launchers/installers on Apple Silicon. Use appropriate OS jobs for packaging; a Windows Server CI build is not proof that Docker Desktop installation works on customer Windows 10/11. Require actual target machines or suitable dedicated virtualization for final install/reboot/restore tests. If target hardware or signing credentials are unavailable, label the corresponding release gate pending; never invent a passing result.

For each phase, commit code with related migrations/tests/version manifests and any deliberate contract changes, update `PROJECT_CONTEXT.md`, record local results and provide a reviewable build. Keep commits small/coherent; no empty activity commits, rewritten dates, secrets, generated ZIPs or installer binaries in source history. New product CI may build/test/upload artifacts within the new repository only. Remote repository creation, pushes and release publication require explicit owner instructions.

## 12. Definition of done

A nontechnical customer can install on a tested target, complete any unavoidable OS/Docker consent/reboot prompts, set up an empty business/admin, select their currency, double-click the desktop icon, log in, transact/report/export with internet disconnected, obtain automatic local ZIP backups, restore a ZIP through the maintenance UI and install a later version without losing data. The customer controls backup storage. The existing hosted software and both source repositories are unchanged throughout.

Release prerequisites to track rather than invent: tested Windows 10 runtime compatibility; access to the target OS/device matrix; owner-provided signing/notarization credentials for polished distribution; approved download hosting and third-party distribution terms. These do not prevent drafting the new product or implementing its isolated core.
