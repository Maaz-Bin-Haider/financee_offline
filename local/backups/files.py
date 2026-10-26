import contextlib,fcntl,json,os,time,uuid
from pathlib import Path
class Busy(RuntimeError):pass

def read(path,default=None):
    try:return json.loads(Path(path).read_text())
    except FileNotFoundError:return default

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    try:
        with tmp.open('x') as f:
            os.chmod(tmp,0o600);json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path);syncdir(path.parent)
    finally:tmp.unlink(missing_ok=True)

def syncdir(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

@contextlib.contextmanager
def lock(path,exclusive=True,timeout=0):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    f=path.open('a+');end=time.monotonic()+timeout
    try:
        while True:
            try:fcntl.flock(f, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=end:raise Busy('Another operation is in progress. Try again shortly.')
                time.sleep(.05)
        yield
    finally:f.close()

@contextlib.contextmanager
def pause(root,timeout=30):
    folder=Path(root)/'Config/maintenance'
    with lock(folder/'intent.lock',timeout=timeout),lock(folder/'gate.lock',timeout=timeout):yield
