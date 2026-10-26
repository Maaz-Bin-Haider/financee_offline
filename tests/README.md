# Offline verification

Only the Financee_Offline disposable stack is an automated-test target.
The business harness refuses every database name except `financee_offline_test`.
No source database/remote/tenant discovery remains.

Preserved suite: parties, items, purchases, sales, returns, cash/contra, opening,
owner equity, month close, reports and the draft SQL lifecycle. Domain assertions
are inherited without financial expectation changes. Old tenant, subscription,
SMTP, cleanup/reversal/deployment assertions are deliberately removed. Their
applicable replacement coverage lives in `local/tests.py`: public-only objects,
singleton/profile/currency guards, no removed routes/models/permissions, local
onboarding, local authorization, activity and attachments. Draft HTTP permission
checks move there; draft SQL tests remain. Frontend unit checks remain under tests/.

The inherited harness marks some source-known defects XFAIL/XPASS; those must be
reported separately, never counted as normal passes. Independent Decimal-based
journal/stock/profit checks supplement those source expectations.

Phase 2 adds validated local module settings, owner editor/currency lock cases,
unchanged reserved-stock guards, SQL/Python business timezone and UTC/DST instant
round-trip checks. `test_currency_concurrency.py` creates/removes only its own
explicit offline race database. `test_business_exports.js` exercises actual PDF/CSV
export generators using developer-only jsPDF/autotable dependencies. Font build
coverage and notices live in static/fonts/financee; runtime needs no FontTools.

## Phase 3 offline presentation

`python3 tests/test_offline_assets.py` checks vendored hashes/licenses, local
resource targets, dependency ordering and runtime isolation settings.
`python3 tests/test_offline_http.py` runs **inside the test web container only**;
it refuses other databases, creates unique disposable fixtures, signs in through
Nginx, fetches every retained screen and CSS/font dependency without a resource
cache, posts a purchase with a PDF, and checks private preview/download, Spotlight
and activity. Results stay in the ignored test customer Cache folder.
Business services use an internal Docker network. Nginx alone joins the bridge
needed for Docker Desktop's published loopback port. Browser CSP denies remote
resources/connections; inline scripts/styles remain required by existing screens.
The test is scoped service/browser-origin isolation, not a host Wi-Fi or OS-reboot
certification. Native platform/release verification remains at later gates.

## Phase 4 recovery

`python tests/test_backups.py` runs inside the test backup container and refuses
any environment other than `financee_offline_test`. It uses a private temporary
customer folder, real PostgreSQL 16 dumps/restores and its own candidate DBs.
It covers archive/path/corruption/space/permission failures, retention, locks,
stream draining, hard interruption, missed-day catch-up, later-posting rewind,
rescue protection and session expiry. It removes only candidates it created.

`python3 tests/run_backup_crossarch.py` uses the cached pinned AMD64 PostgreSQL
image in a networkless disposable container and compares every table/sequence
fingerprint after ARM64 → emulated Linux AMD64 → ARM64. It is a logical portability
test, not native Windows/macOS installation certification.
