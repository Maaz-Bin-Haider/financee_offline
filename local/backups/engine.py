"""Atomic local recovery points. No live volume archive or runtime secret export."""
import contextlib,json,os,shutil,subprocess,tempfile,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from psycopg2 import sql
from . import archive,config,database
from .files import atomic,read,lock,pause,syncdir,Busy

class Engine:
    def __init__(self,root=None,folder=None):
        self.root=Path(root or config.customer_root());self.folder=Path(folder or config.backup_dir())
        self.control=self.root/'Config';self.state=self.control/'backup-status.json'
    def status(self):return read(self.state,{'state':'not_started','message':'No completed local backup yet.'})
    def update(self,**values):
        state=self.status();state.update(values);atomic(self.state,state);return state
    def pg(self,tool,args,database_name=None,timeout=120):
        env=os.environ.copy();env.update(PGHOST=os.environ.get('DB_HOST','db'),PGPORT=os.environ.get('DB_PORT','5432'),PGUSER=os.environ['DB_USER'],PGPASSWORD=os.environ['DB_PASSWORD'],LD_LIBRARY_PATH='/opt/pg16/lib',PGCONNECT_TIMEOUT='5')
        if database_name:env['PGDATABASE']=database_name
        # Never include stderr/credentials/SQL payloads in web status.
        result=subprocess.run(['/opt/pg16/bin/'+tool,*map(str,args)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        if result.returncode:raise RuntimeError(tool+' failed. Check local database availability, free disk space and the selected backup.')
        return result.stdout
    def room(self,folder,required):
        if not folder.is_dir():raise FileNotFoundError('The backup or staging folder is missing. Reconnect it or select an existing writable folder.')
        if shutil.disk_usage(folder).free<required:raise OSError('Not enough free disk space for a verified backup or recovery. Free space and retry.')
    def backup(self,kind='normal',reason='manual'):
        with lock(self.control/'maintenance/operation.lock'):
            if config.pending(self.root):raise Busy('Finish or roll back the pending recovery first.')
            if reason=='daily_or_catchup' and not self.due():return self.folder/self.status()['last_success']['filename']
            return self._backup(kind,reason)
    def _backup(self,kind,reason):
        if kind not in ('normal','rescue'):raise ValueError('Invalid backup kind.')
        active=config.active(self.root);media=self.root/active['media'];last=self.status().get('last_success')
        self.update(state='running',message='Preparing a local recovery point.',started_at=datetime.now(timezone.utc).isoformat(),last_error=None)
        try:
            self.cleanup_staging(active['instance_id'])
            with contextlib.closing(database.connect(active['database'])) as c:
                size=database.scalar(c,'SELECT pg_database_size(current_database())');c.rollback()
            media_size=sum(f.stat().st_size for f in media.rglob('*') if f.is_file())
            self.room(self.folder,size*2+media_size*2+16*1024*1024)
            # Staging shares the final ZIP filesystem so publication is atomic.
            with tempfile.TemporaryDirectory(prefix='.financee-staging-',dir=self.folder) as temporary:
                stage=Path(temporary);atomic(stage/'owner.json',{'format':1,'instance_id':active['instance_id']});payload=stage/'payload';payload.mkdir()
                limit=max(10,min(900,int(os.environ.get('BACKUP_MAX_PAUSE_SECONDS','120'))))
                deadline=time.monotonic()+limit
                with pause(self.root,timeout=30),contextlib.closing(database.connect(active['database'])) as c:
                    with c.cursor() as cur:
                        cur.execute("SET LOCAL lock_timeout='10s'")
                        cur.execute('SET LOCAL statement_timeout=%s',[str(limit*1000)+'ms'])
                        names=database.tables(c)
                        cur.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.SQL(',').join(sql.Identifier('public',name) for name in names)))
                        cur.execute('SELECT row_to_json(t) FROM local_generalsettings t WHERE id=1');profile=cur.fetchone()[0]
                    tz=ZoneInfo(profile['timezone']);now=datetime.now(timezone.utc);local=now.astimezone(tz)
                    database.integrity(c,media,deadline)
                    expected=database.fingerprints(c,deadline)
                    self.pg('pg_dump',['--format=custom','--no-owner','--no-acl','--file',payload/'database.dump'],active['database'],timeout=max(1,deadline-time.monotonic()))
                    (payload/'media').mkdir()
                    if media.is_symlink():raise ValueError('The active uploaded-files folder must not be a symbolic link.')
                    if not media.is_dir():raise FileNotFoundError('The active uploaded-files folder is missing.')
                    for file in sorted(media.rglob('*')):
                        if file.is_symlink():raise ValueError('Uploaded files contain a link. Repair it before backing up.')
                        if not file.is_file():continue
                        relative=file.relative_to(media);archive.safe_name('media/'+relative.as_posix())
                        dest=payload/'media'/relative;dest.parent.mkdir(parents=True,exist_ok=True)
                        with file.open('rb') as source,dest.open('xb') as target:
                            for chunk in iter(lambda:source.read(archive.CHUNK),b''):
                                if time.monotonic()>deadline:raise TimeoutError('The bounded backup pause expired. No ZIP was published.')
                                target.write(chunk)
                    manifest={'product':'Financee_Offline','backup_format':1,'app_version':config.VERSION,'schema':2,'postgres_major':c.server_version//10000,'database_bytes':size,'pause_seconds':round(time.monotonic()-(deadline-limit),3),'id':uuid.uuid4().hex,'installation_id':active['instance_id'],'kind':kind,'reason':reason,'created_utc':now.isoformat(),'timezone':str(tz),'local_day':local.date().isoformat(),'company':profile['name']}
                    for name,value in [('manifest.json',manifest),('configuration.json',{'format':1,'business_profile':profile}),('integrity.json',expected)]:
                        (payload/name).write_text(json.dumps(value,indent=2,default=str)+'\n')
                    c.rollback()
                # Requests resume before compression, full validation and rotation.
                self.update(message='Checking and publishing the ZIP. Business requests are available.')
                self.pg('pg_restore',['--list',payload/'database.dump'])
                zipped=stage/'verified.zip';archive.pack(payload,zipped);verified=archive.validate(zipped)
                with zipped.open('rb') as f:os.fsync(f.fileno())
                name=('Financee_Offline_Backup_' if kind=='normal' else 'Financee_Offline_Rescue_')+local.strftime('%Y-%m-%d_%H%M%S')+'_'+manifest['id']+'.zip'
                final=self.folder/name;os.chmod(zipped,0o600);os.replace(zipped,final);syncdir(self.folder)
                success={'filename':name,'sha256':verified['archive_sha256'],'created_utc':manifest['created_utc'],'local_day':manifest['local_day'],'kind':kind,'timezone':manifest['timezone'],'size':final.stat().st_size,'mtime_ns':final.stat().st_mtime_ns}
                if kind=='normal':last=success
                self.update(state='complete',message='Local ZIP verified and saved.',last_success=last,last_operation=success,last_error=None)
            if kind=='normal':
                try:self.rotate()
                except OSError as exc:self.update(state='complete',message='Backup saved. Older ZIP cleanup needs attention.',last_error=self.error(exc))
            return final
        except BaseException as exc:
            self.update(state='error',message='Backup did not complete. Previous ZIPs are preserved.',last_error=self.error(exc),last_success=last)
            raise
    def cleanup_staging(self,instance):
        for folder in self.folder.glob('.financee-staging-*'):
            if folder.is_symlink() or not folder.is_dir():continue
            try:owner=read(folder/'owner.json',{})
            except (ValueError,OSError):continue
            if owner=={'format':1,'instance_id':instance}:shutil.rmtree(folder)
    @staticmethod
    def error(exc):
        if isinstance(exc,PermissionError):return 'Access denied. Choose a writable backup folder and retry.'
        if isinstance(exc,OSError) and getattr(exc,'errno',None)==28:return 'Disk full. Free space in the backup/data folder and retry.'
        if isinstance(exc,(FileNotFoundError,TimeoutError,Busy,ValueError,RuntimeError,OSError,AssertionError)):return str(exc)[:300]
        return 'Local operation interrupted or failed. Previous data and completed ZIPs are preserved.'
    def rotate(self):
        valid=[]
        for file in self.folder.glob('Financee_Offline_Backup_*.zip'):
            try:
                info=archive.validate(file)
                if info['kind']=='normal' and info.get('installation_id')==config.active(self.root)['instance_id']:valid.append((info['created_utc'],file))
            except Exception:continue  # Never delete unknown/corrupt/rescue files.
        for _,file in sorted(valid,reverse=True)[30:]:file.unlink()
        syncdir(self.folder)
    def inspect(self,path):
        info=archive.validate(path)
        self.room(self.root/'Data',info['uncompressed_bytes']*2+16*1024*1024)
        return info
    def restore(self,path,confirmation):
        with lock(self.control/'maintenance/operation.lock'):
            if config.pending(self.root):raise Busy('An incomplete recovery already exists. Recover it before starting another.')
            info=self.inspect(path)
            if confirmation!=info['archive_sha256']:raise ValueError('Explicit replacement confirmation must match the inspected ZIP SHA-256.')
            old=config.active(self.root);token=uuid.uuid4().hex
            new=dict(old,generation=token,database=os.environ['DB_NAME'][:27]+'_r_'+token[:20],media='Data/generations/'+token+'/media')
            journal={'format':1,'stage':'preparing','old':old,'new':new,'archive_sha256':confirmation,'rescue':None}
            atomic(self.control/'restore-journal.json',journal)
            try:
                # Current data stays intact even when recovery is needed because
                # Django cannot start. Healthy installations require a rescue ZIP.
                healthy=False
                try:
                    with contextlib.closing(database.connect(old['database'])) as c:database.integrity(c,self.root/old['media']);healthy=True
                except Exception:pass
                if healthy:
                    journal['rescue']=self._backup('rescue','pre_restore').name;atomic(self.control/'restore-journal.json',journal)
                generation=self.root/'Data/generations'/token;generation.mkdir(parents=True)
                with pause(self.root),tempfile.TemporaryDirectory(prefix='restore-',dir=generation) as temporary:
                    payload=Path(temporary);check=archive.validate(path,extract=payload)
                    if check['archive_sha256']!=confirmation:raise ValueError('Backup changed after confirmation.')
                    self.pg('pg_restore',['--list',payload/'database.dump'])
                    with contextlib.closing(database.connect('postgres',autocommit=True)) as admin:
                        with admin.cursor() as cur:cur.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(new['database'])))
                    self.pg('pg_restore',['--no-owner','--no-acl','--exit-on-error','--single-transaction','--dbname',new['database'],payload/'database.dump'],timeout=900)
                    shutil.move(payload/'media' if (payload/'media').exists() else self.empty_media(payload),self.root/new['media'])
                    with contextlib.closing(database.connect(new['database'])) as c:
                        database.integrity(c,self.root/new['media'])
                        actual=database.scalar(c,'SELECT row_to_json(t) FROM local_generalsettings t WHERE id=1')
                        if actual!=read(payload/'configuration.json')['business_profile']:raise ValueError('Restored business settings differ from the recovery metadata.')
                        if database.fingerprints(c)!=read(payload/'integrity.json'):raise ValueError('Restored rows or sequences differ from the recovery point.')
                        with c.cursor() as cur:cur.execute('DELETE FROM django_session')
                        c.commit()
                    for folder in sorted((self.root/new['media']).rglob('*'),reverse=True):
                        if folder.is_dir():syncdir(folder)
                    syncdir(self.root/new['media']);syncdir(generation);syncdir(generation.parent)
                    journal['stage']='candidate_verified';atomic(self.control/'restore-journal.json',journal)
                    atomic(self.control/'active.json',new)
                    journal['stage']='awaiting_health';atomic(self.control/'restore-journal.json',journal)
                    self.clear_cache()
                self.update(state='restore_pending',message='Candidate verified. Waiting for application startup verification.')
                return journal
            except BaseException as exc:
                # No active DB/media are dropped, even after a failed candidate.
                atomic(self.control/'active.json',old)
                journal['stage']='failed_before_switch';atomic(self.control/'restore-journal.json',journal)
                self.update(state='error',message='Recovery did not complete. The previous generation is still active.',last_error=self.error(exc))
                raise
    @staticmethod
    def empty_media(payload):
        path=payload/'media';path.mkdir();return path
    def clear_cache(self):
        if os.environ.get('REDIS_URL'):
            import redis
            redis.Redis.from_url(os.environ['REDIS_URL'],socket_connect_timeout=5,socket_timeout=5).flushdb()
    def recover(self,commit=False):
        with lock(self.control/'maintenance/operation.lock'),pause(self.root):
            config.active(self.root)
            journal=read(self.control/'restore-journal.json',{})
            if not config.pending(self.root):return journal
            if commit:
                if journal['stage']!='awaiting_health' or config.active(self.root)!=journal['new']:raise ValueError('No verified switched candidate is waiting for startup verification.')
                with contextlib.closing(database.connect(journal['new']['database'])) as c:database.integrity(c,self.root/journal['new']['media'])
                journal['stage']='committed';self.clear_cache()
                self.update(state='complete',message='Recovery verified. Previous generation and rescue ZIP retained.')
            else:
                atomic(self.control/'active.json',journal['old']);journal['stage']='rolled_back'
                self.update(state='complete',message='Incomplete recovery rolled back. Previous generation is active.')
            atomic(self.control/'restore-journal.json',journal);return journal
    def due(self,now=None):
        if config.pending(self.root):return False
        active=config.active(self.root)
        with contextlib.closing(database.connect(active['database'])) as c:
            tz=database.scalar(c,'SELECT (SELECT timezone FROM local_generalsettings WHERE id=1)')
        if not tz:
            if self.status().get('state')!='waiting_for_setup':self.update(state='waiting_for_setup',message='Complete company setup before the first daily backup.',last_error=None)
            return False
        day=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz)).date().isoformat()
        last=self.status().get('last_success') or {}
        file=self.folder/last.get('filename','')
        def today(created):return datetime.fromisoformat(created).astimezone(ZoneInfo(tz)).date().isoformat()==day
        if file.is_file() and last.get('created_utc') and today(last['created_utc']):
            st=file.stat()
            if last.get('size')==st.st_size and last.get('mtime_ns')==st.st_mtime_ns:return False
        # Recover publication evidence after a crash between rename and status
        # update. Validate eligible ZIPs fully before counting today's success.
        for file in sorted(self.folder.glob('Financee_Offline_Backup_*.zip'),reverse=True):
            try:
                import zipfile
                with zipfile.ZipFile(file) as z:
                    if z.getinfo('manifest.json').file_size>65536:continue
                    manifest=json.loads(z.read('manifest.json'))
                if manifest.get('installation_id')!=active['instance_id'] or manifest.get('kind')!='normal' or not today(manifest['created_utc']):continue
                info=archive.validate(file);st=file.stat()
                last={'filename':file.name,'sha256':info['archive_sha256'],'created_utc':info['created_utc'],'local_day':day,'kind':'normal','timezone':tz,'size':st.st_size,'mtime_ns':st.st_mtime_ns}
                self.update(state='complete',message='Completed ZIP recovered from local backup history.',last_success=last,last_error=None);return False
            except (ValueError,KeyError,OSError,zipfile.BadZipFile):continue
        return True
