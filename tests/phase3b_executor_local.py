"""Real executor transport/rehearsal against an explicitly isolated synthetic DB.

Only called by phase3_recovery_local.py --executor-test. Never calls the
production entry point, service manager, production snapshot or fresh-backup
service. Encrypted fixtures and isolated restore use the existing local helpers.
"""
import ast
import json
from pathlib import Path
import re
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import phase3b_cleanup_remote as executor


def exercise(gate, before, compose, env, env_file, override, passphrase, work):
    project = compose[compose.index("--project-name")+1]
    gate.require(re.fullmatch(r"dbbackup_rehearsal_phase3source_[0-9a-f]{32}", project), "Synthetic source project required")
    gate.require(env["WEB_ENV_FILE"] == str(env_file) and env_file.parent == work, "Isolated synthetic credentials required")
    executor.recovery = gate
    core = (ROOT / "tenancy/management/commands/serial_only_phase3_cleanup.py").read_text()
    catalogue = next(ast.literal_eval(n.value) for n in ast.parse(core).body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "PERMISSIONS" for t in n.targets))
    seed = f'''import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
import django; django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
user=get_user_model().objects.create_user(username="synthetic-executor-user")
permissions=Permission.objects.filter(content_type__app_label="auth",content_type__model="user",codename__in={list(catalogue)!r})
assert permissions.count()==14
user.user_permissions.add(*permissions)
'''
    gate.run([*compose, "exec", "-T", "web", "python", "-c", seed], env=env, log=work / "synthetic-executor-seed.log")
    before["web"]["id"] = gate.run([*compose, "ps", "-q", "web"], env=env)
    web = before["web"]["id"]
    initial = executor.cleanup_call(web, core, work, "synthetic-initial")
    original_serial = executor.continuity(web, work, "synthetic-initial-continuity")
    gate.require(initial["direct_grant_count"] == 14, "Missing synthetic production-shaped grants")

    # Inject a transport-level fault only in this isolated fixture. The actual
    # worker must hit its in-container deadline after destructive DDL and PostgreSQL
    # must roll back. Normal bundled execution always checks the immutable core.
    fault_core = core.replace('cursor.execute("ALTER TABLE public.tenancy_company DROP COLUMN inventory_mode RESTRICT")',
        'cursor.execute("ALTER TABLE public.tenancy_company DROP COLUMN inventory_mode RESTRICT")\n'
        '    import sys,time\n    print("SYNTHETIC_AFTER_DDL", file=sys.stderr, flush=True)\n    time.sleep(8)')
    original_run = gate.run
    def inject(args, **kwargs):
        if "input_text" in kwargs:
            kwargs["input_text"] = kwargs["input_text"].replace(repr(core), repr(fault_core)).replace("signal.alarm(90)", "signal.alarm(3)")
        return original_run(args, **kwargs)
    import datetime as dt
    release = "db-backup-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = time.monotonic()
    blocked = False
    with patch.object(gate, "run", side_effect=inject):
        try:
            executor.cleanup_call(web, core, work, "synthetic-deadline", action="apply", expected=initial["state_sha256"], release=release)
        except gate.GateError:
            blocked = True
    gate.require(blocked and time.monotonic()-started < 15 and "SYNTHETIC_AFTER_DDL" in (work / "synthetic-deadline.log").read_text(),
                 "Injected in-container deadline did not fail after DDL")
    gate.require(executor.cleanup_call(web, core, work, "synthetic-after-deadline")["state_sha256"] == initial["state_sha256"],
                 "Deadline did not roll back exact original metadata")
    print("SYNTHETIC_EXECUTOR_IN_CONTAINER_DEADLINE_ROLLBACK=PASS", flush=True)

    def encrypted_backup(label):
        destination = work / label
        destination.mkdir(mode=0o700)
        result = gate.run(["bash", "backup_database_encrypted.sh"], timeout=240,
                          log=work / (label + ".log"), env={**env,
                              "BACKUP_DEST": str(destination), "BACKUP_PASSPHRASE_FILE": str(passphrase),
                              "BACKUP_COMPOSE_PROJECT": project, "BACKUP_ENV_FILE": str(env_file),
                              "BACKUP_COMPOSE_OVERRIDE": str(override),
                              "DB_USER": "financee_phase3_synthetic", "DB_NAME": "financee_phase3_synthetic"})
        values = gate.key_values(result)
        return "db-backup-" + values["BACKUP_CREATED_AT_UTC"], Path(values["BACKUP_PATH"])

    gate.PASSPHRASE = passphrase
    first_bundle = None
    reports = []
    for action in ("apply", "restore"):
        local_state = executor.cleanup_call(web, core, work, "synthetic-before-"+action)
        local_serial = executor.continuity(web, work, "synthetic-continuity-before-"+action)
        release, encrypted = encrypted_backup("synthetic-backup-before-"+action)
        if first_bundle is None: first_bundle = encrypted
        evidence = work / ("rehearsal-"+action)
        evidence.mkdir(mode=0o700)
        result = gate.restore(before, encrypted, evidence, verifier=lambda c, e:
            executor.rehearse(c, e, before, core, evidence, action, release, local_state, local_serial))
        gate.require(result["verification"]["result"] == "PASS", "Executor recovery was not certified")
        reports.append({"action": action, **result})
        print("SYNTHETIC_ENCRYPTED_"+action.upper()+"_ROUND_TRIP=PASS", flush=True)
        # This source is also synthetic and independently isolated. No production
        # entry point is called or impersonated; it proves the real write transport.
        executor.cleanup_call(web, core, work, "synthetic-source-"+action, action=action,
                              expected=local_state["state_sha256"], release=release)
    final = executor.cleanup_call(web, core, work, "synthetic-final")
    gate.require(executor.candidate_shape(final) == executor.candidate_shape(initial), "Synthetic metadata did not restore")
    checked = executor.continuity(web, work, "synthetic-final-continuity")
    gate.require(executor.serial_witness(checked, include_balances=True) == executor.serial_witness(original_serial, include_balances=True),
                 "Synthetic serial continuity changed")
    evidence = work / "default-recovery"
    evidence.mkdir(mode=0o700)
    default_result = gate.restore(before, first_bundle, evidence)
    print("SYNTHETIC_ORIGINAL_RECOVERY_PATH=PASS", flush=True)
    (work / "executor-summary.json").write_text(json.dumps({"synthetic": True, "result": "PASS", "images": before,
        "rehearsals": reports, "default_recovery": default_result, "authorizes_production_cleanup": False}, indent=2))
    print("SYNTHETIC_EXECUTOR_TRANSPORT_AND_REHEARSAL=PASS", flush=True)


if __name__ == "__main__":
    raise SystemExit("Invoke only through the guarded disposable phase3_recovery_local.py --executor-test")
