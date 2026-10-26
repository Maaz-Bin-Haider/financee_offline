-- cleanup_dead_objects.sql
-- ============================================================================
-- Apply to EXISTING tenants to drop the dead / ambiguous objects that the
-- updated tenant_template.sql already excludes for new tenants.
--
--   1. item_history_view        — hard-coded to '%iPhone 15 Pro%', unused.
--   2. item_transaction_history(text) — redundant 1-arg overload that makes a
--      one-argument call ambiguous. The app always calls the 3-arg version
--      item_transaction_history(text, date, date), which is left intact.
--
-- Idempotent and safe: nothing depends on either object.
--
-- Run across all tenant schemas with the bundled management command:
--     python manage.py apply_sql_all_tenants deploy/cleanup_dead_objects.sql
-- (inside the container: docker compose exec web python manage.py \
--      apply_sql_all_tenants deploy/cleanup_dead_objects.sql)
-- ============================================================================

DROP VIEW IF EXISTS item_history_view;
DROP FUNCTION IF EXISTS item_transaction_history(text);
