"""Explicit local upgrades; old database/media/runtime stay paired and retained.
No customer initialization, registry pulls, global runtime changes or automatic
image-only downgrades. The first policy accepts schema-2, lossless upgrades only.
"""
import contextlib,copy,hashlib,json,os,re,shutil,uuid
from pathlib import Path
from launcher.controller import Controller,SERVICES
from launcher.installation import Installation
from launcher.storage import LauncherError,atomic,read,lock
from .payload import Payload,digest
TERMINAL=(None,'committed','rolled_back')

def pending(root):return read(Path(root)/'Config/upgrade-journal.json',{}).get('stage') not in TERMINAL

def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify_program(program):
    program=Path(program).resolve();r=read(program/'release.json',{})
    if r.get('format')!=1 or r.get('product')!='Financee_Offline':raise LauncherError('Invalid previous Financee program release.')
    if not isinstance(r.get('files'),dict) or not {'compose.yml','nginx.conf'}<=r['files'].keys():raise LauncherError('Previous program resources are incomplete.')
    for name,expected in r['files'].items():
        f=program/name
        if not f.resolve().is_relative_to(program) or not f.is_file() or digest(f)!=expected:raise LauncherError('Previous program resources failed verification.')
    if set(r.get('service_images',{}))!=SERVICES:raise LauncherError('Previous program service identities are incomplete.')
    return r

def check_policy(source,target,policy):
    if (policy.get('format')!=1 or policy.get('product')!='Financee_Offline' or policy.get('target_version')!=target.get('version') or
        source.get('version') not in policy.get('from_versions',[]) or source.get('version')==target.get('version') or
        source.get('schema')!=2 or target.get('schema')!=2 or policy.get('source_schema')!=2 or policy.get('target_schema')!=2 or
        policy.get('postgres_major')!=16 or policy.get('migration_policy')!='no-pending-django-migrations' or policy.get('preserve_business_fingerprints') is not True):
        raise LauncherError('This release does not authorize that source version/schema. Downgrades and unreviewed migrations are refused.')
    def numbers(v):
        m=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-phase\d+)?',v or '')
        if not m:raise LauncherError('Unsupported release version.')
        return tuple(map(int,m.groups()))
    if numbers(target['version'])<=numbers(source['version']):raise LauncherError('A manual upgrade must move to a newer release; image-only downgrade is refused.')
    if source.get('architecture')!=target.get('architecture'):raise LauncherError('Use the matching native architecture.')
    for service in ('db','redis','nginx'):
        if source['service_images'][service]!=target['service_images'][service]:raise LauncherError('This upgrade policy cannot replace shared storage/cache/proxy components.')

def union_ownership(old,new):
    """Recovery alone may stop a mixture of these two exact owned releases."""
    old.context_local();ids=old.command('ps','-aq','--filter','label=com.docker.compose.project='+old.installation.project).split()
    if not ids:return
    for value in json.loads(old.command('inspect',*ids)):
        labels=value.get('Config',{}).get('Labels') or {};service=labels.get('com.docker.compose.service')
        if labels.get('com.docker.compose.project')!=old.installation.project or service not in SERVICES:raise LauncherError('Upgrade recovery found an unexpected project service.')
        allowed={c.image_ids[c.release['service_images'][service]] for c in (old,new)}
        if value.get('Image') not in allowed:raise LauncherError('Upgrade recovery found a foreign image. No resources were changed.')
        mounts=value.get('Mounts',[])
        if service in ('web','backup') and not any(m.get('Destination')=='/customer' and old.customer_mount_matches(m.get('Source','')) for m in mounts):raise LauncherError('Upgrade recovery customer mount differs.')
        if service=='db' and not any(m.get('Name')==old.installation.volume and m.get('Destination')=='/var/lib/postgresql/data' for m in mounts):raise LauncherError('Upgrade recovery database volume differs.')
        if service=='nginx' and value.get('HostConfig',{}).get('PortBindings',{}).get('80/tcp',[])!=[{'HostIp':'127.0.0.1','HostPort':str(old.installation.port)}]:raise LauncherError('Upgrade recovery loopback binding differs.')

