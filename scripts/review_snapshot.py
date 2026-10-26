"""Read-only preservation evidence for the separately owned review build.
Never prints business rows, credentials or customer files. Output stays ignored.
"""
import hashlib,json,os,sys
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings')
import django;django.setup()
from django.conf import settings
from django.db import connection
assert settings.DATABASES['default']['NAME']=='financee_offline_review','Owned review database required'
assert sys.argv[1] in ('phase3_before','phase3_after')
with connection.cursor() as c:
 c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT LIKE 'django_%' AND tablename NOT IN ('auth_user','activity_events') ORDER BY tablename")
 tables=[row[0] for row in c.fetchall()]
result={}
with connection.cursor() as c:
 for name in tables:
  c.execute('SELECT to_regclass(%s)',[name])
  if not c.fetchone()[0]:continue
  c.execute(f'SELECT row_to_json(t)::text FROM {name} t ORDER BY row_to_json(t)::text')
  rows=c.fetchall();result[name]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(r[0] for r in rows).encode()).hexdigest()}
 c.execute('SELECT id,username,is_active,is_staff,is_superuser FROM auth_user ORDER BY id')
 rows=c.fetchall();result['users']={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
 c.execute('SELECT base_currency_id,symbol_override,timezone FROM local_generalsettings WHERE id=1');result['display_profile']=c.fetchone()
root=Path(settings.MEDIA_ROOT)
result['media']={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.rglob('*')) if f.is_file()}
out=Path('/customer/Cache')/(sys.argv[1]+'.json');out.write_text(json.dumps(result,indent=2)+'\n')
if sys.argv[1]=='phase3_after':
 before=json.loads((out.parent/'phase3_before.json').read_text());after=json.loads(out.read_text())
 assert before==after,'Review state changed; inspect private snapshots.'
 print('Review profile, users/permissions, business rows and media hashes unchanged.')
else:print('Review preservation snapshot saved privately.')
