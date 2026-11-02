"""Mac installation and maintenance setup; all work stays off the Tk thread."""
import concurrent.futures,queue,tkinter as tk,webbrowser
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from launcher.storage import LauncherError
from launcher.system import System,docker_path
from launcher import integration
from .controller import Setup,prepare_uninstall
from . import macos_host as host

class MacSetupWindow:
    def __init__(self,root,program,state,preferences,app,payload_file,launch,program_state=None):
        self.root=root;self.app=Path(app);self.preferences=Path(preferences);self.payload_file=Path(payload_file);self.launch=launch
        self.events=queue.Queue();self.worker=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.busy=False;self.prepared=False;self.closed=False;self.handoff_started=False
        self.program_state=Path(program_state or Path(state).parent)
        self.setup=Setup(program,state,progress=lambda text:self.events.put(('progress',text)),context_selector=host.local_context)
        try:host.require_installed(app);self.installed=True
        except LauncherError:self.installed=False
        root.title('Financee Offline — Mac Setup');root.geometry('820x720');root.minsize(760,660);root.protocol('WM_DELETE_WINDOW',self.close)
        root.createcommand('tk::mac::Quit',self.close)
        body=ttk.Frame(root,padding=24);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Set up Financee Offline',font=('Helvetica',22,'bold')).pack(anchor='w')
        ttk.Label(body,text='Apple Silicon development build • not notarized. Your business data and backups stay separate from the app.',wraplength=750).pack(anchor='w',pady=10)
        self.status=tk.StringVar(value='Install this app in Applications first.' if not self.installed else 'Check this Mac, complete Docker setup, then verify the included runtime.')
        ttk.Label(body,textvariable=self.status,wraplength=750).pack(anchor='w',pady=8)
        ttk.Label(body,text=str(app),wraplength=750).pack(anchor='w')
        self.bar=ttk.Progressbar(body,mode='indeterminate');self.bar.pack(fill='x',pady=10)
        self.actions=[('Install to My Applications',self.copy_app),('Check This Mac',self.check),('Docker Download / Requirements',lambda:webbrowser.open(host.DOCKER_URL)),('Verify Included Runtime',self.prepare),('New Empty Business Folder…',lambda:self.select(False)),('Repair / Open Existing Folder…',lambda:self.select(True)),('Open Financee',self.open),('Prepare App Removal…',self.remove)]
        self.buttons=[]
        for offset in (0,3,5):
            row=ttk.Frame(body);row.pack(fill='x',pady=6)
            stop={0:3,3:5,5:8}[offset]
            for title,callback in self.actions[offset:stop]:
                button=ttk.Button(row,text=title,command=callback);button.pack(side='left',padx=(0,8));self.buttons.append(button)
        self.consent=tk.BooleanVar(value=False);self.desktop=tk.BooleanVar(value=False)
        self.consent_button=ttk.Checkbutton(body,text='I reviewed Docker’s requirements/licensing and completed its own setup prompts.',variable=self.consent);self.consent_button.pack(anchor='w',pady=7)
        self.desktop_button=ttk.Checkbutton(body,text='Create a desktop icon after setup (optional)',variable=self.desktop);self.desktop_button.pack(anchor='w')
        ttk.Label(body,text='Runtime images are included. Choose an empty folder for a new business; its Backups folder is the initial backup location. Choose existing only to reuse or repair your current business. No owner or sample data is installed for you.',wraplength=750).pack(anchor='w',pady=10)
        self.output=tk.Text(body,height=8,wrap='word',state='disabled');self.output.pack(fill='both',expand=True)
        menu=tk.Menu(root);root.configure(menu=menu);self.menu=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Setup',menu=self.menu)
        for title,callback in self.actions:self.menu.add_command(label=title,command=callback)
        self.menu.add_separator();self.menu.add_checkbutton(label='Docker Setup Reviewed',variable=self.consent);self.menu.add_checkbutton(label='Create Desktop Icon After Setup',variable=self.desktop)
        self.menu.add_separator();self.menu.add_command(label='Quit Setup',command=self.close)
        if self.setup.state:self.append('Saved setup: '+str(self.setup.state.get('phase'))+'\nBusiness folder: '+str(self.setup.state.get('customer_directory','not selected')))
        root.after(100,self.poll)
    def append(self,text):
        self.output.configure(state='normal');self.output.insert('end',text+'\n');self.output.see('end');self.output.configure(state='disabled')
    def task(self,work,done=None):
        if self.busy or self.closed:return
        self.busy=True;self.bar.start();self.consent_button.state(['disabled']);self.desktop_button.state(['disabled'])
        for button in self.buttons:button.state(['disabled'])
        for index in range(8):self.menu.entryconfigure(index,state='disabled')
        def run():
            try:self.events.put(('done',(work(),done)))
            except Exception as exc:self.events.put(('error',str(exc)))
        self.worker.submit(run)
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':self.status.set(value);self.append(value);continue
                self.busy=False;self.bar.stop();self.consent_button.state(['!disabled']);self.desktop_button.state(['!disabled'])
                for button in self.buttons:button.state(['!disabled'])
                for index in range(8):self.menu.entryconfigure(index,state='normal')
                if kind=='error':self.status.set('Needs attention');self.append(value);messagebox.showerror('Financee Setup needs attention',value,parent=self.root)
                elif value[1]:value[1](value[0])
        except queue.Empty:pass
        if self.closed:return
        try:self.root.after(150,self.poll)
        except tk.TclError:pass
    def copy_app(self):
        if self.installed:messagebox.showinfo('App is installed','This app is already in Applications. Continue with the Mac and runtime checks.',parent=self.root);return
        def done(target):
            if self.handoff_started:return
            self.handoff_started=True;self.launch(target,True);self.close()
        self.task(lambda:host.install_app(self.app,Path.home()/'Applications',self.program_state,System()),done)
    def check(self):
        def done(value):
            result=host.assess(value);self.append('\n'.join(result['blockers']+[result['message']]))
            self.status.set('Mac prerequisites passed. Review Docker setup, then verify the included runtime.' if result['ready'] else 'Complete the listed Mac requirements.')
        self.task(lambda:host.probe(System()),done)
    def require_installed(self):host.require_installed(self.app)
    def prepare(self):
        consent=self.consent.get()
        def work():
            self.require_installed();result=host.assess(host.probe(System()))
            if not result['ready']:raise LauncherError('\n'.join(result['blockers']))
            if not consent:raise LauncherError('Review Docker’s requirements and complete its own setup prompts, then select Docker Setup Reviewed.')
            wait=lambda text:self.events.put(('progress',text))
            host.wait_runtime(System(),docker_path(),self.setup.env,wait)
            return self.setup.prepare(self.setup.state_path.parent/'Cache',self.payload_file)
        def done(value):self.prepared=True;self.status.set('Included runtime verified. Choose a new empty business folder or repair the existing folder.')
        self.task(work,done)
    def select(self,existing):
        if not self.prepared:messagebox.showinfo('Verify runtime first','Choose Verify Included Runtime first. Previously verified files are reused.',parent=self.root);return
        chosen=filedialog.askdirectory(title='Choose your existing Financee business folder' if existing else 'Choose an empty folder for the new Financee business',initialdir=str(Path.home()/'Documents'))
        if not chosen:return
        make_shortcut=self.desktop.get()
        def done(installation):
            installation.data['development']=True;installation.save()
            self.append('Business folder: '+str(installation.root)+'\nBackups: '+str(installation.backup_folder))
            if make_shortcut:
                try:integration.desktop_shortcut(installation,target=self.app,name=self.app.stem)
                except LauncherError as exc:self.append(str(exc))
            self.status.set('Financee is ready. Open it to complete company/currency/owner setup or sign in.');self.open()
        self.task(lambda:self.setup.install(chosen,self.preferences,existing),done)
    def open(self):
        if self.handoff_started:return
        if not self.installed:
            messagebox.showinfo('Install app first','Install this app in Applications before opening your business.',parent=self.root);return
        if not self.preferences.is_file():messagebox.showinfo('Choose business folder','Finish setup or open the existing business folder first.',parent=self.root);return
        self.handoff_started=True;self.launch(self.app,False);self.close()
    def remove(self):
        if not messagebox.askyesno('Prepare App Removal','Stop this verified Financee installation and remove its optional sign-in entry? Business folders, backups and data volumes are retained. After this finishes, quit and move the app to Trash yourself.',parent=self.root):return
        self.task(lambda:prepare_uninstall(self.setup.payload.program,self.preferences,self.setup.state_path.parent/'removal-preserved.json'),lambda value:self.status.set('Financee stopped; data retained. Quit this app, then move it to Trash when ready.'))
    def close(self):
        if self.closed:return
        if self.busy:messagebox.showinfo('Operation running','Wait for the current operation to finish before closing.',parent=self.root);return
        self.closed=True;self.worker.shutdown(wait=True);self.root.quit();self.root.destroy()
