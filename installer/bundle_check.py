"""Headless frozen-bundle check for the build runner. No Docker, browser,
installation initialization, prerequisite change or customer data is needed.
"""
import platform,ssl,sys
from pathlib import Path
from launcher.storage import atomic
from launcher.system import windows_native_arch
from installer.payload import Payload

def check(program,output):
    import tkinter
    payload=Payload(program)
    context=ssl.create_default_context(cafile=str(payload.ca_file) if payload.ca_file else None)
    tcl=tkinter.Tcl()
    result={'format':1,'product':'Financee_Offline','frozen':bool(getattr(sys,'frozen',False)),
            'platform':platform.system(),'native_architecture':windows_native_arch(),
            'python':platform.python_version(),'tcl':tcl.eval('info patchlevel'),
            'program_files_verified':True,'release_sha256':payload.delivery['release_sha256'],
            'payload_architecture':payload.release['architecture'],'tls_context_loaded':bool(context),
            'source_revision':payload.release.get('launcher_revision'),
            'customer_installation_tested':False,'docker_or_wsl_modified':False}
    atomic(Path(output),result)
    return result