class Upgrade:
    def __init__(self,customer,target,previous=None,system=None,progress=None):
        self.installation=Installation(customer);self.payload=Payload(target);self.previous=Path(previous).resolve() if previous else None
        self.system=system;self.progress=progress or (lambda t:None);self.path=self.installation.root/'Config/upgrade-journal.json'
    def emit(self,text):self.progress(text)
    def controller(self,program,data=None):
        i=Installation(self.installation.root)
        if data is not None:i.data=copy.deepcopy(data)
        return Controller(i,program,self.system,self.progress)
    def policy(self):
        name='upgrade-policy.json'
        if name not in self.payload.release['files']:raise LauncherError('This installer has no verified manual-upgrade policy.')
        return read(self.payload.program/name,{})
    def prepare(self,cache,archive):
        if not self.previous:raise LauncherError('Select the previous installed Financee program.')
        if pending(self.installation.root):raise LauncherError('An interrupted upgrade needs recovery before another upgrade.')
        old=self.controller(self.previous);source=verify_program(self.previous);check_policy(source,self.payload.release,self.policy())
        if self.installation.data.get('installed_program') not in (None,digest(self.previous/'release.json')):raise LauncherError('The previous program does not match the selected installation.')
        if not self.installation.data.get('initialized'):raise LauncherError('Finish the existing business setup first; an upgrade never initializes a database.')
        if read(self.installation.root/'Config/restore-journal.json',{}).get('stage') not in (None,'committed','rolled_back','failed_before_switch'):raise LauncherError('Finish pending backup recovery before upgrading.')
        if self.installation.data.get('start_at_signin'):raise LauncherError('Turn off optional sign-in startup in the previous app before upgrading. Enable it in the new app after verification.')
        old.ensure_runtime();old.images_ready();old.ownership();old.verify_storage()
        healthy=old.check_port()
        if not healthy:healthy=old.start(open_browser=False)
        if healthy.get('build')!=source['version'] or healthy.get('schema')!=source['schema'] or not healthy.get('setup_complete'):raise LauncherError('The previous release must be healthy with company setup complete.')
        local=self.payload.acquire(cache,archive,self.progress)
        ids=self.payload.import_images(local,old.system,old.docker,old.context,old.env,self.progress)
        return {'from_version':source['version'],'to_version':self.payload.release['version'],'customer_directory':str(self.installation.root),'backup_directory':str(self.installation.backup_folder),'confirmation':self.consent(),'runtime_ids':ids,'archive':str(local)}
    def consent(self):
        i=Installation(self.installation.root)
        return fingerprint({'installation':i.data,'active':read(i.root/'Config/active.json'),'previous_program':digest(self.previous/'release.json'),'target_program':digest(self.payload.program/'release.json'),'target_delivery':self.payload.identity,'backup_folder':str(i.backup_folder)})
    def record(self,journal,stage,**values):
        journal.update(values,stage=stage);atomic(self.path,journal);self.emit('Upgrade: '+stage.replace('_',' '))
    def snapshot(self,source,target):
        verify_program(source)
        if any(f.is_symlink() for f in Path(source).rglob('*')):raise LauncherError('Program resources must not contain symbolic links.')
        shutil.copytree(source,target);verify_program(target)
        if digest(Path(source)/'release.json')!=digest(target/'release.json'):raise LauncherError('Program snapshot verification failed.')
    def tool(self,c,journal,command,*args,archive=None,code=None):
        name=c.installation.project+'_upgrade_'+journal['id'][:12]
        options=['run','--rm','--no-deps','--pull','never','-T','--name',name]
        if archive:options+=['-v',str(Path(archive).resolve())+':/restore-input/archive.zip:ro']
        script=['python','-c',code] if code else ['python','-m','local.backups.cli',command,*args]
        return c.compose(*options,'backup',*script,timeout=None)
    def apply(self,prepared,confirmation):
        if confirmation!=prepared.get('confirmation') or confirmation!=self.consent():raise LauncherError('Upgrade inputs changed after review. Verify and confirm again.')
        root=self.installation.root
        with lock(root/'Config/launcher-window.lock'),lock(root/'Config/controller.lock'):
            if pending(root):raise LauncherError('An interrupted upgrade needs recovery.')
            # Re-check manifests/images/ownership after confirmation and before stop.
            checked=self.prepare(Path(prepared['archive']).parent,prepared['archive'])
            if checked['confirmation']!=confirmation:raise LauncherError('Upgrade inputs changed after confirmation.')
            old=self.controller(self.previous);token=uuid.uuid4().hex;folder=root/'Cache/upgrades'/token;folder.mkdir(parents=True)
            required=sum(f.stat().st_size for p in (self.previous,self.payload.program) for f in Path(p).rglob('*') if f.is_file())+64*1024*1024
            if shutil.disk_usage(folder).free<required:raise LauncherError('Not enough space to retain both program releases.')
            if not folder.resolve().is_relative_to(root) or any(p.is_symlink() for p in (root/'Cache',root/'Cache/upgrades')):raise LauncherError('Upgrade staging must stay inside the customer Cache folder.')
            self.snapshot(self.previous,folder/'previous-program');self.snapshot(self.payload.program,folder/'target-program')
            old_data=read(root/'Config/launcher.json');target_data=copy.deepcopy(old_data);release_id=digest(folder/'target-program/release.json')
            target_data.update(installed_program=release_id,runtime_images={'release_sha256':release_id,'ids':checked['runtime_ids']})
            journal={'format':1,'product':'Financee_Offline','instance_id':old_data['id'],'id':token,'old_active':read(root/'Config/active.json'),'old_installation':old_data,'target_installation':target_data,'old_restore_journal':read(root/'Config/restore-journal.json'),'previous_program':str((folder/'previous-program').relative_to(root)),'target_program':str((folder/'target-program').relative_to(root)),'previous_release_sha256':digest(folder/'previous-program/release.json'),'target_release_sha256':release_id,'credentials':{name:digest(root/'Config'/name) for name in ('runtime.env','compose.env')},'backup_folder':str(old.installation.backup_folder),'rescue':None,'rescue_sha256':None}
            self.record(journal,'staged')
            try:
                old.compose('stop','web','backup')
                rescue=self.tool(old,journal,None,code="from local.backups.engine import Engine; print(Engine().backup('rescue','pre_upgrade'))").strip()
                if not rescue.startswith('/backups/') or Path(rescue).name!=rescue[len('/backups/'):]:raise LauncherError('Unexpected rescue backup path.')
                rescue=old.installation.backup_folder/Path(rescue).name
                info=json.loads(self.tool(old,journal,'inspect','/restore-input/archive.zip',archive=rescue))
                if info.get('kind')!='rescue' or info.get('installation_id')!=old_data['id'] or info.get('app_version')!=old.release['version']:raise LauncherError('The paired rescue point does not match the installed release.')
                self.record(journal,'rescue_saved',rescue=str(rescue),rescue_sha256=info['archive_sha256'])
                candidate=json.loads(self.tool(old,journal,'restore','/restore-input/archive.zip','--confirm-sha',info['archive_sha256'],archive=rescue))
                if candidate.get('old')!=journal['old_active'] or candidate.get('stage')!='awaiting_health':raise LauncherError('The candidate recovery transaction is inconsistent.')
                self.record(journal,'candidate_prepared',new_active=candidate['new'])
                atomic(root/'Config/launcher.json',target_data);new=self.controller(folder/'target-program')
                self.record(journal,'target_bound')
                checks=json.loads(self.tool(new,journal,'upgrade-check','/restore-input/archive.zip','--confirm-sha',info['archive_sha256'],archive=rescue))
                new.compose('run','--rm','--no-deps','--pull','never','-T','--name',new.installation.project+'_upgrade_'+token[:12],'web','python','manage.py','migrate','--noinput',timeout=180)
                new.compose('run','--rm','--no-deps','--pull','never','-T','--name',new.installation.project+'_upgrade_'+token[:12],'web','python','manage.py','check',timeout=120)
                checks=json.loads(self.tool(new,journal,'upgrade-check','/restore-input/archive.zip','--confirm-sha',info['archive_sha256'],archive=rescue))
                self.record(journal,'candidate_verified',checks=checks)
                self.start_services(new)
                health=new.wait_health();self.record(journal,'awaiting_health',health=health)
                self.tool(new,journal,'commit')
                self.verify_credentials(journal)
                self.record(journal,'committed')
                try:new.compose('up','-d','--no-build','--pull','never','--no-deps','backup')
                except LauncherError:self.emit('Upgrade committed. Reopen Financee to resume the local backup service.')
                self.installation=Installation(root)
                return journal
            except BaseException as exc:
                self.emit('Upgrade interrupted. Recovering the previous paired runtime and data.')
                try:self._recover(journal)
                except BaseException as recovery_error:raise LauncherError('Upgrade needs recovery. Previous data and rescue files remain retained. Reopen this installer and choose Recover Interrupted Upgrade.') from recovery_error
                raise
    def verify_credentials(self,journal):
        for name,expected in journal['credentials'].items():
            if digest(self.installation.root/'Config'/name)!=expected:raise LauncherError('Runtime credentials changed during the upgrade; automatic recovery was stopped.')
    def load_journal(self):
        j=read(self.path,{})
        if j.get('format')!=1 or j.get('product')!='Financee_Offline' or j.get('instance_id')!=self.installation.data['id'] or not re.fullmatch(r'[0-9a-f]{32}',j.get('id','')):raise LauncherError('The upgrade recovery journal is invalid.')
        if j.get('target_release_sha256')!=self.payload.delivery['release_sha256']:raise LauncherError('Use the matching target installer to recover this upgrade.')
        for key,hash_key,leaf in [('previous_program','previous_release_sha256','previous-program'),('target_program','target_release_sha256','target-program')]:
            expected=Path('Cache/upgrades')/j['id']/leaf
            if Path(j.get(key,''))!=expected:raise LauncherError('Upgrade recovery program path is invalid.')
            p=self.installation.root/expected
            if not p.resolve().is_relative_to(self.installation.root):raise LauncherError('Upgrade recovery staging escaped the customer folder.')
            verify_program(p)
            if digest(p/'release.json')!=j[hash_key]:raise LauncherError('Upgrade recovery program identity changed.')
        if read(self.installation.root/'Config/launcher.json') not in (j['old_installation'],j['target_installation']):raise LauncherError('Installation identity changed after the upgrade. Automatic recovery was stopped.')
        for active in (j['old_active'],j.get('new_active',j['old_active'])):
            if active.get('instance_id')!=j['instance_id'] or active.get('database_volume')!=self.installation.volume:raise LauncherError('Upgrade recovery storage identity differs.')
        current=read(self.installation.root/'Config/active.json')
        restore=read(self.installation.root/'Config/restore-journal.json',{})
        allowed=[j['old_active']]
        if restore.get('old')==j['old_active'] and restore.get('archive_sha256')==j.get('rescue_sha256') and restore.get('new',{}).get('instance_id')==j['instance_id'] and restore.get('new',{}).get('database_volume')==self.installation.volume:allowed.append(restore['new'])
        if j.get('new_active'):allowed.append(j['new_active'])
        if current not in allowed:raise LauncherError('The active generation changed outside this upgrade; recovery was stopped.')
        if str(self.installation.backup_folder)!=j['backup_folder']:raise LauncherError('The backup folder changed during this upgrade.')
        self.verify_credentials(j);return j
    def recover(self):
        root=self.installation.root
        with lock(root/'Config/launcher-window.lock'),lock(root/'Config/controller.lock'):
            journal=self.load_journal()
            if journal['stage'] in TERMINAL:return journal
            return self._recover(journal)
    def start_services(self,c):
        c.compose('run','--rm','--no-deps','--pull','never','-T','web','python','manage.py','collectstatic','--noinput',timeout=120)
        c.compose('up','-d','--no-build','--pull','never','--no-deps','web','nginx');c.compose('exec','-T','nginx','nginx','-s','reload')
    def _recover(self,journal):
        # Re-read/validate durable state, never trust caller-supplied recovery paths.
        journal=self.load_journal();root=self.installation.root
        if journal['stage'] in TERMINAL:return journal
        old=self.controller(root/journal['previous_program'],journal['old_installation']);new=self.controller(root/journal['target_program'],journal['target_installation'])
        old.ensure_runtime();new.ensure_runtime();old.images_ready();new.images_ready();union_ownership(old,new);old.verify_storage();old.check_port()
        # A crashed host can leave its one-off migration/restore container alive.
        name=old.installation.project+'_upgrade_'+journal['id'][:12]
        ids=old.command('ps','-aq','--filter','name=^/'+name+'$').split()
        if ids:
            value=json.loads(old.command('inspect',*ids))
            if len(value)!=1 or value[0].get('Name')!='/'+name:raise LauncherError('Upgrade task container identity is inconsistent.')
            labels=value[0].get('Config',{}).get('Labels') or {}
            if labels.get('com.docker.compose.project')!=old.installation.project or labels.get('com.docker.compose.service') not in ('web','backup'):raise LauncherError('A foreign task occupies the upgrade recovery name.')
            old.command('stop','--time','75',name,timeout=90)
        self.record(journal,'rolling_back');new.compose('stop','web','backup','nginx')
        atomic(root/'Config/active.json',journal['old_active']);atomic(root/'Config/launcher.json',journal['old_installation'])
        previous=journal.get('old_restore_journal')
        if previous is None:(root/'Config/restore-journal.json').unlink(missing_ok=True)
        else:atomic(root/'Config/restore-journal.json',previous)
        old.compose('up','-d','--wait','--pull','never','db','redis');self.start_services(old);old.wait_health();self.verify_credentials(journal)
        self.record(journal,'rolled_back');old.compose('up','-d','--no-build','--pull','never','--no-deps','backup');self.installation=Installation(root);return journal
