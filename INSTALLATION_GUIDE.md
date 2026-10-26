# Phase 2 developer review

Build 0.2.0-phase2, schema 2. This is a local Docker review build, not a desktop installation release.
Open http://127.0.0.1:18766/setup/ on this machine. Choose company, currency,
optional display symbol, timezone, owner username and a strong password.
There is no shipped administrator password. Setup cannot replace existing accounts.
Login later at /authentication/login/. Owner-only Admin includes General Settings,
Users and Groups. Non-owners need individually assigned action/report permissions.
Deactivate accounts rather than delete their financial attribution.

Use runtime/dev.py as described in README for start/status/stop. Its review and
test configurations and credentials are separate; the review URL stays 18766.
Program source is here; writable development data is .runtime/review with Config,
Data/media, Backups, Logs and Cache. PostgreSQL volume identity is
financee_offline_review_database. Preserve that volume and configuration. Do not
remove it as a disposable test database. The separate disposable test volume is
financee_offline_test_database. No source or other project volume is operated.

Backups are not implemented at this gate. Do not use the review build as your only
copy of business records. Customer setup, Documents folder selection, desktop
shortcut, prerequisite consent/reboot, repair and data-preserving uninstall are
pending Phases 5–7. No Windows or DMG installer exists at Phase 1.

Phase 2 settings and exports are ready for review; see docs/PHASE2_REVIEW.md.
A developer rescue point exists under the ignored review Backups folder; the
customer backup/restore controls and scheduler are still pending Phase 4.
