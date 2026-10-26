-- Production hardening rollout for existing tenant schemas.
-- Run with:
--   python manage.py apply_sql_all_tenants tenancy/sql/production_hardening.sql

CREATE TABLE IF NOT EXISTS tenant_schema_version (
    id boolean PRIMARY KEY DEFAULT true,
    version integer NOT NULL,
    applied_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tenant_schema_version_singleton CHECK (id)
);

INSERT INTO tenant_schema_version (id, version)
VALUES (true, 2)
ON CONFLICT (id) DO UPDATE
SET version = GREATEST(tenant_schema_version.version, EXCLUDED.version),
    applied_at = CURRENT_TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS ux_purchaseunits_serial_number
    ON purchaseunits (upper(serial_number));

CREATE INDEX IF NOT EXISTS idx_purchaseunits_serial_in_stock
    ON purchaseunits (upper(serial_number), in_stock);

CREATE UNIQUE INDEX IF NOT EXISTS ux_soldunits_one_active_sale_per_unit
    ON soldunits (unit_id)
    WHERE status = 'Sold';

CREATE OR REPLACE FUNCTION assert_sale_invoice_has_no_returns(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM SalesItems si
        JOIN SoldUnits su ON su.sales_item_id = si.sales_item_id
        JOIN PurchaseUnits pu ON pu.unit_id = su.unit_id
        JOIN SalesReturnItems sri ON sri.serial_number = pu.serial_number
        WHERE si.sales_invoice_id = p_invoice_id
    ) THEN
        RAISE EXCEPTION 'Cannot modify sale invoice % because one or more serials have sale return history.', p_invoice_id;
    END IF;
END; $$;

CREATE OR REPLACE FUNCTION create_sale_return(p_party_name text, p_serials jsonb, p_created_by integer DEFAULT NULL::integer) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_return_id   BIGINT;
    v_customer_id BIGINT;
    v_serial      TEXT;
    v_unit        RECORD;
    v_total       NUMERIC(14,2) := 0;
BEGIN
    SELECT party_id INTO v_customer_id FROM Parties WHERE party_name = p_party_name LIMIT 1;
    IF v_customer_id IS NULL THEN
        RAISE EXCEPTION 'Party "%" not found', p_party_name;
    END IF;

    INSERT INTO SalesReturns(customer_id, return_date, total_amount, created_by)
    VALUES (v_customer_id, CURRENT_DATE, 0, p_created_by)
    RETURNING sales_return_id INTO v_return_id;

    FOR v_serial IN SELECT jsonb_array_elements_text(p_serials)
    LOOP
        SELECT su.sold_unit_id, su.unit_id, su.sold_price, si.item_id,
               si.sales_invoice_id, pu.serial_number, pi.unit_price, s.customer_id
        INTO v_unit
        FROM SoldUnits su
        JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
        JOIN SalesInvoices s ON si.sales_invoice_id = s.sales_invoice_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
        WHERE pu.serial_number = v_serial
          AND su.status = 'Sold'
        ORDER BY su.sold_unit_id DESC
        LIMIT 1
        FOR UPDATE OF su, pu;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Serial % is not currently sold (nothing to return)', v_serial;
        END IF;
        IF v_unit.customer_id <> v_customer_id THEN
            RAISE EXCEPTION 'Serial % was not sold to this customer', v_serial;
        END IF;

        UPDATE SoldUnits SET status = 'Returned' WHERE sold_unit_id = v_unit.sold_unit_id;
        UPDATE PurchaseUnits SET in_stock = TRUE WHERE unit_id = v_unit.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (v_unit.item_id, v_serial, 'IN', 'SalesReturn', v_return_id, 1);

        INSERT INTO SalesReturnItems(sales_return_id, item_id, sold_price, cost_price, serial_number)
        VALUES (v_return_id, v_unit.item_id, v_unit.sold_price, v_unit.unit_price, v_serial);

        v_total := v_total + v_unit.sold_price;
    END LOOP;

    UPDATE SalesReturns SET total_amount = v_total WHERE sales_return_id = v_return_id;
    PERFORM rebuild_sales_return_journal(v_return_id);
    RETURN v_return_id;
END; $$;

CREATE OR REPLACE FUNCTION update_sale_return(p_return_id bigint, p_serials jsonb, p_created_by integer DEFAULT NULL::integer) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec           RECORD;
    v_serial      TEXT;
    v_unit        RECORD;
    v_total       NUMERIC(14,2) := 0;
    v_customer_id BIGINT;
BEGIN
    FOR rec IN
        SELECT serial_number, item_id
        FROM SalesReturnItems
        WHERE sales_return_id = p_return_id
    LOOP
        IF EXISTS (
            SELECT 1
            FROM SoldUnits su
            JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
            WHERE pu.serial_number = rec.serial_number
              AND su.status = 'Sold'
        ) THEN
            RAISE EXCEPTION 'Cannot update this sale return: serial % has since been re-sold. Reverse the later sale first.', rec.serial_number;
        END IF;

        UPDATE SoldUnits SET status = 'Sold'
        WHERE sold_unit_id = (
            SELECT su2.sold_unit_id
            FROM SoldUnits su2
            JOIN PurchaseUnits pu2 ON su2.unit_id = pu2.unit_id
            WHERE pu2.serial_number = rec.serial_number
              AND su2.status = 'Returned'
            ORDER BY su2.sold_unit_id DESC
            LIMIT 1
        );

        UPDATE PurchaseUnits SET in_stock = FALSE WHERE serial_number = rec.serial_number;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'OUT', 'SalesReturn-Update-Reverse', p_return_id, 1);
    END LOOP;

    DELETE FROM SalesReturnItems WHERE sales_return_id = p_return_id;

    SELECT customer_id INTO v_customer_id FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF v_customer_id IS NULL THEN
        RAISE EXCEPTION 'Sale return % not found', p_return_id;
    END IF;

    FOR v_serial IN SELECT jsonb_array_elements_text(p_serials)
    LOOP
        SELECT su.sold_unit_id, su.unit_id, su.sold_price, si.item_id,
               si.sales_invoice_id, pu.serial_number, pi.unit_price, s.customer_id
        INTO v_unit
        FROM SoldUnits su
        JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
        JOIN SalesInvoices s ON si.sales_invoice_id = s.sales_invoice_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
        WHERE pu.serial_number = v_serial
          AND su.status = 'Sold'
        ORDER BY su.sold_unit_id DESC
        LIMIT 1
        FOR UPDATE OF su, pu;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Serial % is not currently sold (nothing to return)', v_serial;
        END IF;
        IF v_unit.customer_id <> v_customer_id THEN
            RAISE EXCEPTION 'Serial % was not sold to this customer', v_serial;
        END IF;

        UPDATE SoldUnits SET status = 'Returned' WHERE sold_unit_id = v_unit.sold_unit_id;
        UPDATE PurchaseUnits SET in_stock = TRUE WHERE unit_id = v_unit.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (v_unit.item_id, v_serial, 'IN', 'SalesReturn-Update', p_return_id, 1);

        INSERT INTO SalesReturnItems(sales_return_id, item_id, sold_price, cost_price, serial_number)
        VALUES (p_return_id, v_unit.item_id, v_unit.sold_price, v_unit.unit_price, v_serial);

        v_total := v_total + v_unit.sold_price;
    END LOOP;

    UPDATE SalesReturns
    SET total_amount = v_total,
        created_by = COALESCE(p_created_by, created_by)
    WHERE sales_return_id = p_return_id;

    PERFORM rebuild_sales_return_journal(p_return_id);
END; $$;

CREATE OR REPLACE FUNCTION delete_sale_return(p_return_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    v_journal_id BIGINT;
BEGIN
    FOR rec IN
        SELECT sri.serial_number, sri.item_id
        FROM SalesReturnItems sri
        WHERE sri.sales_return_id = p_return_id
    LOOP
        IF EXISTS (
            SELECT 1
            FROM SoldUnits su
            JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
            WHERE pu.serial_number = rec.serial_number
              AND su.status = 'Sold'
        ) THEN
            RAISE EXCEPTION 'Cannot delete this sale return: serial % has since been re-sold. Reverse the later sale first.', rec.serial_number;
        END IF;

        UPDATE SoldUnits SET status = 'Sold'
        WHERE sold_unit_id = (
            SELECT su2.sold_unit_id
            FROM SoldUnits su2
            JOIN PurchaseUnits pu2 ON su2.unit_id = pu2.unit_id
            WHERE pu2.serial_number = rec.serial_number
              AND su2.status = 'Returned'
            ORDER BY su2.sold_unit_id DESC
            LIMIT 1
        );

        UPDATE PurchaseUnits SET in_stock = FALSE WHERE serial_number = rec.serial_number;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'OUT', 'SalesReturn-Delete', p_return_id, 1);
    END LOOP;

    SELECT journal_id INTO v_journal_id FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF v_journal_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = v_journal_id;
    END IF;

    DELETE FROM SalesReturnItems WHERE sales_return_id = p_return_id;
    DELETE FROM SalesReturns WHERE sales_return_id = p_return_id;
END; $$;

CREATE OR REPLACE FUNCTION delete_sale(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    v_journal_id BIGINT;
BEGIN
    PERFORM assert_sale_invoice_has_no_returns(p_invoice_id);

    FOR rec IN
        SELECT su.unit_id, pu.serial_number, si.item_id
        FROM SoldUnits su
        JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        WHERE si.sales_invoice_id = p_invoice_id
    LOOP
        UPDATE PurchaseUnits SET in_stock = TRUE WHERE unit_id = rec.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'IN', 'SalesInvoice-Delete', p_invoice_id, 1);
    END LOOP;

    SELECT journal_id INTO v_journal_id FROM SalesInvoices WHERE sales_invoice_id = p_invoice_id;
    IF v_journal_id IS NOT NULL THEN
        DELETE FROM JournalLines WHERE journal_id = v_journal_id;
        DELETE FROM JournalEntries WHERE journal_id = v_journal_id;
    END IF;

    DELETE FROM SalesInvoices WHERE sales_invoice_id = p_invoice_id;
END; $$;

CREATE OR REPLACE FUNCTION update_sale_invoice(
    p_invoice_id bigint,
    p_items jsonb,
    p_party_name text DEFAULT NULL::text,
    p_invoice_date date DEFAULT NULL::date
) RETURNS void
    LANGUAGE plpgsql AS $$
BEGIN
    PERFORM update_sale_invoice(p_invoice_id, p_items, p_party_name, p_invoice_date, NULL::integer);
END; $$;

CREATE OR REPLACE FUNCTION update_sale_invoice(
    p_invoice_id bigint,
    p_items jsonb,
    p_party_name text DEFAULT NULL::text,
    p_invoice_date date DEFAULT NULL::date,
    p_created_by integer DEFAULT NULL::integer
) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_item          JSONB;
    v_item_id       BIGINT;
    v_total         NUMERIC(14,2) := 0;
    v_sales_item_id BIGINT;
    v_serial        TEXT;
    v_unit_id       BIGINT;
    v_new_party_id  BIGINT;
BEGIN
    PERFORM assert_sale_invoice_has_no_returns(p_invoice_id);

    IF p_party_name IS NOT NULL THEN
        SELECT party_id INTO v_new_party_id
        FROM Parties WHERE party_name = p_party_name LIMIT 1;

        IF v_new_party_id IS NULL THEN
            RAISE EXCEPTION 'Customer "%" not found in Parties table.', p_party_name;
        END IF;

        UPDATE SalesInvoices SET customer_id = v_new_party_id WHERE sales_invoice_id = p_invoice_id;
    END IF;

    IF p_invoice_date IS NOT NULL THEN
        UPDATE SalesInvoices SET invoice_date = p_invoice_date WHERE sales_invoice_id = p_invoice_id;
    END IF;

    IF p_created_by IS NOT NULL THEN
        UPDATE SalesInvoices SET created_by = p_created_by WHERE sales_invoice_id = p_invoice_id;
    END IF;

    UPDATE PurchaseUnits pu
    SET in_stock = TRUE
    FROM SoldUnits su
    JOIN SalesItems si ON si.sales_item_id = su.sales_item_id
    WHERE pu.unit_id = su.unit_id
      AND si.sales_invoice_id = p_invoice_id;

    DELETE FROM StockMovements
    WHERE reference_type = 'SalesInvoice' AND reference_id = p_invoice_id;

    DELETE FROM SoldUnits
    WHERE sales_item_id IN (
        SELECT sales_item_id FROM SalesItems WHERE sales_invoice_id = p_invoice_id
    );

    DELETE FROM SalesItems WHERE sales_invoice_id = p_invoice_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        SELECT item_id INTO v_item_id
        FROM Items WHERE item_name = (v_item->>'item_name') LIMIT 1;

        IF v_item_id IS NULL THEN
            RAISE EXCEPTION 'Item "%" not found in Items table for update_sale_invoice',
                            (v_item->>'item_name');
        END IF;

        INSERT INTO SalesItems(sales_invoice_id, item_id, quantity, unit_price)
        VALUES (p_invoice_id, v_item_id,
                (v_item->>'qty')::INT, (v_item->>'unit_price')::NUMERIC)
        RETURNING sales_item_id INTO v_sales_item_id;

        v_total := v_total + ((v_item->>'qty')::INT * (v_item->>'unit_price')::NUMERIC);

        FOR v_serial IN SELECT jsonb_array_elements_text(v_item->'serials')
        LOOP
            SELECT unit_id INTO v_unit_id
            FROM PurchaseUnits
            WHERE serial_number = v_serial AND in_stock = TRUE
            LIMIT 1
            FOR UPDATE;

            IF v_unit_id IS NULL THEN
                RAISE EXCEPTION 'Serial % not found in PurchaseUnits', v_serial;
            END IF;

            UPDATE PurchaseUnits SET in_stock = FALSE WHERE unit_id = v_unit_id;

            INSERT INTO SoldUnits(sales_item_id, unit_id, sold_price, status)
            VALUES (v_sales_item_id, v_unit_id, (v_item->>'unit_price')::NUMERIC, 'Sold');

            INSERT INTO StockMovements(item_id, serial_number, movement_type,
                                       reference_type, reference_id, quantity)
            VALUES (v_item_id, v_serial, 'OUT', 'SalesInvoice', p_invoice_id, 1);
        END LOOP;
    END LOOP;

    UPDATE SalesInvoices SET total_amount = v_total
    WHERE sales_invoice_id = p_invoice_id;

    PERFORM rebuild_sales_journal(p_invoice_id);
END; $$;


-- ============================================================================
-- Transaction integrity guards (delete_purchase / qty-vs-serial / COGS reflow)
-- Folded in from tenancy/sql/fix_transaction_integrity_guards.sql
-- ============================================================================
-- ----------------------------------------------------------------------------
-- Idempotent patch for three data-integrity defects surfaced by the deep
-- transaction lifecycle review (tests/test_transaction_lifecycle_deep.py):
--
--   1. delete_purchase had NO guard against deleting a purchase whose serials
--      were already sold. Because soldunits_unit_id_fkey is ON DELETE CASCADE,
--      the delete silently removed the SoldUnits rows and orphaned the sale
--      invoice / revenue journal, corrupting COGS and stock.
--
--   2. create_sale / update_sale_invoice trusted the payload `qty` for revenue
--      and SalesItems.quantity while shipping only the listed serials, so
--      revenue and units shipped could diverge (the trial balance still
--      balanced, hiding the discrepancy).
--
--   3. update_purchase_invoice rebuilt only the purchase journal. A price-only
--      correction after a sale left that sale's COGS frozen at the old cost,
--      while a later sale return recaptured cost from the edited price,
--      producing silent inventory/COGS drift.
--
-- Safe to run repeatedly (CREATE OR REPLACE). Apply to existing tenants with:
--   python manage.py apply_sql_all_tenants tenancy/sql/fix_transaction_integrity_guards.sql
-- ============================================================================

-- --------------------------------------------------------------------------
-- Fix 1: block delete_purchase when serials have downstream history.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION assert_purchase_invoice_deletable(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM PurchaseItems pi
        JOIN PurchaseUnits pu ON pu.purchase_item_id = pi.purchase_item_id
        JOIN SoldUnits su ON su.unit_id = pu.unit_id
        WHERE pi.purchase_invoice_id = p_invoice_id
    ) THEN
        RAISE EXCEPTION 'Cannot delete purchase invoice % because one or more of its serials have sale history.', p_invoice_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM PurchaseItems pi
        JOIN PurchaseUnits pu ON pu.purchase_item_id = pi.purchase_item_id
        JOIN PurchaseReturnItems pri ON pri.serial_number = pu.serial_number
        WHERE pi.purchase_invoice_id = p_invoice_id
    ) THEN
        RAISE EXCEPTION 'Cannot delete purchase invoice % because one or more of its serials have purchase-return history.', p_invoice_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION delete_purchase(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    j_id BIGINT;
BEGIN
    -- Guard: never destroy a purchase whose serials have sale/return history.
    PERFORM assert_purchase_invoice_deletable(p_invoice_id);

    -- 1. Capture the related journal_id (if any)
    SELECT journal_id INTO j_id
    FROM PurchaseInvoices
    WHERE purchase_invoice_id = p_invoice_id;

    -- 2. Log stock OUT movements before deleting
    FOR rec IN
        SELECT pu.serial_number, pi.item_id, pu.purchase_item_id
        FROM PurchaseUnits pu
        JOIN PurchaseItems pi ON pi.purchase_item_id = pu.purchase_item_id
        WHERE pi.purchase_invoice_id = p_invoice_id
    LOOP
        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'OUT', 'PurchaseInvoice-Delete', p_invoice_id, 1);
    END LOOP;

    -- 3. Delete purchase units (serials)
    DELETE FROM PurchaseUnits
    WHERE purchase_item_id IN (
        SELECT purchase_item_id FROM PurchaseItems WHERE purchase_invoice_id = p_invoice_id
    );

    -- 4. Delete purchase items
    DELETE FROM PurchaseItems
    WHERE purchase_invoice_id = p_invoice_id;

    -- 5. Delete journal lines + journal entry if exists
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalLines WHERE journal_id = j_id;
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    -- 6. Delete the purchase invoice itself
    DELETE FROM PurchaseInvoices
    WHERE purchase_invoice_id = p_invoice_id;
END;
$$;

-- --------------------------------------------------------------------------
-- Fix 2: reject qty that does not match the number of serials shipped.
-- Enforced only when serials are supplied, so any non-serial line is untouched.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION create_sale(p_party_id bigint, p_invoice_date date, p_items jsonb, p_created_by integer DEFAULT NULL::integer) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_invoice_id    BIGINT;
    v_sales_item_id BIGINT;
    v_total         NUMERIC(14,2) := 0;
    v_unit_id       BIGINT;
    v_serial        TEXT;
    v_item_id       BIGINT;
    v_item          JSONB;
BEGIN
    INSERT INTO SalesInvoices(customer_id, invoice_date, total_amount, created_by)
    VALUES (p_party_id, p_invoice_date, 0, p_created_by)
    RETURNING sales_invoice_id INTO v_invoice_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        SELECT item_id INTO v_item_id FROM Items
        WHERE item_name = (v_item->>'item_name') LIMIT 1;
        IF v_item_id IS NULL THEN
            RAISE EXCEPTION 'Item "%" not found in Items table', (v_item->>'item_name');
        END IF;

        -- Quantity must match the serials actually shipped.
        IF v_item ? 'serials'
           AND jsonb_typeof(v_item->'serials') = 'array'
           AND jsonb_array_length(v_item->'serials') > 0
           AND (v_item->>'qty')::INT <> jsonb_array_length(v_item->'serials') THEN
            RAISE EXCEPTION 'Quantity (%) does not match the number of serials (%) for item "%".',
                (v_item->>'qty')::INT, jsonb_array_length(v_item->'serials'), (v_item->>'item_name');
        END IF;

        INSERT INTO SalesItems(sales_invoice_id, item_id, quantity, unit_price)
        VALUES (v_invoice_id, v_item_id, (v_item->>'qty')::INT, (v_item->>'unit_price')::NUMERIC)
        RETURNING sales_item_id INTO v_sales_item_id;

        v_total := v_total + ((v_item->>'qty')::INT * (v_item->>'unit_price')::NUMERIC);

        FOR v_serial IN SELECT jsonb_array_elements_text(v_item->'serials')
        LOOP
            SELECT unit_id INTO v_unit_id FROM PurchaseUnits
            WHERE serial_number = v_serial AND in_stock = TRUE
            LIMIT 1
            FOR UPDATE;
            IF v_unit_id IS NULL THEN
                RAISE EXCEPTION 'Serial % not found or already sold', v_serial;
            END IF;
            INSERT INTO SoldUnits(sales_item_id, unit_id, sold_price, status)
            VALUES (v_sales_item_id, v_unit_id, (v_item->>'unit_price')::NUMERIC, 'Sold');
            UPDATE PurchaseUnits SET in_stock = FALSE WHERE unit_id = v_unit_id;
            INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
            VALUES (v_item_id, v_serial, 'OUT', 'SalesInvoice', v_invoice_id, 1);
        END LOOP;
    END LOOP;

    UPDATE SalesInvoices SET total_amount = v_total WHERE sales_invoice_id = v_invoice_id;
    PERFORM rebuild_sales_journal(v_invoice_id);
    RETURN v_invoice_id;
END;
$$;

CREATE OR REPLACE FUNCTION update_sale_invoice(
    p_invoice_id bigint,
    p_items jsonb,
    p_party_name text DEFAULT NULL::text,
    p_invoice_date date DEFAULT NULL::date,
    p_created_by integer DEFAULT NULL::integer
) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_item          JSONB;
    v_item_id       BIGINT;
    v_total         NUMERIC(14,2) := 0;
    v_sales_item_id BIGINT;
    v_serial        TEXT;
    v_unit_id       BIGINT;
    v_new_party_id  BIGINT;
BEGIN
    PERFORM assert_sale_invoice_has_no_returns(p_invoice_id);

    IF p_party_name IS NOT NULL THEN
        SELECT party_id INTO v_new_party_id
        FROM Parties WHERE party_name = p_party_name LIMIT 1;

        IF v_new_party_id IS NULL THEN
            RAISE EXCEPTION 'Customer "%" not found in Parties table.', p_party_name;
        END IF;

        UPDATE SalesInvoices SET customer_id = v_new_party_id WHERE sales_invoice_id = p_invoice_id;
    END IF;

    IF p_invoice_date IS NOT NULL THEN
        UPDATE SalesInvoices SET invoice_date = p_invoice_date WHERE sales_invoice_id = p_invoice_id;
    END IF;

    IF p_created_by IS NOT NULL THEN
        UPDATE SalesInvoices SET created_by = p_created_by WHERE sales_invoice_id = p_invoice_id;
    END IF;

    UPDATE PurchaseUnits pu
    SET in_stock = TRUE
    FROM SoldUnits su
    JOIN SalesItems si ON si.sales_item_id = su.sales_item_id
    WHERE pu.unit_id = su.unit_id
      AND si.sales_invoice_id = p_invoice_id;

    DELETE FROM StockMovements
    WHERE reference_type = 'SalesInvoice' AND reference_id = p_invoice_id;

    DELETE FROM SoldUnits
    WHERE sales_item_id IN (
        SELECT sales_item_id FROM SalesItems WHERE sales_invoice_id = p_invoice_id
    );

    DELETE FROM SalesItems WHERE sales_invoice_id = p_invoice_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        SELECT item_id INTO v_item_id
        FROM Items WHERE item_name = (v_item->>'item_name') LIMIT 1;

        IF v_item_id IS NULL THEN
            RAISE EXCEPTION 'Item "%" not found in Items table for update_sale_invoice',
                            (v_item->>'item_name');
        END IF;

        -- Quantity must match the serials actually shipped.
        IF v_item ? 'serials'
           AND jsonb_typeof(v_item->'serials') = 'array'
           AND jsonb_array_length(v_item->'serials') > 0
           AND (v_item->>'qty')::INT <> jsonb_array_length(v_item->'serials') THEN
            RAISE EXCEPTION 'Quantity (%) does not match the number of serials (%) for item "%".',
                (v_item->>'qty')::INT, jsonb_array_length(v_item->'serials'), (v_item->>'item_name');
        END IF;

        INSERT INTO SalesItems(sales_invoice_id, item_id, quantity, unit_price)
        VALUES (p_invoice_id, v_item_id,
                (v_item->>'qty')::INT, (v_item->>'unit_price')::NUMERIC)
        RETURNING sales_item_id INTO v_sales_item_id;

        v_total := v_total + ((v_item->>'qty')::INT * (v_item->>'unit_price')::NUMERIC);

        FOR v_serial IN SELECT jsonb_array_elements_text(v_item->'serials')
        LOOP
            SELECT unit_id INTO v_unit_id
            FROM PurchaseUnits
            WHERE serial_number = v_serial AND in_stock = TRUE
            LIMIT 1
            FOR UPDATE;

            IF v_unit_id IS NULL THEN
                RAISE EXCEPTION 'Serial % not found in PurchaseUnits', v_serial;
            END IF;

            UPDATE PurchaseUnits SET in_stock = FALSE WHERE unit_id = v_unit_id;

            INSERT INTO SoldUnits(sales_item_id, unit_id, sold_price, status)
            VALUES (v_sales_item_id, v_unit_id, (v_item->>'unit_price')::NUMERIC, 'Sold');

            INSERT INTO StockMovements(item_id, serial_number, movement_type,
                                       reference_type, reference_id, quantity)
            VALUES (v_item_id, v_serial, 'OUT', 'SalesInvoice', p_invoice_id, 1);
        END LOOP;
    END LOOP;

    UPDATE SalesInvoices SET total_amount = v_total
    WHERE sales_invoice_id = p_invoice_id;

    PERFORM rebuild_sales_journal(p_invoice_id);
