# Financee Offline context

2026-10-26, Asia/Karachi. Authorized work: Phase 0 plus Phase 1, then stop for
owner manual review. Later phases need their own review gates. Never infer push,
remote creation or publication permission from local review approval.

Repository: /Users/swisstech/Development/Financee_Offline, independent Git history,
branch codex/single-company-core. Both existing applications are read-only.
Source application snapshot: 96fd8b9dc4105870bc76cbb2b443bf5c36da2d66, confirmed
workflow 40122187390; clean source HEAD 0ea97a2253f0ed12213a24832393e223eed71e21
is documentation only. See SOURCE_PROVENANCE.md and SOURCE_FILES_SHA256.json.
Approved request and full plan are preserved verbatim in this repository.

Implemented: one public dataset with Django auth/local settings, singleton profile
and owner onboarding, fresh local migrations/schema v1, retained business SQL,
module/action/report permissions, local activity and attachment storage. No
Company/Membership models, tenant provisioning/switching, subscriptions, Report
Email, SMTP scheduler, production workflows or operational source tools remain.
No universal password, sample transactions or imported customer data are seeded.
Core settings/currency guards are present because onboarding requires them; the
complete currency/identity presentation work remains Phase 2.

Stable review project financee_offline_review: loopback 18766, own database/static
volumes and independent ignored .runtime/review customer folder/configuration.
Automated tests use financee_offline_test only, plus temporary test DBs within it.
DB/cache have no host ports and no app container mounts Docker's socket.
No source credentials, application images or live databases were used.

Evidence: ported business suite 328/328 assertions across 11 modules; independent
Decimal journal/revenue/COGS/serial-return invariants; all retained screen templates;
local auth, singleton, currency lock, activity append-only, private attachment and
session capability checks. Confirmed source contract: 190 unchanged SQL functions,
12 removed email functions, 2 added profile guards. Final image checks and exact
handoff build are recorded in docs/PHASE1_REVIEW.md.

Remaining gates: Phase 2 full identity/currency labels; Phase 3 all local assets/
fonts and cold disconnected checks; Phase 4 ZIP backups/candidate restore; Phase 5
native GUI launcher prototype; Phases 6/7 real Windows10/11 and ARM64 Mac installers,
prerequisite consent and signing; Phase 8 safe upgrade/recovery; Phase 9 release CI
and explicitly owner-authorized artifacts. No full-offline, backup, installer,
notarization, x64 or upgrade success is claimed. See ADR-002 for current official
platform constraints and the unverified maintained Engine-in-WSL Windows10 path.
