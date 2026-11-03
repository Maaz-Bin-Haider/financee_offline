# Financee Offline

Current development installer **0.8.0-phase8**, schema 2; the existing bound
review business remains on **0.5.0-phase5**. This independent
single-device Django/PostgreSQL edition retains the confirmed financial engine.
Both reference systems remain read-only. Source is stored in
[financee_offline](https://github.com/Maaz-Bin-Haider/financee_offline) on
`codex/single-company-core`. No installer release has been published.

On this Apple Silicon review Mac, double-click **Financee Offline Development**
on the desktop. It opens the maintenance app and the existing review business at
http://127.0.0.1:18766/home/. Use the original owner login; AED and existing data
are preserved. Normal app use requires no terminal, checkout, Python, Git or Node.
The tested Docker images/runtime are already present on this development machine.

A fresh installation chooses an empty customer folder and creates its own company
and owner through setup. No default login or demonstration transactions exist.
Reference currencies, permissions, chart of accounts and cash sentinels are seeded.
The first backup waits until company setup is complete.

Implemented: one public business dataset/profile, local users and permissions,
company/currency/timezone/module settings, local assets and Unicode exports,
private attachments, activity/Spotlight, daily/catch-up verified ZIPs, candidate
recovery and a packaged desktop maintenance window. Tenant/SaaS/email/cloud
operations are removed. Original financial SQL and purchase layout are retained.

See [current desktop review](docs/PHASE5_REVIEW.md) and
[verification evidence](docs/PHASE5_RESULTS.json). **Stop for owner review before
Phase 6.** Windows targets, reboot/Docker-off hardware tests, installers,
notarization, upgrade/recovery packaging and publication remain gated work. The
Mac artifact is locally ad-hoc signed and is not a notarized customer release.

Developer controls require this repository and Docker; they are not customer steps:

```sh
python3 runtime/dev.py init
python3 runtime/dev.py build
python3 runtime/dev.py up
python3 runtime/dev.py status
python3 runtime/dev.py stop
```

Use `--stack test` for disposable tests, never review. Normal starts do not pull
images. All real data, runtime credentials, media, completed ZIPs, logs and generated
app/image/installer payloads are ignored. Customer data and backups are separate
from installed program files and retained when services stop.

[Approved plan](IMPLEMENTATION_PLAN.md) · [Product spec](OFFLINE_PRODUCT_SPEC.md) ·
[Project context](PROJECT_CONTEXT.md) · [Source provenance](SOURCE_PROVENANCE.md)

## Windows setup prototype (Phase 6)

An unsigned Windows x64 development installer and matching AMD64 runtime archive
have been built on a hosted Windows runner. Customer device testing remains pending. See
[the Phase 6 review and Windows build instructions](docs/PHASE6_REVIEW.md).
Windows 10 runtime qualification remains required and pending. The existing Mac
review app remains the Phase 5 build. Phase 7 development work is described below.

Saved local Windows delivery: `dist/Financee-Offline-Windows-x64-Development-60dc9a3.zip`
(about 931 MB), with the installer, matching runtime images and test instructions.
It is unsigned development software; Windows 10 runtime setup and real Windows
10/11 device acceptance remain pending. Build/source `60dc9a3`,
[successful development build](https://github.com/Maaz-Bin-Haider/financee_offline/actions/runs/41422916045).

## Apple Silicon development installer (Phase 7)

Saved local DMG: `dist/Financee-Offline-Apple-Silicon-Development-352b538.dmg`
(about 498 MB), including the native app and matching offline runtime images.
[Phase 7 review, install/removal steps and evidence](docs/PHASE7_REVIEW.md).
Native self-copy, empty setup, handoff, cancellation and data-retaining removal
checks pass on this Mac, along with 106 host and 38 core checks. It is ad-hoc
signed; Developer ID/notarization and fresh-device/reboot acceptance remain pending.
No production resources or review business data were changed. Stop before Phase 8.

## Manual upgrades (Phase 8)

Local Mac development DMG: `dist/Financee-Offline-Apple-Silicon-Development-b12e676.dmg`.
Install the versioned 0.8 app beside the previous app and choose Setup → Upgrade
Existing Business. The policy accepts schema-2 0.5/0.7 sources, preserves a paired
rescue and previous data/runtime, verifies a separate candidate and refuses
unreviewed migrations or downgrades. [Phase 8 tests and review steps](docs/PHASE8_REVIEW.md).

120 host checks, 38 post-upgrade core tests, five forced host exits and real
candidate/startup failure recovery pass on disposable data. Final native Mac
confirmation, cancellation, upgrade/login handoff and safe stop/exit pass on this
host. Windows/native reboot and signing/notarization acceptance remain pending. Stop before Phase 9. No installer was published.
