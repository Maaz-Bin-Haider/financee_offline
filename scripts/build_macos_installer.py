"""Native Apple Silicon development app + self-contained DMG. No customer data,
Docker Desktop redistribution, notarization submission or publication. Optional
Developer ID signing requires an existing owner-provided identity; the default is
ad-hoc development signing. Use the isolated pinned build interpreter.
"""
import argparse,importlib.metadata,json,os,platform,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.payload import Payload,digest
NAME='Financee Offline Mac Development'

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--program',required=True,type=Path);parser.add_argument('--archive',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--identity');a=parser.parse_args()
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise SystemExit('Build on native Apple Silicon; no Intel/Rosetta cross-freeze.')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():raise SystemExit('Commit the reviewed source first so the build has exact source provenance.')
    if a.output.exists():raise SystemExit('Choose a new build output folder.')
    if a.identity:
        identities=subprocess.check_output(['security','find-identity','-v','-p','codesigning'],text=True)
        if not any('Developer ID Application:' in line and a.identity in line for line in identities.splitlines()):raise SystemExit('An existing valid Developer ID Application identity is required. No credentials were created or changed.')
    payload=Payload(a.program)
    if payload.release['architecture']!='arm64':raise SystemExit('Mac setup requires its native Linux ARM64 runtime payload.')
    payload.verify_archive(a.archive)
    import certifi,tkinter
    if importlib.metadata.version('certifi')!='2026.10.23' or importlib.metadata.version('pyinstaller')!='6.22.3':raise SystemExit('Use the pinned Phase 7 build dependencies.')
    if tkinter.Tcl().eval('info patchlevel')!='9.0.4':raise SystemExit('This build recipe requires its recorded native Tcl/Tk 9.0.4 runtime/notices.')
    a.output.mkdir(parents=True);program=a.output/'program';shutil.copytree(payload.program,program)
    notices=program/'notices';shutil.copytree(ROOT/'launcher/notices',notices/'tcl-tk',dirs_exist_ok=True)
    for name in ('pyinstaller','altgraph','macholib','packaging','pyinstaller-hooks-contrib','setuptools','certifi'):
        dist=importlib.metadata.distribution(name)
        for file in dist.files or []:
            if any(part.lower().startswith(('license','copying','copyright')) for part in file.parts):
                source=dist.locate_file(file)
                if source.is_file():
                    target=notices/name/file.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    for file in Path(sys.base_prefix).glob('**/LICENSE*'):
        if file.is_file() and 'site-packages' not in str(file):
            target=notices/'python'/str(file.relative_to(sys.base_prefix)).replace('/','_');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
    (program/'certs').mkdir(exist_ok=True);shutil.copyfile(certifi.where(),program/'certs/cacert.pem')
    bootstrap={'development':True,'auto_start':True,'docker_context':'desktop-linux','preferences_namespace':'Financee Offline Mac Development'}
    (program/'bootstrap.json').write_text(json.dumps(bootstrap,indent=2)+'\n',encoding='utf-8')
    release=payload.release;revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    release.update(setup_version='0.7.0-phase7',launcher_revision=revision,build_host='macos-arm64',python=platform.python_version(),pyinstaller=importlib.metadata.version('pyinstaller'),tcl='9.0.4',certifi=importlib.metadata.version('certifi'),https_ca_file='certs/cacert.pem',development=True)
    release['files']={str(f.relative_to(program)):digest(f) for f in sorted(program.rglob('*')) if f.is_file() and f.name not in ('release.json','delivery.json')}
    (program/'release.json').write_text(json.dumps(release,indent=2)+'\n',encoding='utf-8');delivery=payload.delivery;delivery['release_sha256']=digest(program/'release.json')
    (program/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n',encoding='utf-8')
    env=dict(os.environ,FINANCEE_MAC_PROGRAM=str(program.resolve()),FINANCEE_MAC_ARCHIVE=str(a.archive.resolve()),FINANCEE_MAC_SIGN_IDENTITY=a.identity or '')
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(a.output/'frozen'),'--workpath',str(a.output/'work'),str(ROOT/'installer/macos/financee.spec')],cwd=ROOT,env=env,check=True)
    app=a.output/'frozen'/(NAME+'.app');subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    stage=a.output/'dmg-contents';stage.mkdir();shutil.copytree(app,stage/app.name,symlinks=True);(stage/'Applications').symlink_to('/Applications',target_is_directory=True)
    shutil.copyfile(ROOT/'installer/macos/development-notice.txt',stage/'READ ME FIRST.txt')
    dmg=a.output/('Financee-Offline-Apple-Silicon-Development-'+revision[:7]+'.dmg')
    subprocess.run(['hdiutil','create','-volname',NAME,'-srcfolder',str(stage),'-format','UDZO','-ov',str(dmg)],check=True)
    if a.identity:subprocess.run(['codesign','--sign',a.identity,'--timestamp',str(dmg)],check=True)
    subprocess.run(['hdiutil','verify',str(dmg)],check=True)
    receipt={'setup_version':'0.7.0-phase7','engine_version':release['version'],'source_revision':revision,'platform':'macos-arm64','app':str(app.resolve()),'dmg':str(dmg.resolve()),'dmg_sha256':digest(dmg),'dmg_bytes':dmg.stat().st_size,'runtime_sha256':delivery['archive']['sha256'],'runtime_bytes':delivery['archive']['bytes'],'customer_profile_embedded':False,'image_archive_bundled':True,'signing':'Developer ID; notarization still pending' if a.identity else 'ad-hoc development; not Developer ID','notarized':False,'uploaded':False}
    (a.output/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
