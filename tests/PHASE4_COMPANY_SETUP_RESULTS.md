# Phase 4 — Currency Catalogue and Company Setup Results

**Completed:** 2026-07-25  
**Environment:** isolated Docker Compose projects using the production image path  
**Live/production data changed:** no

## Delivered

- Added the public `Currency` catalogue model with:
  - unique uppercase three-character code;
  - name;
  - display symbol;
  - ISO monetary minor-unit precision;
  - active/inactive selection state.
- Seeded 178 unique entries from the official SIX/ISO 4217 List One published
  2026-01-01.
- Made 165 entries with defined ISO minor units selectable. Thirteen
  non-monetary, testing, precious-metal, or unit-of-account entries whose ISO
  minor units are `N.A.` remain catalogued but inactive for company setup.
- Added the idempotent `seed_currencies` management command.
- Added required `Company.base_currency` and `Company.tax_environment`
  metadata.
- Backfilled every pre-Phase-4 company to PKR and non-tax. This adds reporting
  metadata only; no stored serial transaction, journal, price, or total was
  converted or rounded.
- Added database constraints for currency codes, supported minor-unit
  precision, and tax-environment values.
- Protected referenced currencies from deletion.
- Rejected inactive catalogue entries for new company setup.
- Allowed base-currency/tax-environment correction before financial activity
  and locked both after tenant journal activity exists.
- Updated the admin list, filters, form explanations, active-currency choices,
  and activity-aware read-only behavior.
- Extended `provision_tenant` with `--base-currency` and
  `--tax-environment`, preserving PKR/non-tax defaults for existing automation.
- Added `tests/suite/test_company_setup.py` and integrated it into the complete
  suite.

Tax-code/rate/control-account configuration remains a quantity-tenant feature
for later tax implementation phases. Phase 4 establishes the company-level
tax/non-tax environment only.

## Authoritative Catalogue Source

The frozen source is SIX Financial Information's current List One. SIX is the
ISO 4217 Maintenance Agency. The seed records its publication date as
2026-01-01. ISO does not define unique printable symbols; common unambiguous
glyphs are supplied, and the ISO code is used as the safe symbol otherwise.

## Upgraded-Database Evidence

The preserved Phase 1/3 isolated database contained two established serial
tenants:

- `tenancy.0006_currency_company_setup` applied successfully.
- Both existing company rows received PKR/non-tax metadata.
- Inventory mode and schema names remained unchanged.
- Tenant hardening and indexes continued to apply to both schemas.
- Django checks: no issues.
- Missing-migration guard: no changes detected.
- Phase 3 metadata: 14/14 passed.
- Phase 4 company setup: 30/30 passed.
- Complete suite: all 17 modules passed.
- System harness: 111/111 per tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep transaction lifecycle: all checks passed for both serial tenants.

The first full-suite attempt exposed an existing feature-flag admin POST fixture
that omitted the two newly editable setup fields. The fixture now submits the
company's unchanged base currency and tax environment; its final result is
77/77 checks passed.

## Clean-Database Evidence

A new isolated Compose project used newly created PostgreSQL, Redis, static,
and media volumes:

- All migrations through `tenancy.0006` applied from an empty database.
- The bootstrap serial company received PKR/non-tax.
- A second serial tenant was successfully provisioned with:
  - base currency `USD`;
  - tax environment `tax`;
  - unchanged serial tenant schema.
- Catalogue/setup suite: 30/30 passed.
- Complete suite: all 17 modules passed.
- System harness: 111/111 per tenant; 222/222 total.

## Migration Compatibility Rehearsal

On the disposable clean database:

1. Reversed `tenancy.0006` to `0005` successfully.
2. Reapplied `0006` successfully.
3. Reran the company-setup checks successfully; the final expanded suite
   contains 30/30 passing checks, including real tenant-journal detection.
4. Reran 222 serial system/accounting checks successfully.

Because `0006` changes only the public catalogue and company setup metadata,
tenant financial tables are not altered. The complete serial transaction,
report, and accounting suites confirm that symbols and minor-unit metadata did
not reinterpret or round existing stored values.

## Exit Gate

**PASS**

- Company setup reference data is stable and idempotent.
- Existing customers require no manual repair.
- New serial companies can select an active worldwide base currency and
  tax/non-tax environment.
- Existing serial accounting behavior remains unchanged.
- Phase 5 may begin.
