# Full-System Test Suite — Results

Latest run: 2026-07-06 (after adding document-attachment coverage),
inside the Docker `web` container against both active tenants
(`tenant_company_1`, `tenant_company_2`).

Command:

```bash
docker compose -f deploy/docker-compose.yml exec web python tests/suite/run_all.py
```

Outcome:

```text
ALL MODULES PASSED.
```

Every real check passes on both tenants, with **no `XFAIL` remaining** — the
tenant schema drift the suite originally surfaced has been healed (see
"Tenant drift — healed" below).

## Per-module results

| Module | tenant_company_1 | tenant_company_2 | Notes |
|---|---|---|---|
| `test_parties.py` | 21/21 | 21/21 | — |
| `test_items.py` | 10/10 | 10/10 | — |
| `test_purchases.py` | 29/29 | 29/29 | — |
| `test_sales.py` | 30/30 | 30/30 | cash-sale path asserted on every tenant (feature ported, see below) |
| `test_returns.py` | 31/31 | 31/31 | purchase-return guard now on both tenants |
| `test_cash_movement.py` | 31/31 | 31/31 | — |
| `test_opening.py` | 20/20 | 20/20 | — |
| `test_owner_equity.py` | 13/13 | 13/13 | — |
| `test_month_close.py` | 13/13 | 13/13 | self-restoring (close then reverse) |
| `test_reports.py` | 60/60 | 60/60 | — |
| `test_attachments.py` | 104/104 | 104/104 | document attachment behavior across all supported document types |
| `test_http.py` | 70/70 (single process) | — | Django test client |

Totals: **362** real checks per tenant including attachments, **70** HTTP
checks — **794** real checks, all passing, **0 XFAIL**.

## What each module verifies

### `test_parties.py` (masters)
Creates Customer / Vendor / Both / Expense parties; verifies the Expense party
auto-creates an Expense chart-of-accounts row and AR/AP wiring by type; opening
balances post a balanced journal and yield the correct party balance
(Debit customer → +opening, Credit vendor → −opening); rename + opening change
rebuilds the opening journal; `get_party_by_name`, `get_parties_json`,
`get_party_balances_json`, `get_expense_party_balances_json`, and unknown-party
lookup all behave.

### `test_items.py` (masters)
Item create with category/brand, update by `item_id`, `get_item_by_name`,
`get_items_json`, `get_item_stock_by_name` reflecting a purchase, and the active
autocomplete query. `get_item_names_like` is probed as a documented broken
helper.

### `test_purchases.py`
Create → serials in stock, invoice total = qty×price, journal debits Inventory
and credits the vendor AP (balance −total); `get_current_purchase`,
navigation, `get_purchase_summary`; `validate_purchase_update2` for price-only
and unsold-serial replacement; the **delete guard** (delete blocked when a serial
is sold, allowed for an untouched invoice).

### `test_sales.py`
Credit sale → AR +total, Revenue credited, COGS posted at cost; re-selling a sold
serial blocked; **qty ≠ serial-count rejected**; fetch/navigation/summary;
invoice update; update/delete blocked once a return exists; cash sale debits
Cash and leaves the party AR at 0 (asserted on every tenant); the "Cash Sale" /
"Cash Purchase" sentinel parties are seeded and `get_cash_party_id` resolves.

### `test_returns.py`
Sale return (partial), reversing revenue and restoring stock, lowering customer
AR; wrong-customer and duplicate returns blocked; return update/delete; purchase
return with accounting and stock, wrong-vendor blocked; **sold-serial and
double purchase-return guards** (drift-tolerant, see below); summaries and
navigation.

### `test_cash_movement.py`
Payment to a vendor raises AP toward zero by the amount; update/delete reverse
correctly; invalid amount rejected. Receipt from a customer lowers AR by the
amount; details/history/delete. Contra between two parties; same-party contra
rejected; update/delete. Trial balance stays balanced after each.

### `test_opening.py`
Opening cash singleton debits Cash / credits Owner's Capital (restored to the
original afterward); negative rejected. Opening stock debits Inventory / credits
Opening Balance, with duplicate-serial and existing-serial guards, list/details/
delete. Reclassification moves the Opening Balance account to Owner's Capital and
zeroes it.

### `test_owner_equity.py`
Injection raises Owner's Capital, withdrawal lowers it (both balanced); listing;
invalid direction / non-positive amount / unknown equity account rejected;
deleting both restores capital.

### `test_month_close.py`
Preview (no mutation); close records `period_closes` and posts a balanced entry;
invalid month and duplicate close rejected; listing; reverse reopens the period.
Self-restoring so the run is repeatable.

### `test_reports.py` (every report)
Accounts: `get_trial_balance_json`, `vw_trial_balance` nets to zero,
`detailed_ledger`/`detailed_ledger2`, cash ledger, AR/AP, party & expense
balances (customer net AR value checked). Stock: `stock_summary` quantity checked
against the in-stock serial count, `stock_report`, `stock_worth_report`, item
history, item stock, last-purchase/last-sale views. Serial: all four serial
ledgers/details. Sales analytics: summary, product/customer profitability,
sales-by-product/customer, sale-wise profit (json + table + view),
trend, invoice register, company-worth view. Monthly: company position, income
statement. Dashboard: all 15 `fn_dash_*` functions and the 4 `vw_dash_*` views.

### `test_http.py`
Drives real Django views as a logged-in tenant user: home, master dashboards,
opening/owner-equity/month-close/opening-stock/sales-reports pages return 200;
all dashboard, list, and report JSON APIs return no 5xx; `current_user` works;
a party is created through the real endpoint; logout responds. (Adds a temporary
membership for the superuser if needed and removes it afterward.)

## Tenant drift — healed

The suite originally surfaced these tenant-drift defects. They were healed by
`tenancy/sql/fix_tenant_drift.sql` (applied to all tenants and folded into
`tenant_template.sql`, `production_hardening.sql`, and `build_multitenant_db.sql`;
tenant schema version bumped to 4). The corresponding checks are now normal
passing assertions.

| # | Finding | Status |
|---|---|---|
| 1 | `create_purchase_return` had no in-stock guard on `tenant_company_1` (sold-serial and double purchase-returns not blocked) | **Fixed** — guard added on all tenants |
| 2 | `item_transaction_history(text)` 1-arg overload ambiguous on `tenant_company_1` | **Fixed** — redundant 1-arg overload dropped (3-arg defaulted form remains) |
| 3 | `get_item_names_like` broken on PostgreSQL 16 (ambiguous `item_name`) on both tenants | **Fixed** — column qualified |
| 4 | `item_history_view` present only on `tenant_company_1`, and hardcoded to a specific item (`%iPhone 15 Pro%`) — a debug artifact, not a real report | Excluded from the suite; left in place, not treated as a report |
| 5 | Cash-party feature absent on `tenant_company_1` (`is_cash` column, `get_cash_party_id`) | **Fixed (2026-07-03)** — `tenancy/sql/fix_cash_party_port.sql` (tenant schema version 5) ported the feature and its invoice-description prerequisite to every tenant; the suite now asserts the cash path unconditionally |

Verified after the heal: full suite `ALL MODULES PASSED` (0 XFAIL) and the deep
lifecycle test still passes 2702/2702 on both tenants.

## Conventions

- Runs against **every** active tenant; one representative membership per schema.
- Names are unique per run and per process; repeated runs never collide.
- Expected-failure and destructive-guard probes run in a rolled-back
  transaction, so a wrongly-successful call never persists.
- The suite leaves its valid, uniquely-named accounting trail in place (like the
  deep lifecycle test); use tenant reset for a pristine dataset.
