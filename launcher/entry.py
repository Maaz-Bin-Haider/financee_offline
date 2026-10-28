"""Frozen native entry point; customer startup imports only bundled stdlib/Tk."""
import sys
from pathlib import Path
from launcher.gui import Window
import tkinter as tk

def main():
    program=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'program'
    if not program.is_dir():program=Path(__file__).resolve().parents[1]/'.runtime/phase5-program'
    root=tk.Tk();Window(root,program);root.mainloop()
if __name__=='__main__':main()
