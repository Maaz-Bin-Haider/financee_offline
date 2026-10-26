# Purchase page sizing review

Date: 2026-10-24. Branch: `codex/purchase-ui-sizing`, based on deployed main
`dbd7d7e`. The owner requested comparison with Accounting Plus Inventory after
confirming the feature release works in production. This follow-up remains
local; no push or deployment is authorized yet.

Accounting was read at `ea1f0194f2e4d2b0ec6e120086b29276c4d99365` and remains
unchanged. It was not started, connected to a database or given test writes.
Its template, row markup and CSS were rendered into a temporary synthetic
layout fixture outside both repositories for the visual comparison. This is
a source-layout comparison, not a claim of live Accounting browser/database
testing. GST was off in that fixture; no GST behavior is imported.

## Findings and correction

| Area | Previous Multitenant | Accounting pattern / local correction |
| --- | --- | --- |
| Item row | Five columns compete for at least 780px before padding/gaps; an extra empty grid child | Item, unit price and quantity in the first tier; full-width serials underneath |
| Serial/comment | Fixed 205px serial leaves about 32px for the comment in the laptop sample | Flexible serial plus a readable 100px comment |
| Many serials | One tall serial column, with vertically stacked actions | Serial pairs flow across columns; actions wrap beside their label |
| Phone layout | Late purchase-specific rules override the earlier mobile rules | Final purchase breakpoints keep item/price/quantity and serials inside the viewport |
| Add Item Row | Above the lines | Below the lines it appends to |

With the same 12 synthetic serials at a 1280px viewport, the source fixtures
measured about 838px for the old Multitenant row and 296px for Accounting's
row; comments measured 32px versus 100px. At 390px the old Multitenant fixture
had an 875px document scroll width, versus 384px for Accounting. Fonts and the
real page's extra components can change heights; these are local sample
measurements, not a performance/capacity benchmark.

The correction shares serial-tier markup between new and loaded invoices.
The displayed serial counter counts input slots; quantity continues to count
filled serials only. The separate Financee credit/cash radios and two-field
vendor/date grid remain. Coarse-pointer inputs/buttons get 44px targets and
16px input text, including an explicit item-picker specificity correction.
Semantic light/dark tokens and permission-gated export/attachment controls
remain in place.

There are no SQL, schema, permission, posting, validation, autocomplete endpoint
or PDF calculation changes. The 235-file UI integrity pin changes deliberately;
the independent tenant SQL and 12 serial document implementation anchors pass.

## Verification

- JavaScript syntax check, all 29 serial runtime/source contracts, repository
  hygiene contracts and all 11 dark-mode behavior checks passed. Django system
  checks passed in the committed isolated review image.
- Live Financee review verified loaded purchase #1, a new blank form and newly
  added item rows. Item autocomplete selection, row removal, cash/credit
  controls and light/dark layouts work.
- Tested actual CSS viewport widths 320, 390, 768, 1024, 1280 and 1440. No
  purchase input/button/row overflow at those widths; comments stay 100px.
  After responsive sidebar transitions settle, the 390px document scroll
  width is 384px. Tablet/desktop sidebar margins were checked separately.
- Adding four empty serial fields changed displayed slots from 8 to 12 while
  quantity stayed 8. Filling them changed quantity to 12 and total to 1200
  at price 100. Removing one gave 11 / 1100. Bulk-pasting three entries with
  one duplicate added two, skipped one and produced 13 / 1300. Keyboard Enter
  moves serial → comment → new serial without counting the new empty field.
- No financial form was saved during browser checks. All input experiments
  were discarded by reloading; the original synthetic purchase is retained.
  No full database regression or new GitHub CI is claimed for this
  presentation-only correction.

Temporary comparison and browser evidence is in
`/private/tmp/financee-purchase-*`; screenshots are outside Git in the task's
visualizations directory. The comparison fixture uses synthetic names/serials.

## Owner review

Application: `http://financee-review-activity-purchase.localhost:8187/purchase/purchasing/?open=1`.
This separate stack uses a synthetic database, internal capture mail and
loopback ports. Earlier feature review stacks/data remain intact.

The exact final committed image and synthetic password are in
`/var/folders/qv/qpbw48nx28x_w6tw3q_g7v440000gn/T/financee-review-501/financee_review_activity_purchase/handoff.txt`.
Use `alpha_manager` (or `beta_manager` for the separate company).

1. Open purchase #1 and inspect item name, price, quantity and readable
   serial/comment pairs. Try adding/removing serial fields and an item row.
2. Try bulk paste, keyboard Enter and item-name suggestions. Do not save a
   fixture edit unless you intend to keep that local review change.
3. Resize through phone/tablet/laptop widths and check both themes. Serial
   lists have their own vertical scroll when long; there should be no
   page-wide horizontal scroll.

Stop for manual review. No push or production change has been made.

## Local commits

- `8d46166`: production confirmation and local purchase review scope.
- `9aee3af`: responsive field/serial tiers, shared new/edit markup, button
  placement, theme-safe sizing and the intentional UI integrity pin.
- Final handoff commit: touch item-picker specificity, final verification
  record and review checkpoint. The private handoff identifies its exact SHA.

## Subsequent main push authorization

After reviewing the local handoff `9e8f868`, the owner instructed "now push to
main and watch CI to complete" on 2026-10-24. This supersedes the local-only
push stop above. Preserve the implementation commits with a fast-forward from
verified `origin/main` at `dbd7d7e`, push normally and monitor the exact SHA.
This authorization record changes documentation only; application validation
remains as recorded above. Protected release approvals stay with the owner.
