"""Build a local, ad-hoc development launcher on its native OS/architecture.
No image downloads or customer records are bundled. Installer/release signing is
separate. Run with the isolated PyInstaller build interpreter.
"""
import argparse,hashlib,importlib.metadata,json,platform,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--customer',type=Path);p.add_argument('--name',default='Financee Offline Review');p.add_argument('--no-auto-start',action='store_true');a=p.parse_args()
if platform.system()!='Darwin' or platform.machine()!='arm64':raise SystemExit('This development recipe is native Apple Silicon only. Windows build recipe must run and be verified on Windows.')
program=ROOT/'.runtime/phase5-program';program.mkdir(exist_ok=True)
source=(ROOT/'runtime/compose.yml').read_text()
# The packaged controller starts cached images only; remove developer build paths.
source=source.replace('    build:\n      context: ..\n      dockerfile: runtime/Dockerfile\n','')
(program/'compose.yml').write_text(source);shutil.copyfile(ROOT/'runtime/nginx.conf',program/'nginx.conf')
images=[]
for ref in dict.fromkeys(line.split('image: ',1)[1].strip() for line in source.splitlines() if 'image: ' in line):
    info=json.loads(subprocess.check_output(['docker','image','inspect',ref]))[0]
    if info['Architecture']!='arm64' or info['Os']!='linux':raise SystemExit('Missing native ARM64 payload: '+ref)
    images.append({'reference':ref,'id':info['Id']})
notice=program/'notices';notice.mkdir(exist_ok=True)
shutil.copytree(ROOT/'launcher/notices',notice/'tcl-tk',dirs_exist_ok=True)
for name in ('pyinstaller','altgraph','macholib','packaging','pyinstaller-hooks-contrib','setuptools'):
    dist=importlib.metadata.distribution(name)
    for file in dist.files or []:
        if any(part.lower().startswith(('license','copying','copyright')) for part in file.parts):
            src=dist.locate_file(file)
            if src.is_file():
                target=notice/name/file.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
python_root=Path(sys.base_prefix)
for file in python_root.glob('**/LICENSE*'):
    if file.is_file() and 'site-packages' not in str(file):
        target=notice/'python-tk'/str(file.relative_to(python_root)).replace('/','_');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
files={str(f.relative_to(program)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(program.rglob('*')) if f.is_file() and f.name not in ('release.json','bootstrap.json')}
service_images={};service=None
for line in source.splitlines():
    if line.startswith('  ') and not line.startswith('    ') and line.strip().endswith(':'):service=line.strip()[:-1]
    if line.strip().startswith('image: '):service_images[service]=next(i['id'] for i in images if i['reference']==line.split('image: ',1)[1].strip())
service_images['backup']=service_images['web']
release={'service_images':service_images,'format':1,'product':'Financee_Offline','version':(ROOT/'VERSION').read_text().strip(),'schema':2,'architecture':'arm64','images':images,'files':files,'development':True,'build_host':'macos-arm64','python':platform.python_version(),'pyinstaller':importlib.metadata.version('pyinstaller')}
(program/'release.json').write_text(json.dumps(release,indent=2)+'\n')
bootstrap={'development':True,'auto_start':not a.no_auto_start,'docker_context':'desktop-linux'}
if a.customer:
    bootstrap.update(default_customer=str(a.customer.resolve()),preferences_path=str(a.customer.resolve()/'Config/desktop-preferences.json'))
(program/'bootstrap.json').write_text(json.dumps(bootstrap,indent=2)+'\n')
out=ROOT/'.runtime/phase5-launcher';out.mkdir(exist_ok=True)
args=[sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--noupx','--target-architecture','arm64','--osx-bundle-identifier','com.financee.offline.dev.'+a.name.lower().replace(' ','-'),'--name',a.name,'--paths',str(ROOT),'--add-data',str(program)+':program','--distpath',str(out),'--workpath',str(ROOT/'.runtime/phase5-build'/a.name),'--specpath',str(ROOT/'.runtime/phase5-build'),str(ROOT/'launcher/entry.py')]
subprocess.run(args,cwd=ROOT,check=True)
app=out/(a.name+'.app');print(app)
(app.parent/(a.name+'.build.json')).write_text(json.dumps(dict(release,app=str(app),customer_profile_embedded=bool(a.customer)),indent=2)+'\n')
