# Deep Transaction Lifecycle Flow Results

This document records the exact real-world flows covered by
`tests/test_transaction_lifecycle_deep.py` and the latest observed result from
the Docker test run.

Latest passing run command:

```bash
docker compose -f deploy/docker-compose.yml exec -T web sh -c 'RUN_TAG=deep_fixed_$(date +%H%M%S) python tests/test_transaction_lifecycle_deep.py'
```

## Flow Matrix

| # | Flow | Expected Result | Latest Result |
|---|---|---|---|
| 1 | Create master data: vendors, customers, expense party, `Cash Sale` party if missing, and two stock items | Required parties and items are available | Passed |
| 2 | Run all report groups after setup | Accounts, stock, monthly, sales, dashboard, and legacy report objects execute | Passed |
| 3 | Purchase four serials from vendor | All purchased serials are `in_stock = true` | Passed |
| 4 | Sell serial 1 to customer | Serial 1 becomes `in_stock = false` | Passed |
| 5 | Try to sell serial 1 again while already sold | Duplicate sale is blocked | Passed |
| 6 | Try to return serial 1 from wrong customer | Wrong-customer sale return is blocked | Passed |
| 7 | Return serial 1 from correct customer | Return succeeds and serial becomes `in_stock = true` | Passed |
| 8 | Try to return serial 1 again without a new sale | Duplicate sale return is blocked | Passed |
| 9 | Resell returned serial 1 | Resale succeeds and serial becomes `in_stock = false` | Passed |
| 10 | Return serial 1 after resale | Second valid return succeeds | Passed |
| 11 | Try purchase return with wrong vendor | Wrong-vendor purchase return is blocked | Passed |
| 12 | Purchase return serial after sale/return/resale/return lifecycle | Purchase return succeeds and serial becomes unavailable | Passed |
| 13 | Try to sell serial after purchase return | Sale is blocked | Passed |
| 14 | Purchase mixed-state invoice with four serials | Invoice is created | Passed |
| 15 | Sell one serial from mixed purchase invoice | Sold serial becomes `in_stock = false` | Passed |
| 16 | Validate purchase price-only update while one serial is sold | Validation allows price-only update | Passed |
| 17 | Apply purchase price-only update while one serial is sold | Update succeeds and sold serial remains sold | Passed |
| 18 | Validate replacing only an unsold serial | Validation allows replacement because sold serial is preserved | Passed |
| 19 | Apply replacing only an unsold serial | Replacement succeeds; old unsold serial is removed; replacement is in stock | Passed |
| 20 | Validate removing sold serial from purchase invoice | Validation blocks removal and identifies sold serial | Passed |
| 21 | Try to apply purchase update that removes sold serial | Update is blocked | Passed |
| 22 | Purchase return replacement serial | Purchase return succeeds and replacement becomes unavailable | Passed |
| 23 | Purchase four serials for partial return testing | Serial stock is created | Passed |
| 24 | Sell four serials in one sale invoice | All four serials become sold | Passed |
| 25 | Partially return two of four sold serials | Returned serials become stock; non-returned serials remain sold | Passed |
| 26 | Try to update sale invoice after a sale return exists | Sale invoice update is blocked | Passed |
| 27 | Try to delete sale invoice after a sale return exists | Sale invoice delete is blocked | Passed |
| 28 | Update sale return from two serials down to one serial | Removed return serial goes back to sold; retained return serial stays in stock | Passed |
| 29 | Delete sale return before resale | Return deletion succeeds and all affected serials go back to sold | Passed |
| 30 | Purchase serials for sale-return mutation after resale | Serial stock is created | Passed |
| 31 | Credit sale one serial, then return it | Credit sale return succeeds | Passed |
| 32 | Cash-resell the returned serial | Cash resale succeeds and serial becomes sold | Passed |
| 33 | Try to delete old sale return after the serial was resold | Delete is blocked to avoid two active sold states | Passed |
| 34 | Try to update old sale return after the serial was resold | Update is blocked | Passed |
| 35 | Try to return the cash resale from the old credit customer | Wrong-customer return is blocked | Passed |
| 36 | Return the cash resale from `Cash Sale` | Cash sale return succeeds and serial comes back to stock | Passed |
| 37 | Purchase multi-item serial stock for two items | Multi-item stock is created | Passed |
| 38 | Sell multi-item invoice with six serials | All serials across both items become sold | Passed |
| 39 | Return one serial from each item | Mixed-item partial return succeeds | Passed |
| 40 | Try duplicate mixed-item partial return | Duplicate return is blocked | Passed |
| 41 | Update multi-item return to different sold serials | Old returned serials go back to sold; new returned serials come into stock | Passed |
| 42 | Try to update multi-item sale invoice after return exists | Sale invoice update is blocked | Passed |
| 43 | Try to delete multi-item sale invoice after return exists | Sale invoice delete is blocked | Passed |
| 44 | Run all report groups after every posted entry/checkpoint | Accounts, stock, monthly, sales, dashboard, and retained legacy report objects execute | Passed |
| 45 | Check journal integrity after every checkpoint | No empty journal entries exist | Passed |
| 46 | Check serial sale integrity after every checkpoint | Each tested serial has at most one active `SoldUnits.status = 'Sold'` row | Passed |

