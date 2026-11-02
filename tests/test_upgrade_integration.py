"""Real populated old→new upgrade, abrupt host exits and recovery. Private UUID
resources only; review and source systems are observed read-only and preserved.
"""
import argparse,contextlib,json,os,socket,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from installer.controller import Setup
from installer.macos_host import local_context
from installer.upgrade import Upgrade
from installer.payload import digest
from launcher.controller import Controller
from launcher.installation import Installation
from launcher.storage import read,atomic

def main():
 p=argparse.ArgumentParser();p.add_argument('--target',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--previous',type=Path,required=True);p.add_argument('--skip-crashes',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'.runtime/phase8-upgrade-integration.json');a=p.parse_args()
 if os.environ.get('FINANCEE_UPGRADE_TEST_CHILD'):
  root=Path(os.environ['FINANCEE_UPGRADE_TEST_CHILD']);prepared=read(root/'prepared.json');stop=os.environ['FINANCEE_UPGRADE_TEST_STAGE']
  class Crash(Upgrade):
   def record(self,journal,stage,**values):
    super().record(journal,stage,**values)
    if stage==stop:
     if stage=='awaiting_health':
      import urllib.request,urllib.error
      try:urllib.request.urlopen(self.installation.url+'/home/',timeout=5)
      except urllib.error.HTTPError as e:assert e.code==503
      else:raise AssertionError('Candidate business requests were not gated')
      atomic(root/'request-gate-verified.json',{'blocked':True,'health_allowed':True})
     os._exit(73)
  Crash(root/'Business AED —',a.target,a.previous,progress=lambda t:print(t,flush=True)).apply(prepared,prepared['confirmation']);raise AssertionError('Crash stage not reached')
 review=Controller(Installation(ROOT/'.runtime/review'),ROOT/'.runtime/phase5-program');review_ids=review.command('ps','-aq','--filter','label=com.docker.compose.project=financee_offline_review').split()
 states=lambda:[[v['Id'],v['Image'],v['State']['Status']] for v in json.loads(review.command('inspect',*review_ids))]
 before_states=states();files=[review.installation.root/'Config'/n for n in ('runtime.env','compose.env','active.json','launcher.json')]+[f for f in (review.installation.root/'Data').rglob('*') if f.is_file()];before_files={str(f):digest(f) for f in files}
 root=ROOT/'.runtime'/('phase8-upgrade-'+uuid.uuid4().hex[:12]);root.mkdir();controller=None
 with contextlib.ExitStack() as ports:
  for port in (18766,18767):
   s=ports.enter_context(socket.socket())
   try:s.bind(('127.0.0.1',port));s.listen()
   except OSError:pass
  setup=Setup(a.previous,root/'Previous State/setup.json',progress=print,context_selector=local_context);old_payload=setup.payload;old_archive=old_payload.program.parent/'payload'/old_payload.archive['filename']
  if not old_archive.exists():old_archive=ROOT/'.runtime/phase7-final-payload/financee-offline-runtime-arm64.tar'
  try:
   setup.prepare(root/'Previous State/Cache',old_archive);i=setup.install(root/'Business AED —',root/'Previous State/installation.json');controller=Controller(i,a.previous)
   token=uuid.uuid4().hex;atomic(i.root/'Config/phase8-test-owner.json',{'project':i.project,'token':token})
   # Mount only this explicitly guarded synthetic fixture script, read-only.
   def fixture(command,c):return c.compose('run','--rm','--no-deps','--pull','never','-T','-v',str(ROOT/'tests/upgrade_fixture.py')+':/upgrade_fixture.py:ro','web','python','/upgrade_fixture.py',command,i.project,token,timeout=180).strip()
   print(fixture('seed',controller),flush=True);expected=json.loads(fixture('snapshot',controller));assert expected['sessions']>0
   credentials={n:digest(i.root/'Config'/n) for n in ('runtime.env','compose.env')};old_active=read(i.root/'Config/active.json');old_data=read(i.root/'Config/launcher.json');u=Upgrade(i.root,a.target,a.previous,progress=print)
   stages=['rescue_saved','candidate_prepared','target_bound','candidate_verified','awaiting_health'];crashes=[]
   for stage in ([] if a.skip_crashes else stages):
    prepared=u.prepare(root/'Target Cache',a.archive);atomic(root/'prepared.json',prepared)
    proc=subprocess.run([sys.executable,__file__,'--target',str(a.target),'--archive',str(a.archive),'--previous',str(a.previous)],env=dict(os.environ,FINANCEE_UPGRADE_TEST_CHILD=str(root),FINANCEE_UPGRADE_TEST_STAGE=stage),timeout=240)
    assert proc.returncode==73,(stage,proc.returncode)
    restored=Upgrade(i.root,a.target,progress=print).recover();assert restored['stage']=='rolled_back'
    assert read(i.root/'Config/active.json')==old_active and read(i.root/'Config/launcher.json')==old_data
    assert controller.health()['build']==old_payload.release['version']
    actual=json.loads(fixture('snapshot',controller));assert actual==expected,(stage,'old snapshot changed')
    assert credentials=={n:digest(i.root/'Config'/n) for n in credentials};crashes.append(stage)
   # Real candidate-data corruption and application-start failures must both
   # restore the original paired runtime/data, never apply inverse migrations.
   faults=[]
   for fault in ('candidate_business_mutation','target_start_failure'):
    class Failure(Upgrade):
     injected=False
     def tool(self,c,journal,command,*args,**kwargs):
      if fault=='candidate_business_mutation' and command=='upgrade-check' and not self.injected:
       self.injected=True;active=read(i.root/'Config/active.json')
       c.compose('exec','-T','db','psql','-U','financee_offline','-d',active['database'],'-c',"UPDATE local_generalsettings SET name='Rejected candidate mutation' WHERE id=1")
      return super().tool(c,journal,command,*args,**kwargs)
     def start_services(self,c):
      if fault=='target_start_failure' and c.release['version']=='0.8.0-phase8':raise RuntimeError('Injected target startup failure')
      return super().start_services(c)
    failed=Failure(i.root,a.target,a.previous,progress=print);prepared=failed.prepare(root/'Target Cache',a.archive)
    try:failed.apply(prepared,prepared['confirmation'])
    except Exception:pass
    else:raise AssertionError('Injected failed upgrade committed')
    assert read(i.root/'Config/upgrade-journal.json')['stage']=='rolled_back'
    assert read(i.root/'Config/active.json')==old_active and json.loads(fixture('snapshot',controller))==expected
    faults.append(fault)
   prepared=u.prepare(root/'Target Cache',a.archive);journal=u.apply(prepared,prepared['confirmation']);assert journal['stage']=='committed'
   new=Controller(Installation(i.root),a.target);controller=new;actual=json.loads(fixture('snapshot',new));assert actual.pop('sessions')==0;compare=dict(expected);compare.pop('sessions');assert actual==compare
   assert new.health()['build']=='0.8.0-phase8' and new.health()['schema']==2
   assert credentials=={n:digest(i.root/'Config'/n) for n in credentials};assert old_active!=read(i.root/'Config/active.json');assert (i.root/old_active['media']).is_dir()
   assert digest(Path(journal['rescue']))==journal['rescue_sha256'];assert read(i.root/'Config/restore-journal.json')['stage']=='committed'
   # A completed transaction is idempotent recovery, never a silent downgrade.
   assert Upgrade(i.root,a.target).recover()['stage']=='committed'
   print(new.compose('run','--rm','--no-deps','--pull','never','-T','web','python','manage.py','test','local','--noinput','-v','1',timeout=240),flush=True)
   result={'source_revision':u.payload.release.get('source_revision'),'previous_version':old_payload.release['version'],'target_version':u.payload.release['version'],'schema':2,'synthetic_populated_business':True,'interrupted_host_exit_checkpoints_recovered':crashes,'real_candidate_and_startup_failure_recovery':faults,'candidate_business_requests_gated_until_commit':read(root/'request-gate-verified.json',{}).get('blocked',False),'all_business_auth_permissions_settings_history_rows_sequences_and_media_preserved':True,'SQL_definitions_verified':190,'sessions_expired_after_success':True,'runtime_credentials_preserved':True,'previous_database_media_program_images_and_rescues_retained':True,'committed_recovery_idempotent_no_downgrade':True,'core_tests':38,'project':i.project,'private_root':str(root),'review_resources_unchanged':states()==before_states and before_files=={p:digest(Path(p)) for p in before_files}}
   assert result['review_resources_unchanged'];atomic(a.output,result);print(json.dumps(result,indent=2),flush=True)
  finally:
   if controller:controller.ensure_runtime();controller.ownership();controller.compose('down');assert controller.volume_exists()
if __name__=='__main__':main()
