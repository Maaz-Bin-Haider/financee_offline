"""Windows-only adapters, with an independently testable prerequisite policy."""
import base64,json,os,platform,re,time
from pathlib import Path
from launcher.storage import LauncherError

DOCKER_URL='https://docs.docker.com/desktop/setup/install/windows-install/'
WSL_URL='https://learn.microsoft.com/en-us/windows/wsl/install'
MUTEX='Local\\FinanceeOfflineProgram'
_mutex_handle=None

def hold_program_mutex():
    global _mutex_handle
    if os.name!='nt':return
    import ctypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    api.CreateMutexW.restype=ctypes.c_void_p
    _mutex_handle=api.CreateMutexW(None,False,MUTEX)
    if not _mutex_handle:raise LauncherError('Windows could not protect the running Financee program from replacement.')

def powershell():
    return str(Path(os.environ.get('WINDIR','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')

def probe(system,resource):
    if platform.system()!='Windows':raise LauncherError('This setup is for native Windows x64. No Windows settings were changed.')
    code=Path(resource).read_text(encoding='utf-8')
    encoded=base64.b64encode(code.encode('utf-16-le')).decode('ascii')
    from launcher.system import windows_native_arch
    value=json.loads(system.execute([powershell(),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],timeout=45))
    value['architecture']=windows_native_arch()
    return value

def assess(value):
    blockers=[];actions=[]
    if value.get('system')!='Windows' or value.get('architecture','').upper() not in ('AMD64','X86_64'):
        blockers.append('Use a native Windows x64 computer. Windows ARM and 32-bit Windows are not supported.')
    build=value.get('build',0)
    if value.get('product_type')!=1:blockers.append('Windows Server is not a supported customer target.')
    if build<22000:
        blockers.append('Windows 10 remains a required target, but its maintained runtime pair is not yet qualified. This development setup will not install an obsolete Docker Desktop or alter existing WSL distributions. Windows 10 release testing is still required.')
    elif build<22631:blockers.append('This Windows 11 build is below the current Docker prerequisite floor. Install a serviced Windows release before continuing.')
    if value.get('ram_bytes',0)<8*1024**3:blockers.append('At least 8 GB of RAM is required; 16 GB is recommended.')
    if not value.get('virtualization') or not value.get('slat'):
        blockers.append('Hardware virtualization/SLAT is unavailable. Enable virtualization in firmware or use a supported computer; Financee cannot change firmware settings.')
    version=tuple(map(int,re.findall(r'\d+',value.get('wsl_version') or '0.0.0')[:3]))
    if version<(2,1,5):actions.append('Install or update WSL to 2.1.5 or later, then reopen setup.')
    if value.get('features',{}).get('VirtualMachinePlatform')!=1:actions.append('Enable Windows Virtual Machine Platform using the WSL setup action.')
    if value.get('reboot_pending'):actions.append('Windows has a pending restart. Save your work, restart manually, then reopen Financee Setup.')
    return {'blockers':blockers,'actions':actions,'ready':not blockers and not actions,
            'certified':False,'message':'Development prerequisites only. Native Windows installation, servicing eligibility and offline reboot acceptance remain unverified.'}

def request_wsl_install(update=False):
    """Called only after a native yes/no consent prompt. Windows owns the UAC prompt.
    No distro, automatic reboot, terms acceptance or execution-policy bypass.
    """
    if os.name!='nt':raise LauncherError('WSL setup can only be requested on Windows.')
    import ctypes
    api=ctypes.WinDLL('shell32',use_last_error=True)
    api.ShellExecuteW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]
    api.ShellExecuteW.restype=ctypes.c_void_p
    exe=str(Path(os.environ['WINDIR'])/'System32/wsl.exe')
    result=api.ShellExecuteW(None,'runas',exe,'--update' if update else '--install --no-distribution',None,1)
    if not result or result<=32:raise LauncherError('WSL setup was cancelled or could not start. Existing distributions were preserved. You can retry or follow the Microsoft WSL guide.')

def local_context(system,docker,env):
    for context in ('desktop-linux','default'):
        try:endpoint=json.loads(system.execute([docker,'context','inspect',context,'--format','{{json .Endpoints.docker.Host}}'],env=env))
        except LauncherError:continue
        if isinstance(endpoint,str) and endpoint.startswith('npipe:////./pipe/'):return context
    raise LauncherError('No local Windows Docker connection is available. Complete Docker Desktop setup, select Linux containers, and retry. Remote contexts were not contacted.')


def wait_runtime(system,docker,env,progress=lambda text:None):
    # Only called by the explicit import/download button. Check first so a
    # compatible running engine can be reused without starting Desktop.
    try:
        context=local_context(system,docker,env)
        system.execute([docker,'--context',context,'info','--format','{{json .}}'],env=env,timeout=5)
        return
    except LauncherError:pass
    progress('Starting Docker. Complete its prompts, then wait for readiness.')
    system.start_docker()
    for attempt in range(90):
        try:
            context=local_context(system,docker,env)
            system.execute([docker,'--context',context,'info','--format','{{json .}}'],env=env,timeout=3)
            return
        except LauncherError:time.sleep(1)
    raise LauncherError('Docker is not ready. Complete its prompts and retry setup. Other projects were not stopped.')
