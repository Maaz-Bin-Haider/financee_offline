#!/usr/bin/env python3
"""Developer review tooling only. The packaged customer launcher is Phase 5.
Never operates a source stack or removes a volume. No normal start pulls images.
"""
import argparse, json, os, secrets, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('command',choices=['init','build','up','stop','status','test','business','check'])
parser.add_argument('--stack',choices=['review','test'],default='review')
args=parser.parse_args()
if args.command in ('test','business') and args.stack!='test':parser.error('Automated tests require --stack test; review data is preserved.')
customer=ROOT/'.runtime'/args.stack
config=customer/'Config'
envfile=config/'runtime.env'
composefile=config/'compose.env'
project='financee_offline_'+args.stack
port=18766 if args.stack=='review' else 18767
if args.command=='init':
    for folder in ('Config','Data/media','Backups','Logs','Cache'):(customer/folder).mkdir(parents=True,exist_ok=True)
    if envfile.exists():
        if not composefile.exists():raise SystemExit('Existing runtime config is incomplete; repair it without replacing credentials.')
        print('Existing installation configuration preserved.');sys.exit(0)
    if composefile.exists():raise SystemExit('Partial existing configuration found; repair before initializing.')
    os.umask(0o077)
    text=f'SECRET_KEY={secrets.token_urlsafe(48)}\nDEBUG=False\nDB_NAME=financee_offline_{args.stack}\nDB_USER=financee_offline\nDB_PASSWORD={secrets.token_urlsafe(32)}\nALLOWED_HOSTS=localhost,127.0.0.1,testserver\n'
    envfile.write_text(text)
    composefile.write_text(text+f'HTTP_PORT={port}\nCUSTOMER_DIR={customer}\nRUNTIME_ENV_FILE={envfile}\n')
    print('Created isolated configuration; no database initialized.');sys.exit(0)
if not envfile.exists() or not composefile.exists():raise SystemExit('Run init first. Existing data will not be replaced.')
base=['docker','compose','-p',project,'--env-file',str(composefile),'-f',str(ROOT/'runtime/compose.yml')]
def run(*parts,**kwargs):return subprocess.run(base+list(parts),cwd=ROOT,check=True,**kwargs)
def app(*parts):return run('run','--rm','web',*parts)
if args.command=='build':run('build','web')
elif args.command=='up':
    # Docker refuses collisions; do not open a browser until product health is verified.
    run('up','-d','--wait','db','redis')
    app('python','manage.py','migrate','--noinput')
    app('python','manage.py','collectstatic','--noinput')
    run('up','-d','--no-build','--pull','never','web','nginx')
    url=f'http://127.0.0.1:{port}'
    for attempt in range(30):
        try:
            with urllib.request.urlopen(url+'/health/',timeout=2) as response: health=json.load(response)
            if health.get('product')!='Financee_Offline':raise SystemExit('Port belongs to another application.')
            print(url+('/' if health['setup_complete'] else '/setup/'));break
        except (OSError,ValueError):time.sleep(1)
    else:raise SystemExit('Local startup failed; inspect this stack logs.')
elif args.command=='stop':run('stop')
elif args.command=='status':run('ps')
elif args.command=='test':app('python','manage.py','test','local','--noinput','-v','2')
elif args.command=='business':
    app('python','tests/bootstrap_disposable.py')
    app('python','tests/suite/run_all.py')
elif args.command=='check':
    app('python','manage.py','check')
    app('python','manage.py','makemigrations','--check','--dry-run')
