"""Real native Mac app-copy/setup/repair checks on private disposable resources.
Headless: no Finder/GUI input, OS sign-in enablement, global runtime stop or review
restore. The existing review stack stays in its observed state.
"""
import argparse,contextlib,json,os,platform,socket,subprocess,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from installer.controller import Setup,prepare_uninstall
from installer import macos_host as host
from installer.payload import Payload,digest
from launcher.controller import Controller
from launcher.installation import Installation
from launcher.storage import LauncherError,atomic,read,lock
from launcher.system import System
from launcher import integration
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',type=Path,required=True);a=p.parse_args()
    assert platform.system()=='Darwin' and platform.machine()=='arm64'
    review=Controller(Installation(ROOT/'.runtime/review'),ROOT/'.runtime/phase5-program')
    assert review.installation.project=='financee_offline_review'
    ids=review.command('ps','-aq','--filter','label=com.docker.compose.project=financee_offline_review').split()
    states=lambda:[(c['Id'],c['Image'],c['State']['Status']) for c in json.loads(review.command('inspect',*ids))]
    before_states=states();before_health=review.health()
    files=[review.installation.root/'Config'/n for n in ('runtime.env','compose.env','active.json','launcher.json')]+list((review.installation.root/'Data/media').rglob('*'))
    before_files={str(f):digest(f) for f in files if f.is_file()}
    root=ROOT/'.runtime'/('Phase7 native '+uuid.uuid4().hex[:8]);root.mkdir();home=root/'Home';state=root/'AppState';preferences=state/'installation.json'
    system=System();target=host.install_app(a.app,home/'Applications',state,system);host.require_installed(target,home)
    program=host.program_path(target);payload=Payload(program);archive=target/'Contents/Resources/payload'/payload.archive['filename'];controller=None
    try:
        with contextlib.ExitStack() as guard:
            for port in (18766,18767):
                sock=guard.enter_context(socket.socket())
                try:sock.bind(('127.0.0.1',port));sock.listen()
                except OSError:pass
            setup=Setup(program,state/'setup.json',progress=print,context_selector=host.local_context)
            setup.prepare(state/'Cache',archive);installation=setup.install(root/'Business AED $ —',preferences)
            controller=Controller(installation,program)
            counts=controller.compose('exec','-T','db','psql','-U','financee_offline','-d',installation.project,'-Atc','SELECT (SELECT count(*) FROM auth_user), (SELECT count(*) FROM local_generalsettings), (SELECT count(*) FROM journalentries)').strip()
            assert counts=='0|0|0',counts
            secret=(installation.root/'Config/runtime.env').read_bytes();active=read(installation.root/'Config/active.json');identity=installation.data['id']
            running=controller.command('ps','-q','--filter','label=com.docker.compose.project='+installation.project)
            with lock(host.program_lock(target,state)):
                try:host.install_app(a.app,home/'Applications',state,system)
                except LauncherError as e:assert 'in progress' in str(e)
                else:raise AssertionError('Running app repair accepted')
            # Same-build program repair leaves customer state and running containers unchanged.
            host.install_app(a.app,home/'Applications',state,system)
            again=Setup(program,state/'setup.json',context_selector=host.local_context);again.prepare(state/'Cache');repaired=again.install(installation.root,preferences,True)
            assert repaired.data['id']==identity and (installation.root/'Config/runtime.env').read_bytes()==secret and read(installation.root/'Config/active.json')==active
            assert controller.command('ps','-q','--filter','label=com.docker.compose.project='+installation.project)==running
            alias=integration.desktop_shortcut(installation,target=target,desktop=home/'Desktop',name=target.stem);assert alias.resolve()==target
            agents=home/'Library/LaunchAgents';integration.signin(repaired,True,target,agents);assert list(agents.glob('*.plist'));integration.signin(repaired,False,target,agents);assert not list(agents.glob('*.plist'))
            output=root/'frozen-health.json';env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','_PYI','DYLD_')) and k not in ('VIRTUAL_ENV','TCL_LIBRARY','TK_LIBRARY')};env['PATH']='/usr/bin:/bin:/usr/sbin:/sbin';env['PYINSTALLER_RESET_ENVIRONMENT']='1'
            subprocess.run([str(target/'Contents/MacOS'/target.stem),'--diagnostic-output',str(output),'--customer',str(installation.root)],env=env,check=True,timeout=30)
            health=read(output);assert health['program_verified'] and health['health']['installation_id']==identity and not health['health']['setup_complete']
            prepare_uninstall(program,preferences,state/'removal-preserved.json');assert controller.volume_exists() and 'stopped' in controller.status()
            assert (installation.root/'Config/runtime.env').read_bytes()==secret and read(installation.root/'Config/active.json')==active
            controller.ownership();controller.compose('down');assert controller.volume_exists()
        assert states()==before_states and review.health()==before_health
        assert before_files=={str(f):digest(f) for f in files if f.is_file()}
        result={'source_revision':payload.release['launcher_revision'],'actual_native_app_copy_signature_verified':True,'running_app_repair_refused':True,'same_build_program_and_setup_repair_reused_data_credentials_generation_containers':True,'fresh_owner_company_journal_counts':counts,'frozen_installed_app_health_without_developer_paths':True,'desktop_alias_verified_in_private_fixture':True,'signin_plist_verified_and_removed_in_private_fixture':True,'actual_OS_signin_enabled':False,'removal_preparation_stopped_only_own_services':True,'customer_data_volumes_and_apps_retained':True,'temporary_containers_and_networks_removed':True,'review_states_images_configuration_credentials_media_unchanged':True,'review_database_fingerprint':'not queried; main review services were already stopped','native_UI_tested':False,'project':installation.project,'private_root':str(root)}
        atomic(ROOT/'.runtime/phase7-build-complete/integration-results.json',result);print(json.dumps(result,indent=2))
    finally:
        if controller:controller.ownership();controller.compose('down')

if __name__=='__main__':main()
