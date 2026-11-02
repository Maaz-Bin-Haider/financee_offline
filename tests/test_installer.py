"""Installation failure boundaries; real temporary tar/config files, fake OS/runtime.
No shared Docker service, WSL feature, customer database or OS hook is changed.
"""
import hashlib,io,json,os,subprocess,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from installer.payload import Payload,digest,https_url,HTTPSRedirect
from installer.controller import Setup,prepare_uninstall
from installer.windows_host import assess,local_context
from launcher.storage import LauncherError,atomic,read,lock
from launcher.installation import Installation
from launcher.system import System,docker_path

class Runtime:
    def __init__(self,images,configs=None):
        self.configs=configs or {};self.convert_ids=False
        self.images=images;self.calls=[];self.endpoint='npipe:////./pipe/dockerDesktopLinuxEngine';self.arch='x86_64';self.mode='linux';self.cached={};self.loaded=False;self.off=False
    def execute(self,args,**kw):
        self.calls.append(args);parts=args[3:] if args[1:3]==['--context','desktop-linux'] else args[1:]
        if parts[:2]==['context','inspect']:return json.dumps(self.endpoint)
        if self.off:raise LauncherError('daemon unavailable')
        if parts[0]=='info':return json.dumps({'Architecture':self.arch,'OSType':self.mode})
        if parts[:2]==['compose','version']:return '2.40.0'
        if parts[:2]==['image','ls']:return '\n'.join(self.cached.values())
        if parts[:2]==['image','load']:
            self.loaded=True;self.cached={i['reference']:('sha256:'+hashlib.sha256(('converted '+i['id']).encode()).hexdigest() if self.convert_ids else i['id']) for i in self.images};return ''
        if parts[:2]==['image','save']:
            output=Path(parts[3]);references=parts[4:];manifest=[]
            with tarfile.open(output,'w') as tar:
                def member(name,body):
                    item=tarfile.TarInfo(name);item.size=len(body);tar.addfile(item,io.BytesIO(body))
                for ref in references:
                    if ref not in self.configs:raise LauncherError('unverifiable image contents')
                    data=self.configs[ref];name=hashlib.sha256(data).hexdigest()+'.json';member(name,data)
                    manifest.append({'Config':name,'RepoTags':[ref],'Layers':[]})
                member('manifest.json',json.dumps(manifest).encode())
            return ''
        if parts[:2]==['image','inspect']:
            names=parts[2:];result=[]
            for name in names:
                refs=[ref for ref,value in self.cached.items() if value==name or ref==name]
                if not refs:raise LauncherError('missing image')
                ref=refs[0];result.append({'Id':self.cached[ref],'RepoTags':refs,'RepoDigests':[],'Architecture':'amd64','Os':'linux'})
            return json.dumps(result)
        raise AssertionError(args)

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.program=self.root/'program';self.program.mkdir()
        (self.program/'compose.yml').write_text('services: {}\n');(self.program/'nginx.conf').write_text('fixture')
        self.images=[];self.configs={}
        for n in range(4):
            config=json.dumps({'architecture':'amd64','os':'linux','fixture':n}).encode();identity=hashlib.sha256(config).hexdigest();name=identity+'.json';self.configs[name]=config
            self.images.append({'reference':'financee-offline-payload:amd64-'+identity,'id':'sha256:'+identity})
        self.archive=self.root/'images.tar';self.make_archive(self.archive)
        release={'format':1,'product':'Financee_Offline','version':'0.5.0-phase5','schema':2,'architecture':'amd64','images':self.images,'files':{n:digest(self.program/n) for n in ('compose.yml','nginx.conf')},'service_images':dict(zip(('db','redis','web','nginx','backup'),[i['id'] for i in self.images]+[self.images[2]['id']]))}
        atomic(self.program/'release.json',release);self.delivery={'format':1,'product':'Financee_Offline','architecture':'amd64','release_sha256':digest(self.program/'release.json'),'archive':{'filename':'images.tar','bytes':self.archive.stat().st_size,'sha256':digest(self.archive)}};atomic(self.program/'delivery.json',self.delivery)
        self.payload=Payload(self.program);self.runtime=Runtime(self.images,{i['reference']:config for i,config in zip(self.images,self.configs.values())})
    def tearDown(self):self.tmp.cleanup()
    def make_archive(self,path,arch=None,extra=False):
        manifest=[]
        with tarfile.open(path,'w') as tar:
            def member(name,body):
                value=tarfile.TarInfo(name);value.size=len(body);tar.addfile(value,io.BytesIO(body))
            for (name,config),image in zip(self.configs.items(),self.images):
                if arch:config=json.dumps(dict(json.loads(config),architecture=arch)).encode()
                member(name,config);manifest.append({'Config':name,'RepoTags':[image['reference']],'Layers':[]})
            if extra:manifest[0]['RepoTags'].append('foreign:latest')
            member('manifest.json',json.dumps(manifest).encode())
    def update_archive_digest(self,path):
        self.delivery['archive'].update(bytes=path.stat().st_size,sha256=digest(path));atomic(self.program/'delivery.json',self.delivery);self.payload=Payload(self.program)
    def import_payload(self):return self.payload.import_images(self.archive,self.runtime,'docker','desktop-linux',{})
    def oci_archive(self,bad_binding=False,bad_hash=False):
        blobs=dict(self.configs);manifest=[];top=[];images=[]
        for (config_name,config),image in zip(self.configs.items(),self.images):
            config_sha='sha256:'+hashlib.sha256(config).hexdigest()
            native=json.dumps({'schemaVersion':2,'config':{'digest':'sha256:'+'0'*64 if bad_binding else config_sha},'layers':[]}).encode()
            native_sha=hashlib.sha256(native).hexdigest();blobs['blobs/sha256/'+native_sha]=native
            index=json.dumps({'schemaVersion':2,'manifests':[{'digest':'sha256:'+native_sha,'platform':{'os':'linux','architecture':'amd64'}}]}).encode()
            index_sha=hashlib.sha256(index).hexdigest();blobs['blobs/sha256/'+index_sha]=b'bad' if bad_hash else index
            top.append({'digest':'sha256:'+index_sha,'annotations':{'io.containerd.image.name':'docker.io/library/'+image['reference']}})
            images.append(dict(image,id='sha256:'+index_sha))
            manifest.append({'Config':config_name,'RepoTags':[image['reference']],'Layers':[]})
        blobs['manifest.json']=json.dumps(manifest).encode();blobs['index.json']=json.dumps({'schemaVersion':2,'manifests':top}).encode()
        with tarfile.open(self.archive,'w') as tar:
            for name,body in blobs.items():
                entry=tarfile.TarInfo(name);entry.size=len(body);tar.addfile(entry,io.BytesIO(body))
        self.images=images;release=read(self.program/'release.json');release['images']=images
        release['service_images']=dict(zip(('db','redis','web','nginx','backup'),[i['id'] for i in images]+[images[2]['id']]))
        atomic(self.program/'release.json',release);self.delivery['release_sha256']=digest(self.program/'release.json');self.update_archive_digest(self.archive)
    def test_containerd_oci_index_ids_bound_to_native_configs(self):
        self.oci_archive();self.assertTrue(self.payload.verify_archive(self.archive))
    def test_oci_descriptor_cannot_point_to_different_native_config(self):
        self.oci_archive(bad_binding=True)
        with self.assertRaisesRegex(LauncherError,'contents'):self.payload.verify_archive(self.archive)
    def test_oci_descriptor_hash_must_match_recorded_id(self):
        self.oci_archive(bad_hash=True)
        with self.assertRaisesRegex(LauncherError,'contents'):self.payload.verify_archive(self.archive)
    def test_exact_archive_import_and_post_load_identities(self):
        self.import_payload();self.assertTrue(self.runtime.loaded);self.assertEqual(self.runtime.cached,{i['reference']:i['id'] for i in self.images})
    def test_classic_to_containerd_id_conversion_requires_content_proof(self):
        self.runtime.convert_ids=True;resolved=self.import_payload()
        self.assertTrue(self.runtime.loaded)
        self.assertEqual(resolved,{i['id']:self.runtime.cached[i['reference']] for i in self.images})
        self.assertTrue(all(key!=value for key,value in resolved.items()))
        self.assertTrue(any(c[3:5]==['image','save'] for c in self.runtime.calls))
    def test_repeat_import_accepts_proven_destination_ids_without_reloading(self):
        self.runtime.convert_ids=True;first=self.import_payload();self.runtime.loaded=False
        self.assertEqual(first,self.import_payload());self.assertFalse(self.runtime.loaded)
    def test_changed_content_after_import_is_refused(self):
        self.runtime.convert_ids=True
        self.runtime.configs[self.images[0]['reference']]=json.dumps({'architecture':'amd64','os':'linux','unexpected':True}).encode()
        with self.assertRaisesRegex(LauncherError,'overwrite'):self.import_payload()
    def test_matching_cache_is_reused_without_download(self):
        path=self.payload.acquire(self.root/'cache',self.archive)
        with patch('urllib.request.build_opener',side_effect=AssertionError('network')):self.assertEqual(path,self.payload.acquire(self.root/'cache'))
    def test_already_imported_images_do_not_load_twice(self):
        self.import_payload();self.runtime.loaded=False;self.import_payload();self.assertFalse(self.runtime.loaded)
    def test_corrupt_archive_never_contacts_daemon(self):
        with self.archive.open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(LauncherError,'verification'):self.import_payload()
        self.assertFalse(self.runtime.calls)
    def test_wrong_architecture_tar_with_matching_outer_hash_refused(self):
        self.make_archive(self.archive,arch='arm64');self.update_archive_digest(self.archive)
        with self.assertRaisesRegex(LauncherError,'contents'):self.import_payload()
        self.assertFalse(self.runtime.calls)
    def test_extra_image_tag_with_matching_outer_hash_refused(self):
        self.make_archive(self.archive,extra=True);self.update_archive_digest(self.archive)
        with self.assertRaisesRegex(LauncherError,'contents'):self.import_payload()
        self.assertFalse(self.runtime.calls)
    def test_remote_daemon_refused_before_info(self):
        self.runtime.endpoint='ssh://remote.invalid'
        with self.assertRaisesRegex(LauncherError,'remote'):self.import_payload()
        self.assertFalse(any('info' in c for c in self.runtime.calls))
    def test_foreign_tag_not_replaced(self):
        self.runtime.cached={self.images[0]['reference']:'sha256:'+'f'*64}
        self.runtime.configs[self.images[0]['reference']]=json.dumps({'architecture':'amd64','os':'linux','foreign':True}).encode()
        with self.assertRaisesRegex(LauncherError,'overwrite'):self.import_payload()
        self.assertFalse(self.runtime.loaded)
    def test_unavailable_daemon_not_treated_as_missing_images(self):
        self.runtime.off=True
        with self.assertRaisesRegex(LauncherError,'unavailable'):self.import_payload()
        self.assertFalse(self.runtime.loaded)
    def test_wrong_daemon_architecture_refused_before_load(self):
        self.runtime.arch='aarch64'
        with self.assertRaisesRegex(LauncherError,'architecture'):self.import_payload()
        self.assertFalse(self.runtime.loaded)
    def test_windows_container_mode_refused_before_load(self):
        self.runtime.mode='windows'
        with self.assertRaisesRegex(LauncherError,'mode'):self.import_payload()
        self.assertFalse(self.runtime.loaded)
    def test_existing_cache_file_not_overwritten(self):
        cache=self.root/'cache';cache.mkdir();file=cache/'images.tar';file.write_bytes(b'customer file')
        with self.assertRaisesRegex(LauncherError,'different file'):self.payload.acquire(cache,self.archive)
        self.assertEqual(file.read_bytes(),b'customer file')
    def test_failed_download_keeps_previous_files_and_cleans_stage(self):
        self.delivery['archive']['url']='https://downloads.example.invalid/images.tar';atomic(self.program/'delivery.json',self.delivery);payload=Payload(self.program)
        class Broken:
            def open(self,*a,**k):return io.BytesIO(b'wrong data')
        with self.assertRaisesRegex(LauncherError,'verification'):payload.acquire(self.root/'cache',opener=Broken())
        self.assertEqual(list((self.root/'cache').iterdir()),[])
    def test_oversized_download_is_bounded(self):
        self.delivery['archive']['url']='https://downloads.example.invalid/images.tar';atomic(self.program/'delivery.json',self.delivery)
        class Large:
            def open(self,*a,**k):return io.BytesIO(b'x'*20000)
        with self.assertRaisesRegex(LauncherError,'exceeds'):Payload(self.program).acquire(self.root/'cache',opener=Large())
        self.assertEqual(list((self.root/'cache').iterdir()),[])
    def test_disk_full_refused_before_staging_or_network(self):
        with patch('installer.payload.shutil.disk_usage',return_value=type('Space',(),{'free':1})()):
            with self.assertRaisesRegex(LauncherError,'free space'):self.payload.acquire(self.root/'cache',self.archive)
        self.assertFalse(list((self.root/'cache').iterdir()))
    def test_unpublished_development_payload_requests_local_file(self):
        with self.assertRaisesRegex(LauncherError,'no published'):self.payload.acquire(self.root/'cache')
        self.assertFalse(list((self.root/'cache').iterdir()))
    def test_http_and_credentials_refused(self):
        for url in ('http://example.invalid/a','file:///tmp/a','https://user:pass@example.invalid/a','https://example.invalid/a#fragment'):
            with self.assertRaises(LauncherError):https_url(url)
    def test_https_redirect_cannot_downgrade_to_http(self):
        import urllib.request
        with self.assertRaises(LauncherError):HTTPSRedirect().redirect_request(urllib.request.Request('https://example.invalid/a'),None,302,'',{},'http://example.invalid/b')
    def test_program_file_tamper_refused(self):
        (self.program/'compose.yml').write_text('changed')
        with self.assertRaisesRegex(LauncherError,'verification'):Payload(self.program)
    def test_archive_path_traversal_refused(self):
        self.delivery['archive']['filename']='../images.tar';atomic(self.program/'delivery.json',self.delivery)
        with self.assertRaisesRegex(LauncherError,'metadata'):Payload(self.program)
    def test_manifest_mix_and_match_refused(self):
        self.delivery['release_sha256']='0'*64;atomic(self.program/'delivery.json',self.delivery)
        with self.assertRaisesRegex(LauncherError,'mismatched'):Payload(self.program)
    def setup_ready(self):
        setup=Setup(self.program,self.root/'setup.json',self.runtime)
        with patch('installer.controller.docker_path',return_value='docker'):setup.prepare(self.root/'cache',self.archive)
        return setup
    def test_reboot_state_round_trip_does_not_initialize_customer(self):
        setup=Setup(self.program,self.root/'setup.json',self.runtime);setup.prerequisites_requested('boot-1')
        resumed=Setup(self.program,self.root/'setup.json',self.runtime)
        self.assertEqual(resumed.state['boot_id'],'boot-1');self.assertEqual(resumed.state['phase'],'awaiting_prerequisites');self.assertFalse(self.runtime.calls)
    def test_another_release_cannot_reuse_saved_state(self):
        self.setup_ready();self.delivery['test_revision']=2;atomic(self.program/'delivery.json',self.delivery)
        with self.assertRaisesRegex(LauncherError,'another release'):Setup(self.program,self.root/'setup.json',self.runtime)
    def test_customer_not_created_before_payload(self):
        setup=Setup(self.program,self.root/'setup.json',self.runtime);customer=self.root/'Customer'
        with self.assertRaisesRegex(LauncherError,'before selecting'):setup.install(customer,self.root/'prefs.json')
        self.assertFalse(customer.exists())
    def test_interrupted_setup_resumes_same_credentials_and_identity(self):
        setup=self.setup_ready();customer=self.root/'Company AED $ —';preferences=self.root/'prefs.json'
        with patch('installer.controller.docker_path',return_value='docker'),patch('installer.controller.Controller') as controller:
            controller.return_value.start.side_effect=LauncherError('power interruption')
            with self.assertRaisesRegex(LauncherError,'power interruption'):setup.install(customer,preferences)
            original=Installation(customer);key=(customer/'Config/runtime.env').read_bytes()
            resumed=Setup(self.program,self.root/'setup.json',self.runtime);controller.return_value.start.side_effect=None
            result=resumed.install(customer,preferences)
        self.assertEqual(original.data['id'],result.data['id']);self.assertEqual(key,(customer/'Config/runtime.env').read_bytes());self.assertEqual(read(preferences)['customer_directory'],str(customer.resolve()));self.assertEqual(resumed.state['phase'],'ready')
    def test_repair_keeps_existing_data_credentials_and_selected_backup_folder(self):
        setup=self.setup_ready();customer=self.root/'Customer';installation=Installation.create(customer,18840,'desktop-linux')
        (customer/'Data/media/evidence.txt').write_bytes(b'attachment');atomic(customer/'Config/backup-location.json',{'directory':str(self.root/'External backups')})
        before={p.relative_to(customer):p.read_bytes() for p in customer.rglob('*') if p.is_file()}
        with patch('installer.controller.docker_path',return_value='docker'),patch('installer.controller.Controller') as c:setup.install(customer,self.root/'prefs.json',True)
        for path,content in before.items():
            if path.as_posix()!='Config/launcher.json':self.assertEqual(content,(customer/path).read_bytes())
        self.assertEqual(installation.data['id'],Installation(customer).data['id']);c.return_value.start.assert_called_once_with(open_browser=False)
    def test_repair_of_different_release_is_refused_without_start(self):
        setup=self.setup_ready();installation=Installation.create(self.root/'Customer',18840,'desktop-linux')
        installation.data['installed_program']='another release';installation.save()
        before=(installation.root/'Config/runtime.env').read_bytes()
        with patch('installer.controller.docker_path',return_value='docker'),patch('installer.controller.Controller') as c:
            with self.assertRaisesRegex(LauncherError,'another program release'):setup.install(installation.root,self.root/'prefs.json',True)
            c.assert_not_called()
        self.assertEqual(before,(installation.root/'Config/runtime.env').read_bytes())
    def test_failed_folder_choice_can_be_corrected_without_resetting_state(self):
        setup=self.setup_ready();wrong=self.root/'Wrong';wrong.mkdir();(wrong/'business.txt').write_text('preserve')
        with patch('installer.controller.docker_path',return_value='docker'):
            with self.assertRaisesRegex(LauncherError,'empty folder'):setup.install(wrong,self.root/'prefs.json')
        self.assertNotIn('customer_directory',setup.state);self.assertEqual((wrong/'business.txt').read_text(),'preserve')
    def test_uninstall_after_interrupted_first_start_stops_recorded_installation(self):
        setup=self.setup_ready();customer=self.root/'Customer';preferences=self.root/'prefs.json'
        with patch('installer.controller.docker_path',return_value='docker'),patch('installer.controller.Controller') as c:
            c.return_value.start.side_effect=LauncherError('interrupted')
            with self.assertRaisesRegex(LauncherError,'interrupted'):setup.install(customer,preferences)
            self.assertFalse(preferences.exists())
            prepare_uninstall(self.program,preferences,self.root/'receipt.json');c.return_value.stop.assert_called_once()
        self.assertTrue(Installation(customer).path.exists())
    def test_uninstall_stop_failure_preserves_program_and_customer_data(self):
        installation=Installation.create(self.root/'Customer',18840,'desktop-linux');preferences=self.root/'prefs.json';atomic(preferences,{'customer_directory':str(installation.root)})
        with patch('installer.controller.Controller') as c:
            c.return_value.stop.side_effect=LauncherError('foreign container')
            with self.assertRaisesRegex(LauncherError,'foreign'):prepare_uninstall(self.program,preferences,self.root/'receipt.json')
        self.assertTrue((self.program/'release.json').exists());self.assertTrue(installation.path.exists());self.assertFalse((self.root/'receipt.json').exists())
    def test_uninstall_retains_customer_files_and_runtime(self):
        installation=Installation.create(self.root/'Customer',18840,'desktop-linux');preferences=self.root/'prefs.json';atomic(preferences,{'customer_directory':str(installation.root)})
        before=(installation.root/'Config/runtime.env').read_bytes()
        with patch('installer.controller.Controller') as c:prepare_uninstall(self.program,preferences,self.root/'receipt.json');c.return_value.stop.assert_called_once()
        self.assertEqual(before,(installation.root/'Config/runtime.env').read_bytes());self.assertTrue(read(self.root/'receipt.json')['runtime_retained']);self.assertTrue((self.program/'release.json').exists())
    def test_uninstall_refuses_open_customer_window(self):
        installation=Installation.create(self.root/'Customer',18840,'desktop-linux');preferences=self.root/'prefs.json';atomic(preferences,{'customer_directory':str(installation.root)})
        with lock(installation.root/'Config/launcher-window.lock'),patch('installer.controller.Controller') as c:
            with self.assertRaisesRegex(LauncherError,'in progress'):prepare_uninstall(self.program,preferences,self.root/'receipt.json')
            c.assert_not_called()

