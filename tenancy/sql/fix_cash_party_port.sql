-- ============================================================================
-- fix_cash_party_port.sql
-- ----------------------------------------------------------------------------
-- Ports the cash-party feature (and its invoice-description prerequisite) to
-- every tenant. Heals the last tenant-drift item deferred in FIXED_ISSUES.md /
-- todo.md: the feature existed only on tenant_company_2; tenant_company_1 had
-- no parties.is_cash column, no get_cash_party_id(), and non-cash-aware
-- journal builders, so the cash sale/purchase path in sale/views.py and
-- purchase/views.py errored there. tenant_company_1 was also missing the
-- invoice-description feature (description columns on salesinvoices /
-- purchaseinvoices / salesreturns / purchasereturns and the description-aware
-- get_current_* fetchers), which the cash-aware ledger functions read.
--
-- Contents (all idempotent):
--   0. Invoice-description prerequisite: the four `description` columns and
--      the four read-only get_current_* fetchers (from
--      add_invoice_description.sql; no create/update/delete function is
--      touched, so the transaction-integrity guards are unaffected).
--   1. parties.is_cash column + get_cash_party_id(kind) helper.
--   2. The four cash-aware journal builders (rebuild_sales_journal,
--      rebuild_purchase_journal, rebuild_sales_return_journal,
--      rebuild_purchase_return_journal). These bodies are byte-identical to
--      the versions live on tenant_company_2, which pass the full suite
--      (tests/suite/) and the deep lifecycle test (2702/2702) TOGETHER WITH
--      the transaction-integrity guards (schema v3) - the COGS-reflow fix
--      calls rebuild_sales_journal and these bodies recompute COGS from
--      PurchaseItems.unit_price, so the reflow behavior is preserved.
--      (The integrity patches never redefine these functions; the "merge"
--      feared in todo.md reduces to applying these exact bodies.)
--   3. Cash-aware detailed_ledger / detailed_ledger2 (from
--      add_cash_party_ledger.sql), which also carry the invoice-description
--      enrichment.
--   4. Eager seeding of the "Cash Sale" / "Cash Purchase" parties.
--   5. Tenant schema version bump to 5.
--
-- Apply to all tenants with:
--   python manage.py apply_sql_all_tenants tenancy/sql/fix_cash_party_port.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0) Invoice-description prerequisite (columns + read-only fetchers).
-- ----------------------------------------------------------------------------
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

-- Bump tenant schema version.
UPDATE tenant_schema_version
SET version = GREATEST(version, 5),
    applied_at = CURRENT_TIMESTAMP
WHERE id = true;
