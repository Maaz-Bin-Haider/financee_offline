-- ============================================================================
-- fix_tenant_drift.sql
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
