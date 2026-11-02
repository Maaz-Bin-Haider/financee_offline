"""Native Windows setup entry; no hidden prerequisite or image installation."""
import argparse,os,sys
from pathlib import Path

def main():
    from launcher.storage import LauncherError
    from installer.windows_host import hold_program_mutex
    if os.name!='nt':raise LauncherError('Financee Windows Setup must run on native Windows x64.')
    hold_program_mutex()
    program=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'program'
    base=Path(os.environ['LOCALAPPDATA'])/'Financee Offline'
    preferences=base/'installation.json'
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-uninstall',action='store_true');args=parser.parse_args()
    if args.prepare_uninstall:
        from installer.controller import prepare_uninstall
        prepare_uninstall(program,preferences,base/'uninstall-preserved.json');return
    import tkinter as tk
    from installer.gui import SetupWindow
    root=tk.Tk()
    launcher=Path(sys.executable).parent.parent/'launcher/Financee Offline.exe'
    try:SetupWindow(root,program,base/'setup.json',preferences,launcher)
    except Exception as exc:
        from tkinter import messagebox
        messagebox.showerror('Financee Setup needs attention',str(exc),parent=root);root.destroy();return 1
    root.mainloop();return 0
if __name__=='__main__':
    try:sys.exit(main() or 0)
    except Exception as exc:
        # Uninstall must fail closed; a frozen windowed process has no stderr UI.
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(exc),'Financee Setup needs attention',0x10)
        sys.exit(1)
