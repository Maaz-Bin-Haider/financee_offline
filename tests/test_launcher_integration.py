"""Real launcher lifecycle on owned disposable data only; never review restore.
Run after explicitly deploying the same candidate image with runtime/dev.py.
"""
import hashlib,json,socket,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher.controller import Controller
from launcher.installation import Installation
from launcher.storage import LauncherError,atomic,read
ROOT=Path(__file__).resolve().parents[1]
customer=ROOT/'.runtime/test';program=ROOT/'.runtime/phase5-program'
installation=Installation.adopt(customer)
assert installation.project=='financee_offline_test' and installation.port==18767
c=Controller(installation,program,progress=print)
secrets_before=[(customer/'Config'/name).read_bytes() for name in ('runtime.env','compose.env')]
original=read(customer/'Config/active.json');assert original['generation']=='initial'
ids_before=c.command('ps','-q','--filter','label=com.docker.compose.project='+installation.project)
c.start(False)
assert ids_before==c.command('ps','-q','--filter','label=com.docker.compose.project='+installation.project)
assert 'running' in c.status()
c.stop();assert 'stopped' in c.status();c.start(False)
selected=customer/'Cache'/('Phase5 Selected Backups '+uuid.uuid4().hex[:8]);selected.mkdir()
c.set_backup_folder(selected);backup=Path(c.backup())
# Engine returns its container path; find exactly the named verified host ZIP.
backup=selected/backup.name;assert backup.is_file()
info=c.inspect_backup(backup);assert info['archive_sha256']==hashlib.sha256(backup.read_bytes()).hexdigest()
try:c.restore(backup,'0'*64)
except LauncherError as exc:assert 'changed after inspection' in str(exc)
else:raise AssertionError('Changed digest accepted')
assert read(customer/'Config/active.json')==original
journal=c.restore(backup,info['archive_sha256']);active=read(customer/'Config/active.json')
assert active['generation']!=original['generation'] and read(customer/'Config/restore-journal.json')['stage']=='committed'
assert c.health()['generation']==active['generation'] and (selected/journal['rescue']).is_file()
assert (customer/original['media']).is_dir()
c.compose('exec','-T','web','python','-c',"from local.backups import config,database; c=database.connect(config.active()['database']); assert database.scalar(c,'SELECT count(*) FROM django_session')==0; c.close()")
assert secrets_before==[(customer/'Config'/name).read_bytes() for name in ('runtime.env','compose.env')]
# Retain candidates/rescues but return this disposable installation to its original data.
c.stop();atomic(customer/'Config/active.json',original);c.start(False);c.set_backup_folder(customer/'Backups')
# Fresh installation with difficult paths, no seeded business/user, actual occupied-port refusal.
fresh_root=ROOT/'.runtime'/('Phase5 new AED $cash — '+uuid.uuid4().hex[:8])
with socket.socket() as occupied:
    occupied.bind(('127.0.0.1',0));occupied.listen();port=occupied.getsockname()[1]
    fresh=Installation.create(fresh_root,port,'desktop-linux');n=Controller(fresh,program,progress=print)
    try:n.start(False)
    except LauncherError as exc:assert 'occupied' in str(exc)
    else:raise AssertionError('Occupied port accepted')
    assert not n.volume_exists(),'Collision created a database volume'
value=n.start(False);assert not value['setup_complete'] and fresh.data['initialized']
counts=n.compose('exec','-T','db','psql','-U','financee_offline','-d',fresh.project,'-Atc','SELECT (SELECT count(*) FROM auth_user), (SELECT count(*) FROM local_generalsettings), (SELECT count(*) FROM journalentries)')
assert counts.strip()=='0|0|0',counts
assert 'setup is needed' in n.status();n.stop()
# Fresh test instances retain volumes but release their temporary address pools.
n.compose('down');assert n.volume_exists()
result={'existing_healthy_reused':True,'cold_stop_start':True,'selected_backup_folder':True,'manual_backup_and_inspect':True,'digest_change_refused':True,'candidate_restore_verified':True,'rescue_and_previous_data_retained':True,'restored_sessions_expired':True,'runtime_credentials_preserved':True,'original_test_pointer_restored':True,'actual_port_collision_refused_before_volume_creation':True,'new_empty_installation':True,'spaces_unicode_dollar_path':True,'temporary_networks_removed_data_volume_retained':True,'new_project_stopped':fresh.project,'new_customer':str(fresh_root),'backup_sha256':info['archive_sha256']}
atomic(customer/'Cache/phase5_launcher_results.json',result);print(json.dumps(result,indent=2))
