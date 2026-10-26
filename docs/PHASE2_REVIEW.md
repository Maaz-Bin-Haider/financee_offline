# Phase 2 manual review handoff

**0.2.0-phase2**, schema **2**, core commit `c5e5aeca6cd78be98442f6364337c40b468f9028`.
Native Linux ARM64 image: `sha256:1d730046686324be95151e1e77f7149d0dd2365de3de22e464976cb2133624e1`.
A later documentation-only commit records this handoff. Nothing is published.

## Open the review build

http://127.0.0.1:18766/admin/local/generalsettings/1/change/

Use the owner account you created during onboarding. It remains signed in in the
review browser. No new account/password was created and no credentials changed.
Dashboard: http://127.0.0.1:18766/home/.
Your existing company details, AED, chosen timezone, users and financial/attachment
counts were preserved. All 24 retained local module switches default enabled.

## What changed

General Settings now groups company identity/contact details, base currency,
cosmetic display prefix, timezone selection and local module availability. Admin
remains owner/superuser-only. A normal user cannot open/save it. Currency status
explains the lock after financial activity and the separately editable symbol.
Model/admin validation and database guards enforce the constraints. Two new local
migrations add validated module metadata and serialize the first posting with a
currency change. Existing financial SQL definitions and precision are retained.

Available modules hide their UI and deny disabled URL/API actions while preserving
user permissions, posted data and draft reservations. Dark mode stays available.
Activity recording remains independent of hiding manager analytics.

Company/currency context is present in application screens and existing report,
CSV, document and print exports. Company identity/contact details, currency code,
label/symbol, timezone and generated stamp are included in PDFs. Dynamic reserved
footer space and fitted invoice company headings handle long details. CSV metadata
is quoted, UTF-8/Excel-readable and leaves numeric data unchanged. No active XLSX
writer was present in the imported application; this phase does not claim a new
native Excel-workbook exporter or an Excel application verification.

Locally embedded Financee Sans fonts cover every catalogue currency symbol in all
four styles, including AED, EUR, PKR and BDT symbols. Font notices/provenance and a
developer rebuild script are included. This is currency-symbol coverage, not a
promise to render every writing system/emoji. The complete Phase 3 font/asset audit
remains separately gated.

Business dates, report ranges, future-date validation and generated stamps use the
selected timezone. PostgreSQL's request timezone is reset to UTC afterward. The
PostgreSQL backend preserves returned timestamp offsets, including repeated wall
times at DST changes, so changing local presentation does not shift audit instants.

## Manual checklist

1. Review company name/address/phone/contact email. Select the intended timezone.
   Save, reopen and confirm the displayed values. Contact email is printed text;
   no email transport or SMTP scheduler exists.
2. Keep AED or choose another base currency before any posting. Try an optional
   cosmetic prefix such as Dhs. Confirm dashboard, transaction totals and reports
   identify the currency. There is no FX conversion.
3. Create a disposable transaction and confirm base currency becomes read-only
   while the display prefix remains editable. Verify the original totals/stock.
4. Temporarily disable a local module, check that its link/action is unavailable,
   then enable it again. Normal user permissions still apply; drafts keep reserved
   serials protected while their module is hidden. Dark/light mode still works.
5. Export a report/document PDF and CSV and print a monthly report. Check company
   details, currency, negative/zero/large values, spacing and the local timestamp.

Stop here for Phase 2 owner review. No approval to push, publish or proceed through
later phase gates is inferred.

## Actual verification

- 32/32 local-core tests passed from the final image: settings permissions/editor,
  singleton/profile/currency locks, module guards, preserved draft reservations,
  selected timezone, exact timestamp instants/DST offsets, private attachments,
  server PDF fonts, source SQL contract and independent Decimal accounting checks.
- 328/328 business assertions across 11 modules passed, without skips/XFAIL/XPASS.
- Three real concurrent-connection cases passed in a new disposable database:
  committed posting blocks a racing currency change; rolled-back posting permits
  the waiting change; first posting waits for a currency change to commit.
- All 190 confirmed-source SQL functions still match. There are now three local
  integrity functions; the added one serializes currency changes with posting.
  Source financial expectations were not re-pinned.
- 17 currency JS checks, 18 company/export checks and all 41 prior frontend checks
  passed. Changed JavaScript passed syntax checks. Django system checks passed;
  makemigrations --check reports no drift.
- Real owner-equity PDF/CSV generators produced AED/EUR/PKR/BDT samples with 150
  rows each (five PDF pages per currency). Raw CSV amounts were retained. Identity
  and accounting code were checked on all 20 pages. First pages for all four and
  the final AED page were rendered and visually inspected for glyphs/overlap.
- The live browser showed the saved company/AED/timezone and all 24 enabled local
  module checkboxes. No settings were submitted by the agent in that session.

Machine-readable evidence: PHASE2_RESULTS.json. Ignored command logs and disposable
sample files remain under .runtime/test/Logs and .runtime/test/Exports.
Developer export tests use jspdf 2.5.1, autotable 3.5.31 and FontTools in an ignored
tools folder; these are not customer machine prerequisites.

## Preservation and limits

The review web service was stopped for a bounded maintenance window. A custom-format
logical dump, media and portable metadata were captured into an ignored developer
rescue ZIP; ZIP CRC/member hashes and pg_restore TOC readability were verified.
The source rescue remains at `/Users/swisstech/Development/Financee_Offline/.runtime/review/Backups/DEV_before_Phase2_20261026T113332Z.zip`.
This is a developer maintenance checkpoint, not a delivered customer backup engine
or a tested restore. The earlier image remains locally available. Do not assume an
old image alone reverses migrations; recovery would need the paired data checkpoint.

Only local.0005_local_modules and local.0006_currency_posting_lock were applied.
Existing profile/user/journal/serial/attachment counts were checked before/after.
Stable project/volume/folder ownership remains financee_offline_review; test data
is separate. Only Nginx publishes 127.0.0.1:18766. No Docker socket is mounted.
Both reference checkouts remain clean at their original SHAs, and no source
runtime/database/deployment, Git remote, push or publication was operated.

Pending: full cold disconnected workflows and CDN removal (Phase 3); customer ZIP
backup/restore/scheduling (Phase 4); packaged desktop launcher and real Windows
10/11 x64 / signed Apple Silicon installers; manual installer upgrade/recovery;
release CI and owner-authorized distribution. No corresponding success is claimed.
