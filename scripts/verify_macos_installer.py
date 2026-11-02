"""Verify native app resources/signatures and a read-only DMG. Runs frozen
headless checks outside the checkout with Python/Tcl/developer paths removed.
No Docker mutation, browser, customer initialization or GUI input is performed.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.payload import Payload,digest

def verify_app(app,temporary):
    app=Path(app).resolve();subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    native=[];rows=[]
    for file in sorted(app.rglob('*')):
        relative=str(file.relative_to(app))
        if file.is_symlink():
            assert not Path(os.readlink(file)).is_absolute() and file.resolve().is_relative_to(app),relative
            rows.append([relative,'symlink',os.readlink(file)]);continue
        if not file.is_file():continue
        rows.append([relative,'file',digest(file)])
        with file.open('rb') as stream:magic=stream.read(4)
        if magic in (b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'):
            assert subprocess.check_output(['lipo','-archs',str(file)],text=True).strip()=='arm64',relative
            for line in subprocess.check_output(['otool','-L',str(file)],text=True).splitlines()[1:]:
                library=line.strip().split(' (',1)[0]
                assert library.startswith(('@rpath/','@loader_path/','@executable_path/','/usr/lib/','/System/Library/')),(relative,library)
            native.append(relative)
    payload=Payload(app/'Contents/Resources/program')
    env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','_PYI','DYLD_','LD_LIBRARY')) and k not in ('VIRTUAL_ENV','__PYVENV_LAUNCHER__','TCL_LIBRARY','TK_LIBRARY','SSL_CERT_FILE','SSL_CERT_DIR')}
    env['PATH']='/usr/bin:/bin:/usr/sbin:/sbin';env['PYINSTALLER_RESET_ENVIRONMENT']='1'
    bundle=Path(temporary)/'bundle.json';archive=Path(temporary)/'payload.json'
    subprocess.run([str(app/'Contents/MacOS'/app.stem),'--bundle-check-output',str(bundle),'--verify-payload-output',str(archive)],env=env,cwd=temporary,check=True,timeout=90)
    check=json.loads(bundle.read_text());image=json.loads(archive.read_text())
    assert check['frozen'] and check['platform']=='Darwin' and check['native_architecture']=='arm64' and check['payload_architecture']=='arm64' and check['program_files_verified'] and check['tls_context_loaded']
    assert image['verified'] and image['sha256']==payload.archive['sha256'] and image['images']==len(payload.release['images'])
    return {'bundle_tree_sha256':hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest(),'mach_o_files':len(native),'native_arm64_only':True,'symlinks_stay_in_app':True,'relocatable_library_paths':True,'bundle_check':check,'payload_check':image}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',type=Path,required=True);p.add_argument('--dmg',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='Financee Phase7 relocated ') as folder:
        copied=Path(folder)/a.app.name;shutil.copytree(a.app,copied,symlinks=True);copied_result=verify_app(copied,folder)
    subprocess.run(['hdiutil','verify',str(a.dmg)],check=True)
    with tempfile.TemporaryDirectory(prefix='Financee Phase7 mounted ') as folder:
        mount=Path(folder)/'mount';mount.mkdir()
        subprocess.run(['hdiutil','attach','-readonly','-nobrowse','-mountpoint',str(mount),str(a.dmg)],check=True,capture_output=True)
        try:
            assert (mount/'Applications').is_symlink() and os.readlink(mount/'Applications')=='/Applications'
            mounted_result=verify_app(mount/a.app.name,folder)
            assert copied_result['bundle_tree_sha256']==mounted_result['bundle_tree_sha256']
        finally:subprocess.run(['hdiutil','detach',str(mount)],check=True,capture_output=True)
    receipt={'source_revision':copied_result['bundle_check']['source_revision'],'copied_app_without_developer_environment':copied_result,'read_only_dmg_app_verified':mounted_result,'dmg_sha256':digest(a.dmg),'dmg_bytes':a.dmg.stat().st_size,'codesign':'verified','customer_installation_tested':False,'docker_modified':False,'notarization':'not claimed by this verification'}
    a.output.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
