"""Single installed Mac app: setup first, then the existing maintenance window."""
import argparse,contextlib,os,subprocess,sys
from pathlib import Path

def launch(app,preferences_override=None,setup=False):
    args=[str(Path(app)/'Contents/MacOS'/Path(app).stem)]
    if preferences_override:args+=['--preferences',str(preferences_override)]
    if setup:args+=['--setup']
    subprocess.Popen(args,env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1'))

def main():
    from launcher.storage import LauncherError,read,atomic,lock
    from launcher.integration import app_path
    from installer.payload import Payload
    parser=argparse.ArgumentParser();parser.add_argument('--setup',action='store_true');parser.add_argument('--preferences',type=Path)
    parser.add_argument('--bundle-check-output',type=Path);parser.add_argument('--verify-payload-output',type=Path)
    parser.add_argument('--diagnostic-output',type=Path);parser.add_argument('--customer',type=Path);a=parser.parse_args()
    program=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'program';payload=Payload(program)
    archive=Path(getattr(sys,'_MEIPASS',program.parent))/'payload'/payload.archive['filename']
    if a.bundle_check_output:
        from installer.bundle_check import check
        check(program,a.bundle_check_output)
    if a.verify_payload_output:
        payload.verify_archive(archive);atomic(a.verify_payload_output,{'verified':True,'sha256':payload.archive['sha256'],'bytes':payload.archive['bytes'],'architecture':payload.release['architecture'],'images':len(payload.release['images']),'docker_modified':False})
    if a.bundle_check_output or a.verify_payload_output:return
    if a.diagnostic_output:
        if not a.customer:raise LauncherError('The diagnostic customer folder is required.')
        from launcher.controller import Controller
        from launcher.installation import Installation
        c=Controller(Installation(a.customer),program)
        atomic(a.diagnostic_output,{'program_verified':True,'health':c.health(),'health_error':c.last_health_error});return
    bootstrap=read(program/'bootstrap.json',{})
    if a.preferences and not bootstrap.get('development'):raise LauncherError('Private preference overrides are available in development builds only.')
    namespace=bootstrap.get('preferences_namespace','Financee Offline Mac Development')
    if Path(namespace).name!=namespace or namespace in ('.','..'):raise LauncherError('The app preference namespace is invalid.')
    base=Path.home()/'Library/Application Support'/namespace
    preferences=a.preferences or base/'installation.json'
    # Private test overrides keep every state/cache/receipt in their own folder.
    state_directory=preferences.parent if a.preferences else base
    import tkinter as tk
    from tkinter import messagebox
    from installer.macos_gui import MacSetupWindow
    from installer.macos_host import require_installed,program_lock
    from launcher.gui import Window
    app=app_path();root=tk.Tk()
    with contextlib.ExitStack() as lifetime:
        try:lifetime.enter_context(lock(program_lock(app,base),timeout=3))
        except LauncherError:
            messagebox.showinfo('Financee is already open','Return to the existing Financee window to continue.',parent=root);root.destroy();return
        callback=lambda target,setup=False:launch(target,a.preferences,setup)
        installed=True
        try:require_installed(app)
        except LauncherError:installed=False
        selected=read(preferences,{})
        if a.setup or not installed or not selected.get('customer_directory'):
            MacSetupWindow(root,program,state_directory/'setup.json',preferences,app,archive,callback,program_state=base)
        else:
            Window(root,program,preferences_path=preferences,on_setup=lambda:callback(app,True),desktop_name=app.stem)
        root.mainloop()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Headless build checks must fail without a blocking native alert.
        if not any(flag in sys.argv for flag in ('--bundle-check-output','--verify-payload-output','--diagnostic-output')):
            import tkinter as tk
            from tkinter import messagebox
            root=tk.Tk();root.withdraw();messagebox.showerror('Financee needs attention',str(exc),parent=root);root.destroy()
        raise
