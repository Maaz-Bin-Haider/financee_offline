-- ============================================================================
-- tenant_indexes.sql
-- ----------------------------------------------------------------------------
-- Secondary indexes for the per-tenant business schema.
--
-- WHY THIS FILE EXISTS
--   The tenant template ships with PRIMARY KEYs and a few UNIQUE constraints
--   only. PostgreSQL does NOT auto-index foreign-key *referencing* columns, so
--   every join child->parent, every date-range dashboard/report query, and
--   every ON DELETE CASCADE currently does a sequential scan. These indexes
--   target the exact access paths used by the stored functions and the views.
--
-- HOW TO APPLY
--   These statements are SCHEMA-RELATIVE: they rely on `search_path` pointing at
--   the tenant schema, exactly like tenant_template.sql. Apply in two places:
--     1. New tenants  -> paste this block at the END of tenant_template.sql so
--        every freshly provisioned schema is born indexed.
--     2. Existing tenants -> run it against every schema with the management
--        command `apply_sql_all_tenants` (see apply_sql_all_tenants.py).
--
--   All statements use IF NOT EXISTS, so re-running is safe (idempotent).
--
-- LIVE-DATABASE NOTE (the already-deployed OLD version)
--   On a schema that already holds data and is taking traffic, building an
--   index takes an ACCESS SHARE lock that blocks writes for the build duration.
--   For large tables, switch `CREATE INDEX` to `CREATE INDEX CONCURRENTLY`
--   (which cannot run inside a transaction block, and cannot be combined with
--   IF NOT EXISTS on very old PG versions). On a fresh/greenfield schema the
--   plain form below is fine and faster.
-- ============================================================================

-- ------------------------------------------------------------------ accounting
CREATE INDEX IF NOT EXISTS idx_journalentries_entry_date  ON journalentries (entry_date);

CREATE INDEX IF NOT EXISTS idx_journallines_journal_id    ON journallines (journal_id);
CREATE INDEX IF NOT EXISTS idx_journallines_account_id    ON journallines (account_id);
CREATE INDEX IF NOT EXISTS idx_journallines_party_id      ON journallines (party_id) WHERE party_id IS NOT NULL;

-- --------------------------------------------------------------------- sales
CREATE INDEX IF NOT EXISTS idx_salesinvoices_customer     ON salesinvoices (customer_id);
CREATE INDEX IF NOT EXISTS idx_salesinvoices_date         ON salesinvoices (invoice_date);
CREATE INDEX IF NOT EXISTS idx_salesinvoices_cust_date    ON salesinvoices (customer_id, invoice_date);
CREATE INDEX IF NOT EXISTS idx_salesinvoices_journal      ON salesinvoices (journal_id);

CREATE INDEX IF NOT EXISTS idx_salesitems_invoice         ON salesitems (sales_invoice_id);
CREATE INDEX IF NOT EXISTS idx_salesitems_item            ON salesitems (item_id);

CREATE INDEX IF NOT EXISTS idx_soldunits_sales_item       ON soldunits (sales_item_id);
CREATE INDEX IF NOT EXISTS idx_soldunits_unit             ON soldunits (unit_id);
CREATE INDEX IF NOT EXISTS idx_soldunits_status           ON soldunits (status);

-- ------------------------------------------------------------------ purchases
CREATE INDEX IF NOT EXISTS idx_purchaseinvoices_vendor    ON purchaseinvoices (vendor_id);
CREATE INDEX IF NOT EXISTS idx_purchaseinvoices_date      ON purchaseinvoices (invoice_date);
CREATE INDEX IF NOT EXISTS idx_purchaseinvoices_vend_date ON purchaseinvoices (vendor_id, invoice_date);
CREATE INDEX IF NOT EXISTS idx_purchaseinvoices_journal   ON purchaseinvoices (journal_id);

CREATE INDEX IF NOT EXISTS idx_purchaseitems_invoice      ON purchaseitems (purchase_invoice_id);
CREATE INDEX IF NOT EXISTS idx_purchaseitems_item         ON purchaseitems (item_id);

