"""Verify downloaded development build files without executing an EXE or
importing Docker images. This checks integrity/provenance, not customer acceptance.
"""
import argparse,json,ntpath,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.payload import digest

def verify(directory,revision):
    directory=Path(directory);listed={}
    for line in (directory/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        match=re.fullmatch(r'([a-f0-9]{64})  ([a-zA-Z0-9_.-]+)',line)
        if not match or match[2] in listed:raise ValueError('Invalid or repeated checksum filename')
        listed[match[2]]=match[1]
    expected={'Financee-Offline-Windows-x64-Development-Setup.exe','financee-offline-runtime-amd64.tar','READ-ME-FIRST.txt','build-receipt.json','program-release.json','runtime-delivery.json'}
    if set(listed)!=expected or {p.name for p in directory.iterdir()}!=expected|{'SHA256SUMS.txt'}:raise ValueError('Unexpected or missing delivery files')
    for name,expected_hash in listed.items():
        file=directory/name
        if not file.is_file() or file.is_symlink() or digest(file)!=expected_hash:raise ValueError('File verification failed: '+name)
    receipt=json.loads((directory/'build-receipt.json').read_text(encoding='utf-8'))
    release=json.loads((directory/'program-release.json').read_text(encoding='utf-8'))
    delivery=json.loads((directory/'runtime-delivery.json').read_text(encoding='utf-8'))
    if (receipt['source_revision']!=revision or release['launcher_revision']!=revision or
        receipt['signed'] or not receipt['development'] or receipt['native_customer_acceptance']!='pending' or
        receipt['architecture']!='windows-amd64' or release['architecture']!='amd64' or
        delivery['release_sha256']!=digest(directory/'program-release.json')):raise ValueError('Build provenance or development status mismatch')
    if len(receipt['installers'])!=1:raise ValueError('Expected exactly one setup EXE')
    for item in receipt['installers']:
        file=directory/ntpath.basename(item['filename'])
        if not file.is_file() or file.stat().st_size!=item['bytes'] or digest(file)!=item['sha256']:raise ValueError('Installer receipt mismatch')
    archive=delivery['archive'];file=directory/archive['filename']
    if file.stat().st_size!=archive['bytes'] or digest(file)!=archive['sha256']:raise ValueError('Runtime archive receipt mismatch')
    if len(receipt.get('bundle_checks',[]))!=2:raise ValueError('Both frozen bundle checks are required')
    for check in receipt['bundle_checks']:
        if not (check['frozen'] and check['platform']=='Windows' and check['native_architecture']=='amd64' and
                check['program_files_verified'] and check['tls_context_loaded'] and
                check['payload_architecture']=='amd64' and check['source_revision']==revision and
                check['release_sha256']==delivery['release_sha256'] and not check['customer_installation_tested']):raise ValueError('Frozen Windows bundle evidence mismatch')
    return {'verified':True,'source_revision':revision,'setup':receipt['installers'][0]['sha256'],'runtime':archive['sha256'],
            'files':len(listed)+1,'native_frozen_bundle_checks':2,'signed':False,'customer_acceptance':'pending'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--revision',required=True);a=p.parse_args();print(json.dumps(verify(a.directory,a.revision),indent=2))
