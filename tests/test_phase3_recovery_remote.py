"""Non-production control/failure tests; no Docker, root or network required."""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phase3_recovery", ROOT / "deploy/phase3_recovery_remote.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
BEFORE = {s: {"id": c * 64, "image": "sha256:" + c * 64}
          for s, c in zip(("web", "db", "redis", "nginx"), "abcd")}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()

    def config(self, project="dbbackup_rehearsal_phase3_test"):
        result = gate.override_config(BEFORE)
        result["volumes"] = {"pgdata": {"name": project + "_pgdata"}}
        result["networks"]["default"]["name"] = project + "_default"
        return result

    def backup(self):
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"financee-db-{stamp}.dump.tar.enc"
        bundle = self.root / name
        bundle.write_bytes(b"synthetic-encrypted-fixture")
        Path(str(bundle) + ".sha256").write_text(gate.sha256(bundle) + "  " + name + "\n")
        state = {"LAST_RELEASE": "db-backup-" + stamp, "REMOTE_VERIFIED": "true",
                 "LAST_BACKUP_FILE": name, "LAST_BACKUP_BYTES": str(bundle.stat().st_size)}
        (self.root / "last-success.env").write_text("\n".join(f"{k}={v}" for k, v in state.items()))
        status = ("REMOTE_BACKUP_STATUS=FRESH\nREMOTE_LAST_RELEASE=" + state["LAST_RELEASE"]
                  + "\nLOCAL_LAST_RELEASE=" + state["LAST_RELEASE"])
        return bundle, state, status

    def test_host_helper_hashes_match_reviewed_source(self):
        for name, digest in gate.HOST_HASHES.items():
            self.assertEqual(gate.sha256(ROOT / name), digest, name)

    def test_workflow_is_protected_manual_serialized_and_streamed(self):
        source = (ROOT / ".github/workflows/phase3-production-recovery.yml").read_text()
        for text in ("workflow_dispatch:", "environment: production", "group: production-deploy",
                     "contents: read", "< deploy/phase3_recovery_remote.py", '"$GITHUB_SHA"',
                     "tests.test_phase3_recovery_remote", "retention-days: 90", gate.CONFIRMATION):
            self.assertIn(text, source)
        for text in ("  push:", "git pull", "approve"):
            self.assertNotIn(text, source)
        remote_step = source[source.index("      - name: Stream exact recovery source"):]
        self.assertNotIn("docker pull", remote_step)
        self.assertIn("python3 tests/phase3_recovery_local.py", source)
        self.assertLess(source.index("python3 tests/phase3_recovery_local.py"), source.index("Install production SSH key"))

    def test_valid_restore_config(self):
        gate.validate_config(self.config(), BEFORE, "dbbackup_rehearsal_phase3_test")

    def test_config_rejects_image_resource_network_volume_and_privilege_drift(self):
        for mutation in (
            lambda c: c["services"]["web"].update(image="unexpected"),
            lambda c: c["services"]["db"].update(pull_policy="always"),
            lambda c: c["services"]["web"]["deploy"]["resources"]["limits"].update(memory="1"),
            lambda c: c["services"]["db"].update(ports=[{"published": "5432"}]),
            lambda c: c["services"]["web"].update(network_mode="host"),
            lambda c: c["services"]["web"].update(privileged=True),
            lambda c: c["services"]["web"].update(volumes=[{"type": "bind", "source": "/"}]),
            lambda c: c["volumes"]["pgdata"].update(name="deploy_pgdata"),
            lambda c: c["volumes"]["pgdata"].update(external=True),
            lambda c: c["networks"]["default"].update(internal=False),
            lambda c: c["networks"]["default"].update(name="deploy_default"),
        ):
            with self.subTest(mutation=mutation):
                config = self.config()
                mutation(config)
                with self.assertRaises(gate.GateError):
                    gate.validate_config(config, BEFORE, "dbbackup_rehearsal_phase3_test")

    def test_process_failure_does_not_leak_private_output(self):
        log = self.evidence / "private.log"
        with self.assertRaises(gate.GateError) as caught:
            gate.run([sys.executable, "-c", "print('private-sentinel'); raise SystemExit(1)"], log=log)
        self.assertNotIn("private-sentinel", str(caught.exception))
        self.assertIn("private-sentinel", log.read_text())
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_process_timeout_is_bounded(self):
        with self.assertRaisesRegex(gate.GateError, "timed out"):
            gate.run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.03)

    def test_reviewed_source_can_be_streamed_without_file_copy(self):
        self.assertEqual(gate.run([sys.executable, "-"], input_text="print('synthetic-stream')"), "synthetic-stream")

    def test_process_does_not_inherit_production_connection_or_compose_environment(self):
        with patch.dict(os.environ, {"DB_PASSWORD": "private-sentinel", "COMPOSE_PROJECT_NAME": "production",
                                     "WEB_ENV_FILE": "/production.env"}):
            result = json.loads(gate.run([sys.executable, "-c", "import os,json; print(json.dumps(dict(os.environ)))"]))
        for name in ("DB_PASSWORD", "COMPOSE_PROJECT_NAME", "WEB_ENV_FILE"):
            self.assertNotIn(name, result)

    def test_duplicate_evidence_keys_fail(self):
        with self.assertRaises(gate.GateError):
            gate.key_values("RESTORE_RESULT=FAIL\nRESTORE_RESULT=PASS")

    def test_new_remote_verified_backup(self):
        bundle, state, status = self.backup()
        with patch.object(gate, "BACKUP_ROOT", self.root), patch.object(gate, "run", return_value=status):
            self.assertEqual(gate.fresh_backup(self.evidence), (state["LAST_RELEASE"], bundle))

    def test_backup_rejects_old_unverified_wrong_release_size_and_checksum(self):
        for scenario in ("old", "unverified", "remote-mismatch", "wrong-size", "bad-checksum", "missing"):
            with self.subTest(scenario=scenario):
                bundle, state, status = self.backup()
                if scenario == "old":
                    state["LAST_RELEASE"] = "db-backup-20200101T000000Z"
                elif scenario == "unverified":
                    state["REMOTE_VERIFIED"] = "false"
                elif scenario == "remote-mismatch":
                    status = status.replace("REMOTE_LAST_RELEASE=", "OTHER_RELEASE=")
                elif scenario == "wrong-size":
                    state["LAST_BACKUP_BYTES"] = "1"
                elif scenario == "bad-checksum":
                    Path(str(bundle) + ".sha256").write_text("invalid checksum")
                elif scenario == "missing":
                    bundle.unlink()
                (self.root / "last-success.env").write_text("\n".join(f"{k}={v}" for k, v in state.items()))
                with patch.object(gate, "BACKUP_ROOT", self.root), patch.object(gate, "run", return_value=status):
                    with self.assertRaises(gate.GateError):
                        gate.fresh_backup(self.evidence)

    def test_snapshot_rejects_wrong_sha_arm_health_or_multiple_containers(self):
        for scenario in ("success", "sha", "arch", "health", "multiple"):
            def fake(args, **kwargs):
                if "ps" in args:
                    return "a" * 64 + ("\n" + "b" * 64 if scenario == "multiple" else "")
                if "{{.Architecture}}" in args:
                    return "amd64" if scenario == "arch" else "arm64"
                image = "wrong" if scenario == "sha" else f"ghcr.io/maaz-bin-haider/financee-web:{gate.ROLLBACK_SHA}"
                return "sha256:" + "a" * 64 + f"|{image}|true|" + ("unhealthy" if scenario == "health" else "healthy")
            with self.subTest(scenario=scenario), patch.object(gate, "run", side_effect=fake):
                if scenario == "success":
                    self.assertEqual(len(gate.snapshot(["docker", "compose"], gate.ROLLBACK_SHA)), 4)
                else:
                    with self.assertRaises(gate.GateError):
                        gate.snapshot(["docker", "compose"], gate.ROLLBACK_SHA)

    def test_capacity_stops_before_restore_when_memory_or_disk_insufficient(self):
        for memory, disk in ((100, 2 * 1024**3), (2 * 1024**2, 100)):
            with patch.object(Path, "read_text", return_value=f"MemAvailable: {memory} kB\n"), \
                    patch.object(gate, "run", return_value=str(self.root)), \
                    patch.object(shutil, "disk_usage", return_value=shutil._ntuple_diskusage(10, 1, disk)):
                with self.assertRaises(gate.GateError):
                    gate.capacity()

    def restore_fake(self, scenario):
        self.calls = []
        self.work = None
        def fake(args, **kwargs):
            self.calls.append((args, kwargs))
            if "--project-name" in args:
                project = args[args.index("--project-name") + 1]
                self.work = Path(args[args.index("--env-file") + 1]).parent
                if "config" in args:
                    return json.dumps(self.config(project))
                if "down" in args:
                    if scenario == "cleanup-failure":
                        raise gate.GateError("cleanup failed")
                    return ""
                if "ps" in args:
                    return BEFORE[args[-1]]["id"]
                if "exec" in args:
                    if scenario == "audit-failure":
                        raise gate.GateError("restored audit failed")
                    return "{}"
            if args[:2] == ["bash", "restore_database_backup_rehearsal.sh"]:
                env = kwargs["env"]
                self.assertTrue(env["RESTORE_PROJECT"].startswith("dbbackup_rehearsal_phase3_"))
                self.assertEqual(env["WEB_ENV_FILE"], env["RESTORE_ENV_FILE"])
                self.assertNotEqual(env["RESTORE_ENV_FILE"], "/production.env")
                self.assertEqual(Path(env["RESTORE_ENV_FILE"]).stat().st_mode & 0o777, 0o600)
                if scenario == "helper-failure":
                    raise gate.GateError("helper failed")
                return "RESTORE_RESULT=PASS\nRESTORE_RTO_SECONDS=43"
            if args[:2] == ["docker", "inspect"]:
                for service, state in BEFORE.items():
                    if state["id"] == args[-1]:
                        memory, nano = gate.LIMITS[service]
                        return f"{state['image']}|{memory}|{nano if scenario != 'runtime-limit' else 1}"
            if "--filter" in args:
                return "collision" if scenario == "collision" else ""
            raise AssertionError(args)
        return fake

    def test_restore_cleanup_on_success_helper_audit_and_actual_limit_failure(self):
        for scenario in ("success", "helper-failure", "audit-failure", "runtime-limit", "collision", "cleanup-failure"):
            bundle, _, _ = self.backup()
            with self.subTest(scenario=scenario), patch.object(gate, "run", side_effect=self.restore_fake(scenario)), \
                    contextlib.redirect_stdout(io.StringIO()):
                if scenario == "success":
                    result = gate.restore(BEFORE, bundle, self.evidence)
                    self.assertEqual(result["restore_rto_seconds"], 43)
                else:
                    with self.assertRaises(gate.GateError):
                        gate.restore(BEFORE, bundle, self.evidence)
                downs = [args for args, _ in self.calls if "down" in args]
                self.assertEqual(len(downs), 0 if scenario == "collision" else 1)
                for args in downs:
                    self.assertIn("--project-name", args)
                    self.assertEqual(args[-2:], ["down", "-v"])
                if self.work:
                    self.assertEqual(self.work.exists(), scenario == "cleanup-failure")
                    if self.work.exists():
                        shutil.rmtree(self.work)

    def test_production_audits_always_use_readonly_existing_container(self):
        def fake(args, **kwargs):
            self.assertEqual(args[:4], ["docker", "exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on"])
            self.assertEqual(args[4], BEFORE["web"]["id"])
            return json.dumps({"mode": "database-enforced-read-only", "inventory_review_ready": True,
                               "authorizes_cleanup": False, "ready_for_phase_1": True,
                               "database": {"bytes": 14000000}})
        with patch.object(gate, "run", side_effect=fake):
            gate.production_audits(BEFORE, self.evidence, "before")

    def test_optional_restored_verifier_runs_before_guaranteed_cleanup(self):
        for fail in (False, True):
            bundle, _, _ = self.backup()
            def verifier(compose, env):
                self.assertFalse(any("down" in args for args, _ in self.calls))
                self.assertIn("--project-name", compose)
                self.assertIn("WEB_ENV_FILE", env)
                if fail: raise gate.GateError("round-trip failed")
                return {"result": "PASS"}
            with patch.object(gate, "run", side_effect=self.restore_fake("success")):
                if fail:
                    with self.assertRaises(gate.GateError): gate.restore(BEFORE, bundle, self.evidence, verifier=verifier)
                else:
                    self.assertEqual(gate.restore(BEFORE, bundle, self.evidence, verifier=verifier)["verification"], {"result": "PASS"})
                self.assertEqual(sum("down" in args for args, _ in self.calls), 1)
                self.assertFalse(self.work.exists())

    def test_production_is_rechecked_on_failed_restore_without_reusing_restore_environment(self):
        app = self.root / "app"
        (app / "deploy").mkdir(parents=True)
        (app / "deploy/.env").write_text("synthetic")
        bundle, _, _ = self.backup()
        initial_cwd = Path.cwd()
        try:
            with patch.object(gate.os, "geteuid", return_value=0), patch.object(gate, "PASSPHRASE", bundle), \
                    patch.object(gate, "HOST_HASHES", {}), patch.object(gate, "BACKUP_ROOT", self.root), \
                    patch.object(gate, "capacity"), patch.object(gate, "snapshot", return_value=BEFORE) as snap, \
                    patch.object(gate, "production_audits", return_value=14000000) as audits, \
                    patch.object(gate, "fresh_backup", return_value=("release", bundle)), \
                    patch.object(gate, "restore", side_effect=gate.GateError("restore failed")), \
                    patch.object(shutil, "disk_usage", return_value=shutil._ntuple_diskusage(10, 1, 2 * 1024**3)), \
                    patch.object(gate, "run", return_value=str(self.root)), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(gate.GateError, "restore failed"):
                    gate.execute(str(app), gate.ROLLBACK_SHA, "f" * 40, gate.CONFIRMATION)
                self.assertEqual(snap.call_count, 2)
                self.assertEqual([c.args[-1] for c in audits.call_args_list], ["before", "after"])
                self.assertEqual(snap.call_args_list[0], snap.call_args_list[1])
        finally:
            os.chdir(initial_cwd)

    def test_root_confirmation_and_rollback_identity_are_required(self):
        for uid, sha, source, confirmation in (
            (1, gate.ROLLBACK_SHA, "f" * 40, gate.CONFIRMATION),
            (0, "f" * 40, "f" * 40, gate.CONFIRMATION),
            (0, gate.ROLLBACK_SHA, "main", gate.CONFIRMATION),
            (0, gate.ROLLBACK_SHA, "f" * 40, "yes"),
        ):
            with patch.object(gate.os, "geteuid", return_value=uid), self.assertRaises(gate.GateError):
                gate.execute(str(self.root), sha, source, confirmation)


if __name__ == "__main__":
    unittest.main()
