"""Frozen native entry point; customer startup uses bundled Python/Tk only."""
import argparse,json,os,platform,subprocess,sys
from pathlib import Path

def main():
    if os.name=='nt':
        from installer.windows_host import hold_program_mutex
        hold_program_mutex()
    program=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'program'
    if not program.is_dir():program=Path(__file__).resolve().parents[1]/'.runtime/phase5-program'
    if '--bundle-check-output' in sys.argv:
        p=argparse.ArgumentParser();p.add_argument('--bundle-check-output',type=Path,required=True);a=p.parse_args()
        from installer.bundle_check import check
        check(program,a.bundle_check_output);return
    # Packaging CI can check the frozen stdlib without launching a GUI or Docker.
    if '--diagnostic-output' in sys.argv:
        p=argparse.ArgumentParser();p.add_argument('--diagnostic-output',type=Path,required=True);p.add_argument('--customer',type=Path,required=True);a=p.parse_args()
        from launcher.controller import Controller
        from launcher.installation import Installation
        from launcher.storage import atomic
        c=Controller(Installation(a.customer),program)
        atomic(a.diagnostic_output,dict(program_verified=True,architecture=platform.machine(),version=c.release['version'],health=c.health(),health_error=c.last_health_error))
        return
    if os.name=='nt' and getattr(sys,'frozen',False):
        from launcher.storage import read
        preferences=Path(os.environ['LOCALAPPDATA'])/'Financee Offline/installation.json'
        setup=Path(sys.executable).parent.parent/'setup/Financee Offline Setup.exe'
        if not read(preferences,{}).get('customer_directory') and setup.is_file():
            subprocess.Popen([str(setup)]);return
    import tkinter as tk
    from launcher.gui import Window
    root=tk.Tk();Window(root,program);root.mainloop()
if __name__=='__main__':main()