END;
$$;

-- --------------------------------------------------------------------------
-- Fix 3: keep sale COGS in sync when a purchase price is corrected.
-- After rebuilding the purchase journal, rebuild the journal of every sale
-- that consumed units from this purchase invoice.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_purchase_invoice(p_invoice_id bigint, p_items jsonb, p_party_name text DEFAULT NULL::text, p_invoice_date date DEFAULT NULL::date, p_created_by integer DEFAULT NULL::integer) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_item              JSONB;
    v_item_id           BIGINT;
    v_total             NUMERIC(14,2) := 0;
    v_purchase_item_id  BIGINT;
    v_serial            JSONB;
    v_new_party_id      BIGINT;
    v_existing_serials  TEXT[];
    v_new_serials       TEXT[];
    v_serials_to_remove TEXT[];
    v_serials_to_keep   TEXT[];
    v_validation        JSONB;
    v_temp_item_id      BIGINT := -999999;
    v_sale              RECORD;
BEGIN
    -- Validate
    v_validation := validate_purchase_update2(p_invoice_id, p_items);
    IF (v_validation->>'is_valid')::BOOLEAN = FALSE THEN
        RAISE EXCEPTION '%', v_validation->>'message';
    END IF;

    -- Update Party
    IF p_party_name IS NOT NULL THEN
        SELECT party_id INTO v_new_party_id
        FROM Parties WHERE party_name = p_party_name LIMIT 1;

        IF v_new_party_id IS NULL THEN
            RAISE EXCEPTION 'Vendor "%" not found.', p_party_name;
        END IF;

        UPDATE PurchaseInvoices
        SET vendor_id = v_new_party_id
        WHERE purchase_invoice_id = p_invoice_id;
    END IF;

    -- Update Date
    IF p_invoice_date IS NOT NULL THEN
        UPDATE PurchaseInvoices
        SET invoice_date = p_invoice_date
        WHERE purchase_invoice_id = p_invoice_id;
    END IF;

    -- Update last modifier
    IF p_created_by IS NOT NULL THEN
        UPDATE PurchaseInvoices
        SET created_by = p_created_by
        WHERE purchase_invoice_id = p_invoice_id;
    END IF;

    -- Existing serials
    SELECT ARRAY_AGG(pu.serial_number)
    INTO v_existing_serials
    FROM PurchaseUnits pu
    JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
    WHERE pi.purchase_invoice_id = p_invoice_id;

    IF v_existing_serials IS NULL THEN v_existing_serials := ARRAY[]::TEXT[]; END IF;

    -- New serials from JSON
    SELECT ARRAY_AGG(serial_obj->>'serial')
    INTO v_new_serials
    FROM jsonb_array_elements(p_items) AS item,
         jsonb_array_elements(item->'serials') AS serial_obj;

    IF v_new_serials IS NULL THEN v_new_serials := ARRAY[]::TEXT[]; END IF;

    -- Serials to remove
    SELECT ARRAY_AGG(s) INTO v_serials_to_remove
    FROM unnest(v_existing_serials) AS s WHERE s <> ALL(v_new_serials);
    IF v_serials_to_remove IS NULL THEN v_serials_to_remove := ARRAY[]::TEXT[]; END IF;

    -- Serials to keep
    SELECT ARRAY_AGG(s) INTO v_serials_to_keep
    FROM unnest(v_existing_serials) AS s WHERE s = ANY(v_new_serials);
    IF v_serials_to_keep IS NULL THEN v_serials_to_keep := ARRAY[]::TEXT[]; END IF;

    -- Temp item placeholder
    INSERT INTO PurchaseItems(purchase_invoice_id, item_id, quantity, unit_price)
    VALUES (p_invoice_id, 1, 1, 0)
    RETURNING purchase_item_id INTO v_temp_item_id;

    UPDATE PurchaseUnits SET purchase_item_id = v_temp_item_id
    WHERE serial_number = ANY(v_serials_to_keep);

    -- Remove old stock movements for removed serials
    DELETE FROM StockMovements
    WHERE reference_type = 'PurchaseInvoice'
      AND reference_id = p_invoice_id
      AND serial_number = ANY(v_serials_to_remove);

    -- Delete old items
    DELETE FROM PurchaseItems
    WHERE purchase_invoice_id = p_invoice_id
      AND purchase_item_id != v_temp_item_id;

    -- Recreate items
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        SELECT item_id INTO v_item_id
        FROM Items WHERE item_name = (v_item->>'item_name') LIMIT 1;

        IF v_item_id IS NULL THEN
            INSERT INTO Items(item_name, sale_price)
            VALUES ((v_item->>'item_name'), (v_item->>'unit_price')::NUMERIC)
            RETURNING item_id INTO v_item_id;
        END IF;

        INSERT INTO PurchaseItems(purchase_invoice_id, item_id, quantity, unit_price)
        VALUES (p_invoice_id, v_item_id,
                (v_item->>'qty')::INT, (v_item->>'unit_price')::NUMERIC)
        RETURNING purchase_item_id INTO v_purchase_item_id;

        v_total := v_total + ((v_item->>'qty')::INT * (v_item->>'unit_price')::NUMERIC);

        FOR v_serial IN SELECT * FROM jsonb_array_elements(v_item->'serials')
        LOOP
            IF (v_serial->>'serial') = ANY(v_serials_to_keep) THEN
                UPDATE PurchaseUnits
                SET purchase_item_id = v_purchase_item_id,
                    serial_comment = NULLIF(TRIM(COALESCE(v_serial->>'comment','')), '')
                WHERE serial_number = v_serial->>'serial'
                  AND purchase_item_id = v_temp_item_id;
            ELSE
                INSERT INTO PurchaseUnits(purchase_item_id, serial_number, serial_comment, in_stock)
                VALUES (v_purchase_item_id, v_serial->>'serial',
                        NULLIF(TRIM(COALESCE(v_serial->>'comment','')), ''), TRUE);

                INSERT INTO StockMovements(item_id, serial_number, movement_type,
                                           reference_type, reference_id, quantity)
                VALUES (v_item_id, v_serial->>'serial', 'IN', 'PurchaseInvoice', p_invoice_id, 1);
            END IF;
        END LOOP;
    END LOOP;

    DELETE FROM PurchaseItems WHERE purchase_item_id = v_temp_item_id;

    UPDATE PurchaseInvoices SET total_amount = v_total
    WHERE purchase_invoice_id = p_invoice_id;

    PERFORM rebuild_purchase_journal(p_invoice_id);

    -- Keep COGS in sync: rebuild the journal of every sale that consumed a unit
    -- from this purchase invoice, so a price correction reflows into COGS.
    FOR v_sale IN
        SELECT DISTINCT si.sales_invoice_id AS sid
        FROM PurchaseItems pi
        JOIN PurchaseUnits pu ON pu.purchase_item_id = pi.purchase_item_id
        JOIN SoldUnits su ON su.unit_id = pu.unit_id
        JOIN SalesItems si ON si.sales_item_id = su.sales_item_id
        WHERE pi.purchase_invoice_id = p_invoice_id
    LOOP
        PERFORM rebuild_sales_journal(v_sale.sid);
    END LOOP;
END;
$$;

-- Bump the tenant schema version so the guard is visible to the middleware.
UPDATE tenant_schema_version
SET version = GREATEST(version, 3),
    applied_at = CURRENT_TIMESTAMP
WHERE id = true;


-- ============================================================================
-- Tenant drift heal (purchase-return guard / item_transaction_history overload /
-- get_item_names_like) — folded from tenancy/sql/fix_tenant_drift.sql
-- ============================================================================
-- ----------------------------------------------------------------------------
-- Idempotent patch that heals tenant schema drift found by the full-system test
-- suite (tests/suite/). Safe to run repeatedly and on tenants that already have
-- the corrected objects.
--
--   1. create_purchase_return had no in-stock guard on some tenants, so a sold
--      serial could be purchase-returned and serials could be double-returned.
--      Add the in-stock guard (matches the already-correct tenants).
--
--   2. item_transaction_history existed as BOTH a 1-arg and a 3-arg-with-defaults
--      overload on some tenants, making a 1-arg call ambiguous. Drop the
--      redundant 1-arg overload; the 3-arg (defaulted) covers 1-arg calls.
--
--   3. get_item_names_like referenced an unqualified `item_name` that collides
--      with its OUT column on PostgreSQL 16 (ambiguous column). Qualify it.
--
-- Apply to existing tenants with:
--   python manage.py apply_sql_all_tenants tenancy/sql/fix_tenant_drift.sql
-- ============================================================================

-- --------------------------------------------------------------------------
-- 1. In-stock guard for purchase returns.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION create_purchase_return(p_party_name text, p_serials jsonb, p_created_by integer DEFAULT NULL::integer)
    RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_return_id BIGINT;
    v_vendor_id BIGINT;
    v_serial    TEXT;
    v_rec       RECORD;
    v_total     NUMERIC(14,2) := 0;
BEGIN
    SELECT party_id INTO v_vendor_id FROM Parties WHERE party_name = p_party_name LIMIT 1;
    IF v_vendor_id IS NULL THEN
        RAISE EXCEPTION 'Vendor "%" not found', p_party_name;
    END IF;

    INSERT INTO PurchaseReturns(vendor_id, return_date, total_amount, created_by)
    VALUES (v_vendor_id, CURRENT_DATE, 0, p_created_by)
    RETURNING purchase_return_id INTO v_return_id;

    FOR v_serial IN SELECT jsonb_array_elements_text(p_serials)
    LOOP
        -- Only an in-stock serial belonging to this vendor may be returned.
        SELECT pu.unit_id, pu.purchase_item_id, pi2.unit_price, pi2.item_id,
               pi2.purchase_invoice_id, pu.serial_number
        INTO v_rec
        FROM PurchaseUnits pu
        JOIN PurchaseItems pi2 ON pu.purchase_item_id = pi2.purchase_item_id
        JOIN PurchaseInvoices pinv ON pi2.purchase_invoice_id = pinv.purchase_invoice_id
        WHERE pu.serial_number = v_serial
          AND pinv.vendor_id = v_vendor_id
          AND pu.in_stock = TRUE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Serial % is not in stock or not found for this vendor', v_serial;
        END IF;

        UPDATE PurchaseUnits SET in_stock = FALSE WHERE unit_id = v_rec.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (v_rec.item_id, v_serial, 'OUT', 'PurchaseReturn', v_return_id, 1);

        INSERT INTO PurchaseReturnItems(purchase_return_id, item_id, unit_price, serial_number)
        VALUES (v_return_id, v_rec.item_id, v_rec.unit_price, v_serial);

        v_total := v_total + v_rec.unit_price;
    END LOOP;

    UPDATE PurchaseReturns SET total_amount = v_total WHERE purchase_return_id = v_return_id;
    PERFORM rebuild_purchase_return_journal(v_return_id);
    RETURN v_return_id;
END;
$$;

-- --------------------------------------------------------------------------
-- 2. Remove the redundant 1-arg item_transaction_history overload.
--    The 3-arg (p_item_name text, p_from_date date DEFAULT NULL,
--    p_to_date date DEFAULT NULL) handles 1-arg calls unambiguously.
-- --------------------------------------------------------------------------
DROP FUNCTION IF EXISTS item_transaction_history(text);

-- --------------------------------------------------------------------------
-- 3. Fix the ambiguous column in get_item_names_like.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_item_names_like(search_term text)
    RETURNS TABLE(item_name text)
    LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT i.item_name::text
    FROM items i
    WHERE UPPER(i.item_name) LIKE UPPER(search_term) || '%'
    ORDER BY i.item_name;
END;
$$;

-- Bump tenant schema version.
UPDATE tenant_schema_version
SET version = GREATEST(version, 4),
    applied_at = CURRENT_TIMESTAMP
WHERE id = true;

-- ============================================================================
-- Cash-party feature on every tenant (from fix_cash_party_port.sql; v5),
-- including its invoice-description prerequisite and the pre-flag journal
-- backfill. Idempotent; heals tenants bootstrapped before the feature existed.
-- ============================================================================

ALTER TABLE salesinvoices    ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE purchaseinvoices ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE salesreturns     ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE purchasereturns  ADD COLUMN IF NOT EXISTS description text;

-- 2) Read functions: return the invoice's own description --------------------

CREATE OR REPLACE FUNCTION get_current_sale(p_invoice_id bigint) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'sales_invoice_id', si.sales_invoice_id,
        'Party',            p.party_name,
        'invoice_date',     si.invoice_date,
        'total_amount',     si.total_amount,
        'description',      si.description,
        'created_by',       COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',  i.item_name,
                'qty',        s_items.quantity,
                'unit_price', s_items.unit_price,
                'serials', (
                    SELECT json_agg(pu.serial_number)
                    FROM SoldUnits su
                    JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
                    WHERE su.sales_item_id = s_items.sales_item_id
                )
            ))
            FROM SalesItems s_items
            JOIN Items i ON i.item_id = s_items.item_id
            WHERE s_items.sales_invoice_id = si.sales_invoice_id
        )
    ) INTO result
    FROM SalesInvoices si
    JOIN Parties p ON p.party_id = si.customer_id
    LEFT JOIN auth_user u ON u.id = si.created_by
    WHERE si.sales_invoice_id = p_invoice_id;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION get_current_purchase(p_invoice_id bigint)
 RETURNS json LANGUAGE plpgsql AS $function$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'purchase_invoice_id', pi.purchase_invoice_id,
        'Party',               p.party_name,
        'invoice_date',        pi.invoice_date,
        'total_amount',        pi.total_amount,
        'description',         pi.description,
        'created_by',          COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',  i.item_name,
                'qty',        pi2.quantity,
                'unit_price', pi2.unit_price,
                'serials', (
                    SELECT json_agg(json_build_object('serial', pu.serial_number, 'comment', pu.serial_comment))
                    FROM PurchaseUnits pu
                    WHERE pu.purchase_item_id = pi2.purchase_item_id
                )
            ))
            FROM PurchaseItems pi2
            JOIN Items i ON i.item_id = pi2.item_id
            WHERE pi2.purchase_invoice_id = pi.purchase_invoice_id
        )
    ) INTO result
    FROM PurchaseInvoices pi
    JOIN Parties p ON p.party_id = pi.vendor_id
    LEFT JOIN auth_user u ON u.id = pi.created_by
    WHERE pi.purchase_invoice_id = p_invoice_id
      AND NOT COALESCE(pi.is_opening, false);
    RETURN result;
END; $function$;

CREATE OR REPLACE FUNCTION get_current_sales_return(p_return_id bigint) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'sales_return_id', sr.sales_return_id,
        'Customer',        pa.party_name,
        'return_date',     sr.return_date,
        'total_amount',    sr.total_amount,
        'description',     sr.description,
        'created_by',      COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',     i.item_name,
                'sold_price',    sri.sold_price,
                'cost_price',    sri.cost_price,
                'serial_number', sri.serial_number
            ))
            FROM SalesReturnItems sri
            JOIN Items i ON i.item_id = sri.item_id
            WHERE sri.sales_return_id = sr.sales_return_id
        )
    ) INTO result
    FROM SalesReturns sr
    JOIN Parties pa ON pa.party_id = sr.customer_id
    LEFT JOIN auth_user u ON u.id = sr.created_by
    WHERE sr.sales_return_id = p_return_id;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION get_current_purchase_return(p_return_id bigint) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'purchase_return_id', pr.purchase_return_id,
        'Vendor',             pa.party_name,
        'return_date',        pr.return_date,
        'total_amount',       pr.total_amount,
        'description',        pr.description,
        'created_by',         COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',     i.item_name,
                'unit_price',    pri.unit_price,
                'serial_number', pri.serial_number
            ))
            FROM PurchaseReturnItems pri
            JOIN Items i ON i.item_id = pri.item_id
            WHERE pri.purchase_return_id = pr.purchase_return_id
        )
    ) INTO result
    FROM PurchaseReturns pr
    JOIN Parties pa ON pa.party_id = pr.vendor_id
    LEFT JOIN auth_user u ON u.id = pr.created_by
    WHERE pr.purchase_return_id = p_return_id;
    RETURN result;
END;
$$;

-- 1) Flag on Parties ---------------------------------------------------------
ALTER TABLE Parties ADD COLUMN IF NOT EXISTS is_cash boolean DEFAULT false;

-- 2) Sentinel cash parties: get-or-create, return id -------------------------
CREATE OR REPLACE FUNCTION get_cash_party_id(p_kind text) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_id   bigint;
    v_name text;
    v_type text;
BEGIN
    IF p_kind = 'sale' THEN
        v_name := 'Cash Sale';     v_type := 'Customer';
    ELSIF p_kind = 'purchase' THEN
        v_name := 'Cash Purchase'; v_type := 'Vendor';
    ELSE
        RAISE EXCEPTION 'get_cash_party_id: kind must be sale|purchase, got %', p_kind;
    END IF;

    SELECT party_id INTO v_id FROM Parties WHERE party_name = v_name LIMIT 1;
    IF v_id IS NULL THEN
        PERFORM add_party_from_json(jsonb_build_object(
            'party_name', v_name, 'party_type', v_type,
            'opening_balance', 0, 'balance_type', 'Debit'));
        SELECT party_id INTO v_id FROM Parties WHERE party_name = v_name LIMIT 1;
    END IF;
    UPDATE Parties SET is_cash = true WHERE party_id = v_id AND COALESCE(is_cash,false) = false;
    RETURN v_id;
END; $$;

-- ============================================================================
-- 3) Journal builders — add the cash branch (everything else unchanged)
-- ============================================================================

