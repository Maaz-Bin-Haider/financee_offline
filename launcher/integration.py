"""Explicit user-selected shortcuts/sign-in hooks; no automatic opt-in."""
import os,platform,plistlib,subprocess,sys
from pathlib import Path
from .storage import LauncherError

def app_path():
    exe=Path(sys.executable).resolve()
    if sys.platform=='darwin' and '.app/Contents/MacOS/' in str(exe):return exe.parents[2]
    return exe

def desktop_shortcut(installation,target=None,desktop=None):
    target=Path(target or app_path());desktop=Path(desktop or Path.home()/'Desktop')
    desktop.mkdir(parents=True,exist_ok=True)
    name='Financee Offline Development' if installation.data.get('development',False) else 'Financee Offline'
    if sys.platform=='darwin':
        path=desktop/(name+'.app')
        if path.is_symlink() and path.resolve()==target.resolve():return path
        if path.exists() or path.is_symlink():raise LauncherError('A different Financee shortcut already exists. It was preserved.')
        path.symlink_to(target,target_is_directory=True);return path
    if os.name=='nt':return windows_link(desktop/(name+'.lnk'),target)
    raise LauncherError('Desktop shortcuts require a supported Windows or macOS build.')

def windows_link(path,target):
    if path.exists():raise LauncherError('That shortcut already exists and was preserved.')
    env=dict(os.environ,FINANCEE_LINK=str(path),FINANCEE_TARGET=str(target))
    code="$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut($env:FINANCEE_LINK); $l.TargetPath=$env:FINANCEE_TARGET; $l.Save()"
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',code],env=env,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    return path

def signin(installation,enabled,target=None,agent_dir=None):
    target=Path(target or app_path());label='com.financee.offline.'+installation.data['id']
    if sys.platform=='darwin':
        folder=Path(agent_dir or Path.home()/'Library/LaunchAgents');path=folder/(label+'.plist')
        if enabled:
            folder.mkdir(parents=True,exist_ok=True)
            binary=target/'Contents/MacOS'/target.stem
            if not binary.is_file():raise LauncherError('Use a packaged Financee app before enabling sign-in startup.')
            with path.open('wb') as f:plistlib.dump({'Label':label,'ProgramArguments':[str(binary)],'RunAtLoad':True},f)
        elif path.exists():
            with path.open('rb') as f:record=plistlib.load(f)
            if record.get('Label')!=label:raise LauncherError('The sign-in entry did not match Financee and was preserved.')
            path.unlink()
    elif os.name=='nt':
        folder=Path(agent_dir or Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup');path=folder/(label+'.lnk')
        if enabled:folder.mkdir(parents=True,exist_ok=True);windows_link(path,target)
        elif path.exists():path.unlink()
    else:raise LauncherError('Sign-in startup requires a supported packaged build.')
    installation.data['start_at_signin']=bool(enabled);installation.save()
