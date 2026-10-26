"""Maintenance API for the local controller; no Docker socket or cloud access."""
import argparse,json,signal,time
from .engine import Engine
from . import config
from .files import read,lock,Busy

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['backup','inspect','restore','recover','commit','worker','status'])
    p.add_argument('archive',nargs='?');p.add_argument('--confirm-sha');a=p.parse_args();engine=Engine()
    if a.command=='worker':
        def terminate(*args):raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,terminate)
        try:
            with lock(engine.control/'maintenance/operation.lock'):
                if engine.status().get('state')=='running':engine.update(state='error',message='The previous backup was interrupted. Completed ZIPs remain available; a new attempt will run if due.',last_error='Interrupted before verified publication.')
        except Busy:pass
        request=engine.control/'backup-request.json';retry_at=0
        try:
            while True:
                requested=read(request)
                if time.monotonic()>=retry_at:
                    try:
                        if requested or engine.due():
                            if config.pending(engine.root):raise Busy('Finish pending recovery before backups can resume.')
                            engine.backup(reason='manual' if requested else 'daily_or_catchup')
                            if requested and read(request)==requested:request.unlink(missing_ok=True)
                        retry_at=0
                    except Busy:retry_at=time.monotonic()+10
                    except Exception as exc:
                        engine.update(state='error',message='Automatic backup needs attention. Previous completed ZIPs are preserved.',last_error=engine.error(exc));retry_at=time.monotonic()+60
                time.sleep(5)
        except KeyboardInterrupt:return
    elif a.command=='backup':print(engine.backup())
    elif a.command=='inspect':print(json.dumps(engine.inspect(a.archive),indent=2))
    elif a.command=='restore':print(json.dumps(engine.restore(a.archive,a.confirm_sha),indent=2))
    elif a.command in ('recover','commit'):print(json.dumps(engine.recover(commit=a.command=='commit'),indent=2))
    else:print(json.dumps(engine.status(),indent=2))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(Engine.error(exc),flush=True);raise SystemExit(1)
