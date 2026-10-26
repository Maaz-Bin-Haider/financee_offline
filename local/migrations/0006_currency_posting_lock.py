from django.db import migrations
SQL="""
CREATE OR REPLACE FUNCTION local_profile_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'General Settings cannot be deleted.'; END IF;
    IF NEW.base_currency_id IS DISTINCT FROM OLD.base_currency_id THEN
        PERFORM pg_advisory_xact_lock(726104,2);
        IF EXISTS(SELECT 1 FROM public.journalentries) THEN
            RAISE EXCEPTION 'Base currency is locked after financial activity.';
        END IF;
    END IF;
    RETURN NEW;
END; $$;
CREATE FUNCTION local_currency_posting_lock() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(726104,2);
    RETURN NEW;
END; $$;
CREATE TRIGGER local_currency_posting_lock BEFORE INSERT ON public.journalentries
FOR EACH ROW EXECUTE FUNCTION local_currency_posting_lock();
UPDATE offline_schema_version SET version=2 WHERE id=true;
"""
class Migration(migrations.Migration):
    dependencies=[('local','0005_local_modules')]
    operations=[migrations.RunSQL(SQL)]