-- 3a) SALES ------------------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_sales_journal(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    j_id BIGINT;
    rev_acc BIGINT;
    party_acc BIGINT;
    cogs_acc BIGINT;
    inv_acc BIGINT;
    cash_acc BIGINT;
    v_is_cash BOOLEAN := false;
    total_cost NUMERIC(14,2);
    total_revenue NUMERIC(14,2);
    v_customer_id BIGINT;
    v_invoice_date DATE;
BEGIN
    SELECT journal_id INTO j_id FROM SalesInvoices WHERE sales_invoice_id = p_invoice_id;
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalLines WHERE journal_id = j_id;
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    SELECT s.customer_id, s.total_amount, s.invoice_date
    INTO v_customer_id, total_revenue, v_invoice_date
    FROM SalesInvoices s WHERE s.sales_invoice_id = p_invoice_id;

    SELECT account_id INTO rev_acc  FROM ChartOfAccounts WHERE account_name='Sales Revenue';
    SELECT account_id INTO cogs_acc FROM ChartOfAccounts WHERE account_name='Cost of Goods Sold';
    SELECT account_id INTO inv_acc  FROM ChartOfAccounts WHERE account_name='Inventory';
    SELECT account_id INTO cash_acc FROM ChartOfAccounts WHERE account_name='Cash';
    SELECT ar_account_id INTO party_acc FROM Parties WHERE party_id = v_customer_id;
    SELECT COALESCE(is_cash,false) INTO v_is_cash FROM Parties WHERE party_id = v_customer_id;

    INSERT INTO JournalEntries(entry_date, description)
    VALUES (v_invoice_date, 'Sale Invoice ' || p_invoice_id)
    RETURNING journal_id INTO j_id;

    UPDATE SalesInvoices SET journal_id = j_id WHERE sales_invoice_id = p_invoice_id;

    -- (1) Debit Customer AR  OR  Cash (cash sale -> no party, cash increases now)
    IF v_is_cash THEN
        INSERT INTO JournalLines(journal_id, account_id, debit)
        VALUES (j_id, cash_acc, total_revenue);
    ELSE
        INSERT INTO JournalLines(journal_id, account_id, party_id, debit)
        VALUES (j_id, party_acc, v_customer_id, total_revenue);
    END IF;

    -- (2) Credit Revenue
    INSERT INTO JournalLines(journal_id, account_id, credit)
    VALUES (j_id, rev_acc, total_revenue);

    -- (3) Debit COGS / Credit Inventory
    SELECT COALESCE(SUM(pi.unit_price),0) INTO total_cost
    FROM SoldUnits su
    JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
    JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
    JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
    WHERE si.sales_invoice_id = p_invoice_id;

    IF total_cost > 0 THEN
        INSERT INTO JournalLines(journal_id, account_id, debit)  VALUES (j_id, cogs_acc, total_cost);
        INSERT INTO JournalLines(journal_id, account_id, credit) VALUES (j_id, inv_acc, total_cost);
    END IF;
END; $$;

-- 3b) PURCHASES --------------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_purchase_journal(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    j_id BIGINT;
    inv_acc BIGINT;
    party_acc BIGINT;
    cash_acc BIGINT;
    v_is_cash BOOLEAN := false;
    v_total NUMERIC(14,2);
    v_vendor_id BIGINT;
BEGIN
    SELECT journal_id INTO j_id FROM PurchaseInvoices WHERE purchase_invoice_id = p_invoice_id;
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    SELECT vendor_id, total_amount INTO v_vendor_id, v_total
    FROM PurchaseInvoices WHERE purchase_invoice_id = p_invoice_id;

    SELECT account_id INTO inv_acc  FROM ChartOfAccounts WHERE account_name='Inventory';
    SELECT account_id INTO cash_acc FROM ChartOfAccounts WHERE account_name='Cash';
    SELECT ap_account_id INTO party_acc FROM Parties WHERE party_id = v_vendor_id;
    SELECT COALESCE(is_cash,false) INTO v_is_cash FROM Parties WHERE party_id = v_vendor_id;

    INSERT INTO JournalEntries(entry_date, description)
    SELECT invoice_date, 'Purchase Invoice ' || purchase_invoice_id
    FROM PurchaseInvoices WHERE purchase_invoice_id = p_invoice_id
    RETURNING journal_id INTO j_id;

    UPDATE PurchaseInvoices SET journal_id = j_id WHERE purchase_invoice_id = p_invoice_id;

    -- (6) Debit Inventory
    INSERT INTO JournalLines(journal_id, account_id, debit)
    VALUES (j_id, inv_acc, v_total);

    -- (7) Credit Vendor AP  OR  Cash (cash purchase -> no party, cash decreases now)
    IF v_is_cash THEN
        INSERT INTO JournalLines(journal_id, account_id, credit)
        VALUES (j_id, cash_acc, v_total);
    ELSE
        INSERT INTO JournalLines(journal_id, account_id, party_id, credit)
        VALUES (j_id, party_acc, v_vendor_id, v_total);
    END IF;
END; $$;

-- 3c) SALES RETURN -----------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_sales_return_journal(p_return_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    j_id BIGINT;
    rev_acc BIGINT;
    cogs_acc BIGINT;
    inv_acc BIGINT;
    party_acc BIGINT;
    cash_acc BIGINT;
    v_is_cash BOOLEAN := false;
    v_total NUMERIC(14,2);
    v_cost NUMERIC(14,2);
    v_customer_id BIGINT;
    v_date DATE;
BEGIN
    SELECT journal_id INTO j_id FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    SELECT customer_id, total_amount, return_date
    INTO v_customer_id, v_total, v_date
    FROM SalesReturns WHERE sales_return_id = p_return_id;

    SELECT COALESCE(SUM(cost_price),0) INTO v_cost
    FROM SalesReturnItems WHERE sales_return_id = p_return_id;

    SELECT account_id INTO rev_acc  FROM ChartOfAccounts WHERE account_name='Sales Revenue';
    SELECT account_id INTO cogs_acc FROM ChartOfAccounts WHERE account_name='Cost of Goods Sold';
    SELECT account_id INTO inv_acc  FROM ChartOfAccounts WHERE account_name='Inventory';
    SELECT account_id INTO cash_acc FROM ChartOfAccounts WHERE account_name='Cash';
    SELECT ar_account_id INTO party_acc FROM Parties WHERE party_id = v_customer_id;
    SELECT COALESCE(is_cash,false) INTO v_is_cash FROM Parties WHERE party_id = v_customer_id;

    INSERT INTO JournalEntries(entry_date, description)
    VALUES (v_date, 'Sales Return ' || p_return_id)
    RETURNING journal_id INTO j_id;

    UPDATE SalesReturns SET journal_id = j_id WHERE sales_return_id = p_return_id;

    -- (1) Debit Sales Revenue
    IF v_total > 0 THEN
        INSERT INTO JournalLines(journal_id, account_id, debit)
        VALUES (j_id, rev_acc, v_total);
    END IF;

    -- (2) Credit Customer AR  OR  Cash (cash sale return -> refund cash, no party)
    IF v_total > 0 THEN
        IF v_is_cash THEN
            INSERT INTO JournalLines(journal_id, account_id, credit)
            VALUES (j_id, cash_acc, v_total);
        ELSE
            INSERT INTO JournalLines(journal_id, account_id, party_id, credit)
            VALUES (j_id, party_acc, v_customer_id, v_total);
        END IF;
    END IF;

    -- (3) Debit Inventory / (4) Credit COGS
    IF v_cost > 0 THEN
        INSERT INTO JournalLines(journal_id, account_id, debit)  VALUES (j_id, inv_acc, v_cost);
        INSERT INTO JournalLines(journal_id, account_id, credit) VALUES (j_id, cogs_acc, v_cost);
    END IF;
END; $$;

-- 3d) PURCHASE RETURN --------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_purchase_return_journal(p_return_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    j_id BIGINT;
    inv_acc BIGINT;
    party_acc BIGINT;
    cash_acc BIGINT;
    v_is_cash BOOLEAN := false;
    v_total NUMERIC(14,2);
    v_vendor_id BIGINT;
    v_date DATE;
BEGIN
    SELECT journal_id INTO j_id FROM PurchaseReturns WHERE purchase_return_id = p_return_id;
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    SELECT vendor_id, total_amount, return_date
    INTO v_vendor_id, v_total, v_date
    FROM PurchaseReturns WHERE purchase_return_id = p_return_id;

    SELECT account_id INTO inv_acc  FROM ChartOfAccounts WHERE account_name='Inventory';
    SELECT account_id INTO cash_acc FROM ChartOfAccounts WHERE account_name='Cash';
    SELECT ap_account_id INTO party_acc FROM Parties WHERE party_id = v_vendor_id;
    SELECT COALESCE(is_cash,false) INTO v_is_cash FROM Parties WHERE party_id = v_vendor_id;

    INSERT INTO JournalEntries(entry_date, description)
    VALUES (v_date, 'Purchase Return ' || p_return_id)
    RETURNING journal_id INTO j_id;

    UPDATE PurchaseReturns SET journal_id = j_id WHERE purchase_return_id = p_return_id;

    -- (1) Debit Vendor AP  OR  Cash (cash purchase return -> cash refunded in, no party)
    IF v_total > 0 THEN
        IF v_is_cash THEN
            INSERT INTO JournalLines(journal_id, account_id, debit)
            VALUES (j_id, cash_acc, v_total);
        ELSE
            INSERT INTO JournalLines(journal_id, account_id, party_id, debit)
            VALUES (j_id, party_acc, v_vendor_id, v_total);
        END IF;
    END IF;

    -- (2) Credit Inventory
    IF v_total > 0 THEN
        INSERT INTO JournalLines(journal_id, account_id, credit)
        VALUES (j_id, inv_acc, v_total);
    END IF;
END; $$;

-- ----------------------------------------------------------------------------
-- Cash-aware party ledger (includes the invoice-description enrichment).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION detailed_ledger(p_party_name text, p_start_date date, p_end_date date)
 RETURNS TABLE(entry_date date, journal_id bigint, description text, party_name text, account_type text, debit numeric, credit numeric, running_balance numeric, created_by text)
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_is_cash boolean := false;
    v_cash_id bigint;
BEGIN
    SELECT pp.party_id, COALESCE(pp.is_cash,false) INTO v_cash_id, v_is_cash FROM Parties pp WHERE pp.party_name = p_party_name;

    IF v_is_cash THEN
        RETURN QUERY
        WITH party_ledger AS (
        SELECT
            je.entry_date                   AS entry_date,
            je.journal_id                   AS journal_id,
            (je.description || COALESCE(' — ' || NULLIF((
                SELECT x.d FROM (
                    SELECT si.description AS d FROM salesinvoices si    WHERE si.journal_id = je.journal_id
                    UNION ALL SELECT pi.description FROM purchaseinvoices pi WHERE pi.journal_id = je.journal_id
                    UNION ALL SELECT sr.description FROM salesreturns sr     WHERE sr.journal_id = je.journal_id
                    UNION ALL SELECT pr.description FROM purchasereturns pr  WHERE pr.journal_id = je.journal_id
                ) x WHERE x.d IS NOT NULL AND btrim(x.d) <> '' LIMIT 1
            ), ''), ''))::TEXT            AS description,
            p.party_name::TEXT              AS party_name,
            a.account_name::TEXT            AS account_name,
            jl.debit                        AS debit,
            jl.credit                       AS credit,
            (jl.debit - jl.credit)          AS amount
        FROM JournalLines jl
        JOIN JournalEntries je  ON jl.journal_id  = je.journal_id
        JOIN ChartOfAccounts a  ON jl.account_id  = a.account_id
        JOIN Parties p          ON p.party_name   = p_party_name
        WHERE a.account_name = 'Cash'
          AND je.entry_date BETWEEN p_start_date AND p_end_date
          AND je.journal_id IN (
              SELECT salesinvoices.journal_id FROM salesinvoices    WHERE customer_id = v_cash_id
              UNION ALL SELECT salesreturns.journal_id FROM salesreturns     WHERE customer_id = v_cash_id
              UNION ALL SELECT purchaseinvoices.journal_id FROM purchaseinvoices WHERE vendor_id  = v_cash_id
              UNION ALL SELECT purchasereturns.journal_id FROM purchasereturns  WHERE vendor_id  = v_cash_id
          )
    ),
    -- Map each journal_id to the user who created the source document
    journal_author AS (
        SELECT pi.journal_id, u.username::TEXT
        FROM purchaseinvoices pi LEFT JOIN auth_user u ON u.id = pi.created_by
        WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, u.username::TEXT
        FROM purchasereturns pr LEFT JOIN auth_user u ON u.id = pr.created_by
        WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, u.username::TEXT
        FROM salesinvoices si LEFT JOIN auth_user u ON u.id = si.created_by
        WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, u.username::TEXT
        FROM salesreturns sr LEFT JOIN auth_user u ON u.id = sr.created_by
        WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id, u.username::TEXT
        FROM receipts r LEFT JOIN auth_user u ON u.id = r.created_by
        WHERE r.journal_id IS NOT NULL
        UNION ALL
        SELECT py.journal_id, u.username::TEXT
        FROM payments py LEFT JOIN auth_user u ON u.id = py.created_by
        WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, u.username::TEXT
        FROM contra_entries ce LEFT JOIN auth_user u ON u.id = ce.created_by
        WHERE ce.journal_id IS NOT NULL
    )
    SELECT
        pl.entry_date,
        pl.journal_id,
        pl.description,
        pl.party_name,
        pl.account_name                                                 AS account_type,
        pl.debit,
        pl.credit,
        SUM(pl.amount) OVER (ORDER BY pl.entry_date, pl.journal_id
                             ROWS UNBOUNDED PRECEDING)                  AS running_balance,
        COALESCE(ja.username::TEXT, 'N/A')                              AS created_by
    FROM party_ledger pl
    LEFT JOIN journal_author ja ON ja.journal_id = pl.journal_id
    ORDER BY pl.entry_date, pl.journal_id;
    ELSE
        RETURN QUERY
        WITH party_ledger AS (
        SELECT
            je.entry_date                   AS entry_date,
            je.journal_id                   AS journal_id,
            (je.description || COALESCE(' — ' || NULLIF((
                SELECT x.d FROM (
                    SELECT si.description AS d FROM salesinvoices si    WHERE si.journal_id = je.journal_id
                    UNION ALL SELECT pi.description FROM purchaseinvoices pi WHERE pi.journal_id = je.journal_id
                    UNION ALL SELECT sr.description FROM salesreturns sr     WHERE sr.journal_id = je.journal_id
                    UNION ALL SELECT pr.description FROM purchasereturns pr  WHERE pr.journal_id = je.journal_id
                ) x WHERE x.d IS NOT NULL AND btrim(x.d) <> '' LIMIT 1
            ), ''), ''))::TEXT            AS description,
            p.party_name::TEXT              AS party_name,
            a.account_name::TEXT            AS account_name,
            jl.debit                        AS debit,
            jl.credit                       AS credit,
            (jl.debit - jl.credit)          AS amount
        FROM JournalLines jl
        JOIN JournalEntries je  ON jl.journal_id  = je.journal_id
        JOIN ChartOfAccounts a  ON jl.account_id  = a.account_id
        LEFT JOIN Parties p     ON jl.party_id    = p.party_id
        WHERE p.party_name = p_party_name
          AND je.entry_date BETWEEN p_start_date AND p_end_date
    ),
    -- Map each journal_id to the user who created the source document
    journal_author AS (
        SELECT pi.journal_id, u.username::TEXT
        FROM purchaseinvoices pi LEFT JOIN auth_user u ON u.id = pi.created_by
        WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, u.username::TEXT
        FROM purchasereturns pr LEFT JOIN auth_user u ON u.id = pr.created_by
        WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, u.username::TEXT
        FROM salesinvoices si LEFT JOIN auth_user u ON u.id = si.created_by
        WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, u.username::TEXT
        FROM salesreturns sr LEFT JOIN auth_user u ON u.id = sr.created_by
        WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id, u.username::TEXT
        FROM receipts r LEFT JOIN auth_user u ON u.id = r.created_by
        WHERE r.journal_id IS NOT NULL
        UNION ALL
        SELECT py.journal_id, u.username::TEXT
        FROM payments py LEFT JOIN auth_user u ON u.id = py.created_by
        WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, u.username::TEXT
        FROM contra_entries ce LEFT JOIN auth_user u ON u.id = ce.created_by
        WHERE ce.journal_id IS NOT NULL
    )
    SELECT
        pl.entry_date,
        pl.journal_id,
        pl.description,
        pl.party_name,
        pl.account_name                                                 AS account_type,
        pl.debit,
        pl.credit,
        SUM(pl.amount) OVER (ORDER BY pl.entry_date, pl.journal_id
                             ROWS UNBOUNDED PRECEDING)                  AS running_balance,
        COALESCE(ja.username::TEXT, 'N/A')                              AS created_by
    FROM party_ledger pl
    LEFT JOIN journal_author ja ON ja.journal_id = pl.journal_id
    ORDER BY pl.entry_date, pl.journal_id;
    END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION detailed_ledger2(p_party_name text, p_start_date date, p_end_date date)
 RETURNS TABLE(entry_date date, journal_id bigint, description text, party_name text, account_type text, debit numeric, credit numeric, running_balance numeric, invoice_details jsonb, created_by text)
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_opening_balance NUMERIC;
    v_is_cash boolean := false;
    v_cash_id bigint;
BEGIN
    SELECT pp.party_id, COALESCE(pp.is_cash,false) INTO v_cash_id, v_is_cash FROM parties pp WHERE pp.party_name = p_party_name;

    IF v_is_cash THEN
    SELECT COALESCE(SUM(jl.debit - jl.credit), 0) INTO v_opening_balance
    FROM journallines jl JOIN journalentries je ON jl.journal_id = je.journal_id
    JOIN chartofaccounts a ON jl.account_id = a.account_id
    WHERE a.account_name = 'Cash' AND je.entry_date < p_start_date
      AND je.journal_id IN (SELECT salesinvoices.journal_id FROM salesinvoices WHERE customer_id = v_cash_id
          UNION ALL SELECT salesreturns.journal_id FROM salesreturns WHERE customer_id = v_cash_id
          UNION ALL SELECT purchaseinvoices.journal_id FROM purchaseinvoices WHERE vendor_id = v_cash_id
          UNION ALL SELECT purchasereturns.journal_id FROM purchasereturns WHERE vendor_id = v_cash_id);

        RETURN QUERY
        WITH party_ledger AS (
        SELECT
            je.entry_date                   AS entry_date,
            je.journal_id                   AS journal_id,
            (je.description || COALESCE(' — ' || NULLIF((
                SELECT x.d FROM (
                    SELECT si.description AS d FROM salesinvoices si    WHERE si.journal_id = je.journal_id
                    UNION ALL SELECT pi.description FROM purchaseinvoices pi WHERE pi.journal_id = je.journal_id
                    UNION ALL SELECT sr.description FROM salesreturns sr     WHERE sr.journal_id = je.journal_id
                    UNION ALL SELECT pr.description FROM purchasereturns pr  WHERE pr.journal_id = je.journal_id
                ) x WHERE x.d IS NOT NULL AND btrim(x.d) <> '' LIMIT 1
            ), ''), ''))::TEXT            AS description,
            p.party_name::TEXT              AS party_name,
            a.account_name::TEXT            AS account_name,
            jl.debit                        AS debit,
            jl.credit                       AS credit,
            (jl.debit - jl.credit)          AS amount
        FROM journallines jl
        JOIN journalentries je  ON jl.journal_id   = je.journal_id
        JOIN chartofaccounts a  ON jl.account_id   = a.account_id
        JOIN parties p          ON p.party_name    = p_party_name
        WHERE a.account_name = 'Cash'
          AND je.entry_date BETWEEN p_start_date AND p_end_date
          AND je.journal_id IN (
              SELECT salesinvoices.journal_id FROM salesinvoices    WHERE customer_id = v_cash_id
              UNION ALL SELECT salesreturns.journal_id FROM salesreturns     WHERE customer_id = v_cash_id
              UNION ALL SELECT purchaseinvoices.journal_id FROM purchaseinvoices WHERE vendor_id  = v_cash_id
              UNION ALL SELECT purchasereturns.journal_id FROM purchasereturns  WHERE vendor_id  = v_cash_id
          )
    ),

    journal_source AS (
        SELECT pi.journal_id, 'purchase'::TEXT        AS source_type, pi.purchase_invoice_id  AS source_id FROM purchaseinvoices pi  WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, 'purchase_return'::TEXT AS source_type, pr.purchase_return_id   AS source_id FROM purchasereturns pr   WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, 'sale'::TEXT            AS source_type, si.sales_invoice_id     AS source_id FROM salesinvoices si     WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, 'sale_return'::TEXT     AS source_type, sr.sales_return_id      AS source_id FROM salesreturns sr      WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id,  'receipt'::TEXT         AS source_type, r.receipt_id            AS source_id FROM receipts r           WHERE r.journal_id  IS NOT NULL
        UNION ALL
        SELECT py.journal_id, 'payment'::TEXT         AS source_type, py.payment_id           AS source_id FROM payments py          WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, 'contra'::TEXT          AS source_type, ce.contra_id            AS source_id FROM contra_entries ce    WHERE ce.journal_id IS NOT NULL
    ),

    -- Resolve username from the source document table
    journal_author AS (
        SELECT pi.journal_id, u.username::TEXT
        FROM purchaseinvoices pi LEFT JOIN auth_user u ON u.id = pi.created_by
        WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, u.username::TEXT
        FROM purchasereturns pr LEFT JOIN auth_user u ON u.id = pr.created_by
        WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, u.username::TEXT
        FROM salesinvoices si LEFT JOIN auth_user u ON u.id = si.created_by
        WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, u.username::TEXT
        FROM salesreturns sr LEFT JOIN auth_user u ON u.id = sr.created_by
        WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id, u.username::TEXT
        FROM receipts r LEFT JOIN auth_user u ON u.id = r.created_by
        WHERE r.journal_id IS NOT NULL
        UNION ALL
        SELECT py.journal_id, u.username::TEXT
        FROM payments py LEFT JOIN auth_user u ON u.id = py.created_by
        WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, u.username::TEXT
        FROM contra_entries ce LEFT JOIN auth_user u ON u.id = ce.created_by
        WHERE ce.journal_id IS NOT NULL
    )

    SELECT
        pl.entry_date,
        pl.journal_id,
        pl.description,
        pl.party_name,
        pl.account_name                                                 AS account_type,
        pl.debit,
        pl.credit,
        v_opening_balance + SUM(pl.amount) OVER (
            ORDER BY pl.entry_date, pl.journal_id
            ROWS UNBOUNDED PRECEDING
        )                                                               AS running_balance,

        -- invoice_details
        CASE js.source_type
            WHEN 'purchase' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Purchase Invoice' AS type, pi.purchase_invoice_id, pa.party_name AS vendor, pi.invoice_date, pi.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'qty',pit.quantity,'unit_price',pit.unit_price,'line_total',pit.quantity*pit.unit_price,
                            'serials',(SELECT json_agg(json_build_object('serial',pu.serial_number,'comment',pu.serial_comment)) FROM purchaseunits pu WHERE pu.purchase_item_id=pit.purchase_item_id)))
                         FROM purchaseitems pit JOIN items i ON i.item_id=pit.item_id WHERE pit.purchase_invoice_id=pi.purchase_invoice_id) AS items
                    FROM purchaseinvoices pi JOIN parties pa ON pa.party_id=pi.vendor_id WHERE pi.purchase_invoice_id=js.source_id
                ) d
            )
            WHEN 'purchase_return' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Purchase Return' AS type, pr.purchase_return_id, pa.party_name AS vendor, pr.return_date, pr.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'unit_price',pri.unit_price,'serial_number',pri.serial_number))
                         FROM purchasereturnitems pri JOIN items i ON i.item_id=pri.item_id WHERE pri.purchase_return_id=pr.purchase_return_id) AS items
                    FROM purchasereturns pr JOIN parties pa ON pa.party_id=pr.vendor_id WHERE pr.purchase_return_id=js.source_id
                ) d
            )
            WHEN 'sale' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Sale Invoice' AS type, si.sales_invoice_id, pa.party_name AS customer, si.invoice_date, si.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'qty',sitm.quantity,'unit_price',sitm.unit_price,'line_total',sitm.quantity*sitm.unit_price,
                            'serials',(SELECT json_agg(json_build_object('serial',pu.serial_number,'comment',pu.serial_comment,'sold_price',su.sold_price))
                                       FROM soldunits su JOIN purchaseunits pu ON su.unit_id=pu.unit_id WHERE su.sales_item_id=sitm.sales_item_id)))
                         FROM salesitems sitm JOIN items i ON i.item_id=sitm.item_id WHERE sitm.sales_invoice_id=si.sales_invoice_id) AS items
                    FROM salesinvoices si JOIN parties pa ON pa.party_id=si.customer_id WHERE si.sales_invoice_id=js.source_id
                ) d
            )
            WHEN 'sale_return' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Sale Return' AS type, sr.sales_return_id, pa.party_name AS customer, sr.return_date, sr.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'sold_price',sri.sold_price,'cost_price',sri.cost_price,'serial_number',sri.serial_number))
                         FROM salesreturnitems sri JOIN items i ON i.item_id=sri.item_id WHERE sri.sales_return_id=sr.sales_return_id) AS items
                    FROM salesreturns sr JOIN parties pa ON pa.party_id=sr.customer_id WHERE sr.sales_return_id=js.source_id
                ) d
            )
            WHEN 'receipt' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Receipt' AS type, r.receipt_id, pa.party_name AS party, r.receipt_date, r.amount, r.method, r.reference_no, r.notes, r.description
                    FROM receipts r JOIN parties pa ON pa.party_id=r.party_id WHERE r.receipt_id=js.source_id
                ) d
            )
            WHEN 'payment' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Payment' AS type, py.payment_id, pa.party_name AS party, py.payment_date, py.amount, py.method, py.reference_no, py.notes, py.description
                    FROM payments py JOIN parties pa ON pa.party_id=py.party_id WHERE py.payment_id=js.source_id
                ) d
            )
            WHEN 'contra' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Contra Entry' AS type, ce.contra_id, fp.party_name AS from_party, tp.party_name AS to_party,
                           ce.contra_date, ce.amount, ce.method, ce.reference_no, ce.description
                    FROM contra_entries ce
                    JOIN parties fp ON fp.party_id = ce.from_party_id
                    JOIN parties tp ON tp.party_id = ce.to_party_id
                    WHERE ce.contra_id = js.source_id
                ) d
            )
            ELSE NULL
        END                                                             AS invoice_details,

        COALESCE(ja.username::TEXT, 'N/A')                              AS created_by

    FROM party_ledger pl
    LEFT JOIN journal_source js  ON js.journal_id  = pl.journal_id
    LEFT JOIN journal_author ja  ON ja.journal_id  = pl.journal_id
    ORDER BY pl.entry_date, pl.journal_id;
    ELSE

    -- Opening balance: sum of (debit - credit) before p_start_date
    SELECT COALESCE(SUM(jl.debit - jl.credit), 0)
    INTO   v_opening_balance
    FROM   journallines jl
    JOIN   journalentries je ON jl.journal_id = je.journal_id
    JOIN   parties p         ON jl.party_id   = p.party_id
    WHERE  p.party_name = p_party_name
      AND  je.entry_date < p_start_date;

        RETURN QUERY
        WITH party_ledger AS (
        SELECT
            je.entry_date                   AS entry_date,
            je.journal_id                   AS journal_id,
            (je.description || COALESCE(' — ' || NULLIF((
                SELECT x.d FROM (
                    SELECT si.description AS d FROM salesinvoices si    WHERE si.journal_id = je.journal_id
                    UNION ALL SELECT pi.description FROM purchaseinvoices pi WHERE pi.journal_id = je.journal_id
                    UNION ALL SELECT sr.description FROM salesreturns sr     WHERE sr.journal_id = je.journal_id
                    UNION ALL SELECT pr.description FROM purchasereturns pr  WHERE pr.journal_id = je.journal_id
                ) x WHERE x.d IS NOT NULL AND btrim(x.d) <> '' LIMIT 1
            ), ''), ''))::TEXT            AS description,
            p.party_name::TEXT              AS party_name,
            a.account_name::TEXT            AS account_name,
            jl.debit                        AS debit,
            jl.credit                       AS credit,
            (jl.debit - jl.credit)          AS amount
        FROM journallines jl
        JOIN journalentries je  ON jl.journal_id   = je.journal_id
        JOIN chartofaccounts a  ON jl.account_id   = a.account_id
        LEFT JOIN parties p     ON jl.party_id     = p.party_id
        WHERE p.party_name = p_party_name
          AND je.entry_date BETWEEN p_start_date AND p_end_date
    ),

    journal_source AS (
        SELECT pi.journal_id, 'purchase'::TEXT        AS source_type, pi.purchase_invoice_id  AS source_id FROM purchaseinvoices pi  WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, 'purchase_return'::TEXT AS source_type, pr.purchase_return_id   AS source_id FROM purchasereturns pr   WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, 'sale'::TEXT            AS source_type, si.sales_invoice_id     AS source_id FROM salesinvoices si     WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, 'sale_return'::TEXT     AS source_type, sr.sales_return_id      AS source_id FROM salesreturns sr      WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id,  'receipt'::TEXT         AS source_type, r.receipt_id            AS source_id FROM receipts r           WHERE r.journal_id  IS NOT NULL
        UNION ALL
        SELECT py.journal_id, 'payment'::TEXT         AS source_type, py.payment_id           AS source_id FROM payments py          WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, 'contra'::TEXT          AS source_type, ce.contra_id            AS source_id FROM contra_entries ce    WHERE ce.journal_id IS NOT NULL
    ),

    -- Resolve username from the source document table
    journal_author AS (
        SELECT pi.journal_id, u.username::TEXT
        FROM purchaseinvoices pi LEFT JOIN auth_user u ON u.id = pi.created_by
        WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, u.username::TEXT
        FROM purchasereturns pr LEFT JOIN auth_user u ON u.id = pr.created_by
        WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, u.username::TEXT
        FROM salesinvoices si LEFT JOIN auth_user u ON u.id = si.created_by
        WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, u.username::TEXT
        FROM salesreturns sr LEFT JOIN auth_user u ON u.id = sr.created_by
        WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id, u.username::TEXT
        FROM receipts r LEFT JOIN auth_user u ON u.id = r.created_by
        WHERE r.journal_id IS NOT NULL
        UNION ALL
        SELECT py.journal_id, u.username::TEXT
        FROM payments py LEFT JOIN auth_user u ON u.id = py.created_by
        WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, u.username::TEXT
        FROM contra_entries ce LEFT JOIN auth_user u ON u.id = ce.created_by
        WHERE ce.journal_id IS NOT NULL
    )

    SELECT
        pl.entry_date,
        pl.journal_id,
        pl.description,
        pl.party_name,
        pl.account_name                                                 AS account_type,
        pl.debit,
        pl.credit,
        v_opening_balance + SUM(pl.amount) OVER (
            ORDER BY pl.entry_date, pl.journal_id
            ROWS UNBOUNDED PRECEDING
        )                                                               AS running_balance,

        -- invoice_details
        CASE js.source_type
            WHEN 'purchase' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Purchase Invoice' AS type, pi.purchase_invoice_id, pa.party_name AS vendor, pi.invoice_date, pi.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'qty',pit.quantity,'unit_price',pit.unit_price,'line_total',pit.quantity*pit.unit_price,
                            'serials',(SELECT json_agg(json_build_object('serial',pu.serial_number,'comment',pu.serial_comment)) FROM purchaseunits pu WHERE pu.purchase_item_id=pit.purchase_item_id)))
                         FROM purchaseitems pit JOIN items i ON i.item_id=pit.item_id WHERE pit.purchase_invoice_id=pi.purchase_invoice_id) AS items
                    FROM purchaseinvoices pi JOIN parties pa ON pa.party_id=pi.vendor_id WHERE pi.purchase_invoice_id=js.source_id
                ) d
            )
            WHEN 'purchase_return' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Purchase Return' AS type, pr.purchase_return_id, pa.party_name AS vendor, pr.return_date, pr.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'unit_price',pri.unit_price,'serial_number',pri.serial_number))
                         FROM purchasereturnitems pri JOIN items i ON i.item_id=pri.item_id WHERE pri.purchase_return_id=pr.purchase_return_id) AS items
                    FROM purchasereturns pr JOIN parties pa ON pa.party_id=pr.vendor_id WHERE pr.purchase_return_id=js.source_id
                ) d
            )
            WHEN 'sale' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Sale Invoice' AS type, si.sales_invoice_id, pa.party_name AS customer, si.invoice_date, si.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'qty',sitm.quantity,'unit_price',sitm.unit_price,'line_total',sitm.quantity*sitm.unit_price,
                            'serials',(SELECT json_agg(json_build_object('serial',pu.serial_number,'comment',pu.serial_comment,'sold_price',su.sold_price))
                                       FROM soldunits su JOIN purchaseunits pu ON su.unit_id=pu.unit_id WHERE su.sales_item_id=sitm.sales_item_id)))
                         FROM salesitems sitm JOIN items i ON i.item_id=sitm.item_id WHERE sitm.sales_invoice_id=si.sales_invoice_id) AS items
                    FROM salesinvoices si JOIN parties pa ON pa.party_id=si.customer_id WHERE si.sales_invoice_id=js.source_id
                ) d
            )
            WHEN 'sale_return' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Sale Return' AS type, sr.sales_return_id, pa.party_name AS customer, sr.return_date, sr.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'sold_price',sri.sold_price,'cost_price',sri.cost_price,'serial_number',sri.serial_number))
                         FROM salesreturnitems sri JOIN items i ON i.item_id=sri.item_id WHERE sri.sales_return_id=sr.sales_return_id) AS items
                    FROM salesreturns sr JOIN parties pa ON pa.party_id=sr.customer_id WHERE sr.sales_return_id=js.source_id
                ) d
            )
            WHEN 'receipt' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Receipt' AS type, r.receipt_id, pa.party_name AS party, r.receipt_date, r.amount, r.method, r.reference_no, r.notes, r.description
                    FROM receipts r JOIN parties pa ON pa.party_id=r.party_id WHERE r.receipt_id=js.source_id
                ) d
            )
            WHEN 'payment' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Payment' AS type, py.payment_id, pa.party_name AS party, py.payment_date, py.amount, py.method, py.reference_no, py.notes, py.description
                    FROM payments py JOIN parties pa ON pa.party_id=py.party_id WHERE py.payment_id=js.source_id
                ) d
            )
            WHEN 'contra' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Contra Entry' AS type, ce.contra_id, fp.party_name AS from_party, tp.party_name AS to_party,
                           ce.contra_date, ce.amount, ce.method, ce.reference_no, ce.description
                    FROM contra_entries ce
                    JOIN parties fp ON fp.party_id = ce.from_party_id
                    JOIN parties tp ON tp.party_id = ce.to_party_id
                    WHERE ce.contra_id = js.source_id
                ) d
            )
            ELSE NULL
        END                                                             AS invoice_details,

        COALESCE(ja.username::TEXT, 'N/A')                              AS created_by

    FROM party_ledger pl
    LEFT JOIN journal_source js  ON js.journal_id  = pl.journal_id
    LEFT JOIN journal_author ja  ON ja.journal_id  = pl.journal_id
    ORDER BY pl.entry_date, pl.journal_id;
    END IF;
