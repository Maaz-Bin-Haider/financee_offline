from django.db import migrations

SQL = """
CREATE FUNCTION local_profile_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'General Settings cannot be deleted.'; END IF;
    IF NEW.base_currency_id IS DISTINCT FROM OLD.base_currency_id
       AND EXISTS(SELECT 1 FROM public.journalentries) THEN
        RAISE EXCEPTION 'Base currency is locked after financial activity.';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER local_profile_protected BEFORE UPDATE OR DELETE ON local_generalsettings
FOR EACH ROW EXECUTE FUNCTION local_profile_guard();
CREATE FUNCTION local_profile_no_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'General Settings cannot be truncated.'; END; $$;
CREATE TRIGGER local_profile_no_truncate BEFORE TRUNCATE ON local_generalsettings
FOR EACH STATEMENT EXECUTE FUNCTION local_profile_no_truncate();
"""
class Migration(migrations.Migration):
    dependencies = [('local','0002_business')]
    operations = [migrations.RunSQL(SQL)]