class PrerequisiteTests(unittest.TestCase):
    def good(self,**changes):return dict(system='Windows',architecture='AMD64',build=26100,product_type=1,ram_bytes=16*1024**3,virtualization=True,slat=True,wsl_version='2.6.1',features={'VirtualMachinePlatform':1},reboot_pending=False,**changes)
    def test_ready_is_never_a_certification_claim(self):
        result=assess(self.good());self.assertTrue(result['ready']);self.assertFalse(result['certified'])
    def test_windows10_explicit_qualification_blocker(self):
        value=self.good();value['build']=19045;self.assertIn('Windows 10',assess(value)['blockers'][0])
    def test_arm_and_32bit_os_refused(self):
        for arch in ('ARM64','x86'):
            value=self.good();value['architecture']=arch;self.assertFalse(assess(value)['ready'])
    def test_server_old_build_and_no_virtualization_refused(self):
        for key,new in [('product_type',3),('build',22000),('virtualization',False),('slat',False),('ram_bytes',4*1024**3)]:
            value=self.good();value[key]=new;self.assertTrue(assess(value)['blockers'])
    def test_reboot_or_old_wsl_requires_recheck(self):
        for key,new in [('reboot_pending',True),('wsl_version','2.1.4'),('wsl_version',None),('features',{})]:
            value=self.good();value[key]=new;self.assertFalse(assess(value)['ready']);self.assertTrue(assess(value)['actions'])
    def test_remote_context_is_never_selected(self):
        runtime=Runtime([]);runtime.endpoint='tcp://127.0.0.1:2375'
        with self.assertRaisesRegex(LauncherError,'local Windows'):local_context(runtime,'docker',{})
        self.assertFalse(any('info' in c for c in runtime.calls))
    def test_replaced_windows_startup_link_is_preserved(self):
        from launcher.integration import windows_remove_link
        with tempfile.TemporaryDirectory() as folder:
            link=Path(folder)/'startup.lnk';link.write_bytes(b'foreign shortcut')
            with patch('launcher.integration.subprocess.run',return_value=type('Result',(),{'stdout':'C:\\Other\\Program.exe'})()):
                with self.assertRaisesRegex(LauncherError,'another program'):windows_remove_link(link,'C:/Financee/Financee Offline.exe')
            self.assertEqual(link.read_bytes(),b'foreign shortcut')
    def test_owned_windows_startup_link_can_be_removed(self):
        from launcher.integration import windows_remove_link
        with tempfile.TemporaryDirectory() as folder:
            link=Path(folder)/'startup.lnk';link.touch()
            with patch('launcher.integration.subprocess.run',return_value=type('Result',(),{'stdout':'C:\\Financee\\Financee Offline.exe\n'})()):windows_remove_link(link,'C:/Financee/Financee Offline.exe')
            self.assertFalse(link.exists())
    def test_windows_per_user_docker_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'Programs/DockerDesktop/resources/bin/docker.exe';file.parent.mkdir(parents=True);file.touch()
            with patch('launcher.system.platform.system',return_value='Windows'),patch('launcher.system.shutil.which',return_value=None),patch.dict(os.environ,{'LOCALAPPDATA':folder}):self.assertEqual(str(file.resolve()),docker_path())

if __name__=='__main__':unittest.main(verbosity=2)
