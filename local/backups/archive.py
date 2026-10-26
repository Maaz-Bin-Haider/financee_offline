import hashlib,json,re,stat,unicodedata,zipfile
from pathlib import Path,PurePosixPath
from datetime import datetime,date
from zoneinfo import ZoneInfo
from packaging.version import Version
from .config import VERSION
CHUNK=1024*1024
REQUIRED={'manifest.json','configuration.json','integrity.json','database.dump','checksums.json'}

def digest(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as f:
        for chunk in iter(lambda:f.read(CHUNK),b''):h.update(chunk)
    return h.hexdigest()

def version(value):
    return Version(re.sub(r'-phase([0-9]+)$',r'.dev\1',value))

def safe_name(name):
    path=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or '\0' in name or name.startswith('/') or str(path)!=name or any(p in ('.','..') for p in path.parts):raise ValueError('Unsafe ZIP member path.')
    for part in path.parts:
        if any(ord(c)<32 or c in '<>"|?*' for c in part) or part.endswith((' ','.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',part):raise ValueError('ZIP path is not portable.')
    if name not in REQUIRED and not (name.startswith('media/') and len(path.parts)>1):raise ValueError('Unexpected ZIP member.')
    return name

def validate(path,extract=None):
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)>200000:raise ValueError('Too many ZIP members.')
        seen=set()
        for i in infos:
            safe_name(i.filename);key=unicodedata.normalize('NFC',i.filename).casefold()
            if key in seen:raise ValueError('Duplicate ZIP member path.')
            seen.add(key)
            mode=stat.S_IFMT(i.external_attr>>16)
            if i.is_dir() or mode not in (0,stat.S_IFREG) or i.flag_bits&1:raise ValueError('Links, special files and encrypted members are not supported.')
        names={i.filename for i in infos}
        if not REQUIRED<=names:raise ValueError('Required recovery members are missing.')
        def meta(name):
            if z.getinfo(name).file_size>16*1024*1024:raise ValueError('Recovery metadata is too large.')
            return json.loads(z.read(name))
        manifest=meta('manifest.json');checks=meta('checksums.json')
        if manifest.get('product')!='Financee_Offline' or manifest.get('backup_format')!=1 or manifest.get('schema')!=2 or manifest.get('postgres_major')!=16:raise ValueError('Incompatible backup product, format, schema or PostgreSQL version.')
        for key in ('id','installation_id'):
            if key in manifest and not re.fullmatch(r'[0-9a-f]{32}',manifest[key]):raise ValueError('Invalid recovery identifier.')
        if not isinstance(manifest.get('database_bytes'),int) or manifest['database_bytes']<=0:raise ValueError('Invalid recovery database size.')
        if not isinstance(manifest.get('company'),str) or not manifest['company']:raise ValueError('Missing recovery company identity.')
        if datetime.fromisoformat(manifest['created_utc']).tzinfo is None:raise ValueError('Recovery timestamp needs a UTC offset.')
        ZoneInfo(manifest['timezone']);date.fromisoformat(manifest['local_day'])
        configuration=meta('configuration.json');integrity=meta('integrity.json')
        if configuration.get('format')!=1 or not isinstance(configuration.get('business_profile'),dict) or configuration['business_profile'].get('name')!=manifest['company']:raise ValueError('Recovery company metadata is inconsistent.')
        if not isinstance(integrity.get('tables'),dict) or not isinstance(integrity.get('sequences'),dict):raise ValueError('Recovery fingerprints are missing.')
        if version(manifest['app_version'])>version(VERSION) or manifest.get('kind') not in ('normal','rescue'):raise ValueError('Backup requires a newer Financee release or has an invalid kind.')
        if set(checks)!=names-{'checksums.json'}:raise ValueError('Incomplete member checksum inventory.')
        for i in infos:
            h=hashlib.sha256();size=0
            output=None
            if extract:
                output=Path(extract)/i.filename;output.parent.mkdir(parents=True,exist_ok=True)
                if output.exists():raise ValueError('Extraction destination must be empty.')
                output=output.open('xb')
            try:
                with z.open(i) as f:
                    for chunk in iter(lambda:f.read(CHUNK),b''):
                        h.update(chunk);size+=len(chunk)
                        if output:output.write(chunk)
            finally:
                if output:
                    output.flush()
                    import os
                    os.fsync(output.fileno());output.close()
            if i.filename!='checksums.json':
                expected=checks[i.filename]
                if size!=expected['size'] or h.hexdigest()!=expected['sha256']:raise ValueError('Recovery member checksum mismatch: '+i.filename)
        manifest=dict(manifest,archive_sha256=digest(path),uncompressed_bytes=sum(i.file_size for i in infos))
        return manifest

def pack(folder,destination):
    folder=Path(folder)
    checks={str(p.relative_to(folder)):dict(size=p.stat().st_size,sha256=digest(p)) for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='checksums.json'}
    (folder/'checksums.json').write_text(json.dumps(checks,indent=2)+'\n')
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED,allowZip64=True,compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():
                with p.open('rb') as source,z.open(str(p.relative_to(folder)),'w',force_zip64=True) as target:
                    for chunk in iter(lambda:source.read(CHUNK),b''):target.write(chunk)
