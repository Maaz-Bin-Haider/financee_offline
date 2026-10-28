import os,re,secrets,uuid
from pathlib import Path
from .storage import LauncherError,read,atomic

def env_values(path):
    values={}
    for line in Path(path).read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1)
            if value.startswith("'") and value.endswith("'"):value=value[1:-1].replace("\\'","'")
            values[key]=value
    return values

class Installation:
    def __init__(self,root):
        self.root=Path(root).expanduser().resolve();self.path=self.root/'Config/launcher.json'
        self.data=read(self.path)
        if not self.data or self.data.get('format')!=1 or self.data.get('product')!='Financee_Offline':raise LauncherError('This folder has no valid Financee installation. Choose an existing Financee customer folder or create a new empty one.')
        if Path(self.data.get('customer_directory','')).resolve()!=self.root:raise LauncherError('This customer folder was moved. Repair its recorded location before starting; no data was initialized.')
        if not re.fullmatch(r'financee_offline_[a-z0-9_]{1,40}',self.data['project']):raise LauncherError('The installation project name is invalid.')
        if not re.fullmatch(r'[0-9a-f]{32}',self.data['id']):raise LauncherError('The installation identity is invalid.')
        if not 1024<=self.data['port']<=65535:raise LauncherError('The local port is invalid.')
        if not (self.root/'Config/runtime.env').is_file() or not (self.root/'Config/compose.env').is_file():raise LauncherError('Runtime configuration is incomplete. It will not be replaced. Use recovery or setup repair.')
        values=env_values(self.root/'Config/compose.env')
        if values.get('CUSTOMER_DIR')!=str(self.root) or values.get('RUNTIME_ENV_FILE')!=str(self.root/'Config/runtime.env') or values.get('HTTP_PORT')!=str(self.port):raise LauncherError('Recorded runtime paths or port differ from this customer installation. Use setup repair; existing settings were preserved.')
        active=read(self.root/'Config/active.json')
        if not active or active.get('database_volume')!=self.volume or active.get('instance_id')!=self.data['id']:raise LauncherError('The active data identity does not match this installation. Use recovery; do not initialize a new database.')
    def save(self):atomic(self.path,self.data)
    @property
    def port(self):return self.data['port']
    @property
    def project(self):return self.data['project']
    @property
    def url(self):return f'http://127.0.0.1:{self.port}'
    @property
    def volume(self):return self.project+'_database'
    @property
    def backup_folder(self):
        selected=read(self.root/'Config/backup-location.json',{})
        return Path(selected.get('directory',str(self.root/'Backups')))
    @classmethod
    def adopt(cls,root,context='desktop-linux'):
        root=Path(root).expanduser().resolve()
        if (root/'Config/launcher.json').exists():return cls(root)
        values=env_values(root/'Config/compose.env');active=read(root/'Config/active.json')
        if not active or values.get('CUSTOMER_DIR')!=str(root) or values.get('RUNTIME_ENV_FILE')!=str(root/'Config/runtime.env'):raise LauncherError('Existing folder paths are incomplete or mismatched. No settings were changed.')
        volume=active.get('database_volume')
        if not volume or not volume.startswith('financee_offline_') or not volume.endswith('_database'):raise LauncherError('The existing Financee database volume is not recorded. Repair the installation before attaching it.')
        project=volume[:-len('_database')]
        atomic(root/'Config/launcher.json',{'format':1,'product':'Financee_Offline','id':active['instance_id'],'customer_directory':str(root),'project':project,'port':int(values['HTTP_PORT']),'docker_context':context,'initialized':True,'volume_seen':True,'start_at_signin':False})
        return cls(root)
    @classmethod
    def create(cls,root,port,context):
        root=Path(root).expanduser().resolve()
        if root.exists() and any(root.iterdir()):raise LauncherError('New-company setup requires an empty folder. Existing files were preserved; choose Open Existing instead.')
        if any(c in str(root) for c in ('\n','\r')):raise LauncherError('Choose a folder path without line breaks.')
        root.mkdir(parents=True,exist_ok=True)
        for folder in ('Config','Data/media','Backups','Logs','Cache'):(root/folder).mkdir(parents=True)
        token=uuid.uuid4().hex;project='financee_offline_'+token[:12]
        values={'SECRET_KEY':secrets.token_urlsafe(48),'DEBUG':'False','DB_NAME':project,'DB_USER':'financee_offline','DB_PASSWORD':secrets.token_urlsafe(32),'ALLOWED_HOSTS':'localhost,127.0.0.1,testserver'}
        body=''.join(k+'='+v+'\n' for k,v in values.items())
        quoted=lambda value: "'"+str(value).replace("'","\\'")+"'"
        for file,text in [('runtime.env',body),('compose.env',body+f'HTTP_PORT={port}\nCUSTOMER_DIR={quoted(root)}\nRUNTIME_ENV_FILE={quoted(root/"Config/runtime.env")}\n')]:
            path=root/'Config'/file
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:f.write(text);f.flush();os.fsync(f.fileno())
        atomic(root/'Config/active.json',{'format':1,'instance_id':token,'generation':'initial','database':project,'media':'Data/media','database_volume':project+'_database'})
        atomic(root/'Config/launcher.json',{'format':1,'product':'Financee_Offline','id':token,'customer_directory':str(root),'project':project,'port':port,'docker_context':context,'initialized':False,'volume_seen':False,'start_at_signin':False})
        return cls(root)
