# Financee Offline

Phase 1 local review build: **0.1.1-phase1**. Independent Django/PostgreSQL
single-device edition imported from confirmed application release `96fd8b9`.
Both reference systems remain read-only. No Git remote or publication exists.

Open **http://127.0.0.1:18766/home/** for an existing company. On a fresh
installation, start at **http://127.0.0.1:18766/setup/**. Create your
company and owner username/password. No default login exists. Each fresh installation
starts empty, apart from currencies, permissions, COA and cash sentinels.
After setup, use `/authentication/login/`; manage users/groups and General Settings
through Admin. Keep review data disposable until backups are implemented.

Implemented: public-only business database, singleton profile, first-owner setup,
local auth/permissions, retained serial financial SQL, local activity/Spotlight/
attachments, dark mode and the source purchase layout. Tenant registry, tenant
schema provisioning, subscriptions/SMTP/report email and cloud operations removed.

This is not yet a customer installer or a certified offline release. CDN assets
remain for Phase 3; backup/restore, launchers, platform installers and upgrades are
later gated phases. See [phase handoff](docs/PHASE1_REVIEW.md),
[product requirements](OFFLINE_PRODUCT_SPEC.md), [approved plan](IMPLEMENTATION_PLAN.md),
[source provenance](SOURCE_PROVENANCE.md) and [architecture](docs/ADR-001-single-company.md).

Developer controls (run from this repository with Docker already available):

```sh
python3 runtime/dev.py init
python3 runtime/dev.py build
python3 runtime/dev.py up
python3 runtime/dev.py status
python3 runtime/dev.py stop
```

These preserve the database/media and operate only the selected Financee_Offline
stack. Startup never pulls. Fresh machines must first obtain the exact dependency
images pinned in runtime/compose.yml; installation/payload automation is pending.

Disposable automated-test stack (never point tests at review data):

```sh
python3 runtime/dev.py --stack test init
python3 runtime/dev.py --stack test up
python3 runtime/dev.py --stack test test
python3 runtime/dev.py --stack test business
python3 runtime/dev.py --stack test check
python3 runtime/dev.py --stack test stop
```

Real customer data, secrets, media, ZIPs and logs are ignored. Backups/ is only a
source placeholder. Uninstall/reset automation has not been implemented.