END;
$function$;

-- ----------------------------------------------------------------------------
-- Seed the sentinel cash parties eagerly (get-or-create; idempotent).
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    PERFORM get_cash_party_id('sale');
    PERFORM get_cash_party_id('purchase');
END;
$$;

-- ----------------------------------------------------------------------------
-- Backfill: rebuild the journals of cash-party documents that were posted
-- BEFORE the party was cash-flagged. Those journals carry party AR/AP lines
-- instead of Cash lines, so they are invisible to the cash-party ledger and
-- leave a residual (never-collectable) party balance. Only documents whose
-- journal still has a party-tagged line are rebuilt, so this is a no-op on
-- every subsequent run. The swap (party AR/AP line -> Cash line) is
-- balance-sheet neutral: the trial balance and P&L are unchanged.
-- ----------------------------------------------------------------------------
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT si.sales_invoice_id AS id
        FROM SalesInvoices si
        JOIN Parties p ON p.party_id = si.customer_id
        WHERE COALESCE(p.is_cash, false)
          AND EXISTS (SELECT 1 FROM JournalLines jl
                      WHERE jl.journal_id = si.journal_id
                        AND jl.party_id = si.customer_id)
    LOOP
        PERFORM rebuild_sales_journal(r.id);
    END LOOP;

    FOR r IN
        SELECT sr.sales_return_id AS id
        FROM SalesReturns sr
        JOIN Parties p ON p.party_id = sr.customer_id
        WHERE COALESCE(p.is_cash, false)
          AND EXISTS (SELECT 1 FROM JournalLines jl
                      WHERE jl.journal_id = sr.journal_id
                        AND jl.party_id = sr.customer_id)
    LOOP
        PERFORM rebuild_sales_return_journal(r.id);
    END LOOP;

    FOR r IN
        SELECT pi.purchase_invoice_id AS id
        FROM PurchaseInvoices pi
        JOIN Parties p ON p.party_id = pi.vendor_id
        WHERE COALESCE(p.is_cash, false)
          AND EXISTS (SELECT 1 FROM JournalLines jl
                      WHERE jl.journal_id = pi.journal_id
                        AND jl.party_id = pi.vendor_id)
    LOOP
        PERFORM rebuild_purchase_journal(r.id);
    END LOOP;

    FOR r IN
        SELECT pr.purchase_return_id AS id
        FROM PurchaseReturns pr
        JOIN Parties p ON p.party_id = pr.vendor_id
        WHERE COALESCE(p.is_cash, false)
          AND EXISTS (SELECT 1 FROM JournalLines jl
                      WHERE jl.journal_id = pr.journal_id
                        AND jl.party_id = pr.vendor_id)
    LOOP
        PERFORM rebuild_purchase_return_journal(r.id);
    END LOOP;
END;
$$;

CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id BIGSERIAL PRIMARY KEY,
    document_type TEXT NOT NULL,
    document_id BIGINT NOT NULL,
    file_kind TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    uploaded_by INTEGER NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_attachments_document_type_check CHECK (
        document_type IN ('sale', 'purchase', 'sale_return', 'purchase_return', 'payment', 'receipt', 'contra')
    ),
    CONSTRAINT document_attachments_file_kind_check CHECK (file_kind IN ('image', 'pdf')),
    CONSTRAINT document_attachments_file_size_check CHECK (file_size > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS document_attachments_one_per_kind
    ON document_attachments (document_type, document_id, file_kind);

CREATE INDEX IF NOT EXISTS document_attachments_document_idx
    ON document_attachments (document_type, document_id);

-- Bump tenant schema version.
UPDATE tenant_schema_version
SET version = GREATEST(version, 6),
    applied_at = CURRENT_TIMESTAMP
WHERE id = true;

-- ── Dashboard receivables: exclude expense-party lines (schema version 7) ──
-- vw_dash_party_ar_balance summed every journal line tagged with a party,
-- whatever account it hit, so paying a shop expense made that expense head
-- look like a customer owing money on the dashboard (and raised "Stale
-- Receivable" / "Risky Customer" alerts). Restrict it to lines actually posted
-- to the party's own receivables account. See
-- tenancy/sql/fix_dashboard_expense_receivables.sql for the full rationale.
CREATE OR REPLACE VIEW vw_dash_party_ar_balance AS
 SELECT p.party_id,
    p.party_name,
    p.party_type,
    p.contact_info,
    COALESCE((sum(jl.debit) - sum(jl.credit)), (0)::numeric) AS ar_balance,
    max(je.entry_date) AS last_transaction_date
   FROM ((parties p
     JOIN journallines jl ON ((jl.party_id = p.party_id)))
     JOIN journalentries je ON ((je.journal_id = jl.journal_id)))
  WHERE (p.ar_account_id IS NOT NULL)
    AND (jl.account_id = p.ar_account_id)
  GROUP BY p.party_id, p.party_name, p.party_type, p.contact_info
 HAVING (COALESCE((sum(jl.debit) - sum(jl.credit)), (0)::numeric) > (0)::numeric);


-- ============================================================================
-- DRAFT SALE INVOICES (PROFORMA)
-- Idempotent tenant patch. Folded verbatim into tenant_template.sql,
-- production_hardening.sql and the example tenant of build_multitenant_db.sql.
-- Run on existing tenants with:
--   python manage.py apply_sql_all_tenants tenancy/sql/add_draft_invoices.sql
--
-- Goods are often committed to a customer before their rate is agreed. A draft
-- reserves specific serial numbers for a named customer and moves nothing else:
-- no stock, no journal, no balance. When the rate is agreed a tranche of the
-- draft converts into an ordinary credit sale invoice; the rest stays reserved.
-- Ported from the single-tenant Financee (DRAFT_SALES_PLAN.md, commit 80e8f8a
-- and its post-release corrections).
--
-- THE CENTRAL DESIGN DECISION: no accounting function is forked.
--   Every path that consumes a serial -- create_sale, update_sale_invoice,
--   create_purchase_return, update_sale_return, delete_sale_return,
--   delete_purchase, update_purchase_invoice, delete_opening_stock -- either
--   takes the unit out of stock (in_stock TRUE -> FALSE) or deletes its
--   PurchaseUnits row. One BEFORE UPDATE OR DELETE trigger on PurchaseUnits that
--   refuses both for a RESERVED unit guards all of them, plus raw SQL and
--   anything written later. Conversion settles the reservation first and then
--   calls create_sale unchanged: there remains exactly one function in this
--   system that creates a sale and its journal.
--
-- Switching the feature off (DRAFT_SALES_ENABLED or the per-company
-- draft_invoices flag) hides the screens only. The guard below keeps refusing
-- to sell, return or delete a reserved unit regardless.
--
-- Tenant schema version is deliberately NOT bumped (stays 6): this file is
-- applied to every tenant by production_hardening.sql on every container start,
-- and the Phase 3B restore guard requires exactly version 6.
-- ============================================================================

-- 1. Tables ------------------------------------------------------------------
-- Mirroring SalesInvoices / SalesItems / SoldUnits in shape and naming: a draft
-- is the same document one step earlier in its life.

CREATE TABLE IF NOT EXISTS DraftInvoices (
    draft_invoice_id bigserial PRIMARY KEY,
    customer_id      bigint      NOT NULL REFERENCES Parties(party_id),
    draft_date       date        NOT NULL DEFAULT CURRENT_DATE,
    -- 'Partially Converted' is deliberately NOT stored: it is derivable (Open
    -- with at least one Converted unit), and the read functions compute it.
    status           varchar(20) NOT NULL DEFAULT 'Open'
                     CHECK (status IN ('Open', 'Converted', 'Cancelled')),
    description      text,
    created_by       integer,
    date_created     timestamptz NOT NULL DEFAULT clock_timestamp(),
    closed_at        timestamptz,
    closed_by        integer
);

CREATE INDEX IF NOT EXISTS draft_invoices_status_idx
    ON DraftInvoices (status, draft_date);

CREATE TABLE IF NOT EXISTS DraftItems (
    draft_item_id    bigserial PRIMARY KEY,
    draft_invoice_id bigint  NOT NULL
                     REFERENCES DraftInvoices(draft_invoice_id) ON DELETE CASCADE,
    item_id          bigint  NOT NULL REFERENCES Items(item_id),
    -- The quantity the line was raised with; what remains is derived from
    -- DraftUnits by the read functions.
    quantity         integer NOT NULL CHECK (quantity > 0),
    -- NULL means "no rate agreed yet", a different fact from 0.00.
    unit_price       numeric(14,2) CHECK (unit_price IS NULL OR unit_price >= 0)
);

CREATE INDEX IF NOT EXISTS draft_items_invoice_idx
    ON DraftItems (draft_invoice_id);

-- One row per reserved physical unit. Converted and Released rows are kept as
-- history, never deleted. Deleting the PurchaseUnits row (a purchase edited or
-- deleted, an opening load deleted) takes that finished history with it; a
-- LIVE reservation never gets that far, because trg_protect_reserved_units
-- refuses the delete first.
CREATE TABLE IF NOT EXISTS DraftUnits (
    draft_unit_id    bigserial PRIMARY KEY,
    draft_item_id    bigint      NOT NULL
                     REFERENCES DraftItems(draft_item_id) ON DELETE CASCADE,
    unit_id          bigint      NOT NULL
                     REFERENCES PurchaseUnits(unit_id) ON DELETE CASCADE,
    status           varchar(20) NOT NULL DEFAULT 'Reserved'
                     CHECK (status IN ('Reserved', 'Converted', 'Released')),
    sales_invoice_id bigint,
    reserved_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    converted_at     timestamptz,
    converted_by     integer,
    released_at      timestamptz,
    released_by      integer
);

CREATE INDEX IF NOT EXISTS draft_units_item_idx
    ON DraftUnits (draft_item_id);

CREATE INDEX IF NOT EXISTS draft_units_unit_idx
    ON DraftUnits (unit_id);

-- One physical unit can be reserved exactly once, enforced by the database
-- rather than by every procedure remembering to check.
CREATE UNIQUE INDEX IF NOT EXISTS draft_units_one_live_reservation
    ON DraftUnits (unit_id)
    WHERE status = 'Reserved';

-- The Confirmed Draft Return header: its own number series and screen. The
-- accounting underneath is an ordinary SalesReturns row (sales_return_id), so
-- every ledger, report and the trial balance see it; the date, total and
-- description live on that row, never duplicated here.
CREATE TABLE IF NOT EXISTS DraftReturns (
    draft_return_id  bigserial PRIMARY KEY,
    customer_id      bigint  NOT NULL REFERENCES Parties(party_id),
    draft_invoice_id bigint  REFERENCES DraftInvoices(draft_invoice_id),
    sales_return_id  bigint,
    created_by       integer,
    date_created     timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- 2. The discriminators on existing documents ---------------------------------
-- Nullable, no foreign key, no accounting meaning. An invoice raised from a
-- draft is returned only through the Confirmed Draft Return document, and a
-- return made there is kept out of every ordinary sale-return listing.

ALTER TABLE SalesInvoices ADD COLUMN IF NOT EXISTS draft_invoice_id bigint;

CREATE INDEX IF NOT EXISTS salesinvoices_draft_idx
    ON SalesInvoices (draft_invoice_id)
    WHERE draft_invoice_id IS NOT NULL;

ALTER TABLE SalesReturns ADD COLUMN IF NOT EXISTS draft_return_id bigint;

CREATE INDEX IF NOT EXISTS salesreturns_draft_idx
    ON SalesReturns (draft_return_id)
    WHERE draft_return_id IS NOT NULL;

-- 3. The reservation guard ----------------------------------------------------
-- Refuses taking a RESERVED unit out of stock, or deleting it. Still allowed:
-- putting a unit back in stock (a return must never be strandable), editing any
-- other column (update_purchase_invoice re-points kept units), and consuming a
-- unit whose reservation is already settled -- which is why conversion flips
-- DraftUnits to 'Converted' BEFORE it calls create_sale. That order is
-- load-bearing.

CREATE OR REPLACE FUNCTION trg_fn_protect_reserved_units() RETURNS trigger
    LANGUAGE plpgsql AS $$
DECLARE
    v_customer text;
    v_draft_id bigint;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- Only the in-stock -> out-of-stock transition is a consumption.
        IF NOT (OLD.in_stock = TRUE AND NEW.in_stock = FALSE) THEN
            RETURN NEW;
        END IF;
    END IF;

    SELECT p.party_name, di.draft_invoice_id
    INTO v_customer, v_draft_id
    FROM DraftUnits du
    JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
    JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
    JOIN Parties p ON p.party_id = di.customer_id
    WHERE du.unit_id = OLD.unit_id
      AND du.status = 'Reserved'
    LIMIT 1;

    IF v_draft_id IS NOT NULL THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Serial "%" is reserved for customer "%" on draft invoice #%. Release it from that draft before changing the purchase it was bought on.',
                OLD.serial_number, v_customer, v_draft_id;
        END IF;
        RAISE EXCEPTION 'Serial "%" is reserved for customer "%" on draft invoice #%. Release it from that draft first, or convert that draft instead.',
            OLD.serial_number, v_customer, v_draft_id;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

-- CREATE OR REPLACE rather than DROP + CREATE: a rerun on every container
-- start then never takes an ACCESS EXCLUSIVE lock on purchaseunits.
CREATE OR REPLACE TRIGGER trg_protect_reserved_units
BEFORE UPDATE OR DELETE ON PurchaseUnits
FOR EACH ROW EXECUTE FUNCTION trg_fn_protect_reserved_units();

-- The other half: only a unit in stock can be reserved, and the check takes the
-- SAME PurchaseUnits row lock create_sale takes, so a transaction reserving a
-- serial and one selling it serialise on one row and exactly one wins. Only a
-- 'Reserved' row is checked; Converted and Released rows are history.

CREATE OR REPLACE FUNCTION trg_fn_reserve_only_stocked_units() RETURNS trigger
    LANGUAGE plpgsql AS $$
DECLARE
    v_in_stock boolean;
    v_serial   text;
BEGIN
    IF NEW.status <> 'Reserved' THEN
        RETURN NEW;
    END IF;

    SELECT pu.in_stock, pu.serial_number
    INTO v_in_stock, v_serial
    FROM PurchaseUnits pu
    WHERE pu.unit_id = NEW.unit_id
    FOR UPDATE;

    IF v_in_stock IS NULL THEN
        RAISE EXCEPTION 'Cannot reserve unit %: it does not exist.', NEW.unit_id;
    END IF;
    IF NOT v_in_stock THEN
        RAISE EXCEPTION 'Serial "%" is not available in stock, so it cannot be reserved on a draft invoice. It may already be sold or returned to the vendor.', v_serial;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_reserve_only_stocked_units
BEFORE INSERT OR UPDATE ON DraftUnits
FOR EACH ROW EXECUTE FUNCTION trg_fn_reserve_only_stocked_units();

-- 4. The reservation is visible wherever a serial is --------------------------
-- get_serial_number_details is where every screen learns about a serial, so the
-- customer a unit is held for is appended there. Every caller selects named
-- columns, so appending is safe; a RETURNS TABLE change needs DROP first, done
-- only while the old shape is still in place so a rerun is a no-op.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = current_schema()
          AND p.proname = 'get_serial_number_details'
          AND pg_get_function_result(p.oid) NOT LIKE '%reserved_draft_id%'
    ) THEN
        DROP FUNCTION get_serial_number_details(text);
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION get_serial_number_details(serial text)
RETURNS TABLE(serial_number character varying, item_name character varying, brand character varying,
              category character varying, purchase_invoice_id bigint, vendor_name character varying,
              purchase_date date, purchase_price numeric, in_stock boolean, sales_invoice_id bigint,
              customer_name character varying, sale_date date, sold_price numeric, current_status character varying,
              is_reserved boolean, reserved_for character varying, reserved_draft_id bigint)
    LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        pu.serial_number,
        i.item_name,
        i.brand,
        i.category,
        pi.purchase_invoice_id,
        p.party_name AS vendor_name,
        pi.invoice_date AS purchase_date,
        pit.unit_price AS purchase_price,
        pu.in_stock,
        si.sales_invoice_id,
        c.party_name AS customer_name,
        si.invoice_date AS sale_date,
        su.sold_price,
        COALESCE(su.status, CASE WHEN pu.in_stock THEN 'In Stock' ELSE 'Sold/Unknown' END) AS current_status,
        (res.draft_invoice_id IS NOT NULL) AS is_reserved,
        res.party_name AS reserved_for,
        res.draft_invoice_id AS reserved_draft_id
    FROM PurchaseUnits pu
    JOIN PurchaseItems pit ON pu.purchase_item_id = pit.purchase_item_id
    JOIN Items i ON pit.item_id = i.item_id
    JOIN PurchaseInvoices pi ON pit.purchase_invoice_id = pi.purchase_invoice_id
    JOIN Parties p ON pi.vendor_id = p.party_id
    -- Only ONE sold-unit row: the active 'Sold' one if present, else the newest.
    LEFT JOIN LATERAL (
        SELECT su2.sales_item_id, su2.sold_price, su2.status
        FROM SoldUnits su2
        WHERE su2.unit_id = pu.unit_id
        ORDER BY (su2.status = 'Sold') DESC, su2.sold_unit_id DESC
        LIMIT 1
    ) su ON TRUE
    LEFT JOIN SalesItems si_itm ON su.sales_item_id = si_itm.sales_item_id
    LEFT JOIN SalesInvoices si ON si_itm.sales_invoice_id = si.sales_invoice_id
    LEFT JOIN Parties c ON si.customer_id = c.party_id
    -- The live reservation, if any (draft_units_one_live_reservation makes a
    -- second one impossible; LIMIT 1 is belt and braces).
    LEFT JOIN LATERAL (
        SELECT di.draft_invoice_id, pr.party_name
        FROM DraftUnits du
        JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
        JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
        JOIN Parties pr ON pr.party_id = di.customer_id
        WHERE du.unit_id = pu.unit_id AND du.status = 'Reserved'
        LIMIT 1
    ) res ON TRUE
    WHERE pu.serial_number = serial;
END; $$;

-- The two validators the purchase screen calls before an edit or delete report
-- reserved serials too, so the operator is told before the attempt rather than
-- by the trigger after it.

CREATE OR REPLACE FUNCTION validate_purchase_update2(p_invoice_id bigint, p_items jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_existing_serials TEXT[];
    v_new_serials TEXT[];
    v_removed_serials TEXT[];
    v_sold_serials TEXT[];
    v_returned_serials TEXT[];
    v_reserved_serials TEXT[];
    v_message TEXT;
BEGIN
    -- 1️⃣ Existing serials in invoice
    SELECT ARRAY_AGG(pu.serial_number)
    INTO v_existing_serials
    FROM PurchaseUnits pu
    JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
    WHERE pi.purchase_invoice_id = p_invoice_id;

    IF v_existing_serials IS NULL THEN
        v_existing_serials := ARRAY[]::TEXT[];
    END IF;

    -- 2️⃣ Extract serials from NEW JSON (object format)
    SELECT ARRAY_AGG(serial_obj->>'serial')
    INTO v_new_serials
    FROM jsonb_array_elements(p_items) AS item,
         jsonb_array_elements(item->'serials') AS serial_obj;

    IF v_new_serials IS NULL THEN
        v_new_serials := ARRAY[]::TEXT[];
    END IF;

    -- 3️⃣ Identify removed serials
    SELECT ARRAY_AGG(s)
    INTO v_removed_serials
    FROM unnest(v_existing_serials) AS s
    WHERE s <> ALL(v_new_serials);

    IF v_removed_serials IS NULL THEN
        v_removed_serials := ARRAY[]::TEXT[];
    END IF;

    -- 4️⃣ Check SOLD serials
    SELECT ARRAY_AGG(pu.serial_number)
    INTO v_sold_serials
    FROM SoldUnits su
    JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
    WHERE pu.serial_number = ANY(v_removed_serials);

    IF v_sold_serials IS NULL THEN
        v_sold_serials := ARRAY[]::TEXT[];
    END IF;

    -- 5️⃣ Check RETURNED serials
    SELECT ARRAY_AGG(pri.serial_number)
    INTO v_returned_serials
    FROM PurchaseReturnItems pri
    WHERE pri.serial_number = ANY(v_removed_serials);

    IF v_returned_serials IS NULL THEN
        v_returned_serials := ARRAY[]::TEXT[];
    END IF;

    -- 6️⃣ Check RESERVED serials: a serial held on an open draft invoice cannot
    -- leave stock, so trg_protect_reserved_units would refuse this change.
    SELECT ARRAY_AGG(pu.serial_number)
    INTO v_reserved_serials
    FROM DraftUnits du
    JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
    WHERE du.status = 'Reserved'
      AND pu.serial_number = ANY(v_removed_serials);

    IF v_reserved_serials IS NULL THEN
        v_reserved_serials := ARRAY[]::TEXT[];
    END IF;

    -- 7️⃣ Conflict check
    IF array_length(v_sold_serials, 1) IS NOT NULL
       OR array_length(v_returned_serials, 1) IS NOT NULL
       OR array_length(v_reserved_serials, 1) IS NOT NULL THEN

        v_message := '❌ Cannot update Purchase Invoice ' || p_invoice_id || '.';

        IF array_length(v_sold_serials, 1) IS NOT NULL THEN
            v_message := v_message || ' ' || array_length(v_sold_serials, 1) ||
                        ' serial(s) already sold cannot be removed.';
        END IF;

        IF array_length(v_returned_serials, 1) IS NOT NULL THEN
            v_message := v_message || ' ' || array_length(v_returned_serials, 1) ||
                        ' serial(s) already returned cannot be removed.';
        END IF;

        IF array_length(v_reserved_serials, 1) IS NOT NULL THEN
            v_message := v_message || ' ' || array_length(v_reserved_serials, 1) ||
                        ' serial(s) reserved on an open draft invoice.';
        END IF;

        RETURN jsonb_build_object(
            'is_valid', FALSE,
            'message', v_message,
            'sold_serials', v_sold_serials,
            'returned_serials', v_returned_serials,
            'reserved_serials', v_reserved_serials,
            'removed_serials', v_removed_serials
        );
    END IF;

    -- 8️⃣ Safe
    RETURN jsonb_build_object(
        'is_valid', TRUE,
        'message', '✅ Safe to update — no sold or returned serials will be removed.',
        'sold_serials', v_sold_serials,
        'returned_serials', v_returned_serials,
        'reserved_serials', v_reserved_serials,
        'removed_serials', v_removed_serials
    );
END;
$$;

CREATE OR REPLACE FUNCTION validate_purchase_delete(p_invoice_id bigint) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_invoice_serials TEXT[];
    v_sold_serials TEXT[];
    v_returned_serials TEXT[];
    v_reserved_serials TEXT[];
    v_message TEXT;
BEGIN
    -- 1️⃣ Get all serial numbers from this purchase invoice
    SELECT ARRAY_AGG(pu.serial_number)
    INTO v_invoice_serials
    FROM PurchaseUnits pu
    JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
    WHERE pi.purchase_invoice_id = p_invoice_id;

    IF v_invoice_serials IS NULL THEN
        v_invoice_serials := ARRAY[]::TEXT[];
    END IF;

    -- 2️⃣ Check if any of these serials are sold
    SELECT ARRAY_AGG(pu.serial_number)
    INTO v_sold_serials
    FROM SoldUnits su
    JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
    WHERE pu.serial_number = ANY(v_invoice_serials);

    IF v_sold_serials IS NULL THEN
        v_sold_serials := ARRAY[]::TEXT[];
    END IF;

    -- 3️⃣ Check if any of these serials are already returned to vendor
    SELECT ARRAY_AGG(pri.serial_number)
    INTO v_returned_serials
    FROM PurchaseReturnItems pri
    WHERE pri.serial_number = ANY(v_invoice_serials);

    IF v_returned_serials IS NULL THEN
        v_returned_serials := ARRAY[]::TEXT[];
    END IF;

    -- 4️⃣ Check if any of these serials are reserved on an open draft invoice
    SELECT ARRAY_AGG(pu.serial_number)
    INTO v_reserved_serials
    FROM DraftUnits du
    JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
    WHERE du.status = 'Reserved'
      AND pu.serial_number = ANY(v_invoice_serials);

    IF v_reserved_serials IS NULL THEN
        v_reserved_serials := ARRAY[]::TEXT[];
    END IF;

    -- 5️⃣ If any sold, returned or reserved serials exist, prevent deletion
    IF array_length(v_sold_serials, 1) IS NOT NULL
       OR array_length(v_returned_serials, 1) IS NOT NULL
       OR array_length(v_reserved_serials, 1) IS NOT NULL THEN

        v_message := '❌ Purchase Invoice ' || p_invoice_id || ' cannot be deleted.';

        IF array_length(v_sold_serials, 1) IS NOT NULL THEN
            v_message := v_message || ' ' || array_length(v_sold_serials, 1) || ' sold serial(s) found.';
        END IF;

        IF array_length(v_returned_serials, 1) IS NOT NULL THEN
            v_message := v_message || ' ' || array_length(v_returned_serials, 1) || ' returned serial(s) found.';
        END IF;

        IF array_length(v_reserved_serials, 1) IS NOT NULL THEN
            v_message := v_message || ' ' || array_length(v_reserved_serials, 1) ||
                        ' serial(s) reserved on an open draft invoice.';
        END IF;

        RETURN jsonb_build_object(
            'is_valid', FALSE,
            'message', v_message,
            'sold_serials', v_sold_serials,
            'returned_serials', v_returned_serials,
            'reserved_serials', v_reserved_serials
        );
    END IF;

    -- 6️⃣ Otherwise, safe to delete
    RETURN jsonb_build_object(
        'is_valid', TRUE,
        'message', '✅ Safe to delete — no sold or returned serials found in this invoice.',
        'sold_serials', v_sold_serials,
        'returned_serials', v_returned_serials,
        'reserved_serials', v_reserved_serials
    );
END;
$$;

-- 5. The draft lifecycle ------------------------------------------------------
-- Nothing here writes a journal line, moves stock or touches a balance; only
-- the draft tables are written. Serials arrive as a plain text array, matching
-- create_sale, because conversion hands the same payload shape to create_sale.

-- Shared by create_draft, update_draft and convert_draft_tranche: a draft is
-- always for a named customer that a CREDIT sale can bill. create_sale posts
-- the customer leg to Parties.ar_account_id, and here an Expense party also
-- carries the shared receivable account, so the party type is tested too.
CREATE OR REPLACE FUNCTION assert_draft_customer(p_party_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_name    text;
    v_type    text;
    v_is_cash boolean;
    v_ar      bigint;
BEGIN
    IF p_party_id IS NULL THEN
        RAISE EXCEPTION 'Please select a customer for this draft invoice.';
    END IF;

    SELECT party_name, party_type, COALESCE(is_cash, false), ar_account_id
    INTO v_name, v_type, v_is_cash, v_ar
    FROM Parties WHERE party_id = p_party_id;

    IF v_name IS NULL THEN
        RAISE EXCEPTION 'The selected customer does not exist. Please choose a valid customer.';
    END IF;
    IF v_is_cash THEN
        RAISE EXCEPTION 'This party is a reserved cash account and cannot hold a draft invoice. A draft always reserves goods for a named customer.';
    END IF;
    IF v_type NOT IN ('Customer', 'Both') OR v_ar IS NULL THEN
        RAISE EXCEPTION 'Party "%" is not a customer (its party type is %), so it cannot hold a draft invoice. A draft is invoiced as a credit sale to a customer. Set this party''s type to Customer or Both under Parties, or pick a different customer.',
            v_name, lower(COALESCE(v_type, 'unknown'));
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION create_draft(
    p_party_id    bigint,
    p_draft_date  date,
    p_items       jsonb,
    p_created_by  integer DEFAULT NULL::integer
) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_draft_id     BIGINT;
    v_draft_item   BIGINT;
    v_item         JSONB;
    v_item_name    TEXT;
    v_item_id      BIGINT;
    v_qty_text     TEXT;
    v_price_text   TEXT;
    v_price        NUMERIC(14,2);
    v_qty          INT;
    v_serial_count INT;
    v_serial       TEXT;
    v_unit_id      BIGINT;
    v_serial_item  BIGINT;
    v_in_stock     BOOLEAN;
    v_dup          TEXT;
BEGIN
    PERFORM assert_draft_customer(p_party_id);

    IF p_draft_date IS NULL THEN
        RAISE EXCEPTION 'Draft date is required.';
    END IF;
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'At least one item is required to create a draft invoice.';
    END IF;

    -- Duplicate serials anywhere in the payload.
    SELECT s INTO v_dup
    FROM (SELECT jsonb_array_elements_text(it->'serials') AS s
          FROM jsonb_array_elements(p_items) it) q
    GROUP BY s HAVING count(*) > 1 LIMIT 1;
    IF v_dup IS NOT NULL THEN
        RAISE EXCEPTION 'Serial "%" appears more than once in this draft. Each serial number can only be reserved once.', v_dup;
    END IF;

    -- Per-item validation, before anything is written.
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_item_name  := NULLIF(btrim(COALESCE(v_item->>'item_name','')), '');
        v_qty_text   := v_item->>'qty';
        v_price_text := v_item->>'unit_price';

        IF v_item_name IS NULL THEN
            RAISE EXCEPTION 'Item name is missing for one of the draft rows.';
        END IF;
        IF v_qty_text IS NULL OR v_qty_text !~ '^[0-9]+$' OR v_qty_text::INT <= 0 THEN
            RAISE EXCEPTION 'Quantity for item "%" must be a whole number greater than zero.', v_item_name;
        END IF;
        -- The rate is OPTIONAL on a draft. Absent, null and empty all mean "not
        -- agreed yet"; anything present must still be a valid number.
        IF v_price_text IS NOT NULL AND btrim(v_price_text) <> ''
           AND v_price_text !~ '^[0-9]+(\.[0-9]+)?$' THEN
            RAISE EXCEPTION 'Expected rate for item "%" must be a valid non-negative number, or left blank until it is agreed.', v_item_name;
        END IF;
        IF v_item->'serials' IS NULL OR jsonb_typeof(v_item->'serials') <> 'array' THEN
            RAISE EXCEPTION 'Serial numbers are missing for item "%".', v_item_name;
        END IF;

        v_qty          := v_qty_text::INT;
        v_serial_count := jsonb_array_length(v_item->'serials');

        IF v_qty <> v_serial_count THEN
            RAISE EXCEPTION 'Quantity (%) does not match the number of serial numbers (%) for item "%". Please provide exactly one serial number per unit.', v_qty, v_serial_count, v_item_name;
        END IF;
    END LOOP;

    INSERT INTO DraftInvoices(customer_id, draft_date, status, created_by)
    VALUES (p_party_id, p_draft_date, 'Open', p_created_by)
    RETURNING draft_invoice_id INTO v_draft_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_item_id := NULL;
        SELECT item_id INTO v_item_id FROM Items
        WHERE item_name = (v_item->>'item_name') LIMIT 1;
        IF v_item_id IS NULL THEN
            RAISE EXCEPTION 'Item "%" does not exist. Please create the item first.', (v_item->>'item_name');
        END IF;

        v_price_text := v_item->>'unit_price';
        v_price := CASE
                       WHEN v_price_text IS NULL OR btrim(v_price_text) = '' THEN NULL
                       ELSE v_price_text::NUMERIC
                   END;

        INSERT INTO DraftItems(draft_invoice_id, item_id, quantity, unit_price)
        VALUES (v_draft_id, v_item_id, (v_item->>'qty')::INT, v_price)
        RETURNING draft_item_id INTO v_draft_item;

        FOR v_serial IN SELECT jsonb_array_elements_text(v_item->'serials')
        LOOP
            IF v_serial IS NULL OR btrim(v_serial) = '' THEN
                RAISE EXCEPTION 'A blank serial number was submitted for item "%". Please remove empty serial entries.', (v_item->>'item_name');
            END IF;

            -- FOR UPDATE for the same reason create_sale has it: the row lock
            -- that serialises this draft against a concurrent sale.
            -- trg_reserve_only_stocked_units takes it again on INSERT and is the
            -- real guard; this lookup gives a precise message first.
            v_unit_id := NULL;
            SELECT pu.unit_id, pi.item_id, pu.in_stock
            INTO v_unit_id, v_serial_item, v_in_stock
            FROM PurchaseUnits pu
            JOIN PurchaseItems pi ON pi.purchase_item_id = pu.purchase_item_id
            WHERE pu.serial_number = v_serial
            LIMIT 1
            FOR UPDATE OF pu;

            IF v_unit_id IS NULL THEN
                RAISE EXCEPTION 'Serial "%" does not exist in the system. Please check the serial number.', v_serial;
            END IF;
            IF NOT v_in_stock THEN
                RAISE EXCEPTION 'Serial "%" is not available in stock, so it cannot be reserved on a draft invoice. It may already be sold or returned to the vendor.', v_serial;
            END IF;
            IF v_serial_item <> v_item_id THEN
                RAISE EXCEPTION 'Serial "%" does not belong to item "%". Please check the serial number.', v_serial, (v_item->>'item_name');
            END IF;
            IF EXISTS (SELECT 1 FROM DraftUnits WHERE unit_id = v_unit_id AND status = 'Reserved') THEN
                RAISE EXCEPTION 'Serial "%" is already reserved on another draft invoice.', v_serial;
            END IF;

            INSERT INTO DraftUnits(draft_item_id, unit_id) VALUES (v_draft_item, v_unit_id);
        END LOOP;
    END LOOP;

    RETURN v_draft_id;
END;
$$;

-- Editable only while nothing has been converted. Released rows survive an
-- edit: they are the record of a serial deliberately taken off this deal.
CREATE OR REPLACE FUNCTION update_draft(
    p_draft_id   bigint,
    p_items      jsonb,
    p_party_id   bigint  DEFAULT NULL::bigint,
    p_draft_date date    DEFAULT NULL::date,
    p_created_by integer DEFAULT NULL::integer
) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_status     TEXT;
    v_converted  INT;
    v_new_id     BIGINT;
BEGIN
    SELECT status INTO v_status
    FROM DraftInvoices WHERE draft_invoice_id = p_draft_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        RAISE EXCEPTION 'Draft invoice % was not found.', p_draft_id;
    END IF;
    IF v_status <> 'Open' THEN
        RAISE EXCEPTION 'Draft invoice % is % and can no longer be edited.', p_draft_id, lower(v_status);
    END IF;

    SELECT count(*) INTO v_converted
    FROM DraftUnits du
    JOIN DraftItems di ON di.draft_item_id = du.draft_item_id
    WHERE di.draft_invoice_id = p_draft_id AND du.status = 'Converted';

    IF v_converted > 0 THEN
        RAISE EXCEPTION 'Draft invoice % has already had % unit(s) invoiced and can no longer be edited. Release the remaining serials instead, or raise a new draft.', p_draft_id, v_converted;
    END IF;

    -- Header. The customer may still change, because nothing is converted.
    IF p_party_id IS NOT NULL THEN
        PERFORM assert_draft_customer(p_party_id);
        UPDATE DraftInvoices SET customer_id = p_party_id WHERE draft_invoice_id = p_draft_id;
    END IF;
    IF p_draft_date IS NOT NULL THEN
        UPDATE DraftInvoices SET draft_date = p_draft_date WHERE draft_invoice_id = p_draft_id;
    END IF;

    -- Drop the live reservations, keep the Released history.
    DELETE FROM DraftUnits du
    USING DraftItems di
    WHERE di.draft_item_id = du.draft_item_id
      AND di.draft_invoice_id = p_draft_id
      AND du.status = 'Reserved';

    DELETE FROM DraftItems di
    WHERE di.draft_invoice_id = p_draft_id
      AND NOT EXISTS (SELECT 1 FROM DraftUnits du WHERE du.draft_item_id = di.draft_item_id);

    -- Rebuild through create_draft so validation lives in exactly one place,
    -- then move the rebuilt lines onto this draft and discard the shell.
    v_new_id := create_draft(
        (SELECT customer_id FROM DraftInvoices WHERE draft_invoice_id = p_draft_id),
        (SELECT draft_date FROM DraftInvoices WHERE draft_invoice_id = p_draft_id),
        p_items,
        p_created_by);

    UPDATE DraftItems SET draft_invoice_id = p_draft_id WHERE draft_invoice_id = v_new_id;
    DELETE FROM DraftInvoices WHERE draft_invoice_id = v_new_id;
END;
$$;

CREATE OR REPLACE FUNCTION delete_draft(p_draft_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_status    TEXT;
    v_converted INT;
BEGIN
    SELECT status INTO v_status
    FROM DraftInvoices WHERE draft_invoice_id = p_draft_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        RAISE EXCEPTION 'Draft invoice % was not found.', p_draft_id;
    END IF;

    SELECT count(*) INTO v_converted
    FROM DraftUnits du
    JOIN DraftItems di ON di.draft_item_id = du.draft_item_id
    WHERE di.draft_invoice_id = p_draft_id AND du.status = 'Converted';

    IF v_converted > 0 THEN
        RAISE EXCEPTION 'Draft invoice % has already had % unit(s) invoiced and cannot be deleted. Cancel it instead, which releases whatever is still reserved and keeps the record of what was sold.', p_draft_id, v_converted;
    END IF;

    -- A confirmed draft return may still point at this draft (its units were
    -- converted, then the conversion's sale was deleted and re-entered).
    UPDATE DraftReturns SET draft_invoice_id = NULL WHERE draft_invoice_id = p_draft_id;

    -- ON DELETE CASCADE removes the items and the reservations with it.
    DELETE FROM DraftInvoices WHERE draft_invoice_id = p_draft_id;
END;
$$;

-- A draft with nothing left reserved is finished: Converted if any unit became
-- an invoice, Cancelled if none ever did. Shared by release and conversion so
-- the two can never disagree about when that is.
CREATE OR REPLACE FUNCTION close_draft_if_settled(
    p_draft_id bigint,
    p_actor    integer DEFAULT NULL::integer
) RETURNS text
    LANGUAGE plpgsql AS $$
DECLARE
    v_reserved  INT;
    v_converted INT;
    v_status    TEXT;
BEGIN
    SELECT count(*) FILTER (WHERE du.status = 'Reserved'),
           count(*) FILTER (WHERE du.status = 'Converted')
    INTO v_reserved, v_converted
    FROM DraftUnits du
    JOIN DraftItems di ON di.draft_item_id = du.draft_item_id
    WHERE di.draft_invoice_id = p_draft_id;

    IF v_reserved > 0 THEN
        RETURN 'Open';
    END IF;

    v_status := CASE WHEN v_converted > 0 THEN 'Converted' ELSE 'Cancelled' END;
    UPDATE DraftInvoices
    SET status = v_status, closed_at = clock_timestamp(), closed_by = p_actor
    WHERE draft_invoice_id = p_draft_id AND status = 'Open';
    RETURN v_status;
END;
$$;

-- Take named serials off a draft. Marks, never deletes.
CREATE OR REPLACE FUNCTION release_draft_units(
    p_draft_id    bigint,
    p_serials     jsonb,
    p_released_by integer DEFAULT NULL::integer
) RETURNS integer
    LANGUAGE plpgsql AS $$
DECLARE
    v_status    TEXT;
    v_serial    TEXT;
    v_unit_id   BIGINT;
    v_released  INT := 0;
BEGIN
    SELECT status INTO v_status
    FROM DraftInvoices WHERE draft_invoice_id = p_draft_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        RAISE EXCEPTION 'Draft invoice % was not found.', p_draft_id;
    END IF;
    IF v_status <> 'Open' THEN
        RAISE EXCEPTION 'Draft invoice % is % and holds nothing to release.', p_draft_id, lower(v_status);
    END IF;
    IF p_serials IS NULL OR jsonb_typeof(p_serials) <> 'array' OR jsonb_array_length(p_serials) = 0 THEN
        RAISE EXCEPTION 'At least one serial number is required to release from a draft invoice.';
    END IF;

    FOR v_serial IN SELECT DISTINCT btrim(s) FROM jsonb_array_elements_text(p_serials) AS s
                    WHERE btrim(s) <> ''
    LOOP
        v_unit_id := NULL;
        SELECT du.unit_id INTO v_unit_id
        FROM DraftUnits du
        JOIN DraftItems di ON di.draft_item_id = du.draft_item_id
        JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
        WHERE di.draft_invoice_id = p_draft_id
          AND pu.serial_number = v_serial
          AND du.status = 'Reserved';

        IF v_unit_id IS NULL THEN
            RAISE EXCEPTION 'Serial "%" is not currently reserved on draft invoice %.', v_serial, p_draft_id;
        END IF;

        UPDATE DraftUnits
        SET status = 'Released', released_at = clock_timestamp(), released_by = p_released_by
        WHERE unit_id = v_unit_id AND status = 'Reserved';

        v_released := v_released + 1;
    END LOOP;

    IF v_released = 0 THEN
        RAISE EXCEPTION 'At least one serial number is required to release from a draft invoice.';
    END IF;

    PERFORM close_draft_if_settled(p_draft_id, p_released_by);
    RETURN v_released;
END;
$$;

-- Release everything still reserved and close the draft. Invoices already
-- raised from it stand on their own.
CREATE OR REPLACE FUNCTION cancel_draft(
    p_draft_id     bigint,
    p_cancelled_by integer DEFAULT NULL::integer
) RETURNS integer
    LANGUAGE plpgsql AS $$
DECLARE
    v_status   TEXT;
    v_released INT;
BEGIN
    SELECT status INTO v_status
    FROM DraftInvoices WHERE draft_invoice_id = p_draft_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        RAISE EXCEPTION 'Draft invoice % was not found.', p_draft_id;
    END IF;
    IF v_status <> 'Open' THEN
        RAISE EXCEPTION 'Draft invoice % is already %.', p_draft_id, lower(v_status);
    END IF;

    WITH released AS (
        UPDATE DraftUnits du
        SET status = 'Released', released_at = clock_timestamp(), released_by = p_cancelled_by
        FROM DraftItems di
        WHERE di.draft_item_id = du.draft_item_id
          AND di.draft_invoice_id = p_draft_id
          AND du.status = 'Reserved'
        RETURNING 1
    )
    SELECT count(*) INTO v_released FROM released;

    UPDATE DraftInvoices
    SET status = 'Cancelled', closed_at = clock_timestamp(), closed_by = p_cancelled_by
    WHERE draft_invoice_id = p_draft_id;

    RETURN v_released;
END;
$$;

-- An opening-stock load holding a reserved unit cannot be deleted: its existing
-- definition with a reserved-unit pre-check added, so the operator gets this
-- sentence rather than the trigger's refusal surfacing as a database error.
CREATE OR REPLACE FUNCTION delete_opening_stock(p_id bigint)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE v_sold int; v_reserved int; v_j bigint;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM purchaseinvoices WHERE purchase_invoice_id = p_id AND is_opening = true) THEN
        RETURN jsonb_build_object('status','error','message','Opening stock entry not found.');
    END IF;

    SELECT count(*) INTO v_sold
    FROM purchaseunits u JOIN purchaseitems x ON x.purchase_item_id = u.purchase_item_id
    WHERE x.purchase_invoice_id = p_id AND u.in_stock = false;
    IF v_sold > 0 THEN
        RETURN jsonb_build_object('status','error','message',
            'Cannot delete: '||v_sold||' unit(s) from this opening stock have already been sold or used.');
    END IF;

    SELECT count(*) INTO v_reserved
    FROM purchaseunits u JOIN purchaseitems x ON x.purchase_item_id = u.purchase_item_id
    JOIN draftunits du ON du.unit_id = u.unit_id AND du.status = 'Reserved'
    WHERE x.purchase_invoice_id = p_id;
    IF v_reserved > 0 THEN
        RETURN jsonb_build_object('status','error','message',
            'Cannot delete: '||v_reserved||' unit(s) from this opening stock are reserved on a draft invoice. Release them from the draft first.');
    END IF;

    SELECT journal_id INTO v_j FROM purchaseinvoices WHERE purchase_invoice_id = p_id;
    DELETE FROM purchaseinvoices WHERE purchase_invoice_id = p_id;  -- cascades items + units
    IF v_j IS NOT NULL THEN DELETE FROM journalentries WHERE journal_id = v_j; END IF;

    RETURN jsonb_build_object('status','success','message','Opening stock entry deleted.');
END; $$;

-- 6. Reading drafts -----------------------------------------------------------

-- Navigation walks OPEN drafts only: a converted or cancelled draft holds
-- nothing, and landing on its empty shell reads as a bug. Draft History lists
-- every draft and opens it through get_current_draft, which is unfiltered.
CREATE OR REPLACE FUNCTION get_last_draft_id() RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE last_id BIGINT;
BEGIN
    SELECT draft_invoice_id INTO last_id
    FROM DraftInvoices WHERE status = 'Open'
    ORDER BY draft_invoice_id DESC LIMIT 1;
    RETURN last_id;
END;
$$;

-- Reports what REMAINS: a line's qty is the units still reserved on it, and
-- reserved_details carries each reserved serial's own purchase cost so the
-- conversion screen can warn before a tranche is priced below cost.
CREATE OR REPLACE FUNCTION get_current_draft(p_draft_id bigint) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'draft_invoice_id', d.draft_invoice_id,
        'Party',            p.party_name,
        'draft_date',       d.draft_date,
        'status',           d.status,
        'status_label',     CASE
                                WHEN d.status = 'Open' AND EXISTS (
                                    SELECT 1 FROM DraftUnits du
                                    JOIN DraftItems di2 ON di2.draft_item_id = du.draft_item_id
                                    WHERE di2.draft_invoice_id = d.draft_invoice_id
                                      AND du.status = 'Converted')
                                THEN 'Partially Converted'
                                ELSE d.status
                            END,
        'description',      d.description,
        'created_by',       COALESCE(u.username, 'N/A'),
        'reserved_units',   (SELECT count(*) FROM DraftUnits du
                             JOIN DraftItems di2 ON di2.draft_item_id = du.draft_item_id
                             WHERE di2.draft_invoice_id = d.draft_invoice_id
                               AND du.status = 'Reserved'),
        'converted_units',  (SELECT count(*) FROM DraftUnits du
                             JOIN DraftItems di2 ON di2.draft_item_id = du.draft_item_id
                             WHERE di2.draft_invoice_id = d.draft_invoice_id
                               AND du.status = 'Converted'),
        'invoices',         (SELECT json_agg(DISTINCT du.sales_invoice_id)
                             FROM DraftUnits du
                             JOIN DraftItems di2 ON di2.draft_item_id = du.draft_item_id
                             WHERE di2.draft_invoice_id = d.draft_invoice_id
                               AND du.sales_invoice_id IS NOT NULL),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',    i.item_name,
                'qty',          (SELECT count(*) FROM DraftUnits du
                                 WHERE du.draft_item_id = di.draft_item_id
                                   AND du.status = 'Reserved'),
                'original_qty', di.quantity,
                'unit_price',   di.unit_price,
                'serials', (
                    SELECT json_agg(pu.serial_number ORDER BY pu.serial_number)
                    FROM DraftUnits du
                    JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
                    WHERE du.draft_item_id = di.draft_item_id
                      AND du.status = 'Reserved'
                ),
                'reserved_details', (
                    SELECT json_agg(json_build_object(
                               'serial', pu.serial_number,
                               'unit_cost', pit.unit_price)
                           ORDER BY pu.serial_number)
                    FROM DraftUnits du
                    JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
                    JOIN PurchaseItems pit ON pit.purchase_item_id = pu.purchase_item_id
                    WHERE du.draft_item_id = di.draft_item_id
                      AND du.status = 'Reserved'
                ),
                'converted_serials', (
                    SELECT json_agg(pu.serial_number ORDER BY pu.serial_number)
                    FROM DraftUnits du
                    JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
                    WHERE du.draft_item_id = di.draft_item_id
                      AND du.status = 'Converted'
                ),
                'released_serials', (
                    SELECT json_agg(pu.serial_number ORDER BY pu.serial_number)
                    FROM DraftUnits du
                    JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
                    WHERE du.draft_item_id = di.draft_item_id
                      AND du.status = 'Released'
                )
            ) ORDER BY di.draft_item_id)
            FROM DraftItems di
            JOIN Items i ON i.item_id = di.item_id
            WHERE di.draft_invoice_id = d.draft_invoice_id
        )
    ) INTO result
    FROM DraftInvoices d
    JOIN Parties p ON p.party_id = d.customer_id
    LEFT JOIN auth_user u ON u.id = d.created_by
    WHERE d.draft_invoice_id = p_draft_id;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION get_previous_draft(p_draft_id bigint) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE prev_id BIGINT;
BEGIN
    SELECT draft_invoice_id INTO prev_id
    FROM DraftInvoices
    WHERE draft_invoice_id < p_draft_id AND status = 'Open'
    ORDER BY draft_invoice_id DESC LIMIT 1;
    IF prev_id IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN get_current_draft(prev_id);
END;
$$;

CREATE OR REPLACE FUNCTION get_next_draft(p_draft_id bigint) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE next_id BIGINT;
BEGIN
    SELECT draft_invoice_id INTO next_id
    FROM DraftInvoices
    WHERE draft_invoice_id > p_draft_id AND status = 'Open'
    ORDER BY draft_invoice_id ASC LIMIT 1;
    IF next_id IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN get_current_draft(next_id);
END;
$$;

-- The history popup. The indicative value counts only reserved units whose line
-- carries a rate, and unpriced_lines says how many lines do not.
CREATE OR REPLACE FUNCTION get_draft_summary(
    p_start_date date DEFAULT NULL::date,
    p_end_date   date DEFAULT NULL::date
) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE result JSON;
BEGIN
    SELECT json_agg(x ORDER BY x.draft_date DESC, x.draft_invoice_id DESC)
    INTO result
    FROM (
        SELECT
            d.draft_invoice_id,
            d.draft_date,
            p.party_name AS customer,
            d.status,
            CASE
                WHEN d.status = 'Open' AND count(*) FILTER (WHERE du.status = 'Converted') > 0
                THEN 'Partially Converted'
                ELSE d.status
            END AS status_label,
            count(*) FILTER (WHERE du.status = 'Reserved')  AS reserved_units,
            count(*) FILTER (WHERE du.status = 'Converted') AS converted_units,
            count(*) FILTER (WHERE du.status = 'Released')  AS released_units,
            COALESCE(SUM(di.unit_price) FILTER (WHERE du.status = 'Reserved'
                                                 AND di.unit_price IS NOT NULL), 0)::numeric(14,2)
                AS indicative_value,
            count(DISTINCT di.draft_item_id) FILTER (WHERE di.unit_price IS NULL) AS unpriced_lines,
            (CURRENT_DATE - d.draft_date) AS days_outstanding
        FROM DraftInvoices d
        JOIN Parties p ON p.party_id = d.customer_id
        LEFT JOIN DraftItems di ON di.draft_invoice_id = d.draft_invoice_id
        LEFT JOIN DraftUnits du ON du.draft_item_id = di.draft_item_id
        WHERE (p_start_date IS NULL OR p_end_date IS NULL
               OR d.draft_date BETWEEN p_start_date AND p_end_date)
        GROUP BY d.draft_invoice_id, d.draft_date, p.party_name, d.status
    ) AS x;
    RETURN COALESCE(result, '[]'::json);
END;
$$;

-- 7. Conversion: a tranche becomes a real sale invoice ------------------------
-- The only thing here that moves stock, posts a journal or changes a balance,
-- and it does none of those itself: it delegates to create_sale. p_items is the
-- SAME payload shape create_sale takes. Unlike a draft, the rate is mandatory.
--
-- THE ORDERING IS LOAD-BEARING. The units are flipped to 'Converted' BEFORE
-- create_sale is called, so trg_protect_reserved_units finds no live
-- reservation when create_sale takes them out of stock.

CREATE OR REPLACE FUNCTION convert_draft_tranche(
    p_draft_id     bigint,
    p_items        jsonb,
    p_invoice_date date,
    p_created_by   integer DEFAULT NULL::integer
) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_status      TEXT;
    v_customer_id BIGINT;
    v_item        JSONB;
    v_item_name   TEXT;
    v_price_text  TEXT;
    v_serial      TEXT;
    v_du_id       BIGINT;
    v_du_status   TEXT;
    v_du_draft    BIGINT;
    v_du_item     TEXT;
    v_invoice_id  BIGINT;
    v_dup         TEXT;
BEGIN
    SELECT status, customer_id INTO v_status, v_customer_id
    FROM DraftInvoices WHERE draft_invoice_id = p_draft_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        RAISE EXCEPTION 'Draft invoice % was not found.', p_draft_id;
    END IF;
    IF v_status <> 'Open' THEN
        RAISE EXCEPTION 'Draft invoice % is % and can no longer be converted.', p_draft_id, lower(v_status);
    END IF;

    -- Checked again here: a party's type can change after the draft was raised.
    PERFORM assert_draft_customer(v_customer_id);

    IF p_invoice_date IS NULL THEN
        RAISE EXCEPTION 'Sale date is required.';
    END IF;
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'Select at least one serial number to convert into a sale invoice.';
    END IF;

    SELECT s INTO v_dup
    FROM (SELECT jsonb_array_elements_text(it->'serials') AS s
          FROM jsonb_array_elements(p_items) it) q
    GROUP BY s HAVING count(*) > 1 LIMIT 1;
    IF v_dup IS NOT NULL THEN
        RAISE EXCEPTION 'Serial "%" appears more than once in this conversion. Each serial can only be invoiced once.', v_dup;
    END IF;

    -- Every line must carry an agreed rate, and every serial must be reserved on
    -- THIS draft under the same item. Checked in full before anything is written.
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_item_name  := NULLIF(btrim(COALESCE(v_item->>'item_name','')), '');
        v_price_text := v_item->>'unit_price';

        IF v_item_name IS NULL THEN
            RAISE EXCEPTION 'Item name is missing for one of the rows being converted.';
        END IF;
        IF v_price_text IS NULL OR btrim(v_price_text) = '' THEN
            RAISE EXCEPTION 'A final rate is required for item "%" before it can be invoiced. The rate on a draft is only an expectation.', v_item_name;
        END IF;
        IF v_price_text !~ '^[0-9]+(\.[0-9]+)?$' OR v_price_text::NUMERIC <= 0 THEN
            RAISE EXCEPTION 'Sale price for item "%" must be a number greater than zero.', v_item_name;
        END IF;
        IF v_item->'serials' IS NULL OR jsonb_typeof(v_item->'serials') <> 'array'
           OR jsonb_array_length(v_item->'serials') = 0 THEN
            RAISE EXCEPTION 'Serial numbers are missing for item "%".', v_item_name;
        END IF;
        IF COALESCE(v_item->>'qty', '') !~ '^[0-9]+$'
           OR (v_item->>'qty')::INT <> jsonb_array_length(v_item->'serials') THEN
            RAISE EXCEPTION 'Quantity for item "%" must equal the number of serial numbers being invoiced (%).', v_item_name, jsonb_array_length(v_item->'serials');
        END IF;

        FOR v_serial IN SELECT jsonb_array_elements_text(v_item->'serials')
        LOOP
            v_du_id := NULL;
            SELECT du.draft_unit_id, du.status, di.draft_invoice_id, i.item_name
            INTO v_du_id, v_du_status, v_du_draft, v_du_item
            FROM DraftUnits du
            JOIN DraftItems di ON di.draft_item_id = du.draft_item_id
            JOIN Items i ON i.item_id = di.item_id
            JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
            WHERE pu.serial_number = v_serial
            ORDER BY (du.status = 'Reserved') DESC, du.draft_unit_id DESC
            LIMIT 1;

            IF v_du_id IS NULL THEN
                RAISE EXCEPTION 'Serial "%" is not on any draft invoice, so it cannot be converted. Sell it from the Sale screen instead.', v_serial;
            END IF;
            IF v_du_draft <> p_draft_id THEN
                RAISE EXCEPTION 'Serial "%" belongs to draft invoice #%, not #%.', v_serial, v_du_draft, p_draft_id;
            END IF;
            IF v_du_status = 'Converted' THEN
                RAISE EXCEPTION 'Serial "%" has already been invoiced from this draft.', v_serial;
            END IF;
            IF v_du_status = 'Released' THEN
                RAISE EXCEPTION 'Serial "%" was released from this draft and is no longer reserved for this customer.', v_serial;
            END IF;
            IF v_du_item <> v_item_name THEN
                RAISE EXCEPTION 'Serial "%" is reserved on this draft under item "%", not "%".', v_serial, v_du_item, v_item_name;
            END IF;
        END LOOP;
    END LOOP;

    -- Settle the reservations FIRST (see the section header).
    UPDATE DraftUnits du
    SET status = 'Converted', converted_at = clock_timestamp(), converted_by = p_created_by
    FROM DraftItems di, PurchaseUnits pu
    WHERE di.draft_item_id = du.draft_item_id
      AND pu.unit_id = du.unit_id
      AND di.draft_invoice_id = p_draft_id
      AND du.status = 'Reserved'
      AND pu.serial_number IN (
          SELECT jsonb_array_elements_text(it->'serials')
          FROM jsonb_array_elements(p_items) it);

    -- One function creates a sale in this system, and this is not it. The draft
    -- customer is never a cash party, so this is always a credit sale.
    v_invoice_id := create_sale(v_customer_id, p_invoice_date, p_items, p_created_by);

    -- Record the link in both directions.
    UPDATE SalesInvoices SET draft_invoice_id = p_draft_id
    WHERE sales_invoice_id = v_invoice_id;

    UPDATE DraftUnits du
    SET sales_invoice_id = v_invoice_id
    FROM DraftItems di, PurchaseUnits pu
    WHERE di.draft_item_id = du.draft_item_id
      AND pu.unit_id = du.unit_id
      AND di.draft_invoice_id = p_draft_id
      AND du.status = 'Converted'
      AND du.sales_invoice_id IS NULL
      AND pu.serial_number IN (
          SELECT jsonb_array_elements_text(it->'serials')
          FROM jsonb_array_elements(p_items) it);

    PERFORM close_draft_if_settled(p_draft_id, p_created_by);

    RETURN v_invoice_id;
END;
$$;

-- 8. Returns: the Confirmed Draft Return document ------------------------------
-- A serial sold on an invoice raised from a draft is returned through its own
-- document, never mixed into the ordinary Sale Return. The accounting IS an
-- ordinary sale return -- the same SalesReturns row, stock restoration and
-- journal builder -- because a separate journal would be invisible to every
-- ledger and to the trial balance. Segregation is structural: the ordinary
-- paths refuse draft-sold serials and the draft paths refuse ordinary ones.

-- Why a serial cannot be returned. A reserved serial is still in stock and was
-- never invoiced, so there is nothing to return: say how to free it instead.
CREATE OR REPLACE FUNCTION raise_serial_not_returnable(p_serial text) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_draft BIGINT;
    v_party TEXT;
BEGIN
    SELECT di.draft_invoice_id, p.party_name INTO v_draft, v_party
    FROM DraftUnits du
    JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
    JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
    JOIN Parties p ON p.party_id = di.customer_id
    JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
    WHERE pu.serial_number = p_serial AND du.status = 'Reserved'
    LIMIT 1;

    IF v_draft IS NOT NULL THEN
        RAISE EXCEPTION 'Serial "%" is reserved on draft invoice #% for "%", not sold, so there is nothing to return. Open that draft and use Release Serials to put the unit back into free stock.',
            p_serial, v_draft, v_party;
    END IF;
    RAISE EXCEPTION 'Serial % is not currently sold (nothing to return)', p_serial;
END;
$$;

-- create_sale_return's body, given an explicit return date (NULL keeps
-- CURRENT_DATE) and a flag saying whether draft-sold serials are the ones
-- allowed. Extracted rather than duplicated: there must remain exactly one
-- implementation of what a sale return does to stock and the journal.
CREATE OR REPLACE FUNCTION sale_return_core(
    p_party_name  text,
    p_serials     jsonb,
    p_created_by  integer DEFAULT NULL::integer,
    p_return_date date    DEFAULT NULL::date,
    p_allow_draft boolean DEFAULT FALSE
) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_return_id   BIGINT;
    v_customer_id BIGINT;
    v_serial      TEXT;
    v_unit        RECORD;
    v_total       NUMERIC(14,2) := 0;
