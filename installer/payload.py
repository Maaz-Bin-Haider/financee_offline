"""Verified, restartable image delivery. The manifest is bundled with setup,
not downloaded from an untrusted URL. No archive is extracted onto the host.
"""
import hashlib,json,os,re,shutil,tarfile,tempfile,urllib.parse,urllib.request
from pathlib import Path
from launcher.storage import LauncherError,read

SERVICES={'db','redis','web','backup','nginx'}

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def https_url(value):
    url=urllib.parse.urlsplit(value)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.fragment:
        raise LauncherError('Setup downloads require an HTTPS URL without credentials or a fragment.')
    return value

class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        https_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def native_config_ids(path,references,architecture):
    """Canonical config digests survive classic/OCI store conversions. They bind
    image settings and every uncompressed rootfs layer digest, independently of
    the destination store's manifest/index ID. Read metadata only; never extract.
    """
    from pathlib import PurePosixPath
    try:
        with tarfile.open(path,'r:') as archive:
            def body(name):
                part=PurePosixPath(name)
                if part.is_absolute() or '..' in part.parts:raise ValueError('path')
                member=archive.getmember(name)
                if not member.isfile() or member.size>1024*1024:raise ValueError('metadata')
                return archive.extractfile(member).read()
            manifest=json.loads(body('manifest.json'));result={}
            if not isinstance(manifest,list) or len(manifest)!=len(references):raise ValueError('image count')
            for entry in manifest:
                config=body(entry['Config']);value=json.loads(config)
                if value.get('os')!='linux' or value.get('architecture')!=architecture:raise ValueError('architecture')
                for ref in entry.get('RepoTags') or []:
                    if ref in result:raise ValueError('duplicate tag')
                    result[ref]='sha256:'+hashlib.sha256(config).hexdigest()
            if set(result)!=set(references):raise ValueError('references')
            return result
    except (OSError,tarfile.TarError,KeyError,ValueError,TypeError,AttributeError) as exc:
        raise LauncherError('Local image contents could not be verified against the native runtime archive.') from exc

