# Phase 1 manual review handoff

Build **0.1.0-phase1**, core commit `85dbfc842d277fa40a86098156d208873eaf9e40`.
Native Linux ARM64 image: `sha256:ac24994b508e6e4e47979ea12b11cd01fb665f520166e3aa456394c939c3f069`.
The final documentation commit follows this core commit; no application changes
are made by that evidence commit. Nothing has been pushed or published.

## Open and set up

Open http://127.0.0.1:18766/setup/ on this machine. The page is also open beside
the chat. Enter your company name, currency, optional display-symbol override,
timezone, owner username and a strong password. No default password exists.
The review database has **zero users, profiles, journals, items or serials** at
handoff; only necessary reference seeds exist. Complete setup to access Financee.
Log in later at /authentication/login/. Owner-only Admin manages General Settings,
local users and groups. This development installation is for disposable review.
Automatic backups and recovery do not exist yet.

## Manual checklist

1. Complete onboarding; confirm the company name and owner login. Reopen /setup/
   and confirm it does not create another business.
2. Add a vendor, customer and item; purchase a serial, sell it and exercise both
   applicable return workflows. Check stock, party balances and reports.
3. Create a normal local user with selected rights; verify allowed screens work
   and disallowed actions/reports/admin remain unavailable. Use deactivation to
   preserve actor attribution.
4. Check Spotlight, session-scoped recents, Team Activity and attachment download
   permissions. Toggle dark/light mode and inspect the purchase layout at desktop
   and narrow widths. The original purchase template is retained unchanged.
5. Confirm no tenant/company registry, subscription locks or Report Email menu or
   endpoint appears. General Settings is the single local business profile.

Stop here for owner review. Full currency/identity labels are Phase 2; complete
asset/font vendoring and cold disconnected verification are Phase 3. Later phases
remain separately gated. Local review approval does not authorize publication.

## Actual verification

- 20 local-core tests passed against freshly migrated PostgreSQL test databases,
  including public-only objects, empty onboarding, owner validation/CSRF, retained
  screen rendering, action/report permissions, inactive login, singleton/currency
  database guards, activity actor snapshots/append-only constraints, authenticated
  attachment byte round-trip, rate limits and Spotlight session capabilities.
- 328/328 business assertions passed across 11 ported modules: parties, items,
  purchases, sales, returns, cash movements, opening balances/stock, owner equity,
  month close, reports and draft reservation/conversion/return lifecycle.
  There were no XFAIL, XPASS or skipped checks in this run.
- Independent Decimal assertions reconcile exact purchase/sale totals, revenue,
  COGS, balanced journal lines, stock and sale-return reversal. No financial
  numeric precision or expected business arithmetic was changed.
- Source-derived SQL contract: 190 retained functions match exact confirmed source
  bodies and attributes; 12 email functions removed; 2 profile guards added. The
  comparison used a new disposable reference database, never a source database.
- 41 frontend assertions passed: 11 theme, 7 Spotlight, 15 activity and 8 export
  helpers. The removed subscription-page theme assertion was replaced with setup.
- Django system checks passed and makemigrations --check reports no drift.
  Repeated startup applies no extra migrations and preserves the empty review state.
- Browser inspection confirms the first-run form and shared dark theme render.
  No owner credentials were entered by the agent into the review installation.

Machine-readable evidence: [PHASE1_RESULTS.json](PHASE1_RESULTS.json).
Full local command logs are ignored under .runtime/test/Logs and
.runtime/review/Logs. Frontend checks are reproducible with node tests/test_*.js
for the four retained JS files. See tests/README.md for deliberate test replacement.

## Resource and source isolation

Stable project: financee_offline_review, customer folder .runtime/review,
PostgreSQL volume financee_offline_review_database. Preserve these for review.
Automated-test project: financee_offline_test, separate credentials/data/volumes.
Temporary reference/test databases were removed by their own verification tools.
Developer controls are in README and never remove volumes or shared Docker/WSL.
Only Nginx publishes a host port: **127.0.0.1:18766**. DB/cache ports are internal;
the web app has no Docker socket mount. Approximate idle container memory was
143 MiB before final handoff, excluding Docker's VM/host overhead; this is not a
customer minimum-spec certification.

Both source checkouts are clean and untouched. Production source HEAD remains
0ea97a2253f0ed12213a24832393e223eed71e21; comparison reference HEAD remains
ea1f0194f2e4d2b0ec6e120086b29276c4d99365. No source branch/config, workflow,
container, database, backup or deployment was operated. No remote is configured
in this new repository. Source Git commands were read-only.

## Remaining platform and product limits

Verified here: native Linux ARM64 core runtime on an Apple Silicon host running
macOS 26.5.2. This is not evidence of a native customer app or installer.
Windows10/11 x64 installations, maintained Windows10 runtime choice, AMD64 image
payload, Mac DMG/signing/notarization, desktop GUI, cold offline workflows, ZIP
backup/restore and manual upgrade recovery are unverified and remain their own
phase gates. Source screens still contain external assets and hard-coded currency
presentation awaiting Phases 2–3; do not certify this as fully offline yet.
See ADR-002-runtime-platforms.md for current official support/licensing sources
and the Windows10 Engine-in-WSL candidate that still requires real-machine tests.
