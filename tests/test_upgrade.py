"""Upgrade policy, ownership and interruption guards; no live runtime mutations."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from installer.upgrade import check_policy,verify_program,pending,union_ownership,Upgrade
from installer.payload import digest
from launcher.storage import atomic,read,LauncherError
from launcher.controller import Controller
from launcher.installation import Installation

class UpgradePolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads((Path(__file__).resolve().parents[1]/'upgrades/0.8.0-phase8.json').read_text())
        self.old={'version':'0.7.0-phase7','schema':2,'architecture':'arm64','service_images':{'db':'db','redis':'redis','nginx':'nginx'}}
        self.new=dict(self.old,version='0.8.0-phase8')
    def test_supported_previous_releases(self):
        for v in self.policy['from_versions']:check_policy(dict(self.old,version=v),self.new,self.policy)
    def test_reject_equal_downgrade_unknown_or_future_schema(self):
        for values in ({'version':'0.8.0-phase8'},{'version':'0.9.0-phase9'},{'version':'0.6.0-phase6'},{'schema':3},{'architecture':'amd64'}):
            with self.subTest(values=values),self.assertRaises(LauncherError):check_policy(dict(self.old,**values),self.new,self.policy)
    def test_reject_storage_component_replacement(self):
        for service in ('db','redis','nginx'):
            target=copy.deepcopy(self.new);target['service_images'][service]='foreign'
            with self.subTest(service=service),self.assertRaises(LauncherError):check_policy(self.old,target,self.policy)
    def test_policy_requires_explicit_preservation_and_migration_contract(self):
        for key,value in [('migration_policy','anything'),('preserve_business_fingerprints',False),('postgres_major',17),('format',2),('target_schema',3)]:
            with self.subTest(key=key),self.assertRaises(LauncherError):check_policy(self.old,self.new,dict(self.policy,**{key:value}))
    def test_version_order_even_if_policy_accidentally_allows_downgrade(self):
        source=dict(self.old,version='0.9.0-phase9')
        with self.assertRaises(LauncherError):check_policy(source,self.new,dict(self.policy,from_versions=['0.9.0-phase9']))

class UpgradeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.program=self.root/'program';self.program.mkdir()
        for name in ('compose.yml','nginx.conf'):(self.program/name).write_text(name)
        self.release={'format':1,'product':'Financee_Offline','files':{n:digest(self.program/n) for n in ('compose.yml','nginx.conf')},'service_images':{k:k for k in ('db','web','redis','nginx','backup')}}
        atomic(self.program/'release.json',self.release)
    def tearDown(self):self.tmp.cleanup()
    def test_previous_program_hash_and_path_guards(self):
        verify_program(self.program);(self.program/'nginx.conf').write_text('changed')
        with self.assertRaises(LauncherError):verify_program(self.program)
    def test_previous_program_cannot_escape_root(self):
        outside=self.root/'outside';outside.write_text('outside');self.release['files']['../outside']=digest(outside);atomic(self.program/'release.json',self.release)
        with self.assertRaises(LauncherError):verify_program(self.program)
    def test_pending_only_committed_and_rollback_are_terminal(self):
        for stage in ('staged','rescue_saved','target_bound','awaiting_health','rolling_back'):
            atomic(self.root/'Config/upgrade-journal.json',{'stage':stage});self.assertTrue(pending(self.root))
        for stage in ('committed','rolled_back'):
            atomic(self.root/'Config/upgrade-journal.json',{'stage':stage});self.assertFalse(pending(self.root))
    def test_normal_start_refuses_pending_upgrade_before_runtime_commands(self):
        atomic(self.root/'Config/upgrade-journal.json',{'stage':'target_bound'})
        c=object.__new__(Controller);c.installation=Mock(root=self.root);c.ensure_runtime=Mock()
        with self.assertRaisesRegex(LauncherError,'interrupted upgrade'):c._start()
        c.ensure_runtime.assert_not_called()
    def test_snapshot_refuses_links(self):
        (self.program/'link').symlink_to(self.root/'other');u=object.__new__(Upgrade)
        with self.assertRaises(LauncherError):u.snapshot(self.program,self.root/'copy')
    def test_changed_confirmation_does_not_open_runtime(self):
        u=object.__new__(Upgrade);u.consent=Mock(return_value='current');u.prepare=Mock()
        with self.assertRaises(LauncherError):u.apply({'confirmation':'reviewed'},'reviewed')
        u.prepare.assert_not_called()
    def test_union_rejects_unknown_image_before_stop(self):
        old=Mock();new=Mock();old.installation.project='financee_offline_fixture';old.release=self.release;new.release=self.release
        old.image_ids={k:k for k in self.release['service_images']};new.image_ids=old.image_ids
        old.command.side_effect=['id',json.dumps([{'Config':{'Labels':{'com.docker.compose.project':'financee_offline_fixture','com.docker.compose.service':'web'}},'Image':'foreign'}])]
        with self.assertRaisesRegex(LauncherError,'foreign image'):union_ownership(old,new)
        self.assertEqual(old.command.call_count,2)

if __name__=='__main__':unittest.main()

class UpgradeRecoveryOwnershipTests(unittest.TestCase):
    def controllers(self):
        old=Mock();new=Mock();old.installation.project='financee_offline_fixture';old.installation.port=18769;old.installation.volume='financee_offline_fixture_database'
        for c in (old,new):c.release={'service_images':{k:k for k in ('db','redis','web','backup','nginx')}};c.image_ids={k:k for k in ('db','redis','web','backup','nginx')}
        old.customer_mount_matches.side_effect=lambda path:path=='/customer-fixture'
        return old,new
    def value(self,service):return {'Config':{'Labels':{'com.docker.compose.project':'financee_offline_fixture','com.docker.compose.service':service}},'Image':service,'State':{'Running':True},'Mounts':[],'HostConfig':{'PortBindings':{'80/tcp':[{'HostIp':'127.0.0.1','HostPort':'18769'}]}}}
    def test_verified_own_proxy_is_returned_without_requiring_web_health(self):
        old,new=self.controllers();old.command.side_effect=['id',json.dumps([self.value('nginx')])]
        self.assertEqual(union_ownership(old,new),{'nginx'})
    def test_foreign_folder_volume_and_lan_binding_are_refused(self):
        for service in ('web','db','nginx'):
            old,new=self.controllers();v=self.value(service)
            if service=='web':v['Mounts']=[{'Destination':'/customer','Source':'/foreign'}]
            if service=='db':v['Mounts']=[{'Destination':'/var/lib/postgresql/data','Name':'foreign_volume'}]
            if service=='nginx':v['HostConfig']['PortBindings']['80/tcp'][0]['HostIp']='0.0.0.0'
            old.command.side_effect=['id',json.dumps([v])]
            with self.subTest(service=service),self.assertRaises(LauncherError):union_ownership(old,new)
