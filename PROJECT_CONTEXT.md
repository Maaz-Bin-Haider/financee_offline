# Financee Offline context

2026-10-26, Asia/Karachi. Owner authorized Phase 3 after Phase 2 review. Phase 3 local assets and
attachment/activity correction are implemented; final review deployment is pending.
Stop at the Phase 3 owner gate after verification.
Later phases retain their individual review gates. No push/publication authorized.

Independent repo /Users/swisstech/Development/Financee_Offline, branch
codex/single-company-core. Both source systems remain read-only and unchanged.
Confirmed application baseline 96fd8b9dc4105870bc76cbb2b443bf5c36da2d66, workflow
40122187390; source HEAD 0ea97a2253f0ed12213a24832393e223eed71e21 is documentation only.
Provenance and original imported hashes remain in SOURCE_PROVENANCE.md and
SOURCE_FILES_SHA256.json. Approved requirements/plan are preserved locally.

Current review build **0.2.0-phase2**, schema **2**, core commit c5e5aeca6cd78be98442f6364337c40b468f9028.
Image sha256:1d730046686324be95151e1e77f7149d0dd2365de3de22e464976cb2133624e1 (Linux ARM64).
Review http://127.0.0.1:18766/; owner General Settings at
/admin/local/generalsettings/1/change/. Existing company, AED, timezone, users,
financial/media counts and login preserved; all 24 local modules enabled.
No universal password or sample business data is installed.

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
and ignored. Developer pre-Phase2 rescue ZIP retained under .runtime/review/Backups;
it is not the Phase 4 customer backup implementation or a restore certification.

Remaining gates: Phase 3 complete local assets/cold offline verification; Phase 4
scheduled ZIP backups and candidate restore; Phase 5 native launcher; Phases 6/7
real Windows10/11 x64 and signed/notarized Apple Silicon installers; Phase 8 safe
manual installer upgrades/recovery; Phase 9 release CI/distribution with explicit
owner authorization. No Intel Mac/Windows ARM package in v1. Current fonts cover
catalogue currency symbols, not every possible writing system. CSV is Excel-readable;
no new native XLSX writer or Excel-app verification is claimed. Keep customer data,
media, secrets, logs, ZIPs and installer payloads out of Git. Never operate sources.
