"""Real Nginx HTTP integration smoke; refuse every non-disposable database.
Run inside the owned test web service. No browser or source/review data is used.
"""
import hashlib,http.cookiejar,io,json,os,re,secrets,urllib.parse,urllib.request
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings')
import django;django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from reportlab.pdfgen.canvas import Canvas
from spotlight.policy import PAGES
from local.models import GeneralSettings
from zoneinfo import ZoneInfo
assert settings.DATABASES['default']['NAME']=='financee_offline_test','Disposable test DB required'
base='http://nginx';jar=http.cookiejar.CookieJar();http=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
checks=[];resources={}
def sql(query,args=None):
 with connection.cursor() as c:c.execute(query,args or []);return c.fetchone()[0]
def check(ok,label):
 assert ok,label
 checks.append(label)
def request(path,data=None,ctype=None,opener=http):
 target=urllib.parse.urlsplit(path)
 assert not target.netloc and not target.scheme and path.startswith('/'),path
 headers={'Host':'localhost','Cache-Control':'no-cache'}
 if data is not None:
  headers['X-CSRFToken']=next(c.value for c in jar if c.name=='csrftoken')
  headers['X-Requested-With']='XMLHttpRequest'
  headers['Content-Type']=ctype or 'application/json'
 with opener.open(urllib.request.Request(base+path,data=data,headers=headers),timeout=20) as r:
  body=r.read();check(r.status==200,'HTTP200 '+path)
  check("connect-src 'self'" in r.headers.get('Content-Security-Policy',''),'local CSP '+path)
  return body,r.headers
class Resources(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag in ('script','link','img','source','iframe'):
   target=a.get('src') or a.get('href')
   if target:self.urls.append(target)
def asset(path):
 if path.startswith('data:'):return
 url=urllib.parse.urlsplit(path)
 check(not url.netloc and not url.scheme,'no remote resource '+path)
 if not path.startswith('/static/') or path in resources:return
 body,headers=request(path)
 resources[path]={'size':len(body),'sha256':hashlib.sha256(body).hexdigest()}
 if url.path.endswith('.css'):
  for target in re.findall(r'url\(\s*[\'\"]?([^\s)\'\"]+)',body.decode()):
   asset(urllib.parse.urljoin(path,target))
uid=secrets.token_hex(6);username='http_'+uid;password=secrets.token_urlsafe(32)
owner=get_user_model().objects.create_superuser(username,password=password)
request('/authentication/login/')
body,_=request('/authentication/login/',urllib.parse.urlencode({'username':username,'password':password}).encode(),'application/x-www-form-urlencoded')
check(json.loads(body)['status']=='success','local HTTP sign-in')
paths=sorted({p.path for p in PAGES.values()}|{'/admin/','/admin/local/generalsettings/1/change/'})
for path in paths:
 body,_=request(path);parser=Resources();parser.feed(body.decode())
 for resource in parser.urls:asset(resource)
# Fixtures set up a unique vendor/item; the invoice and upload go through HTTP.
vendor=('HTTP VENDOR '+uid).upper();item=('HTTP DEVICE '+uid).upper();serial='HTTP-SERIAL-'+uid
for fn,data in [('add_party_from_json',{'party_name':vendor,'party_type':'Vendor','created_by_id':str(owner.pk)}),('add_item_from_json',{'item_name':item,'sale_price':200,'created_by_id':str(owner.pk)})]:
 sql('SELECT '+fn+'(%s::jsonb)',[json.dumps(data)])
payload={'action':'submit','party_name':vendor,'purchase_date':'2026-10-01','items':[{'item_name':item,'qty':1,'unit_price':'100.25','serials':[{'serial':serial}]}]}
pdf=io.BytesIO();doc=Canvas(pdf);doc.drawString(50,780,'Disposable offline attachment '+uid);doc.save();contents=pdf.getvalue()
boundary='offline'+uid
body=(f'--{boundary}\r\nContent-Disposition: form-data; name="payload"\r\n\r\n'+json.dumps(payload)+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="attachment_pdf"; filename="offline.pdf"\r\nContent-Type: application/pdf\r\n\r\n').encode()+contents+f'\r\n--{boundary}--\r\n'.encode()
result,_=request('/purchase/purchasing/',body,'multipart/form-data; boundary='+boundary)
check(json.loads(result).get('success'), 'HTTP multipart purchase: '+result.decode())
pid=sql('SELECT i.purchase_invoice_id FROM purchaseunits u JOIN purchaseitems i USING(purchase_item_id) WHERE u.serial_number=%s',[serial])
check(str(sql('SELECT total_amount FROM purchaseinvoices WHERE purchase_invoice_id=%s',[pid]))=='100.25','HTTP posting amount unchanged')
check(sql("SELECT count(*) FROM activity_events WHERE kind='purchase' AND action='create' AND user_id=%s AND record_id=%s",[owner.pk,pid])==1,'multipart posting attributed once')
metadata,_=request(f'/attachments/purchase/{pid}/');check(json.loads(metadata)['attachments']['pdf']['file_size']==len(contents),'private attachment metadata')
download,headers=request(f'/attachments/purchase/{pid}/pdf/download/');check(download==contents,'uploaded/downloaded PDF bytes identical')
check('attachment;' in headers['Content-Disposition'],'private download disposition')
preview,_=request(f'/attachments/purchase/{pid}/pdf/preview/');check(preview==contents,'private PDF preview')
search,_=request('/spotlight/search/?'+urllib.parse.urlencode({'q':serial}));check(serial in search.decode(),'Spotlight finds posted serial')
today=datetime.now(ZoneInfo(GeneralSettings.objects.get().timezone)).date().isoformat()
activity,_=request(f'/activity/api/day/?user={owner.pk}&date={today}');check('purchase' in activity.decode(),'activity API includes HTTP posting')
anon=urllib.request.build_opener()
body,_=request(f'/attachments/purchase/{pid}/pdf/download/',opener=anon);check(b'Sign in to your account' in body,'anonymous attachment redirects to login')
result={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'checks':len(checks),'screens':len(paths),'resources':resources,'purchase_id':pid,'attachment_sha256':hashlib.sha256(contents).hexdigest(),'database':settings.DATABASES['default']['NAME']}
out=Path('/customer/Cache/phase3_http_results.json');out.write_text(json.dumps(result,indent=2)+'\n')
print(f'{len(checks)} HTTP checks passed; {len(paths)} screens; {len(resources)} local resources; posting/upload/download/Spotlight/activity verified.')
