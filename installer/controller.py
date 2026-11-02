"""Restartable explicit setup. Re-running verifies everything again; a saved
stage is an explanation, never permission to skip verification or reset data.
"""
import os,socket
from pathlib import Path
from launcher.controller import Controller
from launcher.installation import Installation
from launcher.storage import LauncherError,atomic,read,lock
from launcher.system import System,docker_path
from .payload import Payload
from .windows_host import local_context

class Setup:
    def __init__(self,program,state,system=None,progress=None,context_selector=None):
        self.payload=Payload(program);self.state_path=Path(state);self.system=system or System();self.progress=progress or (lambda text:None)
        self.select_context=context_selector or local_context
        self.state=read(self.state_path,{})
        if self.state and (self.state.get('format')!=1 or self.state.get('product')!='Financee_Offline'):
            raise LauncherError('The saved setup state is invalid. Existing customer files were preserved.')
        if self.state and self.state.get('delivery')!=self.payload.identity:
            raise LauncherError('This setup state belongs to another release. Manual upgrades are a separate workflow; customer files were preserved.')
        self.env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','LD_LIBRARY_PATH','DYLD_LIBRARY_PATH')}
    def record(self,phase,**values):
        self.state.update(format=1,product='Financee_Offline',delivery=self.payload.identity,phase=phase,**values);atomic(self.state_path,self.state)
    def prerequisites_requested(self,boot_id):
        with lock(self.state_path.with_suffix('.lock')):self.record('awaiting_prerequisites',boot_id=boot_id)
    def prepare(self,cache,local=None):
        with lock(self.state_path.with_suffix('.lock')):
            self.record('verifying_payload',cache=str(Path(cache).resolve()))
            path=self.payload.acquire(cache,local,self.progress)
            docker=docker_path();context=self.select_context(self.system,docker,self.env)
            self.payload.import_images(path,self.system,docker,context,self.env,self.progress)
            self.record('images_ready',context=context,archive=str(path));return context
    def install(self,customer,preferences,existing=False):
        with lock(self.state_path.with_suffix('.lock')):
            # Resume always revalidates the cached bytes, daemon, architecture and images.
            archive=self.state.get('archive')
            if not archive or not self.payload.verified(archive):raise LauncherError('Complete runtime payload verification/import before selecting the business folder.')
            docker=docker_path();context=self.select_context(self.system,docker,self.env)
            runtime_ids=self.payload.import_images(archive,self.system,docker,context,self.env,self.progress)
            root=Path(customer).expanduser().resolve()
            previous=self.state.get('customer_directory')
            if previous and Path(previous).resolve()!=root:
                raise LauncherError('Setup already selected another customer folder. Reopen that folder to resume; no replacement business was created.')
            if not existing and not (root/'Config/launcher.json').exists() and root.exists() and any(root.iterdir()):
                raise LauncherError('New-company setup requires an empty folder. Choose Open Existing for an existing Financee business.')
            self.record('configuring',customer_directory=str(root))
            if existing or (root/'Config/launcher.json').exists():
                installation=Installation.adopt(root,context)
                if installation.data['docker_context']!=context:raise LauncherError('The recorded installation uses another local connection. Use its matching runtime; setup did not replace the recorded context.')
            else:
                for port in range(18766,18866):
                    with socket.socket() as sock:
                        try:sock.bind(('127.0.0.1',port));break
                        except OSError:continue
                else:raise LauncherError('No local Financee port is available. No installation was initialized.')
                installation=Installation.create(root,port,context)
            release_id=self.payload.delivery['release_sha256']
            if installation.data.get('installed_program') not in (None,release_id):
                raise LauncherError('This customer installation belongs to another program release. Use its launcher or the explicit upgrade workflow.')
            installation.data['runtime_images']={'release_sha256':release_id,'ids':runtime_ids};installation.save()
            c=Controller(installation,self.payload.program,self.system,self.progress)
            c.start(open_browser=False)
            installation.data['installed_program']=release_id;installation.save()
            atomic(preferences,{'format':1,'customer_directory':str(root)})
            self.record('ready',installation_id=installation.data['id'],url=installation.url)
            return installation

def prepare_uninstall(program,preferences,receipt,system=None):
    """Stop only a verified installation, remove its own sign-in hook, retain all
    customer files/volumes/images. Inno removes only its recorded program files.
    """
    from launcher import integration
    selection=read(preferences,{})
    if not selection.get('customer_directory'):
        pending=read(Path(preferences).parent/'setup.json',{})
        if pending.get('customer_directory'):
            payload=Payload(program)
            if pending.get('product')!='Financee_Offline' or pending.get('format')!=1 or pending.get('delivery')!=payload.identity:
                raise LauncherError('Interrupted setup belongs to another or invalid release. Repair it before removing program files.')
            selection=pending
    if selection.get('customer_directory'):
        installation=Installation(selection['customer_directory'])
        with lock(installation.root/'Config/launcher-window.lock'):
            controller=Controller(installation,program,system)
            controller.stop()  # Refuse removal if stop/ownership cannot be verified.
            if installation.data.get('start_at_signin'):integration.signin(installation,False)
        root=str(installation.root)
    else:root=None
    atomic(receipt,{'format':1,'product':'Financee_Offline','program_removal_ready':True,'customer_directory':root,'customer_data_retained':True,'runtime_retained':True})
