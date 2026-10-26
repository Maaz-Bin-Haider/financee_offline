-- fix_sale_return_lifecycle_guards.sql
-- ============================================================================
-- Hardens sale/return serial lifecycle rules:
--   * sale returns must target the currently active SoldUnits row only
--   * duplicate sale returns are blocked because no active sale remains
--   * cash-vs-credit returns are matched against the active sale customer
--   * sale invoices with return history cannot be updated or deleted
--
-- Idempotent. Apply with:
--   python manage.py apply_sql_all_tenants tenancy/sql/fix_sale_return_lifecycle_guards.sql
-- ============================================================================

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

UPDATE tenant_schema_version
SET version = GREATEST(version, 2),
    applied_at = CURRENT_TIMESTAMP
WHERE id = true;
