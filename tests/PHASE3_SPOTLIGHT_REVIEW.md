# Phase 3: company-scoped Spotlight

Date: 2026-10-23. Branch: `codex/spotlight`, based on Phase 2 handoff
`82f3d7e`. Application candidate: `f7e21b0`. Later checkpoint changes are
documentation only. The owner explicitly authorized local Phase 3 work while
keeping Phase 2 local. No push, merge, deployment or Team Activity work is
authorized. Owner manual review of Spotlight is pending.

The Accounting Plus Inventory reference was read at
`ea1f0194f2e4d2b0ec6e120086b29276c4d99365` and never modified.
Both earlier review stacks/data remain intact. Phase 2 remains reviewed at
`c2a63b3`; its branch and running image were not changed.

## Delivered behavior

- Cmd/Ctrl+K, `/` outside editable fields, and desktop/mobile search buttons.
  The palette supports arrows, Enter, Escape, focus return/trapping, live
  status, literal safe highlighting, and both themes.
- A capability list matching Financee's target permissions, company features,
  draft runtime/read-only restrictions, subscription and active membership.
  It includes Financee-only modules and local Phase 2 Report Email; no GST,
  retired Profit Reports, workspace chooser or Team Activity links.
- Server-side name/word searches for parties/items (including item code,
  brand/category), serials, sales/purchases, payments/receipts/contra, both
  ordinary returns, drafts and confirmed draft returns. Exact IDs, `#1`,
  `sale 1`, `sale return 1`, `PMT-1`, `RCT-1` and `CON-1` disambiguate documents.
  Voucher references, dates, counterparties and descriptions are searchable.
- Serial details project purchase/vendor/cost, sale/customer/price and draft
  reservations only to eligible callers. Returned stock is distinguished from
  a current sale and from a vendor return. Party balances and item stock reuse
  existing report functions only with the corresponding financial/stock access.
- Strict ID links open existing document endpoints/renderers and master forms.
  Report links select the permitted report tab. Missing/deleted targets do not
  replace the form with another record. Parameters are consumed once.
- Quick actions prefill existing sale/purchase/payment/receipt/draft/report
  forms. They never save/post anything. Customer/vendor/cash scope is checked;
  ambiguous or wildcard names are refused because existing forms save by name.
- Recent records store identifiers only, namespaced by user/company. Every
  displayed recent and clicked result is revalidated. API responses are private,
  no-store and session-bound. Canceled/out-of-order requests are discarded.
  Logout/account changes invalidate old palettes across tabs; stale tabs require
  a reload. Hidden tabs close and clear the palette.

## Database and release decisions

There is no new permission, model, migration, tenant SQL object, schema version,
financial calculation or posting-function change. Tenant version remains 6.
Searches reuse tenant tables and existing report functions. Existing primary
keys serve exact document lookups; substring searches use escaped parameters,
six-row pages, capped offsets (600) and 1.5-second statement timeouts. A measured
10,000-item fixture did not justify adding an index/extension or altering the
bootstrap, tenant template, hardening or SQL integrity pins.

`spotlight` is an explicit new-company default-off switch in the admin plan.
Existing company lists retain their meaning and are not rewritten. It grants
no underlying financial access. The review companies have the switch enabled.
Disabling it hides the palette and denies its APIs. Source modules/reports still
check their own permissions/features independently.

Older images have no Spotlight code and need no SQL reversal. Phase 2 worker
lifecycle remains intact. A broader source-integrity unit test found two stale
recovery helper pins inherited from Phase 2. Commit `cfb9a67` re-reviews the
unchanged Phase 2 Compose/DB-restore helper bytes and updates exactly those pins;
the helpers themselves and production state are unchanged. See FIXED_ISSUES.md.

## Verification

All database tests used the separate disposable
`financee_review_regression_spotlight` project, never a manual review database.
Local evidence is retained outside Git under `/private/tmp/financee-spotlight-*`.

