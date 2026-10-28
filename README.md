# Financee Offline

Local desktop review build **0.5.0-phase5**, schema 2. This independent
single-device Django/PostgreSQL edition retains the confirmed financial engine.
Both reference systems remain read-only. No remote or public release exists.

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
