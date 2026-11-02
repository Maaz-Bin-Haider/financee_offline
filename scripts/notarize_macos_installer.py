"""Explicit owner-operated Developer ID notarization/stapling pipeline. Requires
an already signed app and an owner-configured notarytool keychain profile. No
password/key is accepted or written by this script. Invoking it submits program
artifacts to Apple; it never uploads customer folders or creates a public release.
"""
import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.payload import digest

def require_developer_id(app):
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    value=subprocess.run(['codesign','-d','--verbose=4',str(app)],capture_output=True,text=True,check=True).stderr
    if 'Authority=Developer ID Application:' not in value or 'runtime' not in value or 'TeamIdentifier=not set' in value:
        raise SystemExit('Refusing notarization: a valid Developer ID Application signature, hardened runtime and team identity are required. Ad-hoc builds are not submitted.')

def submit(path,profile,folder):
    raw=subprocess.check_output(['xcrun','notarytool','submit',str(path),'--keychain-profile',profile,'--wait','--output-format','json'],text=True)
    result=json.loads(raw);(folder/(path.stem+'-notary.json')).write_text(json.dumps(result,indent=2)+'\n')
    if result.get('status')!='Accepted':
        if result.get('id'):subprocess.run(['xcrun','notarytool','log',result['id'],'--keychain-profile',profile,str(folder/(path.stem+'-notary-log.json'))],check=False)
        raise SystemExit('Apple did not accept this artifact. Review the saved notary log; nothing is published.')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--identity',required=True);p.add_argument('--keychain-profile',required=True);a=p.parse_args()
    require_developer_id(a.app)
    if a.output.exists():raise SystemExit('Choose a new notarization staging directory; input app is preserved.')
    a.output.mkdir(parents=True);app=a.output/a.app.name;shutil.copytree(a.app,app,symlinks=True)
    archive=a.output/'signed-app.zip';subprocess.run(['ditto','-c','-k','--keepParent',str(app),str(archive)],check=True)
    app_ticket=submit(archive,a.keychain_profile,a.output)
    subprocess.run(['xcrun','stapler','staple',str(app)],check=True);subprocess.run(['xcrun','stapler','validate',str(app)],check=True)
    stage=a.output/'dmg-contents';stage.mkdir();shutil.copytree(app,stage/app.name,symlinks=True);(stage/'Applications').symlink_to('/Applications',target_is_directory=True)
    dmg=a.output/'Financee-Offline-Apple-Silicon-Notarized-Development.dmg'
    subprocess.run(['hdiutil','create','-volname','Financee Offline','-srcfolder',str(stage),'-format','UDZO',str(dmg)],check=True)
    subprocess.run(['codesign','--sign',a.identity,'--timestamp',str(dmg)],check=True)
    dmg_ticket=submit(dmg,a.keychain_profile,a.output)
    subprocess.run(['xcrun','stapler','staple',str(dmg)],check=True);subprocess.run(['xcrun','stapler','validate',str(dmg)],check=True)
    subprocess.run(['spctl','--assess','--type','execute','--verbose=4',str(app)],check=True)
    subprocess.run(['spctl','--assess','--type','open','--context','context:primary-signature','--verbose=4',str(dmg)],check=True)
    receipt={'app_notary_id':app_ticket['id'],'dmg_notary_id':dmg_ticket['id'],'stapled':True,'gatekeeper_assessed':True,'dmg_sha256':digest(dmg),'public_release_created':False,'customer_acceptance':'still requires target-device tests'}
    (a.output/'notarization-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
