import contextlib,json,os,tempfile,time
from pathlib import Path
class LauncherError(RuntimeError):pass

def read(path,default=None):
    try:return json.loads(Path(path).read_text())
    except FileNotFoundError:return default

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

@contextlib.contextmanager
def lock(path,timeout=0):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if os.name=='nt':
            import msvcrt
            if path.stat().st_size==0:f.write(b'0');f.flush()
            def acquire():f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            def acquire():fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        end=time.monotonic()+timeout
        while True:
            try:acquire();break
            except OSError:
                if time.monotonic()>=end:raise LauncherError('Another Financee operation is in progress. Return to its window or wait until it finishes.')
                time.sleep(.1)
        try:yield
        finally:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
