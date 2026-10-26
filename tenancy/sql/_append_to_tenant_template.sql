-- Append THESE TWO LINES to the END of tenancy/sql/tenant_template.sql
-- (so newly provisioned tenants never get the dead view / ambiguous overload).
DROP VIEW IF EXISTS item_history_view;
DROP FUNCTION IF EXISTS item_transaction_history(text);
