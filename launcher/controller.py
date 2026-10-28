"""One host controller for local start, ownership checks and recovery.
No source checkout, Python/Node CLI, registry login, Docker socket in web, or
normal-start network downloads. Installer payload preparation is separate.
"""
import contextlib,hashlib,http.client,json,os,socket,time
from pathlib import Path
from .storage import LauncherError,read,atomic,lock
from .installation import Installation
from .system import System,docker_path,platform_key
SERVICES={'db','redis','web','nginx','backup'}

class Controller:
    def __init__(self,installation,program,system=None,progress=None):
        self.installation=installation;self.program=Path(program);self.system=system or System();self.progress=progress or (lambda text:None)
        self.last_health_error=None
        self.release=read(self.program/'release.json')
        if not self.release or self.release.get('product')!='Financee_Offline' or self.release.get('format')!=1:raise LauncherError('Financee program files are incomplete. Use setup repair; customer data was not initialized.')
        for name,expected in self.release['files'].items():
            file=self.program/name
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=expected:raise LauncherError('Financee program files failed verification. Use setup repair.')
        self.docker=docker_path();self.context=installation.data['docker_context']
        self.env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','LD_LIBRARY_PATH','DYLD_LIBRARY_PATH')}
        self.env['BACKUP_DIR']=str(installation.backup_folder)
        self.base=[self.docker,'--context',self.context]
        self.compose_args=['compose','-p',installation.project,'--env-file',str(installation.root/'Config/compose.env'),'-f',str(self.program/'compose.yml')]
    def step(self,message):
        self.progress(message)
        log=self.installation.root/'Logs/launcher.log';log.parent.mkdir(exist_ok=True)
        if log.exists() and log.stat().st_size>256*1024:log.replace(log.with_suffix('.previous.log'))
        with log.open('a') as f:f.write(time.strftime('%Y-%m-%d %H:%M:%S')+' '+message+'\n')
    def command(self,*args,timeout=60):return self.system.execute([*self.base,*args],env=self.env,timeout=timeout)
    def compose(self,*args,timeout=120):return self.command(*self.compose_args,*args,timeout=timeout)
    def context_local(self):
        # Context metadata is local. Reject remote endpoints before docker info.
        endpoint=json.loads(self.system.execute([self.docker,'context','inspect',self.context,'--format','{{json .Endpoints.docker.Host}}'],env=self.env))
        if not (endpoint.startswith('unix://') or endpoint.startswith('npipe:////./pipe/')):raise LauncherError('Financee requires a local Docker connection. The selected connection is remote; no runtime command was sent to it.')
    def ensure_runtime(self):
        self.context_local()
        try:info=json.loads(self.command('info','--format','{{json .}}',timeout=8))
        except LauncherError:
            self.step('Starting the local Docker runtime. Complete any operating-system or Docker prompts.');self.system.start_docker()
            for _ in range(90):
                try:info=json.loads(self.command('info','--format','{{json .}}',timeout=3));break
                except (LauncherError,OSError,TimeoutError):time.sleep(1)
            else:raise LauncherError('Docker is not ready. Complete its startup prompts, then retry. Financee did not change or stop other projects.')
        _,arch=platform_key()
        actual={'aarch64':'arm64','x86_64':'amd64'}.get(info.get('Architecture'),info.get('Architecture'))
        if info.get('OSType')!='linux' or actual!=arch:raise LauncherError('The local runtime must use Linux containers for this computer’s architecture. Financee will not switch or replace your runtime automatically.')
        if self.release['architecture']!=arch:raise LauncherError('This Financee program payload is for another architecture. Run the matching installer.')
        self.command('compose','version','--short',timeout=8)
    def images_ready(self):
        for item in self.release['images']:
            try:value=json.loads(self.command('image','inspect',item['reference']))[0]
            except LauncherError:raise LauncherError('A required Financee runtime image is missing. Run setup repair/import the tested local payload. Normal startup never downloads images.')
            if value['Id']!=item['id'] or value['Architecture']!=self.release['architecture'] or value['Os']!='linux':raise LauncherError('A cached Financee image differs from the tested payload. Use setup repair before starting.')
    def ownership(self):
        ids=self.command('ps','-aq','--filter','label=com.docker.compose.project='+self.installation.project).split()
        if not ids:return
        values=json.loads(self.command('inspect',*ids))
        for value in values:
            labels=value.get('Config',{}).get('Labels',{}) or {};service=labels.get('com.docker.compose.service')
            if service not in SERVICES:raise LauncherError('The selected project contains an unexpected service. No containers were changed.')
            expected=self.release['service_images'][service]
            if value.get('Image')!=expected:raise LauncherError('This installation uses another runtime image version. Use the explicit update or repair workflow; the launcher will not upgrade it automatically.')
            mounts=value.get('Mounts',[])
            if service in ('web','backup') and not any(m.get('Destination')=='/customer' and Path(m.get('Source','')).resolve()==self.installation.root for m in mounts):raise LauncherError('This project belongs to another customer folder. No containers were changed.')
            if service=='db' and not any(m.get('Name')==self.installation.volume and m.get('Destination')=='/var/lib/postgresql/data' for m in mounts):raise LauncherError('This project uses a different database volume. No containers were changed.')
            if service=='nginx':
                bindings=value.get('HostConfig',{}).get('PortBindings',{}).get('80/tcp',[])
                if bindings!=[{'HostIp':'127.0.0.1','HostPort':str(self.installation.port)}]:raise LauncherError('The Financee web port ownership is inconsistent. No containers were changed.')
    def health(self):
        # This protocol is fixed loopback HTTP: no proxies, TLS CA discovery,
        # cookies, DNS, URL overrides or redirect-following in the frozen app.
        self.last_health_error=None
        try:
            with contextlib.closing(http.client.HTTPConnection('127.0.0.1',self.installation.port,timeout=2)) as conn:
                conn.request('GET','/health/');response=conn.getresponse()
                if response.status!=200:
                    self.last_health_error='Local HTTP status '+str(response.status);return None
                value=json.loads(response.read(65536))
                return value if isinstance(value,dict) else None
        except (OSError,ValueError,http.client.HTTPException) as exc:
            self.last_health_error=type(exc).__name__+': '+str(exc)
            return None
    def port_busy(self):
        with socket.socket() as sock:return sock.connect_ex(('127.0.0.1',self.installation.port))==0
    def check_port(self):
        health=self.health()
        if health and health.get('product')=='Financee_Offline' and health.get('installation_id')==self.installation.data['id']:return health
        if self.port_busy():raise LauncherError(f'Local port {self.installation.port} is occupied by another or unverified service. Nothing was stopped or opened. Close that service or repair the recorded port.'+(' Health check: '+self.last_health_error if self.last_health_error else ''))
        return None
    def volume_exists(self):
        try:self.command('volume','inspect',self.installation.volume);return True
        except LauncherError:return False
    def verify_storage(self):
        if (self.installation.data.get('initialized') or self.installation.data.get('volume_seen')) and not self.volume_exists():raise LauncherError('The recorded Financee database volume is missing. Startup was stopped to protect your data. Use Restore Backup or setup repair; a blank database was not created.')
    def tool(self,command,*args,archive=None):
        options=['run','--rm','--no-deps','--pull','never','-T']
        if archive:options+=['-v',str(Path(archive).resolve())+':/restore-input/archive.zip:ro']
        return self.compose(*options,'backup','python','-m','local.backups.cli',command,*args,timeout=None)
    def wait_health(self):
        active=read(self.installation.root/'Config/active.json')
        for _ in range(60):
            value=self.health()
            if value and value.get('product')=='Financee_Offline' and value.get('installation_id')==self.installation.data['id'] and value.get('generation')==active['generation'] and value.get('schema')==self.release['schema'] and value.get('build')==self.release['version']:return value
            time.sleep(.5)
        raise LauncherError('Financee startup verification failed. Data was preserved. Use the maintenance window or open local logs.')
    def _start(self):
        self.step('Checking the local runtime and Financee installation.');self.ensure_runtime();self.images_ready();self.ownership();self.verify_storage()
        healthy=self.check_port()
        if healthy and (healthy.get('build')!=self.release['version'] or healthy.get('schema')!=self.release['schema']):raise LauncherError('The running Financee version differs from this launcher. Use the matching launcher or explicit update workflow.')
        journal=read(self.installation.root/'Config/restore-journal.json',{})
        pending=journal.get('stage') not in (None,'committed','rolled_back','failed_before_switch')
        active=read(self.installation.root/'Config/active.json')
        if healthy and healthy.get('build')==self.release['version'] and healthy.get('generation')==active['generation'] and not pending:
            self.step('Financee is already running.');return healthy
        self.step('Starting only this Financee installation.');self.compose('stop','web','backup')
        self.compose('up','-d','--wait','--pull','never','db','redis')
        self.installation.data['volume_seen']=True;self.installation.save()
        self.step('Checking recovery state.');self.tool('recover')
        if not self.installation.data.get('initialized'):
            self.step('Preparing the empty local business database.')
            self.compose('run','--rm','--no-deps','--pull','never','-T','web','python','manage.py','migrate','--noinput',timeout=180)
        self.compose('run','--rm','--no-deps','--pull','never','-T','web','python','manage.py','collectstatic','--noinput',timeout=120)
        self.compose('up','-d','--no-build','--pull','never','web','nginx','backup')
        self.compose('exec','-T','nginx','nginx','-s','reload')
        value=self.wait_health();self.installation.data['initialized']=True;self.installation.save();self.step('Financee is ready.');return value
    def start(self,open_browser=True):
        with lock(self.installation.root/'Config/controller.lock'):
            value=self._start()
            url=self.installation.url+('/home/' if value['setup_complete'] else '/setup/')
            if open_browser:self.system.browser(url)
            return value
    def status(self):
        # Read-only: Refresh must not start Docker or change any container.
        self.context_local()
        try:self.command('info','--format','{{json .}}',timeout=8)
        except LauncherError:return 'Docker is unavailable. Use Start / Open Financee when you are ready.'
        self.ownership();self.verify_storage();healthy=self.check_port()
        if not healthy:return 'Financee is stopped. Data and backups are retained.'
        if healthy.get('build')!=self.release['version'] or healthy.get('schema')!=self.release['schema']:return 'A different Financee version is running. Use its matching launcher.'
        return 'Financee is running — '+('ready to open.' if healthy.get('setup_complete') else 'company setup is needed.')
    def stop(self):
        with lock(self.installation.root/'Config/controller.lock'):
            self.ensure_runtime();self.ownership();self.step('Stopping only Financee. Docker and other projects remain running.');self.compose('stop');self.step('Financee stopped. Your data and backups are retained.')
    def backup(self):
        with lock(self.installation.root/'Config/controller.lock'):
            value=self._start()
            if not value.get('setup_complete'):raise LauncherError('Complete company setup in Financee before creating a backup.')
            self.step('Creating and verifying a local ZIP backup.');result=self.tool('backup');self.step('Backup completed.');return result.strip()
    def inspect_backup(self,path):
        with lock(self.installation.root/'Config/controller.lock'):
            self.ensure_runtime();self.images_ready();self.ownership()
            self.step('Validating the selected backup.');return json.loads(self.tool('inspect','/restore-input/archive.zip',archive=path))
    def restore(self,path,digest):
        with lock(self.installation.root/'Config/controller.lock'):
            self.ensure_runtime();self.images_ready();self.ownership();self.check_port()
            info=json.loads(self.tool('inspect','/restore-input/archive.zip',archive=path))
            if info['archive_sha256']!=digest:raise LauncherError('The selected ZIP changed after inspection. Choose and confirm it again.')
            self.compose('up','-d','--wait','--pull','never','db','redis')
            output=self.compose('exec','-T','db','df','-Pk','/var/lib/postgresql/data')
            if int(output.splitlines()[-1].split()[3])*1024<info['database_bytes']*2+16*1024*1024:raise LauncherError('The database volume needs more free disk space for safe recovery.')
            self.step('Saving a rescue point and restoring a separate candidate.');self.compose('stop','backup','web')
            try:
                journal=json.loads(self.tool('restore','/restore-input/archive.zip','--confirm-sha',digest,archive=path))
                self.compose('up','-d','--no-build','--pull','never','--no-deps','web','nginx');self.compose('exec','-T','nginx','nginx','-s','reload')
                self.wait_health();self.tool('commit')
            except BaseException:
                self.compose('stop','web');self.tool('recover')
                self.compose('up','-d','--no-build','--pull','never','--no-deps','web','nginx');self.compose('exec','-T','nginx','nginx','-s','reload');self.wait_health();raise
            finally:self.compose('up','-d','--no-build','--pull','never','--no-deps','backup')
            self.installation.data.update(initialized=True,volume_seen=True);self.installation.save()
            self.step('Recovery verified. Sign in again. Previous data and rescue copies are retained.');return journal
    def set_backup_folder(self,chosen):
        chosen=Path(chosen).resolve(strict=True)
        if not chosen.is_dir():raise LauncherError('Choose an existing backup folder.')
        for forbidden in (self.installation.root/'Data',self.installation.root/'Config'):
            if chosen==forbidden or forbidden in chosen.parents:raise LauncherError('Keep backups outside the active Data and Config folders.')
        with lock(self.installation.root/'Config/controller.lock'):
            self.ensure_runtime();self.images_ready();self.ownership();self.verify_storage();self.check_port()
            location=self.installation.root/'Config/backup-location.json';previous=read(location)
            self.compose('stop','backup','web')
            try:
                atomic(location,{'format':1,'directory':str(chosen)});self.env['BACKUP_DIR']=str(chosen)
                self.compose('up','-d','--no-build','--pull','never','--no-deps','web','backup');self.compose('exec','-T','nginx','nginx','-s','reload');self.wait_health()
            except BaseException:
                if previous is None:location.unlink(missing_ok=True)
                else:atomic(location,previous)
                self.env['BACKUP_DIR']=str(self.installation.backup_folder)
                self.compose('up','-d','--no-build','--pull','never','--no-deps','web','backup');self.compose('exec','-T','nginx','nginx','-s','reload');raise
            self.step('Backup folder updated. Previous ZIPs remain in their former folder.')
    def backup_status(self):return read(self.installation.root/'Config/backup-status.json',{})
