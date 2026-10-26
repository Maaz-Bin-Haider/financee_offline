import subprocess, sys
from pathlib import Path
modules = ['parties','items','purchases','sales','returns','cash_movement','opening','owner_equity','month_close','reports','drafts']
failed = []
for module in modules:
    rc = subprocess.run([sys.executable,str(Path(__file__).parent / ('test_'+module+'.py'))]).returncode
    if rc: failed.append(module)
print('BUSINESS SUITE:', 'PASS' if not failed else 'FAIL '+', '.join(failed))
sys.exit(bool(failed))
