import os,platform,shutil,subprocess,webbrowser
from pathlib import Path
from .storage import LauncherError

def platform_key():
    system=platform.system();arch=windows_native_arch() if system=='Windows' else platform.machine().lower()
    if system=='Darwin' and arch in ('arm64','aarch64'):return 'macos-arm64','arm64'
    if system=='Windows' and arch in ('amd64','x86_64'):return 'windows-amd64','amd64'
    raise LauncherError('This edition targets Apple Silicon Macs and Windows 10/11 x64. This computer is not a supported launcher target.')

def windows_native_arch():
    if os.name!='nt':return platform.machine().lower()  # Off-host unit adapters.
    import ctypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.GetCurrentProcess.restype=ctypes.c_void_p
    api.IsWow64Process2.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ushort),ctypes.POINTER(ctypes.c_ushort)]
    api.IsWow64Process2.restype=ctypes.c_bool
    process=ctypes.c_ushort();native=ctypes.c_ushort()
    if not api.IsWow64Process2(api.GetCurrentProcess(),ctypes.byref(process),ctypes.byref(native)):
        raise LauncherError('Windows could not verify its native processor architecture.')
    return {0x8664:'amd64',0xAA64:'arm64',0x014c:'x86'}.get(native.value,'unknown')

def docker_path():
    candidates=[shutil.which('docker')]
    if platform.system()=='Darwin':candidates+=['/Applications/Docker.app/Contents/Resources/bin/docker','/usr/local/bin/docker']
    if platform.system()=='Windows':
        candidates+=[str(root/'resources/bin/docker.exe') for root in windows_docker_roots()]
    for value in candidates:
        if value and Path(value).is_file():return str(Path(value).resolve())
    raise LauncherError('Docker is not installed or its command is unavailable. Install the supported local runtime using Financee Setup, then retry. No other installation was changed.')

def windows_docker_roots():
    return [Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Programs/DockerDesktop',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Docker/Docker']

class System:
    def execute(self,args,env=None,timeout=60):
        flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        try:
            result=subprocess.run(list(map(str,args)),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,**flags)
        except subprocess.TimeoutExpired as exc:
            raise LauncherError('The local runtime did not respond in time. Check Docker and retry; no global shutdown was requested.') from exc
        except OSError as exc:
            raise LauncherError('The local runtime command could not be started. Check Docker and retry.') from exc
        if result.returncode:raise LauncherError((result.stderr or result.stdout or 'The local runtime command failed.')[-2000:])
        return result.stdout
    def start_docker(self):
        if platform.system()=='Darwin':subprocess.Popen(['open','-g','-a','Docker'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        elif platform.system()=='Windows':
            app=next((root/'Docker Desktop.exe' for root in windows_docker_roots() if (root/'Docker Desktop.exe').is_file()),None)
            if app is None:raise LauncherError('Open your supported local Docker runtime, then retry. Financee will not install or replace it automatically.')
            subprocess.Popen([str(app)],creationflags=subprocess.CREATE_NO_WINDOW)
        else:raise LauncherError('Start the supported local runtime, then retry.')
    def browser(self,url):
        if not webbrowser.open(url):raise LauncherError('Your browser could not be opened. Open '+url+' in your browser.')
    def folder(self,path):
        if not Path(path).is_dir():raise LauncherError('The backup folder is missing. Reconnect it or choose an existing folder.')
        if platform.system()=='Darwin':subprocess.Popen(['open',str(path)])
        elif os.name=='nt':os.startfile(path)
        else:subprocess.Popen(['xdg-open',str(path)])
