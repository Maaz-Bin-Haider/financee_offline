"""Real PostgreSQL/ZIP and isolated fault tests. Refuses source/review databases."""
import contextlib,io,json,os,shutil,signal,stat,subprocess,sys,tempfile,time,unittest,uuid,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from local.backups import archive,config,database
from local.backups.engine import Engine
from local.backups.files import atomic,read,lock,pause,Busy
assert os.environ['DB_NAME']=='financee_offline_test','Only the owned disposable test database is allowed'

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='phase4-',dir='/customer/Cache');cls.root=Path(cls.temp.name)
        (cls.root/'Config').mkdir();(cls.root/'Data').mkdir();cls.folder=cls.root/'Backups';cls.folder.mkdir()
        shutil.copytree('/customer/Data/media',cls.root/'Data/media')
        (cls.root/'Data/media/phase4-binary.bin').write_bytes(bytes(range(256))*100)
        cls.e=Engine(cls.root,cls.folder);cls.original=config.active(cls.root)
        cls.good=cls.e.backup();cls.info=archive.validate(cls.good)
    @classmethod
    def tearDownClass(cls):
        # Delete only candidate databases named by this test's private journal.
        names=getattr(cls,'candidates',set())
        with contextlib.closing(database.connect('postgres',autocommit=True)) as c:
            from psycopg2 import sql
            for name in names:
                assert name.startswith('financee_offline_test_r_') and name!=cls.original['database']
                with c.cursor() as cur:cur.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        cls.temp.cleanup()
    def remember(self):
        journal=read(self.e.control/'restore-journal.json',{})
        if journal.get('new'):self.__class__.candidates=getattr(self.__class__,'candidates',set())|{journal['new']['database']}
        return journal
    def change_zip(self,name,mutate):
        folder=self.root/('edit-'+uuid.uuid4().hex);folder.mkdir();archive.validate(self.good,extract=folder)
        mutate(folder);(folder/'checksums.json').unlink();out=self.root/name;archive.pack(folder,out);shutil.rmtree(folder);return out
    def test_01_complete_zip_and_secret_separation(self):
        with zipfile.ZipFile(self.good) as z:
            self.assertEqual(z.read('media/phase4-binary.bin'),bytes(range(256))*100)
            self.assertTrue(all(i.extract_version>=45 for i in z.infolist()))
            self.assertFalse(any('runtime.env' in n or 'active.json' in n for n in z.namelist()))
            for name in ['manifest.json','configuration.json','integrity.json']:
                self.assertNotIn(os.environ['DB_PASSWORD'],z.read(name).decode())
        self.assertEqual(self.info['postgres_major'],16)
        self.assertFalse(self.e.due())
        tomorrow=datetime.now(timezone.utc)+timedelta(days=1)
        self.assertTrue(self.e.due(tomorrow))
    def test_02_archive_corruption_and_compatibility(self):
        bad=self.change_zip('future.zip',lambda p:(p/'manifest.json').write_text(json.dumps(dict(read(p/'manifest.json'),app_version='99.0.0'))))
        with self.assertRaises(ValueError):archive.validate(bad)
        bad=self.root/'corrupt.zip'
        with zipfile.ZipFile(self.good) as source,zipfile.ZipFile(bad,'w') as target:
            for item in source.infolist():target.writestr(item,source.read(item)+(b'broken' if item.filename=='database.dump' else b''))
        with self.assertRaises(ValueError):archive.validate(bad)
        bad=self.root/'missing.zip'
        with zipfile.ZipFile(bad,'w') as z:z.writestr('manifest.json','{}')
        with self.assertRaises(ValueError):archive.validate(bad)
    def test_03_unsafe_paths_duplicates_links(self):
        for name in ['../outside','/absolute','media/../../escape','media/C:bad','media/a\\b','media/NUL.txt','media/a//b','media/a.','media/a?b']:
            with self.subTest(name=name),self.assertRaises(ValueError):archive.safe_name(name)
        for case in ('duplicate','link'):
            path=self.root/(case+'.zip')
            with zipfile.ZipFile(path,'w') as z:
                if case=='duplicate':z.writestr('media/File','1');z.writestr('media/file','2')
                else:
                    i=zipfile.ZipInfo('media/link');i.create_system=3;i.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(i,'../../outside')
            with self.assertRaises(ValueError):archive.validate(path)
    def test_04_disk_permission_missing_folder_failures_preserve_zip(self):
        before=archive.digest(self.good)
        for error in [OSError(28,'full'),PermissionError('denied')]:
            with patch('local.backups.archive.pack',side_effect=error),self.assertRaises(OSError):self.e.backup()
            self.assertEqual(self.e.status()['state'],'error');self.assertEqual(archive.digest(self.good),before)
        e=Engine(self.root,self.root/'missing')
        with self.assertRaises(FileNotFoundError):e.backup()
        self.assertEqual(self.e.status()['last_success']['filename'],self.good.name)
    def test_05_cross_process_locks_and_crash_release(self):
        code="from local.backups.files import lock;import sys,time;from pathlib import Path\nwith lock(Path(sys.argv[1])):\n print('locked',flush=True);time.sleep(60)"
        p=subprocess.Popen([sys.executable,'-c',code,str(self.e.control/'maintenance/operation.lock')],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(p.stdout.readline().strip(),'locked')
            with self.assertRaises(Busy):self.e.backup()
        finally:p.kill();p.wait();p.stdout.close()
        with lock(self.e.control/'maintenance/operation.lock'):pass
        with pause(self.root):
            from django.test import RequestFactory,override_settings
            from django.http import HttpResponse
            from local.backups.gate import MaintenanceMiddleware
            with override_settings(OFFLINE_CUSTOMER_ROOT=str(self.root),OFFLINE_GENERATION='initial'):
                response=MaintenanceMiddleware(lambda r:HttpResponse('bad'))(RequestFactory().get('/home/'))
                self.assertEqual(response.status_code,503)
    def test_06_streamed_reads_are_drained(self):
        from django.test import RequestFactory,override_settings
        from django.http import StreamingHttpResponse
        from local.backups.gate import MaintenanceMiddleware
        with override_settings(OFFLINE_CUSTOMER_ROOT=str(self.root),OFFLINE_GENERATION='initial'):
            response=MaintenanceMiddleware(lambda r:StreamingHttpResponse(iter([b'content'])))(RequestFactory().get('/attachments/'))
            with self.assertRaises(Busy):
                with pause(self.root,timeout=0):pass
            self.assertEqual(b''.join(response.streaming_content),b'content')
            with pause(self.root,timeout=0):pass
    def test_07_confirmation_and_candidate_roundtrip(self):
        with self.assertRaises(ValueError):self.e.restore(self.good,'not-confirmed')
        # Post after the recovery point; the candidate must rewind the books,
        # while the prior generation retains the later transaction.
        with contextlib.closing(database.connect(self.original['database'])) as c:
            uid=database.scalar(c,'SELECT id FROM auth_user WHERE is_superuser ORDER BY id LIMIT 1')
            suffix=uuid.uuid4().hex[:12];vendor='P4 VENDOR '+suffix;item='P4 DEVICE '+suffix
            database.scalar(c,'SELECT add_party_from_json(%s::jsonb)',[json.dumps({'party_name':vendor,'party_type':'Vendor','created_by_id':str(uid)})])
            database.scalar(c,'SELECT add_item_from_json(%s::jsonb)',[json.dumps({'item_name':item,'sale_price':200,'created_by_id':str(uid)})])
            vid=database.scalar(c,'SELECT party_id FROM parties WHERE upper(party_name)=upper(%s)',[vendor])
            pid=database.scalar(c,'SELECT create_purchase(%s,%s,%s::jsonb,%s)',[vid,'2026-10-01',json.dumps([{'item_name':item,'qty':1,'unit_price':'123.45','serials':[{'serial':'P4-'+suffix}]}]),uid]);c.commit()
        journal=self.e.restore(self.good,self.info['archive_sha256']);self.remember()
        self.assertEqual(config.active(self.root),journal['new']);self.assertTrue((self.folder/journal['rescue']).is_file())
        with contextlib.closing(database.connect(journal['new']['database'])) as c:
            database.integrity(c,self.root/journal['new']['media'])
            self.assertEqual(database.scalar(c,'SELECT count(*) FROM django_session'),0)
            self.assertEqual(database.scalar(c,'SELECT count(*) FROM purchaseinvoices WHERE purchase_invoice_id=%s',[pid]),0)
        with contextlib.closing(database.connect(self.original['database'])) as c:
            self.assertEqual(str(database.scalar(c,'SELECT total_amount FROM purchaseinvoices WHERE purchase_invoice_id=%s',[pid])),'123.45')
        self.e.recover(commit=True)
        self.assertEqual(read(self.e.control/'restore-journal.json')['stage'],'committed')
        self.assertTrue((self.root/journal['old']['media']).is_dir())
        # Private test pointer only: restore the test engine's original generation.
        atomic(self.e.control/'active.json',self.original)
    def test_08_failed_candidate_and_incomplete_switch_keep_old(self):
        original=self.e.pg
        def fail(tool,args,*a,**kw):
            if tool=='pg_restore' and '--dbname' in args:raise RuntimeError('Injected candidate failure')
            return original(tool,args,*a,**kw)
        with patch.object(self.e,'pg',side_effect=fail),self.assertRaises(RuntimeError):self.e.restore(self.good,self.info['archive_sha256'])
        self.remember();self.assertEqual(config.active(self.root),self.original)
        journal=self.e.restore(self.good,self.info['archive_sha256']);self.remember()
        self.assertEqual(journal['stage'],'awaiting_health')
        self.e.recover()
        self.assertEqual(config.active(self.root),self.original)
        self.assertEqual(read(self.e.control/'restore-journal.json')['stage'],'rolled_back')
    def test_09_thirty_normal_backups_and_rescue_protection(self):
        folder=self.root/'rotation';folder.mkdir();e=Engine(self.root,folder)
        for n in range(32):
            target=self.change_zip('rotate'+str(n)+'.zip',lambda p,n=n:(p/'manifest.json').write_text(json.dumps(dict(read(p/'manifest.json'),created_utc=f'2026-09-{n//24+1:02d}T{n%24:02d}:00:00+00:00'))))
            shutil.move(target,folder/f'Financee_Offline_Backup_{n:02d}.zip')
        rescue=folder/'Financee_Offline_Rescue_keep.zip';shutil.copy(self.good,rescue)
        unknown=folder/'Financee_Offline_Backup_corrupt.zip';unknown.write_bytes(b'broken')
        e.rotate()
        self.assertEqual(len(list(folder.glob('Financee_Offline_Backup_*.zip'))),31)
        self.assertFalse((folder/'Financee_Offline_Backup_00.zip').exists());self.assertTrue(rescue.exists() and unknown.exists())
    def test_10_foreign_installation_zips_are_not_rotated(self):
        folder=self.root/'foreign';folder.mkdir();e=Engine(self.root,folder)
        source=self.change_zip('foreign.zip',lambda p:(p/'manifest.json').write_text(json.dumps(dict(read(p/'manifest.json'),installation_id='f'*32))))
        for n in range(32):shutil.copy(source,folder/f'Financee_Offline_Backup_foreign{n}.zip')
        e.rotate();self.assertEqual(len(list(folder.glob('*.zip'))),32)
    def test_11_restore_barrier_and_deadline(self):
        from django.test import RequestFactory,override_settings
        from django.http import HttpResponse
        from local.backups.gate import MaintenanceMiddleware
        atomic(self.e.control/'restore-journal.json',{'stage':'awaiting_health'})
        try:
            with override_settings(OFFLINE_CUSTOMER_ROOT=str(self.root),OFFLINE_GENERATION='initial'):
                middleware=MaintenanceMiddleware(lambda r:HttpResponse('ok'))
                self.assertEqual(middleware(RequestFactory().get('/home/')).status_code,503)
                self.assertEqual(middleware(RequestFactory().get('/health/')).status_code,200)
        finally:atomic(self.e.control/'restore-journal.json',{'stage':'rolled_back'})
        with contextlib.closing(database.connect(self.original['database'])) as c:
            with self.assertRaises(TimeoutError):database.fingerprints(c,time.monotonic()-1)
    def test_12_published_zip_recovers_status_without_duplicate_daily_job(self):
        atomic(self.e.state,{'state':'running','last_success':None})
        self.assertFalse(self.e.due())
        count=len(list(self.folder.glob('Financee_Offline_Backup_*.zip')))
        self.e.backup(reason='daily_or_catchup')
        self.assertEqual(len(list(self.folder.glob('Financee_Offline_Backup_*.zip'))),count)
    def test_13_rotation_error_keeps_published_success(self):
        with patch.object(self.e,'rotate',side_effect=PermissionError('denied')):new=self.e.backup()
        self.assertTrue(new.is_file());self.assertEqual(self.e.status()['state'],'complete')
        self.assertIn('Access denied',self.e.status()['last_error'])
    def test_14_missing_media_prevents_publication(self):
        shutil.rmtree(self.root/'Data/media')
        try:
            with self.assertRaises((FileNotFoundError,AssertionError,ValueError)):self.e.backup()
        finally:shutil.copytree('/customer/Data/media',self.root/'Data/media')

    def test_15_missed_days_create_one_catchup(self):
        folder=self.root/'catchup';folder.mkdir();e=Engine(self.root,folder)
        past=datetime.now(timezone.utc)-timedelta(days=5)
        old=self.change_zip('past.zip',lambda p:(p/'manifest.json').write_text(json.dumps(dict(read(p/'manifest.json'),created_utc=past.isoformat(),local_day=past.date().isoformat()))))
        target=folder/'Financee_Offline_Backup_past.zip';shutil.move(old,target)
        atomic(e.state,{'state':'complete','last_success':{'filename':target.name,'created_utc':past.isoformat(),'local_day':past.date().isoformat()}})
        self.assertTrue(e.due());e.backup(reason='daily_or_catchup')
        self.assertFalse(e.due());self.assertEqual(len(list(folder.glob('*.zip'))),2)
    def test_16_killed_backup_never_publishes_and_owned_staging_is_reclaimed(self):
        before={f.name:archive.digest(f) for f in self.folder.glob('*.zip')}
        code="""import sys,time
from local.backups.engine import Engine
from local.backups import archive
def interrupted(*a):print('staged',flush=True);time.sleep(60)
archive.pack=interrupted
Engine(sys.argv[1],sys.argv[2]).backup()
"""
        child=subprocess.Popen([sys.executable,'-c',code,str(self.root),str(self.folder)],stdout=subprocess.PIPE,text=True)
        try:self.assertEqual(child.stdout.readline().strip(),'staged')
        finally:child.kill();child.wait();child.stdout.close()
        self.assertEqual({f.name:archive.digest(f) for f in self.folder.glob('*.zip')},before)
        self.assertTrue(list(self.folder.glob('.financee-staging-*')))
        self.e.backup();self.assertFalse(list(self.folder.glob('.financee-staging-*')))
    def test_17_busy_stream_drain_times_out_and_releases_intent(self):
        code="""import sys,time
from pathlib import Path
from local.backups.files import lock
with lock(Path(sys.argv[1]),exclusive=False):
 print('shared',flush=True);time.sleep(60)
"""
        child=subprocess.Popen([sys.executable,'-c',code,str(self.e.control/'maintenance/gate.lock')],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'shared')
            with self.assertRaises(Busy):
                with pause(self.root,timeout=.1):pass
            with lock(self.e.control/'maintenance/intent.lock',exclusive=False):pass
        finally:child.kill();child.wait();child.stdout.close()

if __name__=='__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings')
    import django;django.setup();unittest.main(verbosity=2)