BEGIN
    SELECT party_id INTO v_customer_id FROM Parties WHERE party_name = p_party_name LIMIT 1;
    IF v_customer_id IS NULL THEN
        RAISE EXCEPTION 'Party "%" not found', p_party_name;
    END IF;

    INSERT INTO SalesReturns(customer_id, return_date, total_amount, created_by)
    VALUES (v_customer_id, COALESCE(p_return_date, CURRENT_DATE), 0, p_created_by)
    RETURNING sales_return_id INTO v_return_id;

    FOR v_serial IN SELECT jsonb_array_elements_text(p_serials)
    LOOP
        SELECT su.sold_unit_id, su.unit_id, su.sold_price, si.item_id,
               si.sales_invoice_id, pu.serial_number, pi.unit_price, s.customer_id,
               s.invoice_date, (s.draft_invoice_id IS NOT NULL) AS from_draft
        INTO v_unit
        FROM SoldUnits su
        JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
        JOIN SalesInvoices s ON si.sales_invoice_id = s.sales_invoice_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
        WHERE pu.serial_number = v_serial
          AND su.status = 'Sold'
        ORDER BY su.sold_unit_id DESC
        LIMIT 1
        FOR UPDATE OF su, pu;

        IF NOT FOUND THEN
            PERFORM raise_serial_not_returnable(v_serial);
        END IF;
        IF v_unit.customer_id <> v_customer_id THEN
            RAISE EXCEPTION 'Serial % was not sold to this customer', v_serial;
        END IF;
        IF v_unit.from_draft AND NOT p_allow_draft THEN
            RAISE EXCEPTION 'Serial "%" was sold on draft-based invoice #%. Use the Confirmed Draft Return screen to return it.', v_serial, v_unit.sales_invoice_id;
        END IF;
        IF p_allow_draft AND NOT v_unit.from_draft THEN
            RAISE EXCEPTION 'Serial "%" was sold on ordinary sale invoice #%, not from a draft. Use the Sale Return screen to return it.', v_serial, v_unit.sales_invoice_id;
        END IF;
        IF p_return_date IS NOT NULL AND p_return_date < v_unit.invoice_date THEN
            RAISE EXCEPTION 'Return date % is before serial "%" was sold on %.', p_return_date, v_serial, v_unit.invoice_date;
        END IF;

        UPDATE SoldUnits SET status = 'Returned' WHERE sold_unit_id = v_unit.sold_unit_id;
        UPDATE PurchaseUnits SET in_stock = TRUE WHERE unit_id = v_unit.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (v_unit.item_id, v_serial, 'IN', 'SalesReturn', v_return_id, 1);

        INSERT INTO SalesReturnItems(sales_return_id, item_id, sold_price, cost_price, serial_number)
        VALUES (v_return_id, v_unit.item_id, v_unit.sold_price, v_unit.unit_price, v_serial);

        v_total := v_total + v_unit.sold_price;
    END LOOP;

    UPDATE SalesReturns SET total_amount = v_total WHERE sales_return_id = v_return_id;
    PERFORM rebuild_sales_return_journal(v_return_id);
    RETURN v_return_id;
END;
$$;

-- Same signature and behaviour for every existing caller; it now also refuses a
-- draft-sold serial, pointing at the Confirmed Draft Return screen.
CREATE OR REPLACE FUNCTION create_sale_return(p_party_name text, p_serials jsonb, p_created_by integer DEFAULT NULL::integer) RETURNS bigint
    LANGUAGE plpgsql AS $$
BEGIN
    RETURN sale_return_core(p_party_name, p_serials, p_created_by, NULL, FALSE);
END;
$$;

-- The lifecycle-guarded update, unchanged except that the document it edits
-- decides which serials it may take: an ordinary return refuses draft-sold
-- serials and a confirmed draft return refuses ordinary ones (and any dated
-- before their sale).
CREATE OR REPLACE FUNCTION update_sale_return(p_return_id bigint, p_serials jsonb, p_created_by integer DEFAULT NULL::integer) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec               RECORD;
    v_serial          TEXT;
    v_unit            RECORD;
    v_total           NUMERIC(14,2) := 0;
    v_customer_id     BIGINT;
    v_draft_return_id BIGINT;
    v_return_date     DATE;
BEGIN
    FOR rec IN
        SELECT serial_number, item_id
        FROM SalesReturnItems
        WHERE sales_return_id = p_return_id
    LOOP
        IF EXISTS (
            SELECT 1
            FROM SoldUnits su
            JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
            WHERE pu.serial_number = rec.serial_number
              AND su.status = 'Sold'
        ) THEN
            RAISE EXCEPTION 'Cannot update this sale return: serial % has since been re-sold. Reverse the later sale first.', rec.serial_number;
        END IF;

        UPDATE SoldUnits SET status = 'Sold'
        WHERE sold_unit_id = (
            SELECT su2.sold_unit_id
            FROM SoldUnits su2
            JOIN PurchaseUnits pu2 ON su2.unit_id = pu2.unit_id
            WHERE pu2.serial_number = rec.serial_number
              AND su2.status = 'Returned'
            ORDER BY su2.sold_unit_id DESC
            LIMIT 1
        );

        UPDATE PurchaseUnits SET in_stock = FALSE WHERE serial_number = rec.serial_number;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'OUT', 'SalesReturn-Update-Reverse', p_return_id, 1);
    END LOOP;

    DELETE FROM SalesReturnItems WHERE sales_return_id = p_return_id;

    SELECT customer_id, draft_return_id, return_date
    INTO v_customer_id, v_draft_return_id, v_return_date
    FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF v_customer_id IS NULL THEN
        RAISE EXCEPTION 'Sale return % not found', p_return_id;
    END IF;

    FOR v_serial IN SELECT jsonb_array_elements_text(p_serials)
    LOOP
        SELECT su.sold_unit_id, su.unit_id, su.sold_price, si.item_id,
               si.sales_invoice_id, pu.serial_number, pi.unit_price, s.customer_id,
               s.invoice_date, (s.draft_invoice_id IS NOT NULL) AS from_draft
        INTO v_unit
        FROM SoldUnits su
        JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
        JOIN SalesInvoices s ON si.sales_invoice_id = s.sales_invoice_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
        WHERE pu.serial_number = v_serial
          AND su.status = 'Sold'
        ORDER BY su.sold_unit_id DESC
        LIMIT 1
        FOR UPDATE OF su, pu;

        IF NOT FOUND THEN
            PERFORM raise_serial_not_returnable(v_serial);
        END IF;
        IF v_unit.customer_id <> v_customer_id THEN
            RAISE EXCEPTION 'Serial % was not sold to this customer', v_serial;
        END IF;
        IF v_unit.from_draft AND v_draft_return_id IS NULL THEN
            RAISE EXCEPTION 'Serial "%" was sold on draft-based invoice #%. Use the Confirmed Draft Return screen to return it.', v_serial, v_unit.sales_invoice_id;
        END IF;
        IF v_draft_return_id IS NOT NULL AND NOT v_unit.from_draft THEN
            RAISE EXCEPTION 'Serial "%" was sold on ordinary sale invoice #%, not from a draft. Use the Sale Return screen to return it.', v_serial, v_unit.sales_invoice_id;
        END IF;
        IF v_draft_return_id IS NOT NULL AND v_return_date < v_unit.invoice_date THEN
            RAISE EXCEPTION 'Return date % is before serial "%" was sold on %.', v_return_date, v_serial, v_unit.invoice_date;
        END IF;

        UPDATE SoldUnits SET status = 'Returned' WHERE sold_unit_id = v_unit.sold_unit_id;
        UPDATE PurchaseUnits SET in_stock = TRUE WHERE unit_id = v_unit.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (v_unit.item_id, v_serial, 'IN', 'SalesReturn-Update', p_return_id, 1);

        INSERT INTO SalesReturnItems(sales_return_id, item_id, sold_price, cost_price, serial_number)
        VALUES (p_return_id, v_unit.item_id, v_unit.sold_price, v_unit.unit_price, v_serial);

        v_total := v_total + v_unit.sold_price;
    END LOOP;

    UPDATE SalesReturns
    SET total_amount = v_total,
        created_by = COALESCE(p_created_by, created_by)
    WHERE sales_return_id = p_return_id;

    PERFORM rebuild_sales_return_journal(p_return_id);
END; $$;

-- The lifecycle-guarded delete, unchanged except that a return belonging to a
-- confirmed draft return is deleted only through that document, so its header
-- is never left pointing at nothing.
CREATE OR REPLACE FUNCTION delete_sale_return(p_return_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    v_journal_id BIGINT;
    v_draft_return_id BIGINT;
BEGIN
    SELECT draft_return_id INTO v_draft_return_id FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF v_draft_return_id IS NOT NULL
       AND EXISTS (SELECT 1 FROM DraftReturns WHERE draft_return_id = v_draft_return_id) THEN
        RAISE EXCEPTION 'Sale return % belongs to Confirmed Draft Return #%. Delete it from the Confirmed Draft Return screen.', p_return_id, v_draft_return_id;
    END IF;

    FOR rec IN
        SELECT sri.serial_number, sri.item_id
        FROM SalesReturnItems sri
        WHERE sri.sales_return_id = p_return_id
    LOOP
        IF EXISTS (
            SELECT 1
            FROM SoldUnits su
            JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
            WHERE pu.serial_number = rec.serial_number
              AND su.status = 'Sold'
        ) THEN
            RAISE EXCEPTION 'Cannot delete this sale return: serial % has since been re-sold. Reverse the later sale first.', rec.serial_number;
        END IF;

        UPDATE SoldUnits SET status = 'Sold'
        WHERE sold_unit_id = (
            SELECT su2.sold_unit_id
            FROM SoldUnits su2
            JOIN PurchaseUnits pu2 ON su2.unit_id = pu2.unit_id
            WHERE pu2.serial_number = rec.serial_number
              AND su2.status = 'Returned'
            ORDER BY su2.sold_unit_id DESC
            LIMIT 1
        );

        UPDATE PurchaseUnits SET in_stock = FALSE WHERE serial_number = rec.serial_number;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'OUT', 'SalesReturn-Delete', p_return_id, 1);
    END LOOP;

    SELECT journal_id INTO v_journal_id FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF v_journal_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = v_journal_id;
    END IF;

    DELETE FROM SalesReturnItems WHERE sales_return_id = p_return_id;
    DELETE FROM SalesReturns WHERE sales_return_id = p_return_id;
END; $$;

-- The document takes a REAL return date and books the return on it, validated
-- here rather than only in the view. (The ordinary Sale Return and Purchase
-- Return still stamp CURRENT_DATE; this is the model for fixing them.)
CREATE OR REPLACE FUNCTION create_draft_return(
    p_party_name  text,
    p_serials     jsonb,
    p_return_date date,
    p_created_by  integer DEFAULT NULL::integer
) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_sales_return_id BIGINT;
    v_draft_return_id BIGINT;
    v_customer_id     BIGINT;
    v_draft_id        BIGINT;
