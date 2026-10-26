"""Host-side portable backup-folder selection; runtime credentials stay separate."""
import json,os,tempfile
from pathlib import Path

def selected(customer,fallback):
    path=customer/'Config/backup-location.json'
    return Path(json.loads(path.read_text())['directory']) if path.exists() else Path(fallback)

def save(customer,folder):
    path=customer/'Config/backup-location.json'
    fd,tmp=tempfile.mkstemp(prefix='.backup-location-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump({'format':1,'directory':str(folder)},f);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
