"""Host-level recovery workflow test: only the owned disposable installation.
Restores real populated DB/media, verifies web restart, folder scheduling and
startup rollback, then returns this test installation to its initial dataset.
"""
import hashlib,json,os,subprocess,sys,tempfile,time,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];customer=ROOT/'.runtime/test'
assert customer.name=='test' and customer.parent.name=='.runtime'
base=['docker','compose','-p','financee_offline_test','--env-file',str(customer/'Config/compose.env'),'-f',str(ROOT/'runtime/compose.yml')]
def run(*args,**kw):return subprocess.run(list(args),cwd=ROOT,check=True,**kw)
def compose(*args,**kw):
    location=customer/'Config/backup-location.json'
    folder=json.loads(location.read_text())['directory'] if location.exists() else str(customer/'Backups')
    kw['env']=dict(os.environ,BACKUP_DIR=folder)
    return run(*base,*args,**kw)
def load(path):return json.loads(path.read_text())
def save(path,data):
    fd,name=tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd,'w') as f:json.dump(data,f);f.flush();os.fsync(f.fileno())
    os.replace(name,path)
def initial_pointer():
    active=load(customer/'Config/active.json')
    assert active['database']=='financee_offline_test' or active['database'].startswith('financee_offline_test_r_')
    save(customer/'Config/active.json',dict(active,generation='initial',database='financee_offline_test',media='Data/media'))
def dev(command):return run(sys.executable,'runtime/dev.py',command,'--stack','test')
def maintenance(command,*args):return run(sys.executable,'runtime/maintenance.py',command,*args,'--stack','test')
def health():
    with urllib.request.urlopen('http://127.0.0.1:18767/health/',timeout=5) as r:return json.load(r)
secrets_before=[(customer/'Config'/n).read_bytes() for n in ('runtime.env','compose.env')]
compose('stop','web','backup');initial_pointer();dev('up')
selected=customer/'Cache'/('SelectedBackups-'+uuid.uuid4().hex);selected.mkdir()
maintenance('set-folder',str(selected))
for _ in range(150):
    state=load(customer/'Config/backup-status.json')
    info=state.get('last_success') or {};archive=selected/info.get('filename','')
    if state.get('state')=='complete' and archive.is_file():break
    time.sleep(.1)
else:raise AssertionError('Fresh selected-folder daily backup did not complete.')
with zipfile.ZipFile(archive) as z:manifest=json.loads(z.read('manifest.json'))
assert manifest['reason']=='daily_or_catchup'
count=len(list(selected.glob('Financee_Offline_Backup_*.zip')))
dev('stop');dev('up')
time.sleep(1)
assert len(list(selected.glob('Financee_Offline_Backup_*.zip')))==count
sha=hashlib.sha256(archive.read_bytes()).hexdigest();old=load(customer/'Config/active.json')
maintenance('restore',str(archive),'--confirm-sha',sha)
active=load(customer/'Config/active.json');journal=load(customer/'Config/restore-journal.json')
assert active!=old and journal['stage']=='committed' and health()['generation']==active['generation']
assert (selected/journal['rescue']).is_file() and (customer/old['media']).is_dir()
compose('exec','-T','web','python','-c',"from local.backups import config,database;import contextlib; a=config.active(); c=database.connect(a['database']); assert database.scalar(c,'SELECT count(*) FROM django_session')==0; c.close(); print('Restored sessions expired.')")
compose('stop','backup','web')
prepared=compose('run','--rm','--no-deps','backup','python','-m','local.backups.cli','restore','/backups/'+archive.name,'--confirm-sha',sha,stdout=subprocess.PIPE,text=True)
assert json.loads(prepared.stdout)['stage']=='awaiting_health'
dev('up')
assert load(customer/'Config/restore-journal.json')['stage']=='rolled_back'
assert health()['generation']==active['generation']
assert [(customer/'Config'/n).read_bytes() for n in ('runtime.env','compose.env')]==secrets_before
result={'confirmed_restore_and_web_restart':True,'sessions_expired':True,'runtime_credentials_preserved':True,'previous_database_media_rescue_retained':True,'startup_rollback_of_unverified_switch':True,'selected_folder_automatic_backup':True,'same_day_restart_no_duplicate':True,'backup_sha256':sha,'measured_pause_seconds':manifest['pause_seconds']}
(customer/'Cache/phase4_controller_results.json').write_text(json.dumps(result,indent=2)+'\n')
# Test cleanup selects only the original disposable generation; all created
# candidates/rescues remain local for inspection. No customer/review DB is used.
compose('stop','backup','web');initial_pointer();dev('up')
maintenance('set-folder',str(customer/'Backups'))
print(json.dumps(result,indent=2))