BEGIN
    IF p_return_date IS NULL THEN
        RAISE EXCEPTION 'Return date is required.';
    END IF;
    IF p_return_date > CURRENT_DATE THEN
        RAISE EXCEPTION 'Return date cannot be in the future.';
    END IF;
    IF p_serials IS NULL OR jsonb_typeof(p_serials) <> 'array' OR jsonb_array_length(p_serials) = 0 THEN
        RAISE EXCEPTION 'At least one serial number is required.';
    END IF;

    SELECT party_id INTO v_customer_id FROM Parties WHERE party_name = p_party_name LIMIT 1;
    IF v_customer_id IS NULL THEN
        RAISE EXCEPTION 'Customer "%" does not exist. Please check the party name.', p_party_name;
    END IF;

    v_sales_return_id := sale_return_core(p_party_name, p_serials, p_created_by, p_return_date, TRUE);

    -- Which draft the returned goods came from. One return shares one customer
    -- but may span drafts: the header records the first, and the trail per
    -- serial stays in DraftUnits.
    SELECT di.draft_invoice_id INTO v_draft_id
    FROM SalesReturnItems sri
    JOIN PurchaseUnits pu ON pu.serial_number = sri.serial_number
    JOIN DraftUnits du ON du.unit_id = pu.unit_id AND du.status = 'Converted'
    JOIN DraftItems di ON di.draft_item_id = du.draft_item_id
    WHERE sri.sales_return_id = v_sales_return_id
    ORDER BY du.draft_unit_id DESC
    LIMIT 1;

    INSERT INTO DraftReturns(customer_id, draft_invoice_id, sales_return_id, created_by)
    VALUES (v_customer_id, v_draft_id, v_sales_return_id, p_created_by)
    RETURNING draft_return_id INTO v_draft_return_id;

    UPDATE SalesReturns SET draft_return_id = v_draft_return_id
    WHERE sales_return_id = v_sales_return_id;

    RETURN v_draft_return_id;
END;
$$;

-- Delegates to the proven ordinary procedure on the underlying row. The date is
-- written FIRST, so the journal update_sale_return rebuilds carries it.
CREATE OR REPLACE FUNCTION update_draft_return(
    p_draft_return_id bigint,
    p_serials         jsonb,
    p_return_date     date    DEFAULT NULL::date,
    p_created_by      integer DEFAULT NULL::integer
) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_sales_return_id BIGINT;
    v_draft_id        BIGINT;
BEGIN
    SELECT sales_return_id INTO v_sales_return_id
    FROM DraftReturns WHERE draft_return_id = p_draft_return_id
    FOR UPDATE;

    IF NOT FOUND OR v_sales_return_id IS NULL THEN
        RAISE EXCEPTION 'Confirmed draft return % was not found.', p_draft_return_id;
    END IF;
    IF p_serials IS NULL OR jsonb_typeof(p_serials) <> 'array' OR jsonb_array_length(p_serials) = 0 THEN
        RAISE EXCEPTION 'At least one serial number is required.';
    END IF;
    IF p_return_date IS NOT NULL THEN
        IF p_return_date > CURRENT_DATE THEN
            RAISE EXCEPTION 'Return date cannot be in the future.';
        END IF;
        UPDATE SalesReturns SET return_date = p_return_date
        WHERE sales_return_id = v_sales_return_id;
    END IF;

    PERFORM update_sale_return(v_sales_return_id, p_serials, p_created_by);

    SELECT di.draft_invoice_id INTO v_draft_id
    FROM SalesReturnItems sri
    JOIN PurchaseUnits pu ON pu.serial_number = sri.serial_number
    JOIN DraftUnits du ON du.unit_id = pu.unit_id AND du.status = 'Converted'
    JOIN DraftItems di ON di.draft_item_id = du.draft_item_id
    WHERE sri.sales_return_id = v_sales_return_id
    ORDER BY du.draft_unit_id DESC
    LIMIT 1;

    UPDATE DraftReturns SET draft_invoice_id = v_draft_id
    WHERE draft_return_id = p_draft_return_id;
END;
$$;

CREATE OR REPLACE FUNCTION delete_draft_return(p_draft_return_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_sales_return_id BIGINT;
BEGIN
    SELECT sales_return_id INTO v_sales_return_id
    FROM DraftReturns WHERE draft_return_id = p_draft_return_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Confirmed draft return % was not found.', p_draft_return_id;
    END IF;

    -- Header first, so delete_sale_return no longer sees it as owned by a draft
    -- return. A refusal below (a serial since re-sold) rolls both back.
    DELETE FROM DraftReturns WHERE draft_return_id = p_draft_return_id;
    IF v_sales_return_id IS NOT NULL THEN
        PERFORM delete_sale_return(v_sales_return_id);
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION get_last_draft_return_id() RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE last_id BIGINT;
BEGIN
    SELECT draft_return_id INTO last_id
    FROM DraftReturns ORDER BY draft_return_id DESC LIMIT 1;
    RETURN last_id;
END;
$$;

CREATE OR REPLACE FUNCTION get_current_draft_return(p_draft_return_id bigint) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'draft_return_id',  dr.draft_return_id,
        'sales_return_id',  dr.sales_return_id,
        'draft_invoice_id', dr.draft_invoice_id,
        'Party',            p.party_name,
        'return_date',      sr.return_date,
        'total_amount',     sr.total_amount,
        'description',      sr.description,
        'created_by',       COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',     i.item_name,
                'serial_number', sri.serial_number,
                'sold_price',    sri.sold_price
            ) ORDER BY sri.serial_number)
            FROM SalesReturnItems sri
            JOIN Items i ON i.item_id = sri.item_id
            WHERE sri.sales_return_id = dr.sales_return_id
        )
    ) INTO result
    FROM DraftReturns dr
    JOIN Parties p ON p.party_id = dr.customer_id
    LEFT JOIN SalesReturns sr ON sr.sales_return_id = dr.sales_return_id
    LEFT JOIN auth_user u ON u.id = dr.created_by
    WHERE dr.draft_return_id = p_draft_return_id;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION get_previous_draft_return(p_draft_return_id bigint) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE prev_id BIGINT;
BEGIN
    SELECT draft_return_id INTO prev_id FROM DraftReturns
    WHERE draft_return_id < p_draft_return_id ORDER BY draft_return_id DESC LIMIT 1;
    IF prev_id IS NULL THEN RETURN NULL; END IF;
    RETURN get_current_draft_return(prev_id);
END;
$$;

CREATE OR REPLACE FUNCTION get_next_draft_return(p_draft_return_id bigint) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE next_id BIGINT;
BEGIN
    SELECT draft_return_id INTO next_id FROM DraftReturns
    WHERE draft_return_id > p_draft_return_id ORDER BY draft_return_id ASC LIMIT 1;
    IF next_id IS NULL THEN RETURN NULL; END IF;
    RETURN get_current_draft_return(next_id);
END;
$$;

CREATE OR REPLACE FUNCTION get_draft_return_summary(
    p_start_date date DEFAULT NULL::date,
    p_end_date   date DEFAULT NULL::date
) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE result JSON;
BEGIN
    SELECT json_agg(x ORDER BY x.return_date DESC, x.draft_return_id DESC)
    INTO result
    FROM (
        SELECT dr.draft_return_id, sr.return_date, p.party_name AS customer,
               dr.draft_invoice_id, dr.sales_return_id,
               COALESCE(sr.total_amount, 0) AS total_amount
        FROM DraftReturns dr
        JOIN Parties p ON p.party_id = dr.customer_id
        LEFT JOIN SalesReturns sr ON sr.sales_return_id = dr.sales_return_id
        WHERE (p_start_date IS NULL OR p_end_date IS NULL
               OR sr.return_date BETWEEN p_start_date AND p_end_date)
    ) AS x;
    RETURN COALESCE(result, '[]'::json);
END;
$$;

CREATE OR REPLACE FUNCTION serial_exists_in_draft_return(p_serial text) RETURNS boolean
    LANGUAGE plpgsql AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM SalesReturnItems sri
        JOIN SalesReturns sr ON sr.sales_return_id = sri.sales_return_id
        WHERE sri.serial_number = p_serial AND sr.draft_return_id IS NOT NULL);
END;
$$;

-- The ordinary Sale Return screen's navigation and history leave confirmed
-- draft returns out: each is its existing definition with one condition added.

CREATE OR REPLACE FUNCTION get_last_sales_return_id() RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE
    last_id BIGINT;
BEGIN
    SELECT sales_return_id
    INTO last_id
    FROM SalesReturns
    WHERE draft_return_id IS NULL
    ORDER BY sales_return_id DESC
    LIMIT 1;

    RETURN last_id;
END;
$$;

CREATE OR REPLACE FUNCTION get_previous_sales_return(p_return_id bigint) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    prev_id BIGINT;
BEGIN
    SELECT sales_return_id INTO prev_id
    FROM SalesReturns
    WHERE sales_return_id < p_return_id
      AND draft_return_id IS NULL
    ORDER BY sales_return_id DESC
    LIMIT 1;

    IF prev_id IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN get_current_sales_return(prev_id);
END;
$$;

CREATE OR REPLACE FUNCTION get_next_sales_return(p_return_id bigint) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    next_id BIGINT;
BEGIN
    SELECT sales_return_id INTO next_id
    FROM SalesReturns
    WHERE sales_return_id > p_return_id
      AND draft_return_id IS NULL
    ORDER BY sales_return_id ASC
    LIMIT 1;

    IF next_id IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN get_current_sales_return(next_id);
END;
$$;

CREATE OR REPLACE FUNCTION get_sales_return_summary(p_start_date date DEFAULT NULL::date, p_end_date date DEFAULT NULL::date) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    result JSON;
BEGIN
    IF p_start_date IS NOT NULL AND p_end_date IS NOT NULL THEN
        -- 📅 Filter by date range
        SELECT json_agg(p ORDER BY p.return_date DESC)
        INTO result
        FROM (
            SELECT
                sr.sales_return_id,
                sr.return_date,
                pa.party_name AS customer,
                sr.total_amount
            FROM SalesReturns sr
            JOIN Parties pa ON sr.customer_id = pa.party_id
            WHERE sr.draft_return_id IS NULL
              AND sr.return_date BETWEEN p_start_date AND p_end_date
            ORDER BY sr.return_date DESC
        ) AS p;
    ELSE
        -- 📅 Last 20 returns
        SELECT json_agg(p ORDER BY p.return_date DESC)
        INTO result
        FROM (
            SELECT
                sr.sales_return_id,
                sr.return_date,
                pa.party_name AS customer,
                sr.total_amount
            FROM SalesReturns sr
            JOIN Parties pa ON sr.customer_id = pa.party_id
            WHERE sr.draft_return_id IS NULL
            ORDER BY sr.return_date DESC
            LIMIT 20
        ) AS p;
    END IF;

    RETURN COALESCE(result, '[]'::json);
END;
$$;

-- 9. Reporting ----------------------------------------------------------------
-- A reserved unit is still owned and still on the shelf, so every quantity and
-- value is unchanged; what these add is WHO it is spoken for. Stock Worth and
-- company worth are deliberately untouched.

-- Serial Wise Stock: two columns appended (all CREATE OR REPLACE VIEW permits,
-- so no existing column shifts). accountsReports renders them automatically.
CREATE OR REPLACE VIEW stock_report AS
 WITH stock AS (
         SELECT i.item_id,
            i.item_name,
            count(pu.unit_id) OVER (PARTITION BY i.item_id) AS quantity,
            pu.serial_number,
            pu.serial_comment,
            pi.invoice_date AS purchase_date,
            (CURRENT_DATE - pi.invoice_date) AS age_in_days,
            round((((CURRENT_DATE - pi.invoice_date))::numeric / 30.44), 1) AS age_in_months,
            res.party_name AS reserved_for,
            res.draft_invoice_id AS reserved_on_draft,
            row_number() OVER (PARTITION BY i.item_id ORDER BY pu.serial_number) AS rn
           FROM ((((purchaseunits pu
             JOIN purchaseitems pit ON ((pu.purchase_item_id = pit.purchase_item_id)))
             JOIN purchaseinvoices pi ON ((pit.purchase_invoice_id = pi.purchase_invoice_id)))
             JOIN items i ON ((pit.item_id = i.item_id)))
             LEFT JOIN LATERAL ( SELECT di.draft_invoice_id, pr.party_name
                   FROM (((draftunits du
                     JOIN draftitems dit ON ((dit.draft_item_id = du.draft_item_id)))
                     JOIN draftinvoices di ON ((di.draft_invoice_id = dit.draft_invoice_id)))
                     JOIN parties pr ON ((pr.party_id = di.customer_id)))
                  WHERE ((du.unit_id = pu.unit_id) AND ((du.status)::text = 'Reserved'::text))
                 LIMIT 1) res ON (true))
          WHERE ((pu.in_stock = true) AND (NOT (EXISTS ( SELECT 1
                   FROM soldunits su
                  WHERE ((su.unit_id = pu.unit_id) AND ((su.status)::text = 'Sold'::text))))) AND (NOT (EXISTS ( SELECT 1
                   FROM purchasereturnitems pri
                  WHERE ((pri.serial_number)::text = (pu.serial_number)::text)))))
        )
 SELECT
        CASE
            WHEN (rn = 1) THEN (item_id)::text
            ELSE ''::text
        END AS item_id,
        CASE
            WHEN (rn = 1) THEN item_name
            ELSE ''::character varying
        END AS item_name,
        CASE
            WHEN (rn = 1) THEN (quantity)::text
            ELSE ''::text
        END AS quantity,
    serial_number,
    serial_comment,
    age_in_days,
    age_in_months,
    reserved_for,
    reserved_on_draft
   FROM stock
  ORDER BY ((item_id)::integer), rn;

-- Stock Report: how many of an item are already spoken for. They stay counted in
-- quantity_in_stock too. The result shape gains a column, so the old shape is
-- dropped first (only while it is still in place, so a rerun is a no-op).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = current_schema()
          AND p.proname = 'stock_summary'
          AND pg_get_function_result(p.oid) NOT LIKE '%reserved_on_drafts%'
    ) THEN
        DROP FUNCTION stock_summary();
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION stock_summary() RETURNS TABLE(item_id bigint, item_name character varying, category character varying, brand character varying, quantity_in_stock bigint, reserved_on_drafts bigint)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        i.item_id,
        i.item_name,
        i.category,
        i.brand,
        COUNT(pu.unit_id) FILTER (
            WHERE pu.in_stock = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM soldunits su
                  WHERE su.unit_id = pu.unit_id AND su.status = 'Sold'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM purchasereturnitems pri
                  WHERE pri.serial_number = pu.serial_number
              )
        ) AS quantity_in_stock,
        COUNT(pu.unit_id) FILTER (
            WHERE EXISTS (
                  SELECT 1 FROM DraftUnits du
                  WHERE du.unit_id = pu.unit_id AND du.status = 'Reserved'
              )
        ) AS reserved_on_drafts
    FROM Items i
    LEFT JOIN PurchaseItems pi ON i.item_id = pi.item_id
    LEFT JOIN PurchaseUnits pu ON pi.purchase_item_id = pu.purchase_item_id
    GROUP BY i.item_id, i.item_name, i.category, i.brand
    ORDER BY i.item_name ASC;
END;
$$;

-- The Pending Drafts report: one {rows, summary} payload with a server-side
-- summary. The indicative value counts only reserved units whose line has a
-- rate, and unpriced_units says how many do not -- so a total that is quietly
-- small because rates are missing is always called out.
CREATE OR REPLACE FUNCTION draft_pending_report(
    p_from date DEFAULT NULL::date,
    p_to   date DEFAULT NULL::date,
    p_age_warning_days integer DEFAULT 30
) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE
    v_rows    json;
    v_summary json;
BEGIN
    WITH per_draft AS (
        SELECT
            d.draft_invoice_id,
            d.draft_date,
            p.party_name AS customer,
            d.status,
            CASE
                WHEN d.status = 'Open'
                     AND count(*) FILTER (WHERE du.status = 'Converted') > 0
                THEN 'Partially Converted'
                ELSE d.status
            END AS status_label,
            count(*) FILTER (WHERE du.status = 'Reserved')  AS reserved_units,
            count(*) FILTER (WHERE du.status = 'Converted') AS converted_units,
            count(*) FILTER (WHERE du.status = 'Released')  AS released_units,
            COALESCE(SUM(di.unit_price) FILTER (
                WHERE du.status = 'Reserved' AND di.unit_price IS NOT NULL), 0)::numeric(14,2)
                AS indicative_value,
            count(*) FILTER (WHERE du.status = 'Reserved' AND di.unit_price IS NULL)
                AS unpriced_units,
            (CURRENT_DATE - d.draft_date) AS days_outstanding,
            ((CURRENT_DATE - d.draft_date) >= p_age_warning_days) AS is_aged
        FROM DraftInvoices d
        JOIN Parties p ON p.party_id = d.customer_id
        LEFT JOIN DraftItems di ON di.draft_invoice_id = d.draft_invoice_id
        LEFT JOIN DraftUnits du ON du.draft_item_id = di.draft_item_id
        WHERE d.status = 'Open'
          AND (p_from IS NULL OR p_to IS NULL OR d.draft_date BETWEEN p_from AND p_to)
        GROUP BY d.draft_invoice_id, d.draft_date, p.party_name, d.status
        HAVING count(*) FILTER (WHERE du.status = 'Reserved') > 0
    )
    SELECT
        COALESCE(json_agg(r ORDER BY r.days_outstanding DESC, r.draft_invoice_id), '[]'::json),
        json_build_object(
            'draft_count',       COALESCE(count(*), 0),
            'customer_count',    COALESCE(count(DISTINCT r.customer), 0),
            'reserved_units',    COALESCE(SUM(r.reserved_units), 0),
            'indicative_value',  COALESCE(SUM(r.indicative_value), 0)::numeric(14,2),
            'unpriced_units',    COALESCE(SUM(r.unpriced_units), 0),
            'aged_drafts',       COALESCE(count(*) FILTER (WHERE r.is_aged), 0),
            'age_warning_days',  p_age_warning_days
        )
    INTO v_rows, v_summary
    FROM per_draft r;

    RETURN json_build_object('rows', v_rows, 'summary', v_summary);
END;
$$;

-- The dashboard card's source.
CREATE OR REPLACE FUNCTION fn_dash_draft_reservations(
    p_limit integer DEFAULT 5,
    p_age_warning_days integer DEFAULT 30
) RETURNS json
    LANGUAGE plpgsql AS $$
DECLARE
    v_limit integer := GREATEST(1, LEAST(COALESCE(p_limit, 5), 100));
    result  json;
BEGIN
    WITH open_drafts AS (
        SELECT d.draft_invoice_id, d.draft_date, p.party_name AS customer,
               count(*) FILTER (WHERE du.status = 'Reserved') AS reserved_units,
               (CURRENT_DATE - d.draft_date) AS days_outstanding
        FROM DraftInvoices d
        JOIN Parties p ON p.party_id = d.customer_id
        LEFT JOIN DraftItems di ON di.draft_invoice_id = d.draft_invoice_id
        LEFT JOIN DraftUnits du ON du.draft_item_id = di.draft_item_id
        WHERE d.status = 'Open'
        GROUP BY d.draft_invoice_id, d.draft_date, p.party_name
        HAVING count(*) FILTER (WHERE du.status = 'Reserved') > 0
    )
    SELECT json_build_object(
        'open_drafts',      (SELECT count(*) FROM open_drafts),
        'reserved_units',   (SELECT COALESCE(SUM(reserved_units), 0) FROM open_drafts),
        'aged_drafts',      (SELECT count(*) FROM open_drafts
                             WHERE days_outstanding >= p_age_warning_days),
        'oldest_days',      (SELECT COALESCE(MAX(days_outstanding), 0) FROM open_drafts),
        'age_warning_days', p_age_warning_days,
        'recent', COALESCE((
            SELECT json_agg(x ORDER BY x.days_outstanding DESC, x.draft_invoice_id DESC)
            FROM (SELECT * FROM open_drafts
                  ORDER BY days_outstanding DESC, draft_invoice_id DESC
                  LIMIT v_limit) x
        ), '[]'::json)
    ) INTO result;
    RETURN result;
END;
$$;

-- The serial ledgers show a serial's draft events: reserved, converted and
-- released. Each moves NO stock (qty_in = qty_out = 0), so the running balance
-- carries straight through. Both ledgers are their existing definitions with
-- three CTEs added to the UNION ALL; get_serial_ledger_purchase is untouched.
CREATE OR REPLACE FUNCTION get_serial_ledger(p_serial text) RETURNS TABLE(serial_number text, serial_comment text, item_name text, txn_date date, particulars text, reference text, qty_in integer, qty_out integer, balance integer, party_name text, purchase_price numeric, sale_price numeric, profit numeric)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY

    WITH item_info AS (
        SELECT
            pu.serial_number::text AS serial_number,
            pu.serial_comment::text AS serial_comment,
            i.item_name::text AS item_name
        FROM PurchaseUnits pu
        JOIN PurchaseItems pit ON pu.purchase_item_id = pit.purchase_item_id
        JOIN Items i ON pit.item_id = i.item_id
        WHERE pu.serial_number = p_serial
        LIMIT 1
    ),

    purchase AS (
        SELECT
            pi.invoice_date AS dt,
            'Purchase'::text AS particulars,
            pi.purchase_invoice_id::text AS reference,
            1 AS qty_in,
            0 AS qty_out,
            p.party_name::text AS party_name,
            pit.unit_price AS purchase_price,
            NULL::numeric AS sale_price
        FROM PurchaseUnits pu
        JOIN PurchaseItems pit ON pu.purchase_item_id = pit.purchase_item_id
        JOIN PurchaseInvoices pi ON pit.purchase_invoice_id = pi.purchase_invoice_id
        JOIN Parties p ON pi.vendor_id = p.party_id
        WHERE pu.serial_number = p_serial
    ),

    purchase_return AS (
        SELECT
            pr.return_date AS dt,
            'Purchase Return'::text AS particulars,
            pr.purchase_return_id::text AS reference,
            0 AS qty_in,
            1 AS qty_out,
            p.party_name::text AS party_name,
            pri.unit_price AS purchase_price,
            NULL::numeric AS sale_price
        FROM PurchaseReturnItems pri
        JOIN PurchaseReturns pr ON pri.purchase_return_id = pr.purchase_return_id
        JOIN Parties p ON pr.vendor_id = p.party_id
        WHERE pri.serial_number = p_serial
    ),

    sale AS (
        SELECT
            si.invoice_date AS dt,
            'Sale'::text AS particulars,
            si.sales_invoice_id::text AS reference,
            0 AS qty_in,
            1 AS qty_out,
            c.party_name::text AS party_name,
            pit.unit_price AS purchase_price,
            su.sold_price AS sale_price
        FROM SoldUnits su
        JOIN SalesItems sitm ON su.sales_item_id = sitm.sales_item_id
        JOIN SalesInvoices si ON sitm.sales_invoice_id = si.sales_invoice_id
        JOIN Parties c ON si.customer_id = c.party_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        JOIN PurchaseItems pit ON pu.purchase_item_id = pit.purchase_item_id
        WHERE pu.serial_number = p_serial
    ),

    sales_return AS (
        SELECT
            sr.return_date AS dt,
            'Sales Return'::text AS particulars,
            sr.sales_return_id::text AS reference,
            1 AS qty_in,
            0 AS qty_out,
            c.party_name::text AS party_name,
            sri.cost_price AS purchase_price,
            sri.sold_price AS sale_price
        FROM SalesReturnItems sri
        JOIN SalesReturns sr ON sri.sales_return_id = sr.sales_return_id
        JOIN Parties c ON sr.customer_id = c.party_id
        WHERE sri.serial_number = p_serial
    ),

    -- Dated by the draft (the document), like every other row here.
    reservation AS (
        SELECT
            di.draft_date AS dt,
            'Reserved on Draft'::text AS particulars,
            di.draft_invoice_id::text AS reference,
            0 AS qty_in,
            0 AS qty_out,
            p.party_name::text AS party_name,
            NULL::numeric AS purchase_price,
            NULL::numeric AS sale_price
        FROM DraftUnits du
        JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
        JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
        JOIN Parties p ON p.party_id = di.customer_id
        JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
        WHERE pu.serial_number = p_serial
    ),

    -- The reservation's closing event. Keyed on converted_at (something that
    -- happened) rather than status, and dated by the invoice it produced --
    -- falling back to the timestamp if that invoice has since been deleted.
    conversion AS (
        SELECT
            COALESCE(csi.invoice_date, du.converted_at::date) AS dt,
            'Converted from Draft'::text AS particulars,
            di.draft_invoice_id::text AS reference,
            0 AS qty_in,
            0 AS qty_out,
            p.party_name::text AS party_name,
            NULL::numeric AS purchase_price,
            NULL::numeric AS sale_price
        FROM DraftUnits du
        JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
        JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
        JOIN Parties p ON p.party_id = di.customer_id
        JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
        LEFT JOIN SalesInvoices csi ON csi.sales_invoice_id = du.sales_invoice_id
        WHERE pu.serial_number = p_serial
          AND du.converted_at IS NOT NULL
    ),

    release_from_draft AS (
        SELECT
            du.released_at::date AS dt,
            'Released from Draft'::text AS particulars,
            di.draft_invoice_id::text AS reference,
            0 AS qty_in,
            0 AS qty_out,
            p.party_name::text AS party_name,
            NULL::numeric AS purchase_price,
            NULL::numeric AS sale_price
        FROM DraftUnits du
        JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
        JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
        JOIN Parties p ON p.party_id = di.customer_id
        JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
        WHERE pu.serial_number = p_serial
          AND du.released_at IS NOT NULL
    )

    SELECT
        ii.serial_number,
        ii.serial_comment,
        ii.item_name,
        l.dt AS txn_date,
        l.particulars,
        l.reference,
        l.qty_in,
        l.qty_out,
        CAST(SUM(l.qty_in - l.qty_out) OVER (ORDER BY l.dt, l.reference) AS INT) AS balance,
        l.party_name,
        l.purchase_price,
        l.sale_price,
        CASE
            WHEN l.sale_price IS NOT NULL AND l.purchase_price IS NOT NULL
            THEN l.sale_price - l.purchase_price
        END AS profit
    FROM (
        SELECT * FROM purchase
        UNION ALL SELECT * FROM purchase_return
        UNION ALL SELECT * FROM sale
        UNION ALL SELECT * FROM sales_return
        UNION ALL SELECT * FROM reservation
        UNION ALL SELECT * FROM conversion
        UNION ALL SELECT * FROM release_from_draft
    ) l
    CROSS JOIN item_info ii
    ORDER BY l.dt, l.reference;

