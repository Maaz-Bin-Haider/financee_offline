"""Stage public program resources from this checkout and exact cached Linux
images. No customer folder, build, pull, service mutation or source repo access.
Run on the payload build machine after explicitly building/importing its images.
"""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.payload import digest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--architecture',choices=['amd64','arm64'],required=True);p.add_argument('--engine-image',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise SystemExit('Choose a new staging folder. Existing files were preserved.')
    version=(ROOT/'VERSION').read_text().strip()
    source=(ROOT/'runtime/compose.yml').read_text().replace('    build:\n      context: ..\n      dockerfile: runtime/Dockerfile\n','')
    source=source.replace('image: financee-offline:'+version,'image: '+a.engine_image)
    images=[];services={};service=None;engine_revision=None
    for line in source.splitlines():
        if line.startswith('  ') and not line.startswith('    ') and line.strip().endswith(':'):service=line.strip()[:-1]
        if line.strip().startswith('image: '):
            ref=line.split('image: ',1)[1].strip()
            value=json.loads(subprocess.check_output(['docker','image','inspect',ref],text=True))[0]
            if value['Os']!='linux' or value['Architecture']!=a.architecture:raise SystemExit('Missing exact native cached image: '+ref)
            services[service]=value['Id']
            if service=='web':engine_revision=(value.get('Config',{}).get('Labels') or {}).get('org.opencontainers.image.revision')
            if ref not in [i['reference'] for i in images]:images.append({'reference':ref,'id':value['Id']})
    if a.engine_image not in [i['reference'] for i in images]:raise SystemExit('Engine image replacement did not match the current Compose version.')
    services['backup']=services['web']
    if set(services)!={'db','redis','web','backup','nginx'}:raise SystemExit('Unexpected Compose service/image contract.')
    a.output.mkdir(parents=True);(a.output/'compose.yml').write_text(source);shutil.copyfile(ROOT/'runtime/nginx.conf',a.output/'nginx.conf')
    notice=a.output/'notices';notice.mkdir();target='macos' if a.architecture=='arm64' else 'windows';shutil.copyfile(ROOT/('installer/'+target+'/development-notice.txt'),notice/(target+'-development.txt'))
    policy=ROOT/'upgrades'/(version+'.json')
    if policy.is_file():shutil.copyfile(policy,a.output/'upgrade-policy.json')
    release={'format':1,'product':'Financee_Offline','version':version,'schema':2,'architecture':a.architecture,'images':images,'service_images':services,'development':True,'engine_revision':engine_revision,'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'files':{str(f.relative_to(a.output)).replace('\\','/'):digest(f) for f in a.output.rglob('*') if f.is_file()}}
    (a.output/'release.json').write_text(json.dumps(release,indent=2)+'\n');print(json.dumps({'program':str(a.output.resolve()),'architecture':a.architecture,'images':len(images),'built_or_pulled':False},indent=2))
if __name__=='__main__':main()
