"""Collect only the unsigned build, matching runtime archive and public receipts.
No release, network upload, source deployment, data or credentials are included.
"""
import argparse,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.payload import Payload,digest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=ROOT/'.runtime/phase6-windows');p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    payload=Payload(a.build/'program');payload.verify_archive(a.archive)
    receipt=json.loads((a.build/'build-receipt.json').read_text(encoding='utf-8'))
    if receipt['signed'] or receipt['native_customer_acceptance']!='pending':raise SystemExit('This packager is for unsigned unaccepted development builds only.')
    if a.output.exists():raise SystemExit('Choose a new output directory.')
    a.output.mkdir(parents=True)
    for image in receipt['installers']:
        src=Path(image['filename'])
        if digest(src)!=image['sha256']:raise SystemExit('Installer differs from its build receipt.')
        shutil.copyfile(src,a.output/src.name)
    shutil.copyfile(a.archive,a.output/payload.archive['filename'])
    shutil.copyfile(a.build/'build-receipt.json',a.output/'build-receipt.json')
    shutil.copyfile(a.build/'program/release.json',a.output/'program-release.json')
    shutil.copyfile(a.build/'program/delivery.json',a.output/'runtime-delivery.json')
    (a.output/'READ-ME-FIRST.txt').write_text('''Financee Offline — Windows x64 DEVELOPMENT build

This unsigned installer was compiled on a hosted Windows x64 build runner.
It has NOT passed Windows 10/11 customer installation, UAC/WSL/reboot, offline
cold-start, repair/uninstall or backup/restore acceptance. Do not use live business
data to test it. Windows 10 runtime/business setup is currently blocked pending a
maintained runtime implementation and qualification. Windows ARM is unsupported.

Keep the setup EXE and matching runtime .tar together. Review Windows/Docker
requirements and third-party terms in the setup's official links. Run the EXE,
finish the prerequisite prompts, then choose Import Local Runtime File and select
the included financee-offline-runtime-amd64.tar. Choose a NEW EMPTY folder for a
disposable test business; create your own owner and password in first-run setup.
There is no universal login or sample business data. Keep independent backup
copies. If Windows asks for a restart, save work, restart manually and reopen
Financee Setup from the Start menu to continue.

This is an untrusted-by-Windows unsigned development artifact. Do not disable
Windows security protections or treat compilation as installation certification.
No public release was created. The included SHA256SUMS.txt checks local file
integrity, not publisher identity. Signing and customer acceptance remain pending.
''',encoding='utf-8')
    files=sorted(p for p in a.output.iterdir() if p.is_file())
    (a.output/'SHA256SUMS.txt').write_text(''.join(digest(f)+'  '+f.name+'\n' for f in files),encoding='utf-8')
    print(json.dumps({'directory':str(a.output),'files':[{'name':f.name,'bytes':f.stat().st_size,'sha256':digest(f)} for f in a.output.iterdir() if f.is_file()],'source_revision':receipt['source_revision'],'signed':False,'customer_acceptance':'pending'},indent=2))
if __name__=='__main__':main()
