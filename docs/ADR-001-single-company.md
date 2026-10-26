# ADR 001: one local public dataset

Accepted 2026-10-26 for Phase 1.

Django auth, sessions, currency reference data, singleton local_generalsettings,
and all serial financial objects share `public` in one PostgreSQL 16 database.
There is no tenant registry, membership, provisioning command, schema-family
selection, tenant verification cache or request-driven search-path change.
Connections explicitly use public; HTTP headers/query strings cannot select it.

The source template was loaded into Financee_Offline's disposable PostgreSQL,
then canonicalized with PostgreSQL 16 pg_dump into local/sql/0001_business.sql.
Only COA and the required Cash Sale/Cash Purchase sentinels are seeded. No owner,
customer, item, stock, invoice or journal is preloaded. Offline schema v1 starts
with fresh local migrations; legacy retirement/reversal migrations are absent.
Migrations fail on pre-existing business-object collisions instead of overwriting.
A fresh database containing Django auth/local objects migrated successfully.

The source SQL was independently loaded from the exact provenance-hashed release
into a separate disposable reference database. All 190 retained function bodies,
identities, result types, volatility, strictness and security-definer settings
match. Twelve report-email functions are deliberately absent. Two profile guards
are added. The source-derived contract in tests/sql_source_contract.json is
checked on every fresh local-core test database. No accounting expectations
were re-pinned to the new implementation.

LocalAccessMiddleware explicitly retains module permission and rate checks;
action-specific permissions remain in business views. Local groups and inactive
account checks remain. Every retained module defaults available. Admin remains
superuser-only; user deletion is disabled in favor of deactivation. Onboarding
uses validated owner-chosen credentials, CSRF and a transaction advisory lock;
existing accounts prevent accidental reinitialization. Profile PK/check enforce
one company; admin cannot add/delete it. Database guards protect deletion and
base-currency changes after journals exist; symbols remain cosmetic.

Spotlight targets still check permissions; local user/session scopes invalidate
recents across sign-in changes. Activity resolves a fresh local actor and records
username snapshots in append-only SQL. Rosters include local accounts and historic
snapshots. Attachments use a fixed installation media namespace and authenticated
routes. Source-record capability checks, path checks and upload limits remain.
Legacy cross-company attribution backfill is removed because v1 starts empty.

Phase 2 still owns the complete company identity/currency presentation audit and
installation-level optional module controls. Phase 3 owns CDN/font vendoring and
cold disconnected workflow verification. Phase 4 owns coordinated ZIP recovery;
this Phase 1 build deliberately supplies no pretend backup scheduler.
