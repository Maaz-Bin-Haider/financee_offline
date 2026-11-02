"""Native Windows x64 development build. Requires a verified AMD64 exported
payload, native Python/Tk, pinned PyInstaller, and Inno Setup ISCC on Windows.
Never downloads prerequisites, images, build tools or publishes an artifact.
"""
import argparse,importlib.metadata,json,os,platform,shutil,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.payload import Payload,digest
from launcher.system import windows_native_arch

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--program',required=True,type=Path);p.add_argument('--archive',required=True,type=Path);p.add_argument('--iscc',required=True,type=Path);a=p.parse_args()
    if platform.system()!='Windows' or windows_native_arch() not in ('amd64','x86_64') or struct.calcsize('P')!=8 or os.environ.get('PROCESSOR_ARCHITEW6432','').upper()=='ARM64':raise SystemExit('Build on native Windows x64 with 64-bit Python; cross-freezing/emulation is not a Windows acceptance result.')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():raise SystemExit('Commit the reviewed source first; frozen build provenance requires a clean checkout.')
    payload=Payload(a.program)
    if payload.release['architecture']!='amd64':raise SystemExit('Windows requires a native Linux AMD64 payload.')
    payload.verify_archive(a.archive)
    import tkinter
    if importlib.metadata.version('pyinstaller')!='6.22.3':raise SystemExit('Use pinned Windows build requirements.')
    out=ROOT/'.runtime/phase6-windows';out.mkdir(parents=True,exist_ok=True)
    program=out/'program'
    if program.exists():shutil.rmtree(program)
    shutil.copytree(payload.program,program)
    notices=program/'notices/windows-builder';notices.mkdir(parents=True,exist_ok=True)
    for name in ('pyinstaller','altgraph','packaging','pyinstaller-hooks-contrib','setuptools','pefile','pywin32-ctypes'):
        dist=importlib.metadata.distribution(name)
        for file in dist.files or []:
            if any(part.lower().startswith(('license','copying','copyright')) for part in file.parts):
                src=dist.locate_file(file)
                if src.is_file():
                    target=notices/name/file.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
    # Official Python for Windows includes the Python and bundled Tcl/Tk licenses.
    base=Path(sys.base_prefix)
    found_python=list(base.glob('LICENSE*'));found_tk=list((base/'tcl').glob('**/license*'))
    if not found_python or not found_tk:raise SystemExit('Build requires Python and Tcl/Tk notices from its official native Windows distribution.')
    for index,file in enumerate(found_python+found_tk):
        if file.is_file():shutil.copyfile(file,notices/(str(index)+'-'+file.name))
    (program/'bootstrap.json').write_text(json.dumps({'development':True,'auto_start':True,'preferences_namespace':'Financee Offline 0.8 Development'},indent=2)+'\n')
    release=payload.release
    release.update(python=platform.python_version(),pyinstaller=importlib.metadata.version('pyinstaller'),build_host='windows-amd64',launcher_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    release['files']={str(f.relative_to(program)).replace('\\','/'):digest(f) for f in program.rglob('*') if f.is_file() and f.name not in ('release.json','delivery.json')}
    (program/'release.json').write_text(json.dumps(release,indent=2)+'\n')
    delivery=payload.delivery;delivery['release_sha256']=digest(program/'release.json')
    (program/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n')
    for name,entry in [('Financee Offline','launcher/entry.py'),('Financee Offline Setup','installer/entry.py')]:
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--noupx','--name',name,'--paths',str(ROOT),'--add-data',str(program)+os.pathsep+'program','--distpath',str(out/'frozen'),'--workpath',str(out/'work'/name),'--specpath',str(out/'spec'),str(ROOT/entry)],cwd=ROOT,check=True)
    checks=[]
    for name in ('Financee Offline','Financee Offline Setup'):
        output=out/(name.replace(' ','-')+'-bundle-check.json')
        subprocess.run([str(out/'frozen'/name/(name+'.exe')),'--bundle-check-output',str(output)],check=True,timeout=60)
        result=json.loads(output.read_text(encoding='utf-8'))
        if not (result['frozen'] and result['platform']=='Windows' and result['native_architecture']=='amd64' and result['program_files_verified'] and result['payload_architecture']=='amd64' and result['tls_context_loaded']):raise SystemExit('Native frozen-bundle check failed: '+name)
        checks.append(result)
    subprocess.run([str(a.iscc.resolve()),'/DStageDir='+str(out/'frozen'),'/DOutputDir='+str(out/'installer'),'/DProgramIdentity='+digest(program/'release.json'),str(ROOT/'installer/windows/financee.iss')],check=True)
    receipt={'setup_version':release['version'],'engine_version':release['version'],'architecture':'windows-amd64','source_revision':release['launcher_revision'],'development':True,'signed':False,'native_customer_acceptance':'pending','bundle_checks':checks,'compiler':{'path':str(a.iscc),'version':subprocess.run([str(a.iscc.resolve()),'/?'],capture_output=True,text=True).stdout.splitlines()[:3]},'installers':[{ 'filename':str(f),'sha256':digest(f),'bytes':f.stat().st_size} for f in (out/'installer').glob('*.exe')]}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
