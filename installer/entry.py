"""Native Windows setup entry; no hidden prerequisite or image installation."""
import argparse,os,sys,subprocess
from pathlib import Path

def main():
    from launcher.storage import LauncherError
    from installer.windows_host import hold_program_mutex
    if os.name!='nt':raise LauncherError('Financee Windows Setup must run on native Windows x64.')
    hold_program_mutex()
    program=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'program'
    from launcher.storage import read
    namespace=read(program/'bootstrap.json',{}).get('preferences_namespace','Financee Offline')
    if Path(namespace).name!=namespace:raise LauncherError('Invalid preferences namespace.')
    base=Path(os.environ['LOCALAPPDATA'])/namespace
    preferences=base/'installation.json'
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-uninstall',action='store_true');parser.add_argument('--upgrade',action='store_true');parser.add_argument('--bundle-check-output',type=Path);args=parser.parse_args()
    if args.bundle_check_output:
        from installer.bundle_check import check
        check(program,args.bundle_check_output);return
    if args.prepare_uninstall:
        from installer.controller import prepare_uninstall
        prepare_uninstall(program,preferences,base/'uninstall-preserved.json');return
    import tkinter as tk
    from installer.gui import SetupWindow
    root=tk.Tk()
    launcher=Path(sys.executable).parent.parent/'launcher/Financee Offline.exe'
    handoff=[]
    try:
        from installer.upgrade import pending
        selected=read(preferences,{})
        if args.upgrade or (selected.get('customer_directory') and pending(selected['customer_directory'])):
            from installer.upgrade_gui import UpgradeWindow
            UpgradeWindow(root,program,None,preferences,base/'setup.json',on_done=lambda:handoff.append('launcher'))
        else:SetupWindow(root,program,base/'setup.json',preferences,launcher,on_upgrade=lambda:handoff.append('upgrade'))
    except Exception as exc:
        from tkinter import messagebox
        messagebox.showerror('Financee Setup needs attention',str(exc),parent=root);root.destroy();return 1
    root.mainloop()
    if handoff:subprocess.Popen([str(launcher)] if handoff[-1]=='launcher' else [sys.executable,'--upgrade'])
    return 0
if __name__=='__main__':
    try:sys.exit(main() or 0)
    except Exception as exc:
        # Uninstall must fail closed; a frozen windowed process has no stderr UI.
        if os.name=='nt' and '--bundle-check-output' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(exc),'Financee Setup needs attention',0x10)
        sys.exit(1)
