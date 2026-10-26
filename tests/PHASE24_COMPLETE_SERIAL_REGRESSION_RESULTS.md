# Phase 24 — Complete Serial Regression Results

Date: 2026-07-26  
Result: PASS

## Certification matrix

Two fresh serial companies were provisioned at schema version 6. The
idempotent production hardening and tenant-index rollouts were reapplied before
the unchanged legacy test matrix ran.

Each fresh tenant received the legacy party, item, purchase, sale, return,
cash, opening, owner-equity, month-close, report, attachment, and HTTP
workflows. The SQL system-function and deep transaction lifecycle harnesses
also discovered and executed against both tenants.

## Phase 1 baseline comparison

- System-function harness: **111/111 on each fresh tenant**.
- Deep transaction lifecycle: **2702/2702 on each fresh tenant**.
- Legacy domain modules: passed with **zero XFAIL/XPASS**.
- Serial schema version: **6**.
- Base serial tables: **24**.
- Required indexes: **at least 86**.
- Fresh-tenant required object fingerprints: identical.
- Trial balances: balanced.
- Orphan journal lines: zero.
- Trial balance and sales-report JSON contracts: available.

## Quantity separation

Neither serial tenant contained quantity metadata, product-variant,
warehouse, movement, FIFO, transfer, count, tax, currency-settlement, audit,
report, or dashboard database objects. Serial navigation retained legacy
Accounts, Stock, and Sales Reports while hiding Quantity Reports, Warehouses,
Transfers, Physical Counts, and Audit. Every quantity-only backend route was
denied.

## Release gates

- Phase 24 focused matrix: **51/51 passed**.
- Complete aggregate suite: **37/37 modules passed**.
- HTTP regression: **70/70 passed**.
- Production ARM64 image build and static collection: passed.

Expected exception logs from deliberate negative-path tests were observed;
their modules passed.
