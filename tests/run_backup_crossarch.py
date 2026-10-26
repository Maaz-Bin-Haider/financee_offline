"""Host integration driver. Requires cached pinned AMD64 PG16 and emulation.
Only financee_offline_test and a named networkless disposable container are used.
"""
import json,subprocess,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];customer=ROOT/'.runtime/test'
base=['docker','compose','-p','financee_offline_test','--env-file',str(customer/'Config/compose.env'),'-f',str(ROOT/'runtime/compose.yml')]
state=json.loads((customer/'Config/backup-status.json').read_text());archive=customer/'Backups'/state['last_success']['filename']
folder=customer/'Cache/xarch';folder.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as z:
    for name in ['database.dump','integrity.json']:(folder/name).write_bytes(z.read(name))
name='financee_offline_crossarch_test'
subprocess.run(['docker','run','-d','--rm','--pull','never','--platform','linux/amd64','--network','none','--label','financee.offline.test=crossarch','--name',name,'-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_USER=offline_xarch','-e','POSTGRES_DB=offline_xarch','postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d'],check=True,stdout=subprocess.DEVNULL)
try:
    for i in range(90):
        # TCP readiness excludes the entrypoint's temporary init-only server.
        if subprocess.run(['docker','exec',name,'pg_isready','-h','127.0.0.1','-U','offline_xarch','-d','offline_xarch'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
        time.sleep(.5)
    else:raise RuntimeError('Emulated x64 PostgreSQL did not start.')
    subprocess.run(['docker','exec',name,'uname','-m'],check=True)
    subprocess.run(['docker','cp',str(folder/'database.dump'),name+':/tmp/input.dump'],check=True)
    subprocess.run(['docker','exec',name,'pg_restore','-U','offline_xarch','-d','offline_xarch','--no-owner','--no-acl','--exit-on-error','--single-transaction','/tmp/input.dump'],check=True)
    with (folder/'amd64.dump').open('wb') as f:subprocess.run(['docker','exec',name,'pg_dump','-U','offline_xarch','-d','offline_xarch','-Fc','--no-owner','--no-acl'],stdout=f,check=True)
    subprocess.run(base+['run','--rm','--no-deps','-v',str(ROOT)+':/app','backup','python','tests/test_backup_crossarch.py'],check=True)
finally:subprocess.run(['docker','stop',name],check=True,stdout=subprocess.DEVNULL)