## Financial Invariants (checked at every checkpoint)

Added after the coverage review. The suite previously only *executed* the trial
balance / party balance reports; it now asserts their values. These hold on a
live schema regardless of accumulated data:

| Invariant | Check | Latest Result |
|---|---|---|
| Double-entry identity | `SUM(debit) = SUM(credit)` across `journallines` | Passed |
| No orphaned journal lines | Every `journallines` row has a parent `journalentries` | Passed |
| Sign sanity | No negative `debit`/`credit` amounts | Passed |
| Stock/sold coherence | Per tested serial, `in_stock` flag matches active `Sold` row (allowing purchase-returned serials) | Passed |

## New Serious Scenarios (coverage review)

| # | Flow | Expected Result | Latest Result |
|---|---|---|---|
| 47 | `delete_purchase` on an untouched (unsold) invoice | Delete succeeds | Passed |
| 48 | `delete_purchase` on an invoice whose serial is already sold | Blocked | Passed (fixed) |
| 49 | Sale with `qty` (5) greater than serial count (2) | Rejected | Passed (fixed) |
| 50 | Sale with `qty` (1) less than serial count (2) | Rejected | Passed (fixed) |
| 51 | Same serial listed twice in one sale invoice | Blocked by in-stock guard | Passed |
| 52 | Sale with a negative unit price | Rejected | Passed (blocked by `journallines` CHECK constraint) |
| 53 | Price-only purchase edit after sale, then sale return | Sale COGS reflows to the corrected cost and matches the return basis | Passed (fixed) |
| 54 | Single sale return spanning two invoices of the same customer | Return succeeds; both serials back in stock | Passed (documents current behavior) |

## Fixed Bugs

The three data-integrity defects surfaced by this review were fixed in
`tenancy/sql/fix_transaction_integrity_guards.sql` (folded into
`tenant_template.sql`, `production_hardening.sql`, and `build_multitenant_db.sql`;
tenant schema version bumped to 3). All three now pass as normal checks on both
tenants.

| Bug | Root cause | Fix |
|---|---|---|
| `delete_purchase` had no sold-serial guard | `soldunits_unit_id_fkey` is `ON DELETE CASCADE`; `delete_purchase` deleted `PurchaseUnits` unconditionally, cascade-deleting sold rows | `assert_purchase_invoice_deletable()` blocks the delete when any serial has sale or purchase-return history |
| `create_sale` / `update_sale_invoice` trusted payload `qty` | Revenue and `SalesItems.quantity` used `qty` while only listed serials shipped | Both functions reject a `qty` that does not equal the serial count (when serials are supplied) |
| Cost-basis drift on return after price edit | Sale COGS was frozen at post time; a later return recaptured cost from the edited `PurchaseItems.unit_price` | `update_purchase_invoice` now rebuilds the journal of every sale that consumed a unit from the edited purchase, keeping COGS in sync |

## Current Summary

Latest Docker run result (after the fix):

```text
tenant_company_1: 2702/2702 real checks passed
tenant_company_2: 2702/2702 real checks passed
PASSED: all deep lifecycle checks passed.
```

All real checks pass on both tenants, including the newly added financial
invariants and the three formerly-failing scenarios. No known bugs remain open.
The `known_bug`/`XFAIL` plumbing is retained for future use.
