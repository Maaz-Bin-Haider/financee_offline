import concurrent.futures,contextlib,datetime,json,os,queue,socket,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from .controller import Controller
from .installation import Installation
from .storage import LauncherError,read,atomic,lock
from .system import System,docker_path
from . import integration

class Window:
    def __init__(self,root,program):
        self.root=root;self.program=Path(program);self.bootstrap=read(self.program/'bootstrap.json',{})
        self.events=queue.Queue();self.executor=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.controller=None;self.busy=False;self.window_lock=contextlib.ExitStack()
        title='Financee Offline'+(' — Development Review' if self.bootstrap.get('development') else '')
        root.title(title);root.geometry('780x740');root.minsize(740,680);root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.configure('Title.TLabel',font=('Helvetica',22,'bold'));style.configure('Heading.TLabel',font=('Helvetica',12,'bold'))
        frame=ttk.Frame(root,padding=22);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Financee Offline',style='Title.TLabel').pack(anchor='w')
        self.subtitle=tk.StringVar(value='Start your business app and keep recovery copies on your device.')
        ttk.Label(frame,textvariable=self.subtitle,wraplength=680).pack(anchor='w',pady=(5,14))
        self.location=tk.StringVar(value='Choose your Financee customer folder to begin.')
        ttk.Label(frame,textvariable=self.location,wraplength=680).pack(anchor='w')
        self.status=tk.StringVar(value='Ready to start');ttk.Label(frame,textvariable=self.status,style='Heading.TLabel',wraplength=680).pack(anchor='w',pady=(14,6))
        self.bar=ttk.Progressbar(frame,mode='indeterminate');self.bar.pack(fill='x',pady=(0,14))
        self.wizard=ttk.Frame(frame);self.wizard.pack(fill='x')
        ttk.Button(self.wizard,text='Open Existing Financee Folder',command=self.existing).pack(side='left',padx=(0,8))
        ttk.Button(self.wizard,text='Create New Empty Installation',command=self.new).pack(side='left')
        self.controls=ttk.Frame(frame);self.buttons=[]
        actions=[('Start / Open Financee',self.start),('Backup Now',self.backup),('Restore Backup…',self.restore),('Open Backups Folder',self.open_folder),('Choose Backup Folder…',self.choose_backups),('Stop Financee',self.stop),('Refresh Status',self.refresh_status),('Open Local Logs',self.logs),('Create Desktop Shortcut',self.shortcut)]
        for i,(label,command) in enumerate(actions):
            button=ttk.Button(self.controls,text=label,command=command);button.grid(row=i//3,column=i%3,sticky='ew',padx=4,pady=5);self.buttons.append(button)
        for col in range(3):self.controls.columnconfigure(col,weight=1)
        self.at_signin=tk.BooleanVar(value=False)
        self.signin_button=ttk.Checkbutton(frame,text='Start Financee when I sign in (optional)',variable=self.at_signin,command=self.signin)
        self.backup_text=tk.StringVar(value='No installation selected.');ttk.Label(frame,textvariable=self.backup_text,wraplength=680).pack(anchor='w',pady=12)
        self.activity=tk.Text(frame,height=6,wrap='word',state='disabled',font=('Helvetica',11));self.activity.pack(fill='both',expand=True)
        ttk.Label(frame,text='Closing this window or your browser keeps Financee running. Stop Financee affects only this installation.',wraplength=680).pack(anchor='w',pady=(12,0))
        if self.bootstrap.get('development'):ttk.Label(frame,text='Local development build • not notarized • installers/platform certification are separate review stages.',wraplength=680).pack(anchor='w',pady=(6,0))
        preference=self.bootstrap.get('preferences_path')
        if preference:self.preferences=Path(preference)
        elif sys.platform=='darwin':self.preferences=Path.home()/'Library/Application Support/Financee Offline/installation.json'
        else:self.preferences=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Financee Offline/installation.json'
        customer=self.bootstrap.get('default_customer') or read(self.preferences,{}).get('customer_directory')
        if customer:
            try:self.attach(Installation.adopt(customer,context=self.bootstrap.get('docker_context','desktop-linux' if sys.platform=='darwin' else 'default')))
            except Exception as exc:self.show_error(exc)
        root.after(100,self.poll)
        if self.controller and self.bootstrap.get('auto_start',True):root.after(300,self.start)
    def append(self,text):
        self.activity.configure(state='normal');self.activity.insert('end',text+'\n');self.activity.see('end');self.activity.configure(state='disabled')
    def attach(self,installation):
        try:self.window_lock.enter_context(lock(installation.root/'Config/launcher-window.lock'))
        except LauncherError:
            atomic(installation.root/'Cache/launcher-open-request.json',{'open':True});self.root.after(10,self.root.destroy);return
        installation.data['development']=bool(self.bootstrap.get('development'));installation.save()
        self.controller=Controller(installation,self.program,progress=lambda text:self.events.put(('progress',text)))
        atomic(self.preferences,{'format':1,'customer_directory':str(installation.root)})
        self.location.set(str(installation.root));self.wizard.pack_forget();self.controls.pack(fill='x',after=self.bar);self.signin_button.pack(anchor='w',after=self.controls,pady=(8,0));self.at_signin.set(installation.data.get('start_at_signin',False));self.refresh()
    def context(self):
        system=System();docker=docker_path()
        for name in ('desktop-linux','default') if sys.platform=='darwin' else ('default','desktop-linux'):
            try:
                endpoint=json.loads(system.execute([docker,'context','inspect',name,'--format','{{json .Endpoints.docker.Host}}']))
                if endpoint.startswith(('unix://','npipe:////./pipe/')):return name
            except Exception:pass
        raise LauncherError('No supported local Docker connection was found. Complete local runtime setup and retry.')
    def existing(self):
        path=filedialog.askdirectory(title='Choose the existing Financee customer folder')
        if path:
            try:self.attach(Installation.adopt(path,self.context()))
            except Exception as exc:self.show_error(exc)
    def new(self):
        path=filedialog.askdirectory(title='Choose an empty folder for Financee_Offline',initialdir=str(Path.home()/'Documents'))
        if not path:return
        try:
            context=self.context()
            for port in range(18766,18866):
                with socket.socket() as s:
                    try:s.bind(('127.0.0.1',port));break
                    except OSError:continue
            else:raise LauncherError('No local Financee port is available.')
            self.attach(Installation.create(path,port,context))
            if self.controller:self.start()
        except Exception as exc:self.show_error(exc)
    def task(self,fn,done=None):
        if self.busy:return
        self.busy=True;self.bar.start(12)
        for button in self.buttons:button.state(['disabled'])
        self.signin_button.state(['disabled'])
        def run():
            try:self.events.put(('done',(fn(),done)))
            except BaseException as exc:self.events.put(('error',exc))
        self.executor.submit(run)
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':self.status.set(value);self.append(value)
                else:
                    self.busy=False;self.bar.stop()
                    for b in self.buttons:b.state(['!disabled'])
                    self.signin_button.state(['!disabled'])
                    if kind=='error':self.show_error(value)
                    elif value[1]:value[1](value[0])
                    self.refresh()
        except queue.Empty:pass
        if self.controller and not self.busy:
            request=self.controller.installation.root/'Cache/launcher-open-request.json'
            if request.exists():request.unlink();self.start()
        try:self.root.after(150,self.poll)
        except tk.TclError:pass
    def show_error(self,error):
        message=str(error) or 'The local operation did not finish. Data was preserved.'
        self.status.set('Needs attention');self.append(message);messagebox.showerror('Financee needs attention',message,parent=self.root)
    def start(self):self.task(lambda:self.controller.start(),lambda value:self.status.set('Financee is ready — opened in your browser.'))
    def backup(self):self.task(lambda:self.controller.backup(),lambda value:messagebox.showinfo('Backup completed','The local ZIP was verified and saved.\n\n'+str(value),parent=self.root))
    def stop(self):self.task(lambda:self.controller.stop(),lambda value:self.status.set('Financee stopped. Data and backups are retained.'))
    def restore(self):
        path=filedialog.askopenfilename(title='Choose a Financee recovery ZIP',initialdir=str(self.controller.installation.backup_folder),filetypes=[('Financee ZIP','*.zip')])
        if not path:return
        def inspected(info):
            message=f"Company: {info['company']}\nRecovery point: {info['created_utc']}\nVersion: {info['app_version']}\nSHA-256: {info['archive_sha256']}\n\nReplace the active business with this recovery point?\nA healthy current business gets a rescue ZIP; previous data is retained. You will sign in again."
            if messagebox.askyesno('Confirm Restore Backup',message,icon='warning',default='no',parent=self.root):self.task(lambda:self.controller.restore(path,info['archive_sha256']),lambda value:messagebox.showinfo('Recovery completed','Recovery and startup checks passed. Open Financee and sign in again.',parent=self.root))
        self.task(lambda:self.controller.inspect_backup(path),inspected)
    def refresh_status(self):self.task(lambda:self.controller.status(),lambda value:self.status.set(value))
    def refresh(self):
        if not self.controller:return
        state=self.controller.backup_status();last=state.get('last_success') or {}
        details=['Backups: '+str(self.controller.installation.backup_folder),state.get('message','No local backup yet.')]
        if last:
            details+=['Last ZIP: '+last['filename'],'Completed: '+last['created_utc']]
            try:
                from zoneinfo import ZoneInfo
                zone=ZoneInfo(last['timezone']);today=datetime.datetime.now(zone).date()
                saved=datetime.datetime.fromisoformat(last['created_utc']).astimezone(zone).date()
                due='Due while running; catches up on next start.' if saved!=today or not (self.controller.installation.backup_folder/last['filename']).is_file() else 'Next due: '+str(today+datetime.timedelta(days=1))+' ('+last['timezone']+'), while running.'
                details.append(due)
            except (KeyError,ValueError):details.append('Daily backup runs while Financee is running; missed days catch up on start.')
        if state.get('last_error'):details.append('Needs attention: '+state['last_error'])
        self.backup_text.set('\n'.join(details))
    def open_folder(self):
        try:self.controller.system.folder(self.controller.installation.backup_folder)
        except Exception as exc:self.show_error(exc)
    def choose_backups(self):
        chosen=filedialog.askdirectory(title='Choose an existing backup folder',initialdir=str(self.controller.installation.backup_folder))
        if chosen:self.task(lambda:self.controller.set_backup_folder(chosen))
    def logs(self):self.controller.system.folder(self.controller.installation.root/'Logs')
    def shortcut(self):
        try:
            target=integration.desktop_shortcut(self.controller.installation)
            messagebox.showinfo('Desktop shortcut ready',str(target),parent=self.root)
        except Exception as exc:self.show_error(exc)
    def signin(self):
        try:integration.signin(self.controller.installation,self.at_signin.get())
        except Exception as exc:self.at_signin.set(not self.at_signin.get());self.show_error(exc)
    def close(self):
        if self.busy:messagebox.showinfo('Operation still running','Please wait for the current operation to finish before closing this window.',parent=self.root);return
        self.window_lock.close();self.executor.shutdown(wait=False);self.root.destroy()
