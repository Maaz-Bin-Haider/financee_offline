#!/usr/bin/env python3
"""Synthetic local integration of the exact-image DB-only backup/restore gate.

Never calls the production orchestrator or backup service. Requires Docker and
the three explicitly named local images; creates/removes only fresh projects.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import uuid
import sys


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phase3_recovery", ROOT / "deploy/phase3_recovery_remote.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def main():
    if sys.argv[1:] not in ([], ["--cleanup-test"], ["--executor-test"]):
        raise SystemExit("Use no arguments for recovery, --cleanup-test, or --executor-test (disposable only)")
    cleanup_test = sys.argv[1:] == ["--cleanup-test"]
    executor_test = sys.argv[1:] == ["--executor-test"]
    os.umask(0o077)
    os.chdir(ROOT / "deploy")
    project = "dbbackup_rehearsal_phase3source_" + uuid.uuid4().hex
    work = Path(tempfile.mkdtemp(prefix="phase3-recovery-synthetic-"))
    print(f"SYNTHETIC_EVIDENCE_DIR={work}", flush=True)
    env_file = work / "source.env"
    override = work / "source.json"
    passphrase = work / "synthetic-passphrase"
    passphrase.write_text(uuid.uuid4().hex + uuid.uuid4().hex)
    env_file.write_text("\n".join([
        "SECRET_KEY=" + uuid.uuid4().hex + uuid.uuid4().hex, "DEBUG=False",
        "ALLOWED_HOSTS=localhost,127.0.0.1", "CSRF_TRUSTED_ORIGINS=http://localhost",
        "DB_NAME=financee_phase3_synthetic", "DB_USER=financee_phase3_synthetic",
        "DB_PASSWORD=" + uuid.uuid4().hex, "DB_HOST=db", "DB_PORT=5432", "",
    ]))
    before = {}
    for service, tag in (("web", f"ghcr.io/maaz-bin-haider/financee-web:{gate.ROLLBACK_SHA}"),
                         ("db", "postgres:16"), ("redis", "redis:7-alpine")):
        image = gate.run(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
        before[service] = {"image": image}
    override.write_text(json.dumps(gate.override_config(before)))
    env = {"WEB_ENV_FILE": str(env_file), "WEB_IMAGE": before["web"]["image"]}
    compose = ["docker", "compose", "--project-name", project, "--env-file", str(env_file),
               "-f", "docker-compose.yml", "-f", str(override)]
    gate.no_resources(project)
    attempted = False
    cleaned = False
    try:
        config = json.loads(gate.run([*compose, "config", "--format", "json"], env=env))
        gate.validate_config(config, before, project)
        attempted = True
        gate.run([*compose, "up", "-d", "--wait", "--wait-timeout", "180", "db", "redis", "web"],
                 env=env, timeout=240, log=work / "synthetic-startup.log")
        # build_multitenant_db.sql builds tenant_company_1 but no longer creates
        # the tenancy registry, so the entrypoint registers it after migrate.
        # The pinned 3A source image predates that command, which would leave
        # tenant_company_1 orphaned and collide with the first company created
        # here. Copy the current command in and run it; it refuses to act on any
        # database that already has a company, so it is a no-op if the image
        # already handled it.
        gate.run([*compose, "cp",
                  str(ROOT / "tenancy/management/commands/register_bootstrap_tenant.py"),
                  "web:/app/tenancy/management/commands/register_bootstrap_tenant.py"], env=env)
        gate.run([*compose, "exec", "-T", "web", "python", "manage.py",
                  "register_bootstrap_tenant"], env=env,
                 log=work / "synthetic-bootstrap-tenant.log")
        # The old image's entrypoint already ran apply_sql_all_tenants before
        # that registration existed, so it skipped the unregistered schema.
        # Reapply the rollout in the entrypoint's own order so this estate
        # matches what a normal boot produces -- otherwise the restored copy
        # (whose backup already carries the registry row) gets the indexes and
        # the live source does not, and the structural witnesses diverge.
        for rollout in ("tenancy/sql/production_hardening.sql",
                        "tenancy/sql/tenant_indexes.sql"):
            gate.run([*compose, "exec", "-T", "web", "python", "manage.py",
                      "apply_sql_all_tenants", rollout, "--family", "serial"],
                     env=env, timeout=240,
                     log=work / ("synthetic-rollout-" + Path(rollout).stem + ".log"))
        print("SYNTHETIC_SOURCE_STARTUP=PASS", flush=True)
        if executor_test:
            sys.path.insert(0, str(ROOT))
            from tests.phase3b_executor_local import exercise
            exercise(gate, before, compose, env, env_file, override, passphrase, work)
            return
        if cleanup_test:
            for command in (
                "serial_only_phase3_cleanup.py",
                "serial_only_phase4_audit.py",
            ):
                gate.run([
                    *compose,
                    "cp",
                    str(ROOT / "tenancy/management/commands" / command),
                    "web:/app/tenancy/management/commands/" + command,
                ], env=env)
            gate.run([*compose, "cp", str(ROOT / "tests"), "web:/app/"], env=env)
            for test in ("tests/phase1_serial_only_creation.py", "tests/suite/test_company_metadata.py"):
                gate.run([*compose, "exec", "-T", "web", "python", test], env=env,
                         timeout=180, log=work / ("pre-cleanup-" + Path(test).stem + ".log"))
            print("SYNTHETIC_PRE_CLEANUP_CREATION_METADATA=PASS", flush=True)
            result = gate.run([*compose, "exec", "-T", "-e", "PHASE3B_TEST_DISPOSABLE=1", "web",
                               "python", "tests/phase3b_cleanup.py"], env=env, timeout=240, log=work / "cleanup-tests.log")
            print(result, flush=True)
            # Recreate from the unmodified published image: copied test/command
            # files do not survive. Its normal entrypoint must tolerate 3B.
            gate.run([*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "180", "web"],
                     env=env, timeout=240, log=work / "old-image-startup.log")
            proof = '''import os,time
os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
import django; django.setup()
from django.db import connection,transaction
from django.core.exceptions import ValidationError
from tenancy.models import Company
from tenancy.schema_verification import verify_company_schema
with connection.cursor() as c:
 c.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='tenancy_company' AND column_name='inventory_mode'")
 assert c.fetchone()[0] == 0
 c.execute("SELECT state FROM public.tenancy_phase3b_retirement_archive WHERE operation_key='serial-only-phase3b-v1'")
 assert c.fetchone() == ('applied',)
 c.execute("""SELECT count(*) FROM public.auth_permission p
 JOIN public.django_content_type ct ON ct.id=p.content_type_id
 WHERE ct.app_label='auth' AND ct.model='user' AND p.codename IN (
 SELECT value->>'codename' FROM public.tenancy_phase3b_retirement_archive a,
 jsonb_array_elements(a.payload->'targets'->'permissions'))""")
 assert c.fetchone()[0] == 0, 'published image startup recreated retired permissions'
with transaction.atomic():
 company=Company.objects.create(name="3B old-image synthetic "+str(time.time_ns()))
 company.refresh_from_db(); company.full_clean()
 assert company.provisioning_state == 'ready' and verify_company_schema(company,use_cache=False).ok
 company.contact_email='synthetic@example.com'; company.save(update_fields=['contact_email']); company.refresh_from_db()
 assert company.contact_email=='synthetic@example.com' and company.get_inventory_mode_display()=='Serial-number based'
 try: Company.objects.create(name='rejected synthetic',inventory_mode='quantity')
 except ValidationError: pass
 else: raise AssertionError('quantity accepted')
 transaction.set_rollback(True)
print('PASS: actual published 3A normal entrypoint retains retirement; company reads/creation/edit and quantity rejection after contraction')
'''
            print(gate.run([*compose, "exec", "-T", "web", "python", "-c", proof], env=env,
                           log=work / "old-image-proof.log"), flush=True)
            # Current tests now verify the contracted state as well as the old
            # retained-column state. Application code stays the published image.
            gate.run([*compose, "cp", str(ROOT / "tests"), "web:/app/"], env=env)
            gate.run([*compose, "cp", str(ROOT / "tenancy/management/commands/serial_only_phase3_cleanup.py"),
                      "web:/app/tenancy/management/commands/serial_only_phase3_cleanup.py"], env=env)
            gate.run([*compose, "exec", "-T", "web", "python", "-c",
                      "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings'); import django; django.setup(); from tenancy.models import Company; Company.objects.update(disabled_features=[])"], env=env)
            gate.run([*compose, "exec", "-T", "-e", "DJANGO_SUPERUSER_USERNAME=admin",
                      "-e", "DJANGO_SUPERUSER_PASSWORD=ci-admin-password", "-e", "DJANGO_SUPERUSER_EMAIL=admin@example.com",
                      "web", "python", "manage.py", "createsuperuser", "--noinput"], env=env)
            gate.run([*compose, "exec", "-T", "web", "python", "manage.py", "provision_tenant", "CI Company Two"], env=env)
            gate.run([*compose, "exec", "-T", "web", "python", "tests/ci_bootstrap.py"], env=env)
            gate.run([*compose, "exec", "-T", "web", "python", "tests/suite/run_all.py"], env=env,
                     timeout=1200, log=work / "post-cleanup-full-suite.log")
            gate.run([*compose, "exec", "-T", "web", "python", "manage.py", "serial_only_phase3_cleanup", "--strict"],
                     env=env, log=work / "post-suite-cleanup-state.json")
            print("SYNTHETIC_POST_CLEANUP_FULL_SUITE=PASS", flush=True)
            return
        backup = gate.run(["bash", "backup_database_encrypted.sh"], timeout=240,
                          log=work / "synthetic-backup.log", env={**env,
                              "BACKUP_DEST": str(work), "BACKUP_PASSPHRASE_FILE": str(passphrase),
                              "BACKUP_COMPOSE_PROJECT": project, "BACKUP_ENV_FILE": str(env_file),
                              "BACKUP_COMPOSE_OVERRIDE": str(override),
                              "DB_USER": "financee_phase3_synthetic", "DB_NAME": "financee_phase3_synthetic"})
        bundle = Path(gate.key_values(backup)["BACKUP_PATH"])
        print("SYNTHETIC_ENCRYPTED_BACKUP=PASS", flush=True)
        gate.PASSPHRASE = passphrase
        report = gate.restore(before, bundle, work)
        print(json.dumps({"source_sha": gate.ROLLBACK_SHA, "images": before,
                          "synthetic": True, **report, "result": "PASS"}, sort_keys=True), flush=True)
    finally:
        if attempted:
            gate.run([*compose, "down", "-v"], env=env, log=work / "synthetic-cleanup.log", timeout=180)
            gate.no_resources(project)
            cleaned = True
        if not attempted or cleaned:
            env_file.unlink(missing_ok=True)
            passphrase.unlink(missing_ok=True)
        print(f"SYNTHETIC_SOURCE_CLEANED={not attempted or cleaned}", flush=True)


if __name__ == "__main__":
    main()
