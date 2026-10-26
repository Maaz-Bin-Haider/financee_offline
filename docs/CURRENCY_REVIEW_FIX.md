# Saved AED currency presentation correction

Build: **0.1.1-phase1**, application commit `a7c104d5beb9da99d44e5502f64437d7455ae0d9`.
Native Linux ARM64 image: `sha256:d7678230f8ddabbb54b934aad67960b22ba5f6628bcd4c56736726447c8081f7`.
Running review URL: http://127.0.0.1:18766/home/.

The owner's stored setting was already AED with an empty symbol override. The
live dashboard reproduced PKR because home_script.js constructed a fixed-PKR
Intl formatter and fixed chart-axis text. Smart-alert SQL also contained PKR in
three generated message prefixes. Separate transaction chips, document PDFs and
draft fallbacks retained similar inherited labels. This was a presentation defect;
no currency conversion or monetary-data repair was needed.

The local context now serializes code, symbol and display label safely through
Django json_script. A shared browser formatter retains the original two-decimal
presentation precision. Default amount prefixes use the selected code (AED); an
optional cosmetic display override takes precedence without changing the code.
The dashboard identifies the saved code and symbol, including AED's د.إ.
Cards, monetary tables, chart summaries/tooltips/axes, dashboard PDF data and
Spotlight now read that shared setting. Fixed transaction total chips, purchase/
sale history and document PDF labels and draft labels use the same local context.
Custom labels are escaped where inserted into HTML.

Known smart-alert prefixes are localized at the HTTP response boundary. Exact
amount text is retained, and customer names/titles are not rewritten. This avoids
changing any financial SQL or broadly re-pinning source contracts. There are no
new migrations or financial arithmetic changes. Unicode PDF font certification
remains part of Phase 3; changing label data does not certify those font paths.

Verification:

- 23/23 local-core tests passed from the patch image, including 40 rendered page/
  currency combinations (AED, USD, EUR/€, AED/Dhs), alert API localization, safe
  serialization, accounting invariants and the unchanged 190-function SQL contract.
- 17/17 new Node currency checks passed, executing the actual dashboard loaders,
  Chart axis/tooltip callbacks and dashboard PDF callback data with test adapters.
  These are data/behavior checks, not a claim of PDF font/raster certification.
- Existing 41 frontend assertions passed; changed JS files passed syntax checks.
- Django system checks passed; no migration drift.
- Read-only review checks before and after deployment confirmed saved AED and
  identical user, journal, serial and attachment counts. No customer records,
  credentials or base-currency setting were edited. Only the owned review web
  container and hashed static assets were updated; its database/schema stayed 1.
- The existing authenticated browser session remained valid. Browser inspection
  confirmed AED on sales, profit, cash, receivable/payable, aging and expense
  amounts, and AED · د.إ in the header. No review test transactions were inserted.

Only Financee_Offline was changed. No pushes, remote creation, publication or
source-system operations occurred. The later phase gates remain in effect.
