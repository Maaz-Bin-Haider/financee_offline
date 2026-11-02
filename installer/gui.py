import concurrent.futures,queue,subprocess,sys,tkinter as tk,webbrowser
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from launcher.storage import LauncherError
from launcher.system import System,docker_path
from .controller import Setup
from .windows_host import probe,assess,request_wsl_install,DOCKER_URL,WSL_URL,wait_runtime

class SetupWindow:
    def __init__(self,root,program,state,preferences,launcher,on_upgrade=None):
        self.on_upgrade=on_upgrade
        self.root=root;self.preferences=preferences;self.launcher=launcher;self.queue=queue.Queue();self.worker=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.busy=False;self.snapshot=None;self.context_ready=False
        self.setup=Setup(program,state,progress=lambda t:self.queue.put(('progress',t)))
        root.title('Financee Offline Setup — Windows Development');root.geometry('800x710');root.minsize(760,650);root.protocol('WM_DELETE_WINDOW',self.close)
        body=ttk.Frame(root,padding=24);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Set up Financee Offline',font=('Segoe UI',22,'bold')).pack(anchor='w')
        ttk.Label(body,text='Windows x64 development build. Native Windows acceptance and signing are pending. Your customer data and backups stay separate from installed program files.',wraplength=730).pack(anchor='w',pady=12)
        self.status=tk.StringVar(value='Check this computer to begin. Saved setup steps resume after you reopen this window.')
        ttk.Label(body,textvariable=self.status,wraplength=730).pack(anchor='w',pady=8)
        self.bar=ttk.Progressbar(body,mode='indeterminate');self.bar.pack(fill='x')
        self.buttons=[];row=ttk.Frame(body);row.pack(fill='x',pady=8)
        def button(parent,text,command):
            b=ttk.Button(parent,text=text,command=command);b.pack(side='left',padx=(0,6));self.buttons.append(b)
        button(row,'Check / Resume',self.check);button(row,'Set up WSL…',self.wsl);button(row,'Update WSL…',lambda:self.wsl(True))
        button(row,'Docker download / requirements',lambda:webbrowser.open(DOCKER_URL));button(row,'Microsoft WSL guide',lambda:webbrowser.open(WSL_URL))
        self.consent=tk.BooleanVar(value=False)
        self.checkbutton=ttk.Checkbutton(body,text='I have reviewed Docker’s requirements and licensing and completed its own setup prompts.',variable=self.consent)
        self.checkbutton.pack(anchor='w',pady=8)
        ttk.Label(body,text='Setup never accepts third-party terms or restarts Windows for you. If asked to restart, save your work and reopen Financee Setup afterward. Existing Docker projects and WSL distributions are preserved.',wraplength=730).pack(anchor='w')
        row=ttk.Frame(body);row.pack(fill='x',pady=12)
        button(row,'Import Local Runtime File…',lambda:self.prepare(True));button(row,'Download Runtime',lambda:self.prepare(False))
        row=ttk.Frame(body);row.pack(fill='x',pady=8)
        button(row,'New Empty Business Folder…',lambda:self.select(False));button(row,'Repair / Open Existing Folder…',lambda:self.select(True));button(row,'Open Financee',self.open_launcher)
        ttk.Label(body,text='Keep backup copies on another drive. Uninstall preserves your business folder, backups and runtime data. Setup repair uses the same release; data-changing upgrades have a separate workflow.',wraplength=730).pack(anchor='w',pady=8)
        if on_upgrade:
            row=ttk.Frame(body);row.pack(fill='x');button(row,'Upgrade Existing Business…',self.upgrade)
        self.output=tk.Text(body,wrap='word',state='disabled',height=12);self.output.pack(fill='both',expand=True)
        if self.setup.state:self.append('Saved stage: '+str(self.setup.state.get('phase'))+'\nCustomer folder: '+str(self.setup.state.get('customer_directory','not selected')))
        root.after(100,self.poll);root.after(200,self.check)
    def append(self,text):
        self.output.configure(state='normal');self.output.insert('end',text+'\n');self.output.see('end');self.output.configure(state='disabled')
    def task(self,work,done=None):
        if self.busy:return
        self.busy=True;self.bar.start();self.checkbutton.state(['disabled'])
        for b in self.buttons:b.state(['disabled'])
        def run():
            try:self.queue.put(('done',(work(),done)))
            except Exception as e:self.queue.put(('error',str(e)))
        self.worker.submit(run)
    def poll(self):
        try:
            while True:
                kind,value=self.queue.get_nowait()
                if kind=='progress':self.status.set(value);self.append(value);continue
                self.busy=False;self.bar.stop();self.checkbutton.state(['!disabled'])
                for b in self.buttons:b.state(['!disabled'])
                if kind=='error':self.status.set('Needs attention');self.append(value);messagebox.showerror('Setup needs attention',value,parent=self.root)
                elif value[1]:value[1](value[0])
        except queue.Empty:pass
        self.root.after(150,self.poll)
    def check(self):
        def done(value):
            self.snapshot=value;result=assess(value);self.append('\n'.join(result['blockers']+result['actions']+[result['message']]))
            self.status.set('Prerequisite checks passed; review Docker setup, then import the runtime file.' if result['ready'] else 'Complete the listed prerequisites, then choose Check / Resume.')
        self.task(lambda:probe(System(),self.setup.payload.program/'prerequisites.ps1'),done)
    def wsl(self,update=False):
        if not self.snapshot:self.check();return
        if assess(self.snapshot)['blockers']:
            messagebox.showerror('Resolve computer requirements','\n'.join(assess(self.snapshot)['blockers']),parent=self.root);return
        if messagebox.askyesno('Update WSL' if update else 'Set up Windows Subsystem for Linux',('This requests a WSL update. ' if update else 'This requests WSL without a Linux distribution. ')+'Windows may ask for administrator permission and a restart. Existing distributions are retained. Continue?',parent=self.root):
            try:
                self.setup.prerequisites_requested(self.snapshot['boot_id']);request_wsl_install(update)
                self.status.set('Complete Windows prompts, restart manually if requested, then reopen Setup and choose Check / Resume.')
            except Exception as exc:messagebox.showerror('WSL setup',str(exc),parent=self.root)
    def prepare(self,local):
        # Probe again rather than trusting an old saved prerequisite result.
        path=filedialog.askopenfilename(title='Select the matching Financee runtime .tar',filetypes=[('Runtime archive','*.tar')]) if local else None
        if local and not path:return
        consent=self.consent.get()
        def work():
            current=probe(System(),self.setup.payload.program/'prerequisites.ps1');result=assess(current)
            if not result['ready']:raise LauncherError('\n'.join(result['blockers']+result['actions']))
            if not consent:raise LauncherError('Review the Docker requirements and complete its interactive setup prompts before importing the runtime.')
            docker=docker_path()
            # Starting Docker here is an explicit setup action; it never happens on status checks.
            wait_runtime(System(),docker,self.setup.env,lambda text:self.queue.put(('progress',text)))
            return self.setup.prepare(self.setup.state_path.parent/'Cache',path)
        def done(value):self.context_ready=True;self.status.set('Runtime files verified. Choose a new empty folder or repair the existing business folder.')
        self.task(work,done)
    def select(self,existing):
        if not self.context_ready:
            messagebox.showinfo('Verify runtime first','Choose Import Local Runtime File or Download Runtime first. Cached verified files are reused after restart.',parent=self.root);return
        path=filedialog.askdirectory(title='Choose existing Financee folder' if existing else 'Choose an empty Financee customer folder',initialdir=str(Path.home()/'Documents'))
        if path:self.task(lambda:self.setup.install(path,self.preferences,existing),lambda i:self.ready(i))
    def ready(self,installation):
        self.status.set('Financee is ready. Open Financee to complete company, currency and owner setup or sign in.')
        self.append('Customer folder: '+str(installation.root)+'\nBackups: '+str(installation.backup_folder));self.open_launcher()
    def open_launcher(self):
        if self.setup.state.get('phase')!='ready':
            messagebox.showinfo('Complete setup','Verify/import the runtime and choose your business folder first.',parent=self.root);return
        if not self.launcher.is_file():
            messagebox.showerror('Launcher missing','Repair the installed program files with the same setup release.',parent=self.root);return
        subprocess.Popen([str(self.launcher)])
    def upgrade(self):
        if self.busy:return
        self.on_upgrade();self.close()
    def close(self):
        if self.busy:messagebox.showinfo('Setup still running','Wait for verification or import to finish before closing.',parent=self.root);return
        self.worker.shutdown(wait=True);self.root.quit();self.root.destroy()
