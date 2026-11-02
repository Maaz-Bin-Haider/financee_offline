"""Synthetic populated upgrade fixture. Requires a unique host-written marker.
Never used by normal installation; refuses every unmarked/source/review dataset.
"""
import hashlib,json,os,re,secrets,sys
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group,Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client,RequestFactory
from local.backups import config,database
root=Path('/customer');marker=json.loads((root/'Config/phase8-test-owner.json').read_text());project=sys.argv[2]
assert re.fullmatch(r'financee_offline_[0-9a-f]{12}',project) and marker=={'project':project,'token':sys.argv[3]}
a=config.active(root);assert a['instance_id'][:12]==project.removeprefix('financee_offline_') and os.environ['DB_NAME']==project
assert settings.DATABASES['default']['NAME']==a['database'] and a['database']!= 'financee_offline_review'
if sys.argv[1]=='seed':
 from local.models import GeneralSettings
 assert not GeneralSettings.objects.exists() and get_user_model().objects.count()==0
 password=secrets.token_urlsafe(32);client=Client();response=client.post('/setup/',dict(company_name='Disposable upgrade business',currency='AED',timezone='Asia/Dubai',username='upgrade_owner',password1=password,password2=password));assert response.status_code==302
 owner=get_user_model().objects.get(username='upgrade_owner');observer=get_user_model().objects.create_user('upgrade_observer',password=secrets.token_urlsafe(32));get_user_model().objects.create_user('upgrade_inactive',password=secrets.token_urlsafe(32),is_active=False)
 group=Group.objects.create(name='Upgrade viewers');permission=Permission.objects.filter(codename='view_purchase').first();assert permission;group.permissions.add(permission);observer.groups.add(group)
 c=database.connect(a['database'])
 def q(query,args=None):return database.scalar(c,query,args)
 vendor='Upgrade Vendor';customer='Upgrade Customer';item='Upgrade Device'
 for name,kind in [(vendor,'Vendor'),(customer,'Customer')]:q('SELECT add_party_from_json(%s::jsonb)',[json.dumps({'party_name':name,'party_type':kind,'created_by_id':str(owner.pk)})])
 q('SELECT add_item_from_json(%s::jsonb)',[json.dumps({'item_name':item,'sale_price':200,'created_by_id':str(owner.pk)})])
 vid=q('SELECT party_id FROM parties WHERE party_name=%s',[vendor]);cid=q('SELECT party_id FROM parties WHERE party_name=%s',[customer])
 pid=q('SELECT create_purchase(%s,%s,%s::jsonb,%s)',[vid,'2026-10-01',json.dumps([{'item_name':item,'qty':2,'unit_price':'123.45','serials':[{'serial':'UPGRADE-SERIAL-1'},{'serial':'UPGRADE-SERIAL-2'}]}]),owner.pk])
 q('SELECT create_sale(%s,%s,%s::jsonb,%s)',[cid,'2026-10-02',json.dumps([{'item_name':item,'qty':1,'unit_price':'200.00','serials':['UPGRADE-SERIAL-1']}]),owner.pk]);c.commit();c.close()
 request=RequestFactory().post('/synthetic-fixture/',{'attachment_pdf':SimpleUploadedFile('upgrade-proof.pdf',b'%PDF-1.4\nSynthetic upgrade attachment\n%%EOF\n',content_type='application/pdf')});request.user=owner
 from attachments.utils import save_document_attachments
 save_document_attachments(request,'purchase',pid)
 from activity.recorder import record
 assert record(request,'create','purchase',pid,label='Synthetic upgrade purchase')
 (Path(settings.MEDIA_ROOT)/'unreferenced-binary.bin').write_bytes(bytes(range(256))*40)
 print('Synthetic owner, group, permission, inactive user, serialized purchase/sale, history and attachment created.')
elif sys.argv[1]=='snapshot':
 c=database.connect(a['database']);database.integrity(c,root/a['media']);fp=database.fingerprints(c);sessions=fp['tables'].pop('django_session')['count'];c.close()
 media={str(p.relative_to(root/a['media'])):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/a['media']).rglob('*') if p.is_file()}
 print(json.dumps({'fingerprints':fp,'media':media,'sessions':sessions,'financial_SQL_verified':190}))
else:raise AssertionError('Unknown test command')
