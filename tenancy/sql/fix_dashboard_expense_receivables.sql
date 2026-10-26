-- ============================================================================
-- fix_dashboard_expense_receivables.sql
--
-- No tenant schema version bump. The change replaces one reporting view and is
-- compatible in both directions — the old code reads the new view fine, and the
-- new code reads the old view (it just shows the bug). Raising the version gate
-- would buy nothing and would block the Phase 3B reversal path, whose registry
-- guard requires the tenant to be at exactly serial version 6. Every tenant
-- still receives this fix: production_hardening.sql carries it and is applied
-- on every web container start, before gunicorn accepts traffic.
--
-- Idempotent patch. Apply to every tenant:
--   python manage.py apply_sql_all_tenants \
--       tenancy/sql/fix_dashboard_expense_receivables.sql
--
-- PROBLEM
--   `vw_dash_party_ar_balance` summed EVERY journal line tagged with a party,
--   regardless of which account the line was posted to, and admitted any party
--   whose `ar_account_id` was not null.
--
--   `add_party_from_json` gives an Expense party BOTH `ar_account_id` (the
--   shared Accounts Receivable account) AND `ap_account_id` (its own new
--   Expense account). Paying a shop expense therefore debits the Expense
--   account with the expense party's id attached, and the view counted that
--   debit as a receivable.
--
--   Result: paying rent, salaries or a utility bill made that expense head
--   appear on the dashboard as a customer owing money, and raised
--   "Stale Receivable: Shop Rent" and "Risky Customer: Staff Salaries"
--   alerts from fn_dash_smart_alerts. fn_dash_receivables_aging counted the
--   same amounts in its aging buckets and totals.
--
-- FIX
--   Restrict the view to lines actually posted to the party's own accounts
--   receivable account. Verified against real tenant data:
--
--     party_type | account its party-tagged lines hit | = ar_account_id
--     -----------+-----------------------------------+----------------
--     Customer   | Accounts Receivable               | always
--     Both       | Accounts Receivable               | always
--     Expense    | its own Expense account           | never
--     Vendor     | Accounts Payable                  | n/a (ar is NULL)
--
--   So Customer and Both are untouched, Expense parties drop out, and Vendors
--   remain excluded exactly as before.
--
--   This is deliberately an account test rather than `party_type <> 'Expense'`:
--   a receivable is a balance in the receivables account, so the rule stays
--   correct if a new party type is ever introduced.
--
-- BEHAVIOUR NOTE
--   For a "Both" party the view previously netted their receivable against
--   their payable, because it summed every line. It now reports only what they
--   owe you, which is what a receivables view should show. Their payable is
--   still reported by the payables report and the trial balance.
--
-- NOT AFFECTED
--   `get_accounts_receivable_json_excluding` already filtered expense parties
--   out (`type NOT ILIKE '%Expense%'` over vw_trial_balance), so the Accounts
--   Receivable report was always correct. Only the dashboard was wrong.
-- ============================================================================

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

