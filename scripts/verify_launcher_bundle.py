"""Native development-bundle verification; no GUI, service mutation or downloads."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('app',type=Path);p.add_argument('--customer',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
app=a.app.resolve();customer=a.customer.resolve();rows=[];architectures=set();count=0
for file in sorted(app.rglob('*')):
    relative=str(file.relative_to(app))
    if file.is_symlink():
        target=os.readlink(file);assert not Path(target).is_absolute(),'External absolute symlink: '+relative
        assert file.resolve().is_relative_to(app),'Escaping bundle symlink: '+relative
        rows.append([relative,'symlink',target]);continue
    if not file.is_file():continue
    data=file.read_bytes();rows.append([relative,'file',hashlib.sha256(data).hexdigest()])
    if data[:4] in (b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'):
        arch=subprocess.check_output(['lipo','-archs',str(file)],text=True).strip();assert arch=='arm64',(relative,arch)
        architectures.add(arch);count+=1
        libs=subprocess.check_output(['otool','-L',str(file)],text=True).splitlines()[1:]
        for line in libs:
            name=line.strip().split(' (',1)[0]
            assert name.startswith(('@rpath/','@loader_path/','@executable_path/','/usr/lib/','/System/Library/')),(relative,name)
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
release=json.loads((app/'Contents/Resources/program/release.json').read_text())
for name,digest in release['files'].items():assert hashlib.sha256((app/'Contents/Resources/program'/name).read_bytes()).hexdigest()==digest
assert (app/'Contents/Resources/program/notices/tcl-tk/Tcl-9.0.4-license.terms').is_file()
assert (app/'Contents/Resources/program/notices/tcl-tk/Tk-9.0.4-license.terms').is_file()
with tempfile.TemporaryDirectory(prefix='Financee standalone proof ') as folder:
    dest=Path(folder)/app.name;shutil.copytree(app,dest,symlinks=True)
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','VIRTUAL_ENV','__PYVENV_LAUNCHER__','LD_LIBRARY_PATH','DYLD_LIBRARY_PATH')}
    env['PATH']='/usr/bin:/bin:/usr/sbin:/sbin'
    output=Path(folder)/'diagnostics.json'
    subprocess.run([str(dest/'Contents/MacOS'/dest.stem),'--diagnostic-output',str(output),'--customer',str(customer)],cwd=folder,env=env,check=True,timeout=30)
    result=json.loads(output.read_text());assert result['program_verified'] and result['health_error'] is None
    assert result['health']['product']=='Financee_Offline' and result['health']['build']==release['version']
    assert result['health']['installation_id']==json.loads((customer/'Config/launcher.json').read_text())['id']
receipt=dict(bundle_tree_sha256=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest(),mach_o_files=count,architectures=sorted(architectures),relocatable_library_paths=True,symlinks_stay_in_bundle=True,program_files_verified=True,codesign='ad-hoc signature verified; not notarized',copied_app_without_developer_path=True,frozen_health_verified=True,launcher_revision=release['launcher_revision'],version=release['version'])
a.output.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
