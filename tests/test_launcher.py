"""Host-only lifecycle guards. No Docker daemon, business data or OS hooks changed."""
import hashlib,json,plistlib,socket,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from launcher.controller import Controller
from launcher.installation import Installation,env_values
from launcher.storage import LauncherError,atomic,lock
from launcher.system import System,platform_key
from launcher import integration
from launcher.confirmation import RestoreConsent

class FakeSystem:
    def __init__(self):
        self.calls=[];self.endpoint='unix:///test/docker.sock';self.containers=[];self.volume=True;self.off=False;self.started=0;self.urls=[]
    def execute(self,args,env=None,timeout=60):
        self.calls.append(args);parts=args[3:] if args[1:3]==['--context','test'] else args[1:]
        if parts[:2]==['context','inspect']:return json.dumps(self.endpoint)
        if parts[0]=='info':
            if self.off:raise LauncherError('offline')
            return json.dumps({'Architecture':'aarch64','OSType':'linux'})
        if parts[:2]==['image','inspect']:return json.dumps([{'Id':'sha256:app','Architecture':'arm64','Os':'linux'}])
        if parts[:2]==['volume','inspect']:
            if not self.volume:raise LauncherError('not found')
            return '[]'
        if parts[0]=='ps':return 'owned' if self.containers else ''
        if parts[0]=='inspect':return json.dumps(self.containers)
        return ''
    def start_docker(self):self.started+=1;self.off=False
    def browser(self,url):self.urls.append(url)

