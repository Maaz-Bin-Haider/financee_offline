"""Native Apple Silicon setup checks. No OS settings or shared runtime changes."""
import hashlib,json,os,platform,shutil,subprocess,tempfile,time,uuid
from pathlib import Path
from launcher.storage import LauncherError,atomic,lock,read

DOCKER_URL='https://docs.docker.com/desktop/setup/install/mac-install/'
SUPPORTED_MAJORS=(15,26,27)  # Current plus previous two; reviewed 2026-11-02.

def probe(system):
    if platform.system()!='Darwin':raise LauncherError('This setup requires an Apple Silicon Mac.')
    def number(key,default=None):
        try:return int(system.execute(['/usr/sbin/sysctl','-n',key]).strip())
        except (LauncherError,ValueError):
            if default is not None:return default
            raise LauncherError('macOS could not verify '+key+'. No settings were changed.')
    return {'system':'Darwin','architecture':platform.machine().lower(),'version':platform.mac_ver()[0],
            'ram_bytes':number('hw.memsize'),'hypervisor':number('kern.hv_support',0),
            'translated':number('sysctl.proc_translated',0)}

def assess(value):
    blockers=[]
    if value.get('system')!='Darwin' or value.get('architecture') not in ('arm64','aarch64') or value.get('translated'):
        blockers.append('Use the native Apple Silicon edition. Intel Macs and Rosetta execution are not supported.')
    try:major=int(value.get('version','0').split('.')[0])
    except ValueError:major=0
    if major not in SUPPORTED_MAJORS:blockers.append('This macOS version is outside the setup prerequisite policy. Review Docker’s current requirements before continuing.')
    if value.get('ram_bytes',0)<8*1024**3:blockers.append('Financee requires at least 8 GB of RAM; 16 GB is recommended.')
    if value.get('hypervisor')!=1:blockers.append('The native macOS virtualization capability is unavailable.')
    return {'ready':not blockers,'blockers':blockers,'certified':False,
            'message':'Prerequisites only. This build is not notarized or certified for customer distribution.'}

def local_context(system,docker,env):
    for context in ('desktop-linux','default'):
        try:endpoint=json.loads(system.execute([docker,'context','inspect',context,'--format','{{json .Endpoints.docker.Host}}'],env=env))
        except LauncherError:continue
        if isinstance(endpoint,str) and endpoint.startswith('unix://') and len(endpoint)>7:return context
    raise LauncherError('No local Mac Docker connection is available. Complete Docker setup and retry. Remote contexts were not contacted.')

def wait_runtime(system,docker,env,progress=lambda text:None):
    try:
        context=local_context(system,docker,env)
        system.execute([docker,'--context',context,'info','--format','{{json .}}'],env=env,timeout=5);return
    except LauncherError:pass
    progress('Starting Docker. Complete any macOS and Docker prompts.')
    system.start_docker()
    for _ in range(90):
        try:
            context=local_context(system,docker,env)
            system.execute([docker,'--context',context,'info','--format','{{json .}}'],env=env,timeout=3);return
        except LauncherError:time.sleep(1)
    raise LauncherError('Docker is not ready. Complete its prompts and retry; other projects were not stopped.')

def app_info(app):
    import plistlib
    with (Path(app)/'Contents/Info.plist').open('rb') as f:return plistlib.load(f)

def program_path(app):return Path(app)/'Contents/Resources/program'

def require_installed(app,home=None):
    app=Path(app).resolve();home=Path(home or Path.home()).resolve()
    if app.parent not in (Path('/Applications'),home/'Applications') or 'AppTranslocation' in app.parts:
        raise LauncherError('Install this app in Applications first. The app can do this without moving your business data.')
    return app

def program_lock(app,state_directory):
    return Path(state_directory)/'program-locks'/(hashlib.sha256(str(Path(app).resolve()).encode()).hexdigest()+'.lock')

def install_app(source,folder,state_directory,system):
    """Explicit copy/repair of an exact program build, separate from customer data.
    Stage and verify first; refuse foreign or different builds and running targets.
    """
    from .payload import digest
    source=Path(source).resolve();folder=Path(folder).expanduser().resolve()
    info=app_info(source);release=program_path(source)/'release.json'
    if not source.is_dir() or not source.name.endswith('.app') or not release.is_file():raise LauncherError('The source Mac app is incomplete.')
    identifier=info.get('CFBundleIdentifier','')
    if not identifier.startswith('com.financee.offline.'):raise LauncherError('This is not a Financee Mac app.')
    system.execute(['/usr/bin/codesign','--verify','--deep','--strict',str(source)])
    folder.mkdir(parents=True,exist_ok=True);target=folder/source.name
    if target==source:return target
    if target.is_symlink():raise LauncherError('Another application shortcut occupies that location and was preserved.')
    if target.exists():
        try:matches=app_info(target).get('CFBundleIdentifier')==identifier and digest(program_path(target)/'release.json')==digest(release)
        except (OSError,ValueError):matches=False
        if not matches:raise LauncherError('Another or different Financee app build already exists there. It was preserved; data-changing upgrades are a separate workflow.')
    with lock(program_lock(target,state_directory)):
        stage=None
        previous=folder/('.'+source.stem+'-previous-'+uuid.uuid4().hex+'.app')
        moved=False;published=False
        try:
            if shutil.disk_usage(folder).free<sum(f.stat().st_size for f in source.rglob('*') if f.is_file())+64*1024*1024:
                raise LauncherError('Not enough free space to stage the Mac app. Existing files were preserved.')
            if previous.exists():raise LauncherError('A temporary app repair location already exists. Existing files were preserved; retry.')
            stage=Path(tempfile.mkdtemp(prefix='.'+source.stem+'-staging-',suffix='.app',dir=folder))
            shutil.copytree(source,stage,symlinks=True,dirs_exist_ok=True)
            system.execute(['/usr/bin/codesign','--verify','--deep','--strict',str(stage)])
            if target.exists():target.rename(previous);moved=True
            stage.rename(target);published=True
            system.execute(['/usr/bin/codesign','--verify','--deep','--strict',str(target)])
            atomic(Path(state_directory)/'program-install.json',{'format':1,'product':'Financee_Offline','app':str(target),'identifier':identifier,'release_sha256':digest(release)})
        except BaseException:
            if published and target.exists():shutil.rmtree(target)
            if moved and previous.exists():previous.rename(target)
            raise
        finally:
            if stage is not None and stage.exists():shutil.rmtree(stage)
        if moved and previous.exists():shutil.rmtree(previous)
    return target