| Check | Result |
| --- | --- |
| Complete sequential `tests/suite/run_all.py` on `f7e21b0` | All 24 modules passed; 75/75 HTTP; four-company isolation passed |
| Real PostgreSQL/HTTP Spotlight integration | 13 scenarios passed: isolation, field permissions, feature/subscription/membership revocation, strict IDs, escaped wildcards, session scope, recents, actions, concurrent companies, all document groups, paging and authorized facts |
| 10,000-item all-group search with facts | About 57 ms locally; six-row bounded pages; not a production capacity claim |
| Serial compatibility proof | 20/20 passed |
| Source/release/backup contract scripts | 17/17 passed; unchanged SQL/posting-view anchors retained |
| Remote helper unit tests | 51/51 passed after the exact recovery pin correction |
| Spotlight JS core | 7 passed; strict IDs, parameter consumption, safe URLs, bounded identifier-only recents, safe highlighting |
| Existing frontend helpers | Dark mode 11 passed; Report Email 33 passed |
| Worker/rollback simulations | Matching worker, unsupported older worker stop, unhealthy-worker rollback and HTTP rollback passed |
| Django readiness | `check`, `makemigrations --check --dry-run`, `release_preflight` passed |

Browser checks exercised Alpha and Beta, their separate recents and PKR/AED
serial values; sale/payment/sale-return/master opening; serial ledger and item
history prefilling; Sale-wise Profit tab selection; pagination; Cmd+K; light/dark
views; 390-pixel phone layout; and stale-tab refusal after logout elsewhere.
No business form was saved during these checks. Final screenshots are outside
Git in `/private/tmp/financee-spotlight-desktop.png`.

No GitHub CI run, remote update, production action, fresh encrypted restore drill
or historical destructive cleanup is claimed for Phase 3. The Phase 2 restore/
migration/staging evidence remains in its own review record. This feature makes
no SQL/migration/deploy-helper implementation changes that require repeating
those destructive drills.

## Review environment and checklist

Application: `http://financee-review-spotlight.localhost:8183/`.
Capture inbox: `http://financee-review-spotlight-mail.localhost:8184/`.
This is a separate production-image stack with its own synthetic database,
volumes, internal network and loopback ports. No report schedule is enabled in
this new review project. Mail is captured internally; billing email is disabled.

The exact final image/commit and shared synthetic password are in:
`/var/folders/qv/qpbw48nx28x_w6tw3q_g7v440000gn/T/financee-review-501/financee_review_spotlight/handoff.txt`.
Accounts: `alpha_manager`, `beta_manager`, `alpha_staff`, `beta_staff`,
`alpha_reader`, `suspended_user`, `review_operator`. Managers have the source
permissions; the operator has no company membership. The reader's draft/quick
create access remains denied. Staff retain their fixture's ordinary permissions;
use the synthetic operator to adjust them for manual denial checks if desired.

1. Sign in as Alpha, open Search everything, and try `REVIEW CUSTOMER`,
   `REVIEW PHONE`, `REVIEW-004`, `sale 1`, `payment 1`, and `Sale-wise Profit`.
2. Open a result. Check the exact document/master ID and the selected report
   form. Quick actions should fill the correct party/item without saving.
3. Search `REVIEW`; use Show more serials and arrows/Enter. Check returned,
   sold and reserved serials; compare permitted figures with the source screen.
4. Check themes, Escape/focus return, slash outside a field, and phone layout.
5. Switch to Beta. Identical serials/documents must show Beta's AED figures;
   Alpha's recents must be absent. Leave another tab open and verify it requires
   a reload after logout/account switching.
6. Check `alpha_reader`, the suspended user and an operator without membership.
   Turn off source modules/reports or Spotlight for a synthetic company and
   verify both results and direct API access follow those switches.

Keep all manual review stacks/data intact. Stop here for owner review and an
explicit next instruction. Do not push Phase 2/3 or begin Team Activity.

## Focused local commits

| Commit | Increment |
| --- | --- |
| `b82db7c` | Local Phase 3 authorization above unpushed Phase 2 |
| `9f1c8ac` | Company-scoped capability list, search, strict resolvers and integration tests |
| `3cd23ba` | Palette, keyboard controls, recents, record/report links and UI tests |
| `293aace` | Exact references, multiword/metadata search, serial states and paging |
| `e1f24cd` | Cross-tab session invalidation and paging focus |
| `cfb9a67` | Exact recovery integrity pins for already-reviewed Phase 2 helpers |
| `f7e21b0` | Authorized balances/stock from existing report functions |

Later handoff commits record verification only. The private handoff always names
the exact checkout/image actually running for review.
