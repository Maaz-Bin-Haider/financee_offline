"""Installer update mode; all verification and recovery run off the UI thread."""
import concurrent.futures,queue,sys,tkinter as tk
from pathlib import Path
from tkinter import filedialog,messagebox,simpledialog,ttk
from launcher.storage import LauncherError,atomic,read
from .upgrade import Upgrade

class UpgradeWindow:
    def __init__(self,root,program,archive,preferences,state,on_done=None):
        self.root=root;self.program=Path(program);self.archive=Path(archive) if archive else None;self.preferences=Path(preferences);self.state=Path(state);self.on_done=on_done
        self.worker=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.events=queue.Queue();self.busy=False;self.closed=False;self.prepared=None;self.upgrade=None
        root.title('Financee Offline — Manual Upgrade');root.geometry('820x700');root.minsize(760,650);root.protocol('WM_DELETE_WINDOW',self.close)
        if sys.platform=='darwin':root.createcommand('tk::mac::Quit',self.close)
        body=ttk.Frame(root,padding=24);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Upgrade your existing business',font=('Helvetica',22,'bold')).pack(anchor='w')
        ttk.Label(body,text='Keep the previous Financee app. This installer creates a verified rescue ZIP and upgrades a separate copy of your database and attachments. Your current data stays retained for recovery.',wraplength=750).pack(anchor='w',pady=12)
        selected=read(self.preferences,{})
        self.customer=tk.StringVar(value=selected.get('customer_directory',''))
        default=Path.home()/'Applications/Financee Offline Mac Development.app'
        self.previous=tk.StringVar(value=str(default) if sys.platform=='darwin' and default.exists() else '')
        for label,var,action in [('Business folder',self.customer,self.choose_customer),('Previous Financee app or program folder',self.previous,self.choose_previous)]:
            ttk.Label(body,text=label).pack(anchor='w',pady=(8,2));row=ttk.Frame(body);row.pack(fill='x');ttk.Entry(row,textvariable=var,state='readonly').pack(side='left',fill='x',expand=True);ttk.Button(row,text='Choose…',command=action).pack(side='left',padx=8)
        ttk.Label(body,text='Close the previous maintenance window before applying. If sign-in startup is enabled, turn it off in the previous app first and enable it in the new app after verification. Downgrades and schema changes outside this release’s reviewed policy are refused.',wraplength=750).pack(anchor='w',pady=12)
        self.status=tk.StringVar(value='Choose your business and previous app, then verify this upgrade.');ttk.Label(body,textvariable=self.status,wraplength=750).pack(anchor='w',pady=8)
        self.bar=ttk.Progressbar(body,mode='indeterminate');self.bar.pack(fill='x',pady=8)
        actions=[('Verify / Prepare Upgrade',self.verify),('Apply Verified Upgrade…',self.apply),('Recover Interrupted Upgrade',self.recover)]
        row=ttk.Frame(body);row.pack(fill='x',pady=8);self.buttons=[]
        for label,action in actions:
            b=ttk.Button(row,text=label,command=action);b.pack(side='left',padx=(0,8));self.buttons.append(b)
        self.output=tk.Text(body,height=12,wrap='word',state='disabled');self.output.pack(fill='both',expand=True)
        menu=tk.Menu(root);root.configure(menu=menu);self.menu=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Upgrade',menu=self.menu)
        for label,action in [('Choose Business Folder…',self.choose_customer),('Choose Previous Financee App…',self.choose_previous),*actions,('Close Upgrade Window',self.close)]:self.menu.add_command(label=label,command=action)
        root.after(100,self.poll)
    def append(self,text):
        self.output.configure(state='normal');self.output.insert('end',text+'\n');self.output.see('end');self.output.configure(state='disabled')
    def choose_customer(self):
        if self.busy:return
        path=filedialog.askdirectory(title='Choose the existing Financee business folder')
        if path:self.customer.set(path);self.prepared=None
    def choose_previous(self):
        if self.busy:return
        path=filedialog.askdirectory(title='Choose the previous Financee app or installed program folder')
        if path:self.previous.set(path);self.prepared=None
    def program_path(self):
        path=Path(self.previous.get())
        choices=[path/'Contents/Resources/program',path/'_internal/program',path/'launcher/_internal/program',path]
        for choice in choices:
            if (choice/'release.json').is_file():return choice
        raise LauncherError('Choose the previous installed Financee app or program folder.')
    def task(self,work,done):
        if self.busy or self.closed:return
        self.busy=True;self.bar.start()
        for b in self.buttons:b.state(['disabled'])
        def run():
            try:self.events.put(('done',(work(),done)))
            except Exception as exc:self.events.put(('error',str(exc)))
        self.worker.submit(run)
    def make_upgrade(self,previous=True):
        if not self.customer.get():raise LauncherError('Choose the existing business folder.')
        return Upgrade(self.customer.get(),self.program,self.program_path() if previous else None,progress=lambda t:self.events.put(('progress',t)))
    def verify(self):
        try:u=self.make_upgrade()
        except Exception as exc:messagebox.showerror('Choose the existing business',str(exc),parent=self.root);return
        def done(value):
            self.upgrade=u;self.prepared=value;self.status.set('Verified '+value['from_version']+' → '+value['to_version']+'. Apply when ready.')
            self.append('Business: '+value['customer_directory']+'\nProtected rescue folder: '+value['backup_directory'])
        self.task(lambda:u.prepare(Path(self.customer.get())/'Cache/upgrade-images'/u.payload.identity,self.archive),done)
    def apply(self):
        if not self.prepared:messagebox.showinfo('Verify first','Choose Verify / Prepare Upgrade first.',parent=self.root);return
        reviewed=self.prepared
        if not messagebox.askyesno('Upgrade this business?',reviewed['from_version']+' → '+reviewed['to_version']+'\n\n'+reviewed['customer_directory']+'\n\nA protected rescue ZIP and the previous database, attachments and runtime will be retained. Financee will be unavailable during verification. Continue?',parent=self.root):return
        text=simpledialog.askstring('Confirm manual upgrade','Type UPGRADE to apply the verified release to this business.',parent=self.root)
        if text!='UPGRADE':return
        self.prepared=None
        self.task(lambda:self.upgrade.apply(reviewed,reviewed['confirmation']),self.complete)
    def complete(self,journal):
        if journal['stage']!='committed':self.status.set('Previous release restored. Open the previous Financee app to continue.');return
        from .controller import Setup
        u=Upgrade(self.customer.get(),self.program)
        setup=Setup(self.program,self.state);setup.record('ready',customer_directory=str(u.installation.root),installation_id=u.installation.data['id'],url=u.installation.url)
        atomic(self.preferences,{'format':1,'customer_directory':str(u.installation.root)})
        self.status.set('Upgrade verified. Sign in again. Previous data, program and rescue copies are retained.')
        if self.on_done:self.on_done();self.close()
    def recover(self):
        try:u=self.make_upgrade(False)
        except Exception as exc:messagebox.showerror('Choose the existing business',str(exc),parent=self.root);return
        if not messagebox.askyesno('Recover interrupted upgrade?','Recover only the selected installation using its recorded previous runtime and data generation? All data, candidate generations and rescue ZIPs remain retained.',parent=self.root):return
        self.task(u.recover,self.complete)
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':self.status.set(value);self.append(value);continue
                self.busy=False;self.bar.stop()
                for b in self.buttons:b.state(['!disabled'])
                if kind=='error':self.status.set('Needs attention; retained data is available for recovery.');self.append(value);messagebox.showerror('Financee upgrade needs attention',value,parent=self.root)
                else:value[1](value[0])
        except queue.Empty:pass
        if not self.closed:self.root.after(150,self.poll)
    def close(self):
        if self.closed:return
        if self.busy:messagebox.showinfo('Upgrade running','Wait for the current operation. If interrupted, reopen this installer and choose Recover Interrupted Upgrade.',parent=self.root);return
        self.closed=True;self.worker.shutdown(wait=True);self.root.quit();self.root.destroy()
