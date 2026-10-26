from django.db import migrations

def seed(apps, schema_editor):
    from local.currencies import seed_currency_catalogue
    seed_currency_catalogue(apps.get_model('local','Currency'))

class Migration(migrations.Migration):
    dependencies = [('local','0003_profile_guards')]
    operations = [migrations.RunPython(seed)]
