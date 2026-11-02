"""Mac setup boundaries on private app fixtures. No real app, sign-in entry,
customer database, Docker service, keychain credential or OS setting is changed.
"""
import json,plistlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from installer import macos_host as host
from launcher.storage import LauncherError,atomic,lock
from launcher import integration

class Signer:
    def __init__(self):self.calls=[];self.fail=None
    def execute(self,args,**kw):
        self.calls.append(args)
        if self.fail and self.fail(args):raise LauncherError('signature verification failed')
        return ''

class MacAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.source=self.root/'Download/Financee Test.app';self.folder=self.root/'Home/Applications';self.state=self.root/'State'
        self.make(self.source);self.signer=Signer()
    def tearDown(self):self.tmp.cleanup()
    def make(self,app,version='same',identifier='com.financee.offline.macos.development'):
        (app/'Contents/Resources/program').mkdir(parents=True)
        with (app/'Contents/Info.plist').open('wb') as f:plistlib.dump({'CFBundleIdentifier':identifier},f)
        atomic(app/'Contents/Resources/program/release.json',{'version':version})
        (app/'Contents/MacOS').mkdir();(app/'Contents/MacOS'/app.stem).write_bytes(b'program')
    def test_install_copies_program_only_and_records_receipt(self):
        customer=self.root/'Business';customer.mkdir();(customer/'backup.zip').write_bytes(b'keep')
        target=host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertTrue((target/'Contents/MacOS'/target.stem).is_file());self.assertEqual((customer/'backup.zip').read_bytes(),b'keep')
        self.assertEqual(json.loads((self.state/'program-install.json').read_text())['app'],str(target))
        self.assertEqual({a[0] for a in self.signer.calls},{'/usr/bin/codesign'})
    def test_different_build_is_not_overwritten(self):
        target=self.folder/self.source.name;self.make(target,'other');before=(target/'Contents/Resources/program/release.json').read_bytes()
        with self.assertRaisesRegex(LauncherError,'different'):host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertEqual(before,(target/'Contents/Resources/program/release.json').read_bytes())
    def test_foreign_app_is_not_overwritten(self):
        target=self.folder/self.source.name;self.make(target,identifier='org.other.app')
        with self.assertRaisesRegex(LauncherError,'preserved'):host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertEqual(host.app_info(target)['CFBundleIdentifier'],'org.other.app')
    def test_existing_shortcut_is_preserved(self):
        self.folder.mkdir(parents=True);target=self.folder/self.source.name;target.symlink_to(self.source,target_is_directory=True)
        with self.assertRaisesRegex(LauncherError,'shortcut'):host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertTrue(target.is_symlink())
    def test_same_build_repair_replaces_program_without_customer_changes(self):
        target=host.install_app(self.source,self.folder,self.state,self.signer);binary=target/'Contents/MacOS'/target.stem;binary.write_bytes(b'corrupt program')
        customer=self.root/'Customer';customer.mkdir();(customer/'data').write_bytes(b'accounting')
        host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertEqual(binary.read_bytes(),b'program');self.assertEqual((customer/'data').read_bytes(),b'accounting')
        self.assertEqual(list(self.folder.glob('.*-previous-*.app')),[])
    def test_running_destination_refuses_repair(self):
        target=host.install_app(self.source,self.folder,self.state,self.signer)
        with lock(host.program_lock(target,self.state)):
            with self.assertRaisesRegex(LauncherError,'in progress'):host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertTrue(target.is_dir())
    def test_staging_verification_failure_preserves_current_app(self):
        target=host.install_app(self.source,self.folder,self.state,self.signer);binary=target/'Contents/MacOS'/target.stem;binary.write_bytes(b'current program')
        self.signer.fail=lambda args:'-staging-' in args[-1]
        with self.assertRaisesRegex(LauncherError,'signature'):host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertEqual(binary.read_bytes(),b'current program')
    def test_published_verification_failure_rolls_back(self):
        target=host.install_app(self.source,self.folder,self.state,self.signer);binary=target/'Contents/MacOS'/target.stem;binary.write_bytes(b'current program')
        self.signer.fail=lambda args:args[-1]==str(target)
        with self.assertRaisesRegex(LauncherError,'signature'):host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertEqual(binary.read_bytes(),b'current program')
    def test_receipt_failure_rolls_back_program(self):
        target=host.install_app(self.source,self.folder,self.state,self.signer);binary=target/'Contents/MacOS'/target.stem;binary.write_bytes(b'current program')
        with patch('installer.macos_host.atomic',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertEqual(binary.read_bytes(),b'current program')
    def test_insufficient_staging_space_preserves_app(self):
        with patch('installer.macos_host.shutil.disk_usage',return_value=type('Space',(),{'free':0})()):
            with self.assertRaisesRegex(LauncherError,'free space'):host.install_app(self.source,self.folder,self.state,self.signer)
        self.assertFalse((self.folder/self.source.name).exists());self.assertFalse(list(self.folder.glob('.*.app')))
    def test_mount_workspace_and_translocation_cannot_initialize_business(self):
        for path in (self.source,Path('/Volumes/Financee/Financee.app'),Path('/private/tmp/AppTranslocation/Financee.app')):
            with self.assertRaisesRegex(LauncherError,'Applications'):host.require_installed(path,self.root/'Home')
        self.assertEqual(host.require_installed(self.folder/'Financee.app',self.root/'Home'),self.folder/'Financee.app')
    def test_desktop_alias_uses_app_name_and_preserves_another_alias(self):
        class Installation:data={'development':True}
        desktop=self.root/'Desktop'
        with patch('launcher.integration.sys.platform','darwin'):
            link=integration.desktop_shortcut(Installation(),self.source,desktop,name='Financee Mac Test')
            self.assertEqual(link.resolve(),self.source)
            with self.assertRaisesRegex(LauncherError,'preserved'):integration.desktop_shortcut(Installation(),self.root/'Different.app',desktop,name='Financee Mac Test')
    def test_replaced_signin_entry_is_preserved(self):
        class Installation:
            data={'id':'a'*32,'signin_target':str(self.source),'start_at_signin':True}
            def save(self):raise AssertionError('unexpected save')
        folder=self.root/'LaunchAgents';folder.mkdir();path=folder/('com.financee.offline.'+'a'*32+'.plist')
        with path.open('wb') as f:plistlib.dump({'Label':'com.financee.offline.'+'a'*32,'ProgramArguments':['/different/program']},f)
        with patch('launcher.integration.sys.platform','darwin'):
            with self.assertRaisesRegex(LauncherError,'preserved'):integration.signin(Installation(),False,self.source,folder)
        self.assertTrue(path.exists())

class MacPrerequisites(unittest.TestCase):
    def good(self):return {'system':'Darwin','architecture':'arm64','version':'26.5.2','ram_bytes':16*1024**3,'hypervisor':1,'translated':0}
    def test_native_ready_is_not_customer_certification(self):
        value=host.assess(self.good());self.assertTrue(value['ready']);self.assertFalse(value['certified'])
    def test_intel_rosetta_old_os_low_memory_and_missing_hypervisor_refused(self):
        for key,value in [('architecture','x86_64'),('translated',1),('version','14.8'),('version','28.0'),('ram_bytes',4*1024**3),('hypervisor',0)]:
            check=self.good();check[key]=value;self.assertFalse(host.assess(check)['ready'])
    def test_remote_and_windows_pipe_contexts_refused_before_daemon_info(self):
        for endpoint in ('ssh://host','tcp://localhost:2375','npipe:////./pipe/docker_engine'):
            class System:
                def execute(self,args,**kw):
                    if 'info' in args:raise AssertionError('daemon contacted')
                    return json.dumps(endpoint)
            with self.assertRaisesRegex(LauncherError,'local Mac'):host.local_context(System(),'docker',{})
    def test_local_unix_context_selected_without_switching_global_context(self):
        calls=[]
        class System:
            def execute(self,args,**kw):calls.append(args);return json.dumps('unix:///local/docker.sock')
        self.assertEqual(host.local_context(System(),'docker',{}),'desktop-linux');self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main(verbosity=2)
