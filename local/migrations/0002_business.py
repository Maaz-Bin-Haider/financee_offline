"""Fresh offline SQL bootstrap; never imports legacy production migration history."""
from pathlib import Path
import re
from django.db import migrations

SQL_PATH = Path(__file__).resolve().parents[1] / 'sql' / '0001_business.sql'

def bootstrap(apps, schema_editor):
    sql = SQL_PATH.read_text()
    names = set(name.lower() for name in re.findall(r'CREATE (?:TABLE|VIEW|SEQUENCE)(?: IF NOT EXISTS)? (?:public\.)?([a-zA-Z_][a-zA-Z_0-9]*)',sql,re.I))
    with schema_editor.connection.cursor() as cur:
        cur.execute("SELECT relname FROM pg_class JOIN pg_namespace n ON n.oid=relnamespace WHERE n.nspname='public'")
        collisions = names.intersection(row[0].lower() for row in cur.fetchall())
        if collisions: raise RuntimeError('Business schema collides with existing objects: '+', '.join(sorted(collisions)))
        cur.execute(sql)
        cur.execute('UPDATE offline_schema_version SET version=1 WHERE id=true')

class Migration(migrations.Migration):
    dependencies = [('local','0001_initial'),('auth','0012_alter_user_first_name_max_length')]
    operations = [migrations.RunPython(bootstrap)]