END;
$$;

CREATE OR REPLACE FUNCTION get_serial_ledger_sales(p_serial text) RETURNS TABLE(serial_number text, serial_comment text, item_name text, txn_date date, particulars text, reference text, qty_in integer, qty_out integer, balance integer, party_name text, sale_price numeric)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY

    WITH item_info AS (
        SELECT
            pu.serial_number::text,
            pu.serial_comment::text,
            i.item_name::text
        FROM purchaseunits pu
        JOIN purchaseitems pit ON pu.purchase_item_id = pit.purchase_item_id
        JOIN items i ON pit.item_id = i.item_id
        WHERE pu.serial_number = p_serial
        LIMIT 1
    ),

    sale AS (
        SELECT
            si.invoice_date AS dt,
            'Sale'::text AS particulars,
            si.sales_invoice_id::text AS reference,
            0 AS qty_in,
            1 AS qty_out,
            c.party_name::text,
            su.sold_price AS sale_price
        FROM soldunits su
        JOIN salesitems sitm ON su.sales_item_id = sitm.sales_item_id
        JOIN salesinvoices si ON sitm.sales_invoice_id = si.sales_invoice_id
        JOIN parties c ON si.customer_id = c.party_id
        JOIN purchaseunits pu ON su.unit_id = pu.unit_id
        WHERE pu.serial_number = p_serial
    ),

    sales_return AS (
        SELECT
            sr.return_date AS dt,
            'Sales Return'::text AS particulars,
            sr.sales_return_id::text AS reference,
            1 AS qty_in,
            0 AS qty_out,
            c.party_name::text,
            sri.sold_price AS sale_price
        FROM salesreturnitems sri
        JOIN salesreturns sr ON sri.sales_return_id = sr.sales_return_id
        JOIN parties c ON sr.customer_id = c.party_id
        WHERE sri.serial_number = p_serial
    ),

    reservation AS (
        SELECT
            di.draft_date AS dt,
            'Reserved on Draft'::text AS particulars,
            di.draft_invoice_id::text AS reference,
            0 AS qty_in,
            0 AS qty_out,
            p.party_name::text AS party_name,
            NULL::numeric AS sale_price
        FROM DraftUnits du
        JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
        JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
        JOIN Parties p ON p.party_id = di.customer_id
        JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
        WHERE pu.serial_number = p_serial
    ),

    conversion AS (
        SELECT
            COALESCE(csi.invoice_date, du.converted_at::date) AS dt,
            'Converted from Draft'::text AS particulars,
            di.draft_invoice_id::text AS reference,
            0 AS qty_in,
            0 AS qty_out,
            p.party_name::text AS party_name,
            NULL::numeric AS sale_price
        FROM DraftUnits du
        JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
        JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
        JOIN Parties p ON p.party_id = di.customer_id
        JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
        LEFT JOIN SalesInvoices csi ON csi.sales_invoice_id = du.sales_invoice_id
        WHERE pu.serial_number = p_serial
          AND du.converted_at IS NOT NULL
    ),

    release_from_draft AS (
        SELECT
            du.released_at::date AS dt,
            'Released from Draft'::text AS particulars,
            di.draft_invoice_id::text AS reference,
            0 AS qty_in,
            0 AS qty_out,
            p.party_name::text AS party_name,
            NULL::numeric AS sale_price
        FROM DraftUnits du
        JOIN DraftItems dit ON dit.draft_item_id = du.draft_item_id
        JOIN DraftInvoices di ON di.draft_invoice_id = dit.draft_invoice_id
        JOIN Parties p ON p.party_id = di.customer_id
        JOIN PurchaseUnits pu ON pu.unit_id = du.unit_id
        WHERE pu.serial_number = p_serial
          AND du.released_at IS NOT NULL
    )

    SELECT
        ii.serial_number,
        ii.serial_comment,
        ii.item_name,
        l.dt AS txn_date,
        l.particulars,
        l.reference,
        l.qty_in,
        l.qty_out,
        CAST(SUM(l.qty_in - l.qty_out) OVER (ORDER BY l.dt, l.reference) AS INT) AS balance,
        l.party_name,
        l.sale_price
    FROM (
        SELECT * FROM sale
        UNION ALL
        SELECT * FROM sales_return
        UNION ALL
        SELECT * FROM reservation
        UNION ALL
        SELECT * FROM conversion
        UNION ALL
        SELECT * FROM release_from_draft
    ) l
    CROSS JOIN item_info ii
    ORDER BY l.dt, l.reference;

END;
$$;

-- Company-scoped report email. No financial tables or calculations change.
-- Password is write-only through settings_get; backups contain the stored secret.
CREATE TABLE IF NOT EXISTS report_email_settings (
    id              integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    sender_email    text        NOT NULL,
    sender_name     text        NOT NULL DEFAULT 'Financee Reports',
    app_password    text,
    smtp_host       text        NOT NULL DEFAULT 'smtp.gmail.com',
    smtp_port       integer     NOT NULL DEFAULT 587 CHECK (smtp_port BETWEEN 1 AND 65535),
    use_tls         boolean     NOT NULL DEFAULT true,
    send_hour       smallint    NOT NULL DEFAULT 0  CHECK (send_hour BETWEEN 0 AND 23),
    send_minute     smallint    NOT NULL DEFAULT 0  CHECK (send_minute BETWEEN 0 AND 59),
    -- The business day the report is *about* is decided in this zone, not in
    -- the server's. A sale dated Monday belongs to Monday where the business
    -- is, whatever UTC says at the moment the mail goes out.
    timezone        text        NOT NULL DEFAULT 'Asia/Karachi',
    is_enabled      boolean     NOT NULL DEFAULT true,
    authorized_user_id bigint,
    updated_by      text,
    updated_at      timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS report_email_recipients (
    recipient_id bigserial PRIMARY KEY,
    email        text        NOT NULL,
    label        text,
    is_active    boolean     NOT NULL DEFAULT true,
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Case-insensitive, because a mailbox is: adding the same address twice in
-- different case would silently double every delivery.
CREATE UNIQUE INDEX IF NOT EXISTS report_email_recipients_email_key
    ON report_email_recipients (lower(email));

-- 19.3 Settings -------------------------------------------------------------

-- Deliberately does not select app_password. The browser never needs it, and a
-- read path that cannot leak it is worth more than one that remembers not to.
CREATE OR REPLACE FUNCTION report_email_settings_get()
    RETURNS json
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN (
        SELECT COALESCE(
            (SELECT json_build_object(
                'configured',     true,
                'authorized_user_id', s.authorized_user_id,
                'sender_email',   s.sender_email,
                'sender_name',    s.sender_name,
                'has_password',   (s.app_password IS NOT NULL AND s.app_password <> ''),
                'smtp_host',      s.smtp_host,
                'smtp_port',      s.smtp_port,
                'use_tls',        s.use_tls,
                'send_hour',      s.send_hour,
                'send_minute',    s.send_minute,
                'timezone',       s.timezone,
                'is_enabled',     s.is_enabled,
                'updated_by',     s.updated_by,
                'updated_at',     s.updated_at
             )
             FROM report_email_settings s WHERE s.id = 1),
            json_build_object('configured', false, 'is_enabled', false,
                              'smtp_host', 'smtp.gmail.com', 'smtp_port', 587,
                              'use_tls', true, 'send_hour', 0, 'send_minute', 0,
                              'timezone', 'Asia/Karachi', 'has_password', false)
        )
    );
END;
$$;

-- Every message here is written for the person typing into the form; they
-- reach the browser verbatim through financee.db_errors.user_db_error.
--
-- p_payload.app_password is optional on an update: an absent key leaves the
-- stored password alone, so the settings can be edited without retyping it.
-- An explicit empty string clears it.
CREATE OR REPLACE FUNCTION save_report_email_settings_from_json(p_payload jsonb)
    RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_sender    text := btrim(COALESCE(p_payload->>'sender_email', ''));
    v_name      text := btrim(COALESCE(p_payload->>'sender_name', ''));
    -- Blank or absent means Gmail, which is what this is for. A host is not
    -- something the person filling in the form should have to know.
    v_host      text := COALESCE(NULLIF(btrim(COALESCE(p_payload->>'smtp_host', '')), ''),
                                 'smtp.gmail.com');
    v_port      integer;
    v_hour      integer;
    v_minute    integer;
    v_timezone  text := btrim(COALESCE(p_payload->>'timezone', ''));
    v_actor     text := NULLIF(btrim(COALESCE(p_payload->>'actor', '')), '');
    v_existing  text;
    v_password  text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email', 0));
    IF v_sender = '' THEN
        RAISE EXCEPTION 'A sending email address is required.';
    END IF;
    IF v_sender !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' THEN
        RAISE EXCEPTION 'Sending address "%" is not a valid email address.', v_sender;
    END IF;
    IF length(v_sender) > 254 OR length(v_name) > 150 OR v_name ~ '[\r\n]' THEN
        RAISE EXCEPTION 'Invalid sender name or address length.';
    END IF;
    IF v_host ~ '[[:space:]]' THEN
        RAISE EXCEPTION 'SMTP server "%" is not a valid host name.', v_host;
    END IF;

    BEGIN
        v_port := COALESCE((p_payload->>'smtp_port')::integer, 587);
    EXCEPTION WHEN others THEN
        RAISE EXCEPTION 'SMTP port "%" is not a whole number.', p_payload->>'smtp_port';
    END;
    IF v_port < 1 OR v_port > 65535 THEN
        RAISE EXCEPTION 'SMTP port must be between 1 and 65535; % was given.', v_port;
    END IF;

    BEGIN
        v_hour := COALESCE((p_payload->>'send_hour')::integer, 0);
        v_minute := COALESCE((p_payload->>'send_minute')::integer, 0);
    EXCEPTION WHEN others THEN
        RAISE EXCEPTION 'The send time must be given as an hour and a minute.';
    END;
    IF v_hour < 0 OR v_hour > 23 THEN
        RAISE EXCEPTION 'The send hour must be between 0 and 23; % was given.', v_hour;
    END IF;
    IF v_minute < 0 OR v_minute > 59 THEN
        RAISE EXCEPTION 'The send minute must be between 0 and 59; % was given.', v_minute;
    END IF;

    IF v_timezone = '' THEN
        v_timezone := 'Asia/Karachi';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = v_timezone) THEN
        RAISE EXCEPTION 'Time zone "%" is not recognised. Use a name like Asia/Karachi.', v_timezone;
    END IF;

    IF NOT ((v_port = 587 AND COALESCE((p_payload->>'use_tls')::boolean, true))
        OR (v_port = 465 AND NOT COALESCE((p_payload->>'use_tls')::boolean, true))) THEN
        RAISE EXCEPTION 'Use port 587 with TLS, or port 465 with implicit TLS.';
    END IF;

    SELECT app_password INTO v_existing FROM report_email_settings WHERE id = 1;

    IF p_payload ? 'app_password' THEN
        v_password := NULLIF(p_payload->>'app_password', '');
    ELSE
        v_password := v_existing;   -- absent key: leave what is stored alone
    END IF;

    INSERT INTO report_email_settings AS s (
        id, authorized_user_id, sender_email, sender_name, app_password, smtp_host, smtp_port,
        use_tls, send_hour, send_minute, timezone, is_enabled, updated_by, updated_at
    ) VALUES (
        1, (p_payload->>'authorized_user_id')::bigint, v_sender, COALESCE(NULLIF(v_name, ''), 'Financee Reports'), v_password,
        v_host, v_port,
        COALESCE((p_payload->>'use_tls')::boolean, true),
        v_hour, v_minute, v_timezone,
        COALESCE((p_payload->>'is_enabled')::boolean, true),
        v_actor, clock_timestamp()
    )
    ON CONFLICT (id) DO UPDATE SET
        authorized_user_id = EXCLUDED.authorized_user_id,
        sender_email = EXCLUDED.sender_email,
        sender_name  = EXCLUDED.sender_name,
        app_password = v_password,
        smtp_host    = EXCLUDED.smtp_host,
        smtp_port    = EXCLUDED.smtp_port,
        use_tls      = EXCLUDED.use_tls,
        send_hour    = EXCLUDED.send_hour,
        send_minute  = EXCLUDED.send_minute,
        timezone     = EXCLUDED.timezone,
        is_enabled   = EXCLUDED.is_enabled,
        updated_by   = EXCLUDED.updated_by,
        updated_at   = clock_timestamp();

    RETURN report_email_settings_get();
END;
$$;

-- 19.4 Recipients -----------------------------------------------------------

CREATE OR REPLACE FUNCTION report_email_recipients_list()
    RETURNS json
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN (
        SELECT COALESCE(json_agg(row_to_json(r) ORDER BY r.is_active DESC, lower(r.email)), '[]'::json)
        FROM (
            SELECT recipient_id, email, label, is_active, created_by, created_at
            FROM report_email_recipients
        ) r
    );
END;
$$;

CREATE OR REPLACE FUNCTION add_report_recipient_from_json(p_payload jsonb)
    RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_email text := btrim(COALESCE(p_payload->>'email', ''));
    v_label text := NULLIF(btrim(COALESCE(p_payload->>'label', '')), '');
    v_actor text := NULLIF(btrim(COALESCE(p_payload->>'actor', '')), '');
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email', 0));
    IF v_email = '' THEN
        RAISE EXCEPTION 'A recipient email address is required.';
    END IF;
    IF v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' THEN
        RAISE EXCEPTION '"%" is not a valid email address.', v_email;
    END IF;
    IF EXISTS (SELECT 1 FROM report_email_recipients WHERE lower(email) = lower(v_email)) THEN
        RAISE EXCEPTION '"%" is already on the recipient list.', v_email;
    END IF;

    IF (SELECT count(*) FROM report_email_recipients) >= 50 THEN
        RAISE EXCEPTION 'At most 50 recipients can be configured.';
    END IF;
    INSERT INTO report_email_recipients (email, label, created_by)
    VALUES (v_email, v_label, v_actor);

    RETURN report_email_recipients_list();
END;
$$;

CREATE OR REPLACE FUNCTION update_report_recipient_from_json(p_payload jsonb)
    RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_id    bigint;
    v_email text := btrim(COALESCE(p_payload->>'email', ''));
    v_label text := NULLIF(btrim(COALESCE(p_payload->>'label', '')), '');
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email', 0));
    BEGIN
        v_id := (p_payload->>'recipient_id')::bigint;
    EXCEPTION WHEN others THEN
        RAISE EXCEPTION 'A recipient must be identified before it can be changed.';
    END;
    IF NOT EXISTS (SELECT 1 FROM report_email_recipients WHERE recipient_id = v_id) THEN
        RAISE EXCEPTION 'That recipient no longer exists. Refresh the page and try again.';
    END IF;

    IF v_email = '' THEN
        RAISE EXCEPTION 'A recipient email address is required.';
    END IF;
    IF v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' THEN
        RAISE EXCEPTION '"%" is not a valid email address.', v_email;
    END IF;
    IF EXISTS (
        SELECT 1 FROM report_email_recipients
        WHERE lower(email) = lower(v_email) AND recipient_id <> v_id
    ) THEN
        RAISE EXCEPTION '"%" is already on the recipient list.', v_email;
    END IF;

    UPDATE report_email_recipients
    SET email = v_email,
        label = v_label,
        is_active = COALESCE((p_payload->>'is_active')::boolean, is_active)
    WHERE recipient_id = v_id;

    RETURN report_email_recipients_list();
END;
$$;

CREATE OR REPLACE FUNCTION delete_report_recipient(p_recipient_id bigint)
    RETURNS json
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email', 0));
    IF NOT EXISTS (SELECT 1 FROM report_email_recipients WHERE recipient_id = p_recipient_id) THEN
        RAISE EXCEPTION 'That recipient no longer exists. Refresh the page and try again.';
    END IF;
    DELETE FROM report_email_recipients WHERE recipient_id = p_recipient_id;
    RETURN report_email_recipients_list();
END;
$$;

-- Durable reservations are made BEFORE SMTP. A session advisory lock remains
-- held across transport, so another worker cannot claim/re-arm during a send.
CREATE TABLE IF NOT EXISTS report_email_log (
    log_id bigserial PRIMARY KEY,
    report_date date NOT NULL,
    status text NOT NULL CHECK (status IN ('pending','sending','sent','failed','skipped','unknown')),
    trigger_source text NOT NULL CHECK (trigger_source IN ('schedule','manual','test','rearm')),
    recipients text[] NOT NULL DEFAULT '{}',
    subject text NOT NULL DEFAULT '',
    unit_count integer,
    total_sales numeric,
    total_profit numeric,
    currency_code text,
    error_message text NOT NULL DEFAULT '',
    triggered_by text,
    duration_ms integer,
    superseded boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS report_email_log_created_idx ON report_email_log(created_at DESC,log_id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS report_email_one_live_day ON report_email_log(report_date)
    WHERE trigger_source='schedule' AND NOT superseded AND status IN ('pending','sending','sent','unknown');

CREATE OR REPLACE FUNCTION report_email_due(p_day date) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT EXISTS (SELECT 1 FROM report_email_settings WHERE id=1 AND is_enabled
                AND NULLIF(app_password,'') IS NOT NULL AND authorized_user_id IS NOT NULL)
    AND EXISTS (SELECT 1 FROM report_email_recipients WHERE is_active)
    AND NOT EXISTS (SELECT 1 FROM report_email_log WHERE report_date=p_day
                   AND trigger_source='schedule' AND NOT superseded
                   AND status IN ('pending','sending','sent','unknown'))
    AND (SELECT count(*) FROM report_email_log WHERE report_date=p_day
         AND trigger_source='schedule' AND NOT superseded AND status IN ('failed','skipped')) < 12
    AND NOT EXISTS (SELECT 1 FROM report_email_log WHERE report_date=p_day
                   AND trigger_source='schedule' AND NOT superseded AND status IN ('failed','skipped')
                   AND created_at > clock_timestamp()-interval '30 minutes');
$$;

CREATE OR REPLACE FUNCTION report_email_recover() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email',0));
    -- Called only after obtaining the tenant session lock: no live sender is
    -- running. Preparing cannot have sent mail; sending might have, so stop.
    UPDATE report_email_log SET status=CASE WHEN status='pending' THEN 'failed' ELSE 'unknown' END,
        error_message=CASE WHEN status='pending' THEN 'Preparation interrupted; retry allowed.'
                      ELSE 'Delivery interrupted; check the inbox before re-arming.' END,
        finished_at=clock_timestamp()
        WHERE status IN ('pending','sending');
END; $$;

CREATE OR REPLACE FUNCTION report_email_claim(p_day date,p_trigger text,p_actor text)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE v_id bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email',0));
    IF p_trigger NOT IN ('schedule','manual','test') THEN RAISE EXCEPTION 'Invalid delivery source.'; END IF;
    IF p_trigger='schedule' AND NOT report_email_due(p_day) THEN RETURN NULL; END IF;
    INSERT INTO report_email_log(report_date,status,trigger_source,triggered_by)
      VALUES(p_day,'pending',p_trigger,p_actor) RETURNING log_id INTO v_id;
    RETURN v_id;
END; $$;

CREATE OR REPLACE FUNCTION report_email_finish(p_id bigint,p_data jsonb)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    UPDATE report_email_log SET status=p_data->>'status',
      recipients=COALESCE(ARRAY(SELECT jsonb_array_elements_text(p_data->'recipients')),'{}'),
      subject=COALESCE(p_data->>'subject',''),
      unit_count=(p_data->>'unit_count')::integer,
      total_sales=(p_data->>'total_sales')::numeric,
      total_profit=(p_data->>'total_profit')::numeric,
      currency_code=p_data->>'currency_code',
      error_message=left(COALESCE(p_data->>'error_message',''),500),
      duration_ms=(p_data->>'duration_ms')::integer,
      finished_at=CASE WHEN p_data->>'status'='sending' THEN NULL ELSE clock_timestamp() END
      WHERE log_id=p_id AND status IN ('pending','sending');
END; $$;

CREATE OR REPLACE FUNCTION report_email_log_list(p_limit integer,p_offset integer)
RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object('rows',COALESCE((SELECT jsonb_agg(to_jsonb(r)) FROM
   (SELECT * FROM report_email_log ORDER BY created_at DESC,log_id DESC
    LIMIT LEAST(100,GREATEST(1,p_limit)) OFFSET LEAST(100000,GREATEST(0,p_offset))) r),'[]'::jsonb),
   'total',(SELECT count(*) FROM report_email_log),
   'summary',(SELECT jsonb_build_object('sent',count(*) FILTER(WHERE status='sent'),
     'failed',count(*) FILTER(WHERE status='failed'),'skipped',count(*) FILTER(WHERE status='skipped'),
     'unknown',count(*) FILTER(WHERE status='unknown'),
     'last_sent_at',max(finished_at) FILTER(WHERE status='sent')) FROM report_email_log));
$$;

CREATE OR REPLACE FUNCTION rearm_report_email_day(p_day date,p_actor text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE v_count integer;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email',0));
    IF EXISTS (SELECT 1 FROM report_email_log WHERE report_date=p_day AND status IN ('pending','sending')) THEN
        RAISE EXCEPTION 'A delivery is in progress. Refresh before re-arming.';
    END IF;
    UPDATE report_email_log SET superseded=true WHERE report_date=p_day
        AND trigger_source='schedule' AND NOT superseded;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count=0 THEN RAISE EXCEPTION 'Nothing to re-arm for this day.'; END IF;
    INSERT INTO report_email_log(report_date,status,trigger_source,triggered_by,subject,finished_at)
      VALUES(p_day,'skipped','rearm',p_actor,'Re-armed after inbox reconciliation',clock_timestamp());
    RETURN jsonb_build_object('superseded',v_count,'report_date',p_day,'due',report_email_due(p_day));
END; $$;

-- Company activity is separate from public auth and the optional platform log.
-- Additive, repeatable, version 6 compatible. Backfill is an explicit command.
CREATE TABLE IF NOT EXISTS activity_events (
    event_id bigserial PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT clock_timestamp(),
    user_id integer,
    username text NOT NULL DEFAULT '',
    action text NOT NULL CHECK (action IN ('create','update','delete','convert','cancel','release','run','export','sign_in','sign_out','sign_in_failed')),
    kind text NOT NULL CHECK (kind IN ('sale','purchase','sale_return','purchase_return','payment','receipt','contra','draft','draft_return','party','item','opening_stock','opening_cash','owner_equity','month_close','report','session')),
    record_id bigint,
    label text NOT NULL DEFAULT '',
    source text NOT NULL DEFAULT 'live' CHECK (source IN ('live','browser','backfill')),
    ip inet,
    dedupe_key text,
    document_date date,
    CHECK (length(username) <= 150 AND length(label) <= 200),
    CHECK (record_id IS NULL OR record_id > 0)
);
CREATE INDEX IF NOT EXISTS activity_events_user_at_idx ON activity_events(user_id,at);
CREATE INDEX IF NOT EXISTS activity_events_at_idx ON activity_events(at);
CREATE INDEX IF NOT EXISTS activity_events_record_idx ON activity_events(kind,record_id);
CREATE INDEX IF NOT EXISTS activity_events_sign_in_idx ON activity_events(user_id,at) WHERE action='sign_in';
CREATE INDEX IF NOT EXISTS activity_events_dedupe_idx ON activity_events(user_id,dedupe_key,at) WHERE dedupe_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS activity_events_backfill_key ON activity_events(dedupe_key) WHERE source='backfill';
CREATE OR REPLACE FUNCTION activity_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'activity_events is append-only: % refused', TG_OP;
END;
$$;
CREATE OR REPLACE TRIGGER activity_events_no_change BEFORE UPDATE OR DELETE ON activity_events
FOR EACH ROW EXECUTE FUNCTION activity_events_append_only();
CREATE OR REPLACE TRIGGER activity_events_no_truncate BEFORE TRUNCATE ON activity_events
FOR EACH STATEMENT EXECUTE FUNCTION activity_events_append_only();