class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.install=Installation.create(self.root/'Customer',18781,'test')
        self.program=self.root/'Program';self.program.mkdir();(self.program/'compose.yml').write_text('fixture')
        atomic(self.program/'release.json',{'format':1,'product':'Financee_Offline','version':'0.5.0-phase5','schema':2,'architecture':'arm64','files':{'compose.yml':hashlib.sha256(b'fixture').hexdigest()},'images':[{'reference':'app:5','id':'sha256:app'}],'service_images':dict.fromkeys(['db','redis','web','backup','nginx'],'sha256:app')})
        self.system=FakeSystem();self.patches=[patch('launcher.controller.docker_path',return_value='/fixture/docker'),patch('launcher.controller.platform_key',return_value=('macos-arm64','arm64'))]
        for p in self.patches:p.start()
        self.c=Controller(self.install,self.program,self.system)
        self.c.health=lambda:None;self.c.port_busy=lambda:False
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def health(self,**changes):
        return dict(product='Financee_Offline',installation_id=self.install.data['id'],build='0.5.0-phase5',generation='initial',schema=2,setup_complete=True,**changes)
    def mutations(self):return [c for c in self.system.calls if any(v in c for v in ('stop','up','run','exec'))]
    def container(self,service='web',**changes):
        value={'Image':'sha256:app','Config':{'Labels':{'com.docker.compose.service':service}},'Mounts':[{'Destination':'/customer','Source':str(self.install.root)}]};value.update(changes);return value
    def test_distinct_installations_random_credentials_and_empty_setup(self):
        other=Installation.create(self.root/'Other',18782,'test')
        a=env_values(self.install.root/'Config/runtime.env');b=env_values(other.root/'Config/runtime.env')
        self.assertNotEqual(a['SECRET_KEY'],b['SECRET_KEY']);self.assertNotEqual(a['DB_PASSWORD'],b['DB_PASSWORD']);self.assertNotEqual(self.install.project,other.project)
        self.assertFalse(self.install.data['initialized']);self.assertFalse(self.install.data['start_at_signin']);self.assertFalse(self.mutations())
    def test_existing_folder_never_reinitialized(self):
        before=(self.install.root/'Config/runtime.env').read_bytes()
        with self.assertRaisesRegex(LauncherError,'empty folder'):Installation.create(self.install.root,18781,'test')
        self.assertEqual(before,(self.install.root/'Config/runtime.env').read_bytes())
    def test_adoption_preserves_identity_credentials(self):
        before=(self.install.root/'Config/runtime.env').read_bytes();self.install.path.unlink()
        adopted=Installation.adopt(self.install.root,'test');self.assertEqual(adopted.data['id'],self.install.data['id']);self.assertEqual(before,(adopted.root/'Config/runtime.env').read_bytes())
    def test_recorded_path_mismatch_refused(self):
        p=self.install.root/'Config/compose.env';p.write_text(p.read_text().replace('HTTP_PORT=18781','HTTP_PORT=18782'))
        with self.assertRaisesRegex(LauncherError,'paths or port'):Installation(self.install.root)
    def test_spaces_unicode_dollar_and_quote_paths_round_trip(self):
        other=Installation.create(self.root/"Company's AED $cash — Dubai",18782,'test')
        self.assertEqual(env_values(other.root/'Config/compose.env')['CUSTOMER_DIR'],str(other.root));self.assertEqual(Installation(other.root).project,other.project)
    def test_restore_consent_requires_exact_typed_phrase(self):
        consent=RestoreConsent('sha256')
        for text in ('','yes','restore','RESTORE '):
            with self.assertRaisesRegex(LauncherError,'Type RESTORE'):consent.confirm(text)
        self.assertFalse(consent.used);self.assertEqual(consent.confirm('RESTORE'),'sha256')
    def test_restore_consent_is_single_use(self):
        consent=RestoreConsent('sha256');consent.confirm('RESTORE')
        with self.assertRaisesRegex(LauncherError,'already used'):consent.confirm('RESTORE')
    def test_tampered_program_refused(self):
        (self.program/'compose.yml').write_text('changed')
        with self.assertRaisesRegex(LauncherError,'verification'):Controller(self.install,self.program,self.system)
    def test_remote_context_refused_before_daemon_contact(self):
        self.system.endpoint='ssh://example.invalid'
        with self.assertRaisesRegex(LauncherError,'remote'):self.c.start(False)
        self.assertFalse(any('info' in c for c in self.system.calls));self.assertFalse(self.mutations())
    def test_docker_off_starts_runtime_without_global_stop(self):
        self.system.off=True;self.c.ensure_runtime();self.assertEqual(self.system.started,1);self.assertFalse(self.mutations())
    def test_missing_image_never_pulls(self):
        old=self.system.execute
        def execute(args,**kwargs):
            if 'image' in args:raise LauncherError('missing')
            return old(args,**kwargs)
        self.system.execute=execute
        with self.assertRaisesRegex(LauncherError,'missing'):self.c.start(False)
        self.assertFalse(self.mutations());self.assertFalse(any('pull' in c for c in self.system.calls))
    def test_wrong_cached_image_refused(self):
        self.c.release['images'][0]['id']='sha256:other'
        with self.assertRaisesRegex(LauncherError,'differs'):self.c.start(False)
        self.assertFalse(self.mutations())
    def test_missing_owned_volume_never_initializes_blank_database(self):
        self.install.data['initialized']=True;self.system.volume=False
        with self.assertRaisesRegex(LauncherError,'volume is missing'):self.c.start(False)
        self.assertFalse(self.mutations())
    def test_occupied_port_refused_before_start_or_stop(self):
        self.c.port_busy=lambda:True
        with self.assertRaisesRegex(LauncherError,'occupied'):self.c.start(False)
        self.assertFalse(self.mutations());self.assertFalse(self.system.urls)
    def test_other_financee_identity_on_port_refused(self):
        value=self.health();value['installation_id']='another';self.c.health=lambda:value;self.c.port_busy=lambda:True
        with self.assertRaisesRegex(LauncherError,'occupied'):self.c.start(False)
        self.assertFalse(self.mutations())
    def test_already_running_reuses_without_migrations_or_restart(self):
        self.c.health=self.health;value=self.c.start();self.assertTrue(value['setup_complete']);self.assertFalse(self.mutations());self.assertTrue(self.system.urls[0].endswith('/home/'))
    def test_status_does_not_start_unavailable_docker(self):
        self.system.off=True;self.assertIn('unavailable',self.c.status());self.assertEqual(self.system.started,0);self.assertFalse(self.mutations())
    def test_status_reports_running_without_mutations(self):
        self.c.health=self.health;self.assertIn('running',self.c.status());self.assertFalse(self.mutations())
    def test_health_uses_fixed_loopback_http_without_proxy_or_redirects(self):
        with patch('launcher.controller.http.client.HTTPConnection') as make:
            conn=make.return_value;response=conn.getresponse.return_value;response.status=200;response.read.return_value=json.dumps(self.health()).encode()
            value=Controller.health(self.c)
            self.assertEqual(value['installation_id'],self.install.data['id']);make.assert_called_once_with('127.0.0.1',18781,timeout=2);conn.request.assert_called_once_with('GET','/health/');response.read.assert_called_once_with(65536);conn.close.assert_called_once()
    def test_health_redirect_is_refused(self):
        with patch('launcher.controller.http.client.HTTPConnection') as make:
            make.return_value.getresponse.return_value.status=302
            self.assertIsNone(Controller.health(self.c));self.assertIn('302',self.c.last_health_error)
    def test_health_errors_are_visible_for_diagnostics(self):
        with patch('launcher.controller.http.client.HTTPConnection',side_effect=OSError('local unavailable')):
            self.assertIsNone(Controller.health(self.c));self.assertIn('local unavailable',self.c.last_health_error)
    def test_setup_incomplete_opens_setup(self):
        value=self.health();value['setup_complete']=False;self.c.health=lambda:value;self.c.start();self.assertTrue(self.system.urls[0].endswith('/setup/'))
    def test_different_running_version_never_implicitly_upgrades(self):
        value=self.health();value['build']='0.4.0-phase4';self.c.health=lambda:value
        with self.assertRaisesRegex(LauncherError,'version differs'):self.c.start(False)
        self.assertFalse(self.mutations())
    def test_cold_container_image_mismatch_refused(self):
        self.system.containers=[self.container(Image='sha256:old')]
        with self.assertRaisesRegex(LauncherError,'another runtime image'):self.c.start(False)
        self.assertFalse(self.mutations())
    def test_mac_desktop_mount_alias_matches_only_confirmed_runtime(self):
        source='/host_mnt'+str(self.install.root);self.assertFalse(self.c.customer_mount_matches(source))
        self.c.desktop_runtime=True;self.assertTrue(self.c.customer_mount_matches(source))
        self.assertFalse(self.c.customer_mount_matches('/host_mnt/another-customer'))
    def test_mac_alias_is_not_applied_to_windows_or_other_runtime(self):
        self.c.desktop_runtime=True;self.c.platform_name='windows-amd64'
        self.assertFalse(self.c.customer_mount_matches('/host_mnt'+str(self.install.root)))
    def test_foreign_customer_mount_refused(self):
        self.system.containers=[self.container(Mounts=[{'Destination':'/customer','Source':'/foreign'}])]
        with self.assertRaisesRegex(LauncherError,'another customer'):self.c.stop()
        self.assertFalse(self.mutations())
    def test_unexpected_service_refused(self):
        self.system.containers=[self.container('unrecognized')]
        with self.assertRaisesRegex(LauncherError,'unexpected'):self.c.stop()
        self.assertFalse(self.mutations())
    def test_stop_is_project_scoped_without_volume_removal(self):
        self.c.stop();calls=self.mutations();self.assertEqual(len(calls),1);self.assertIn(self.install.project,calls[0]);self.assertEqual(calls[0][-1],'stop');self.assertNotIn('down',calls[0]);self.assertNotIn('-v',calls[0])
    def test_duplicate_operation_rejected(self):
        with lock(self.install.root/'Config/controller.lock'):
            with self.assertRaisesRegex(LauncherError,'in progress'):self.c.start(False)
        self.assertFalse(self.system.calls)
    def test_corrupt_json_refuses_overwrite(self):
        self.install.path.write_text('{invalid')
        with self.assertRaises(ValueError):Installation(self.install.root)
        self.assertEqual(self.install.path.read_text(),'{invalid')
    def test_timeout_has_actionable_message(self):
        with patch('launcher.system.subprocess.run',side_effect=subprocess.TimeoutExpired('docker',8)):
            with self.assertRaisesRegex(LauncherError,'did not respond'):System().execute(['docker','info'])
    def test_unsupported_architecture_refused(self):
        with patch('launcher.system.platform.system',return_value='Darwin'),patch('launcher.system.platform.machine',return_value='x86_64'):
            with self.assertRaisesRegex(LauncherError,'not a supported'):platform_key()
    def test_mac_shortcut_never_overwrites_existing(self):
        app=self.root/'Financee.app';app.mkdir();desktop=self.root/'Desktop'
        with patch('launcher.integration.sys.platform','darwin'):
            shortcut=integration.desktop_shortcut(self.install,app,desktop);self.assertEqual(shortcut.resolve(),app)
            other=self.root/'Other.app';other.mkdir()
            with self.assertRaisesRegex(LauncherError,'preserved'):integration.desktop_shortcut(self.install,other,desktop)
    def test_signin_opt_in_and_disable_are_scoped_to_private_fixture(self):
        app=self.root/'Financee.app';binary=app/'Contents/MacOS/Financee';binary.parent.mkdir(parents=True);binary.write_bytes(b'fixture');agents=self.root/'LaunchAgents'
        with patch('launcher.integration.sys.platform','darwin'):
            integration.signin(self.install,True,app,agents);path=next(agents.glob('*.plist'))
            with path.open('rb') as f:record=plistlib.load(f)
            self.assertTrue(record['RunAtLoad']);self.assertEqual(record['ProgramArguments'],[str(binary)]);self.assertTrue(self.install.data['start_at_signin'])
            integration.signin(self.install,False,app,agents);self.assertFalse(path.exists());self.assertFalse(self.install.data['start_at_signin'])

if __name__=='__main__':unittest.main(verbosity=2)
