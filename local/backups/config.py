import os,re,uuid
from pathlib import Path
from .files import read,atomic,lock
ROOT=Path(__file__).resolve().parents[2]
VERSION=(ROOT/'VERSION').read_text().strip()

def customer_root():return Path(os.environ.get('OFFLINE_CUSTOMER_ROOT','/customer'))
def backup_dir():return Path(os.environ.get('OFFLINE_BACKUP_DIR','/backups'))
def pending(root):return read(root/'Config/restore-journal.json',{}).get('stage') not in (None,'committed','rolled_back','failed_before_switch')
def active(root=None):
    root=root or customer_root();path=root/'Config/active.json'
    with lock(root/'Config/maintenance/config.lock',timeout=10):
        value=read(path)
        if value is None:
            value={'format':1,'instance_id':uuid.uuid4().hex,'generation':'initial','database':os.environ['DB_NAME'],'media':'Data/media','database_volume':os.environ.get('OFFLINE_DATABASE_VOLUME')}
            atomic(path,value)
    if not value.get('database_volume') and os.environ.get('OFFLINE_DATABASE_VOLUME'):
        value['database_volume']=os.environ['OFFLINE_DATABASE_VOLUME'];atomic(path,value)
    if value.get('format')!=1 or not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,62}',value.get('database','')):raise ValueError('Invalid active database configuration.')
    if not re.fullmatch(r'[0-9a-f]{32}',value.get('instance_id','')) or not re.fullmatch(r'initial|[0-9a-f]{32}',value.get('generation','')):raise ValueError('Invalid installation/generation identity.')
    media=Path(value.get('media',''))
    if not media.parts or media.is_absolute() or any(x in ('.','..') for x in media.parts) or media.parts[0]!='Data':raise ValueError('Invalid active media configuration.')
    return value
