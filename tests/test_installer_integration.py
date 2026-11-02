"""Real shared setup-engine smoke on this Mac's native ARM64 payload.
This is deliberately NOT Windows/WSL/UAC/Inno acceptance. A single adapter is
substituted to select the known local Unix context instead of a Windows pipe.
Only a new UUID-owned disposable installation is started/stopped. No review
restore, runtime restart, image removal or volume removal is performed.
"""
import contextlib,json,socket,sys,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from installer.controller import Setup,prepare_uninstall
from installer.payload import Payload,digest
from launcher.controller import Controller
from launcher.installation import Installation
from launcher.storage import atomic,read
ROOT=Path(__file__).resolve().parents[1]

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--payload',required=True,type=Path);args=parser.parse_args()
    program=args.payload/'program';payload=Payload(program)
    assert payload.release['architecture']=='arm64','This smoke is native ARM64, not a Windows test'
    review_installation=Installation(ROOT/'.runtime/review')
    assert review_installation.project=='financee_offline_review'
    review=Controller(review_installation,ROOT/'.runtime/phase5-program')
    before_ids=review.command('ps','-aq','--filter','label=com.docker.compose.project='+review_installation.project)
    before_health=review.health()
    before_states=[(i['Id'],i['State']['Status'],i['Image']) for i in json.loads(review.command('inspect',*before_ids.split()))]
    preserved=[review_installation.root/'Config'/n for n in ('runtime.env','compose.env','active.json','launcher.json')]
    preserved+=list((review_installation.root/'Data/media').rglob('*'))
    before_files={str(p):digest(p) for p in preserved if p.is_file()}
    # The snapshot command queries only this separately-owned offline review DB.
    code=(ROOT/'scripts/review_snapshot.py').read_text().replace("'phase5_before','phase5_after'", "'phase5_before','phase5_after','phase6_before','phase6_after'")
    if before_health:review.compose('exec','-T','web','python','-c',code,'phase6_before')
    home=ROOT/'.runtime'/('Phase6 setup engine '+uuid.uuid4().hex[:8]);home.mkdir()
    customer=home/'Company AED $ —';preferences=home/'preferences.json';state=home/'setup.json'
    setup=Setup(program,state,progress=print);controller=None
    try:
        # No image pull/build. The acquired cache and native tar are verified.
        with contextlib.ExitStack() as guard:
            guard.enter_context(patch('installer.controller.local_context',return_value='desktop-linux'))
            # Reserve the stable review/test ports even if their stacks are off.
            for port in (18766,18767):
                sock=guard.enter_context(socket.socket())
                try:sock.bind(('127.0.0.1',port));sock.listen()
                except OSError:pass
            setup.prepare(home/'Cache',args.payload/payload.archive['filename'])
            installation=setup.install(customer,preferences)
            controller=Controller(installation,program,progress=print)
            health=controller.health();assert health and not health['setup_complete']
            counts=controller.compose('exec','-T','db','psql','-U','financee_offline','-d',installation.project,'-Atc','SELECT (SELECT count(*) FROM auth_user), (SELECT count(*) FROM local_generalsettings), (SELECT count(*) FROM journalentries)')
            assert counts.strip()=='0|0|0',counts
            secret=(customer/'Config/runtime.env').read_bytes();active=read(customer/'Config/active.json')
            before=controller.command('ps','-q','--filter','label=com.docker.compose.project='+installation.project)
            # Fresh Setup object simulates a reopened installer without skipping import verification.
            resumed=Setup(program,state,progress=print);resumed.prepare(home/'Cache')
            repaired=resumed.install(customer,preferences,existing=True)
            assert repaired.data['id']==installation.data['id']
            assert (customer/'Config/runtime.env').read_bytes()==secret
            assert read(customer/'Config/active.json')==active
            assert controller.command('ps','-q','--filter','label=com.docker.compose.project='+installation.project)==before
            prepare_uninstall(program,preferences,home/'uninstall-preserved.json')
            assert controller.volume_exists() and 'stopped' in controller.status()
            assert (customer/'Config/runtime.env').read_bytes()==secret
            assert (program/'release.json').is_file()
            # Release only this temporary network/container set; all volumes remain.
            controller.ownership();controller.compose('down');assert controller.volume_exists()
        if before_health:review.compose('exec','-T','web','python','-c',code,'phase6_after')
        assert review.command('ps','-aq','--filter','label=com.docker.compose.project='+review_installation.project)==before_ids
        assert review.health()==before_health
        assert [(i['Id'],i['State']['Status'],i['Image']) for i in json.loads(review.command('inspect',*before_ids.split()))]==before_states
        assert before_files=={str(p):digest(p) for p in preserved if p.is_file()}
        result={'kind':'real macOS ARM64 shared-engine smoke; NOT Windows certification','archive_sha256':payload.archive['sha256'],'archive_bytes':payload.archive['bytes'],'native_images_verified':len(payload.release['images']),'new_empty_counts':'0|0|0','reopened_setup_reused_identity_credentials_generation':True,'same_release_repair_reused_container_ids':True,'uninstall_preparation_stopped_only_owned_services':True,'customer_data_and_named_volumes_retained':True,'temporary_containers_and_networks_released':True,'review_containers_states_images_config_credentials_media_unchanged':True,'review_business_fingerprint':'unchanged' if before_health else 'not queried: review stack was already stopped; preserved its state','customer_directory':str(customer),'project':installation.project,'published':False}
        atomic(ROOT/'.runtime/phase6-installer-integration-results.json',result);print(json.dumps(result,indent=2))
    finally:
        if controller:
            controller.ownership();controller.compose('down')

if __name__=='__main__':main()