CREATE INDEX IF NOT EXISTS idx_purchaseunits_pitem        ON purchaseunits (purchase_item_id);
-- Fast "what is still on the shelf" lookups (serial_number is already UNIQUE):
CREATE INDEX IF NOT EXISTS idx_purchaseunits_instock      ON purchaseunits (purchase_item_id) WHERE in_stock;

-- -------------------------------------------------------------- payments / rcpt
CREATE INDEX IF NOT EXISTS idx_payments_party_date        ON payments (party_id, payment_date);
CREATE INDEX IF NOT EXISTS idx_payments_account           ON payments (account_id);
CREATE INDEX IF NOT EXISTS idx_payments_journal           ON payments (journal_id);
CREATE INDEX IF NOT EXISTS idx_payments_date              ON payments (payment_date);

CREATE INDEX IF NOT EXISTS idx_receipts_party_date        ON receipts (party_id, receipt_date);
CREATE INDEX IF NOT EXISTS idx_receipts_account           ON receipts (account_id);
CREATE INDEX IF NOT EXISTS idx_receipts_journal           ON receipts (journal_id);
CREATE INDEX IF NOT EXISTS idx_receipts_date              ON receipts (receipt_date);

-- ------------------------------------------------------------- stock movements
CREATE INDEX IF NOT EXISTS idx_stockmovements_item        ON stockmovements (item_id);
CREATE INDEX IF NOT EXISTS idx_stockmovements_serial      ON stockmovements (serial_number);
CREATE INDEX IF NOT EXISTS idx_stockmovements_date        ON stockmovements (movement_date);
CREATE INDEX IF NOT EXISTS idx_stockmovements_ref         ON stockmovements (reference_type, reference_id);

-- ----------------------------------------------------------------- returns
CREATE INDEX IF NOT EXISTS idx_purchasereturns_vendor     ON purchasereturns (vendor_id);
CREATE INDEX IF NOT EXISTS idx_purchasereturns_date       ON purchasereturns (return_date);
CREATE INDEX IF NOT EXISTS idx_purchasereturns_journal    ON purchasereturns (journal_id);

CREATE INDEX IF NOT EXISTS idx_prereturnitems_return      ON purchasereturnitems (purchase_return_id);
CREATE INDEX IF NOT EXISTS idx_prereturnitems_item        ON purchasereturnitems (item_id);
CREATE INDEX IF NOT EXISTS idx_prereturnitems_serial      ON purchasereturnitems (serial_number);

CREATE INDEX IF NOT EXISTS idx_salesreturns_customer      ON salesreturns (customer_id);
CREATE INDEX IF NOT EXISTS idx_salesreturns_date          ON salesreturns (return_date);
CREATE INDEX IF NOT EXISTS idx_salesreturns_journal       ON salesreturns (journal_id);

CREATE INDEX IF NOT EXISTS idx_sreturnitems_return        ON salesreturnitems (sales_return_id);
CREATE INDEX IF NOT EXISTS idx_sreturnitems_item          ON salesreturnitems (item_id);
CREATE INDEX IF NOT EXISTS idx_sreturnitems_serial        ON salesreturnitems (serial_number);

-- --------------------------------------------------- case-insensitive lookups
-- The sale/purchase views validate with WHERE UPPER(party_name)=%s and
-- WHERE UPPER(item_name)=%s. The existing UNIQUE btrees are case-sensitive and
-- cannot serve those, so add matching functional indexes.
CREATE INDEX IF NOT EXISTS idx_items_upper_name           ON items   (UPPER(item_name));
CREATE INDEX IF NOT EXISTS idx_parties_upper_name         ON parties (UPPER(party_name));

-- ------------------------------------------------- contra entries (if present)
DO $$
BEGIN
    IF to_regclass('contra_entries') IS NOT NULL THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_contra_from    ON contra_entries (from_party_id)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_contra_to      ON contra_entries (to_party_id)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_contra_journal ON contra_entries (journal_id)';
    END IF;
END$$;

-- Refresh planner statistics on the freshly indexed objects.
ANALYZE;
