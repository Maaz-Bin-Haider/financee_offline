-- ============================================================================
-- fix_transaction_integrity_guards.sql
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
