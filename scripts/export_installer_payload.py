"""Developer export of already-cached, exact native Linux images. Never pulls,
builds, starts services, reads customer folders or uploads anything. Docker save
loses repository digests, so archive references use unique image-ID-based tags.
"""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.payload import Payload,digest,https_url

def export(source,out,url=None):
    source=Path(source).resolve();out=Path(out).resolve()
    if out.exists():raise SystemExit('Choose a new output folder; existing payload files were preserved.')
    release=json.loads((source/'release.json').read_text())
    if release.get('product')!='Financee_Offline' or release.get('architecture') not in ('arm64','amd64'):raise SystemExit('Invalid source release manifest.')
    def docker(*args):return subprocess.check_output(['docker',*args],text=True)
    images=[];renames={}
    for image in release['images']:
        value=json.loads(docker('image','inspect',image['reference']))[0]
        if value['Id']!=image['id'] or value['Architecture']!=release['architecture'] or value['Os']!='linux':raise SystemExit('Cached native image differs from release: '+image['reference'])
        alias='financee-offline-payload:'+release['architecture']+'-'+image['id'].split(':')[1]
        # Inspect existing tags via read-only enumeration, not an exception-as-absence shortcut.
        known=docker('image','ls','--format','{{.Repository}}:{{.Tag}}').splitlines()
        if alias in known and json.loads(docker('image','inspect',alias))[0]['Id']!=image['id']:raise SystemExit('Payload alias collision; nothing overwritten.')
        renames[image['reference']]=alias;images.append({'reference':alias,'id':image['id']})
    out.mkdir(parents=True);program=out/'program';program.mkdir()
    for name,expected in release['files'].items():
        file=(source/name).resolve()
        if not file.is_relative_to(source) or digest(file)!=expected:raise SystemExit('Source program resource failed validation: '+name)
        target=program/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
    compose=(program/'compose.yml').read_text()
    if '    build:' in compose:raise SystemExit('Installer must not contain a developer image build path.')
    for before,after in renames.items():compose=compose.replace('image: '+before,'image: '+after)
    (program/'compose.yml').write_text(compose)
    if release['architecture']=='amd64':shutil.copyfile(ROOT/'installer/windows/prerequisites.ps1',program/'prerequisites.ps1')
    (program/'bootstrap.json').write_text(json.dumps({'development':True,'auto_start':True,'docker_context':'desktop-linux'},indent=2)+'\n')
    release.update(images=images,development=True,setup_version='0.7.0-phase7' if release['architecture']=='arm64' else '0.6.0-phase6',setup_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    release['files']={str(f.relative_to(program)).replace('\\','/'):digest(f) for f in sorted(program.rglob('*')) if f.is_file() and f.name not in ('release.json','delivery.json')}
    (program/'release.json').write_text(json.dumps(release,indent=2)+'\n')
    for image in images:subprocess.run(['docker','image','tag',image['id'],image['reference']],check=True)
    archive=out/('financee-offline-runtime-'+release['architecture']+'.tar')
    part=archive.with_suffix('.tar.part')
    subprocess.run(['docker','image','save','--output',str(part),*[i['reference'] for i in images]],check=True)
    part.replace(archive)
    delivery={'format':1,'product':'Financee_Offline','architecture':release['architecture'],'release_sha256':digest(program/'release.json'),'archive':{'filename':archive.name,'bytes':archive.stat().st_size,'sha256':digest(archive)}}
    if url:delivery['archive']['url']=https_url(url)
    (program/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n')
    payload=Payload(program);payload.verify_archive(archive)
    print(json.dumps({'program':str(program),'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive),'architecture':release['architecture'],'image_count':len(images),'published':False},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--program',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--download-url');a=p.parse_args();export(a.program,a.output,a.download_url)