class Payload:
    def __init__(self,program):
        self.program=Path(program).resolve();self.release=read(self.program/'release.json',{})
        self.delivery=read(self.program/'delivery.json',{})
        r=self.release;d=self.delivery
        if (r.get('product')!='Financee_Offline' or r.get('format')!=1 or
            r.get('architecture') not in ('amd64','arm64') or
            d.get('format')!=1 or d.get('product')!='Financee_Offline' or
            d.get('architecture')!=r.get('architecture') or
            d.get('release_sha256')!=digest(self.program/'release.json')):
            raise LauncherError('Setup manifest is incomplete or mismatched. Obtain the matching setup package.')
        self.identity=digest(self.program/'delivery.json')
        if not isinstance(r.get('files'),dict) or not {'compose.yml','nginx.conf'}<=r['files'].keys():
            raise LauncherError('Required program resources are not listed in the setup manifest.')
        for name,expected in r['files'].items():
            file=self.program/name
            if not file.resolve().is_relative_to(self.program) or not file.is_file() or digest(file)!=expected:
                raise LauncherError('Setup program resources failed verification.')
        images=r.get('images',[])
        if not images or len({x.get('reference') for x in images})!=len(images):
            raise LauncherError('Setup image references are missing or duplicated.')
        for image in images:
            if not re.fullmatch(r'sha256:[a-f0-9]{64}',image.get('id','')) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_./:@-]{0,250}',image.get('reference','')):
                raise LauncherError('Setup image identity is invalid.')
        if set(r.get('service_images',{}))!=SERVICES or not set(r['service_images'].values())<={x['id'] for x in images}:
            raise LauncherError('Setup service image identities are incomplete.')
        self.archive=d.get('archive',{})
        if (not re.fullmatch(r'[a-zA-Z0-9_-]+\.tar',self.archive.get('filename','')) or
            not re.fullmatch(r'[a-f0-9]{64}',self.archive.get('sha256','')) or
            type(self.archive.get('bytes')) is not int or self.archive['bytes']<=0):
            raise LauncherError('Setup archive metadata is invalid.')
        if self.archive.get('url'):https_url(self.archive['url'])
    def verified(self,path):
        path=Path(path)
        return path.is_file() and path.stat().st_size==self.archive['bytes'] and digest(path)==self.archive['sha256']
    def acquire(self,cache,local=None,progress=lambda text:None,opener=None):
        cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
        target=cache/self.archive['filename']
        if self.verified(target):return target
        source=Path(local).resolve() if local else None
        if source and not self.verified(source):raise LauncherError('The selected runtime archive failed size/SHA-256 verification. No images were imported.')
        # An invalid existing final file is preserved, never replaced implicitly.
        if target.exists():raise LauncherError('A different file already exists in the setup cache. Choose another empty cache folder or move that file before retrying.')
        if shutil.disk_usage(cache).free<self.archive['bytes']+64*1024*1024:
            raise LauncherError('Not enough free space for the verified setup archive. Choose a larger cache folder.')
        fd,name=tempfile.mkstemp(prefix='.financee-download-',suffix='.part',dir=cache)
        try:
            if source:stream=source.open('rb')
            else:
                url=self.archive.get('url')
                if not url:raise LauncherError('This development setup has no published download URL. Choose its matching local runtime .tar file.')
                progress('Downloading the matching runtime payload. Your business data stays on this device.')
                opener=opener or urllib.request.build_opener(HTTPSRedirect())
                stream=opener.open(https_url(url),timeout=30)
            with os.fdopen(fd,'wb') as out,stream:
                fd=None;total=0;h=hashlib.sha256()
                for chunk in iter(lambda:stream.read(1024*1024),b''):
                    total+=len(chunk)
                    if total>self.archive['bytes']:raise LauncherError('The setup download exceeds its recorded size.')
                    out.write(chunk);h.update(chunk)
                out.flush();os.fsync(out.fileno())
            if total!=self.archive['bytes'] or h.hexdigest()!=self.archive['sha256']:
                raise LauncherError('Runtime download verification failed. Retry setup; no images were imported.')
            os.replace(name,target);return target
        finally:
            if fd is not None:os.close(fd)
            Path(name).unlink(missing_ok=True)
    def verify_archive(self,path):
        if not self.verified(path):raise LauncherError('Runtime archive failed size/SHA-256 verification.')
        expected={i['reference']:i['id'] for i in self.release['images']}
        try:
            with tarfile.open(path,'r:') as archive:
                def small_json(name):
                    from pathlib import PurePosixPath
                    part=PurePosixPath(name)
                    if part.is_absolute() or '..' in part.parts:raise ValueError('archive path')
                    member=archive.getmember(name)
                    if not member.isfile() or member.size>1024*1024:raise ValueError('archive metadata')
                    return archive.extractfile(member).read()
                manifest=json.loads(small_json('manifest.json'));actual={}
                if not isinstance(manifest,list) or len(manifest)!=len(expected):raise ValueError('image count')
                for image in manifest:
                    config=small_json(image['Config']);value=json.loads(config)
                    if value.get('os')!='linux' or value.get('architecture')!=self.release['architecture']:raise ValueError('architecture')
                    identity='sha256:'+hashlib.sha256(config).hexdigest()
                    for reference in image.get('RepoTags') or []:
                        if reference in actual:raise ValueError('duplicate tag')
                        actual[reference]=identity
                # Containerd's Docker image ID can be an OCI index/manifest
                # digest instead of the classic config digest. Verify the
                # descriptor chain that binds this tag to the native config.
                if set(actual)!=set(expected):raise ValueError('image references')
                if actual!=expected:
                    index=json.loads(small_json('index.json'))
                    descriptors={}
                    for desc in index.get('manifests',[]):
                        name=desc.get('annotations',{}).get('io.containerd.image.name','')
                        for ref in expected:
                            if name in (ref,'docker.io/library/'+ref):descriptors[ref]=desc
                    def contains_config(desc,target,depth=0):
                        if depth>4:raise ValueError('descriptor depth')
                        identity=desc.get('digest','')
                        if not re.fullmatch(r'sha256:[a-f0-9]{64}',identity):raise ValueError('descriptor digest')
                        raw=small_json('blobs/sha256/'+identity.split(':')[1])
                        if 'sha256:'+hashlib.sha256(raw).hexdigest()!=identity:raise ValueError('descriptor hash')
                        value=json.loads(raw)
                        if value.get('config',{}).get('digest')==target:return True
                        for child in value.get('manifests',[]):
                            selected=child.get('platform',{})
                            if selected and (selected.get('os')!='linux' or selected.get('architecture')!=self.release['architecture']):continue
                            if contains_config(child,target,depth+1):return True
                        return False
                    for reference,identity in expected.items():
                        if actual[reference]==identity:continue
                        desc=descriptors.get(reference,{})
                        if desc.get('digest')!=identity or not contains_config(desc,actual[reference]):raise ValueError('OCI image identity')
        except (OSError,tarfile.TarError,KeyError,ValueError,TypeError,AttributeError) as exc:
            raise LauncherError('Runtime archive contents differ from the recorded native image set. No images were imported.') from exc
        return True
    def import_images(self,path,system,docker,context,env,progress=lambda text:None):
        self.verify_archive(path)
        endpoint=json.loads(system.execute([docker,'context','inspect',context,'--format','{{json .Endpoints.docker.Host}}'],env=env))
        if not isinstance(endpoint,str) or not endpoint.startswith(('unix://','npipe:////./pipe/')):
            raise LauncherError('Setup refuses a remote Docker endpoint.')
        base=[docker,'--context',context]
        info=json.loads(system.execute([*base,'info','--format','{{json .}}'],env=env))
        actual={'x86_64':'amd64','aarch64':'arm64'}.get(info.get('Architecture'),info.get('Architecture'))
        if info.get('OSType')!='linux' or actual!=self.release['architecture']:
            raise LauncherError('The runtime architecture or container mode differs from this setup package.')
        system.execute([*base,'compose','version','--short'],env=env)
        # Enumerate before inspect: an unavailable daemon is never treated as a missing image.
        ids=system.execute([*base,'image','ls','-q','--no-trunc'],env=env).split()
        values=json.loads(system.execute([*base,'image','inspect',*sorted(set(ids))],env=env)) if ids else []
        existing={ref:v['Id'] for v in values for ref in (v.get('RepoTags') or [])+(v.get('RepoDigests') or [])}
        expected_configs=native_config_ids(path,[i['reference'] for i in self.release['images']],actual)
        def prove_local(references):
            if not references:return
            cache=Path(path).parent
            if shutil.disk_usage(cache).free<self.archive['bytes']+64*1024*1024:
                raise LauncherError('More free cache space is needed to verify Docker image-store conversion. No business was initialized.')
            fd,name=tempfile.mkstemp(prefix='.financee-image-readback-',suffix='.tar',dir=cache);os.close(fd)
            try:
                progress('Verifying imported image contents for this local Docker image store.')
                system.execute([*base,'image','save','--output',name,*references],env=env,timeout=1800)
                local=native_config_ids(name,references,actual)
                if local!={ref:expected_configs[ref] for ref in references}:
                    raise LauncherError('A payload image reference already belongs to different image contents. Setup did not overwrite it.')
            finally:Path(name).unlink(missing_ok=True)
        different=[i['reference'] for i in self.release['images'] if i['reference'] in existing and existing[i['reference']]!=i['id']]
        prove_local(different)  # Read-only proof before any existing tag can be reused.
        if any(i['reference'] not in existing for i in self.release['images']):
            progress('Importing verified local runtime images. Other Docker projects remain running.')
            system.execute([*base,'image','load','--input',str(path)],env=env,timeout=1800)
        resolved={};different=[]
        for image in self.release['images']:
            value=json.loads(system.execute([*base,'image','inspect',image['reference']],env=env))[0]
            if value['Os']!='linux' or value['Architecture']!=actual:
                raise LauncherError('Imported image architecture differs from the tested payload. Setup did not initialize a business.')
            resolved[image['id']]=value['Id']
            if value['Id']!=image['id']:different.append(image['reference'])
        prove_local(different)
        return resolved
