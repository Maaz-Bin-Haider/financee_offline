"""Frozen native entry point; customer startup uses bundled Python/Tk only."""
import argparse,json,platform,sys
from pathlib import Path

def main():
    program=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'program'
    if not program.is_dir():program=Path(__file__).resolve().parents[1]/'.runtime/phase5-program'
    # Packaging CI can check the frozen stdlib without launching a GUI or Docker.
    if '--diagnostic-output' in sys.argv:
        p=argparse.ArgumentParser();p.add_argument('--diagnostic-output',type=Path,required=True);p.add_argument('--customer',type=Path,required=True);a=p.parse_args()
        from launcher.controller import Controller
        from launcher.installation import Installation
        from launcher.storage import atomic
        c=Controller(Installation(a.customer),program)
        atomic(a.diagnostic_output,dict(program_verified=True,architecture=platform.machine(),version=c.release['version'],health=c.health(),health_error=c.last_health_error))
        return
    import tkinter as tk
    from launcher.gui import Window
    root=tk.Tk();Window(root,program);root.mainloop()
if __name__=='__main__':main()
