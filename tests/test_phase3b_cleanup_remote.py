"""Executor control/failure tests. No production, Docker or network access."""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import phase3b_cleanup_remote as executor
import phase3b_cleanup_bundle as bundle
recovery = executor.recovery
CORE = (ROOT / bundle.FILES["core"]).read_text()
BEFORE = {s: {"id": c * 64, "image": "sha256:" + c * 64} for s, c in zip(("web", "db", "redis", "nginx"), "abcd")}
H0, H1 = "0" * 64, "1" * 64
PERMISSIONS = [{"id": 125, "codename": "view_warehouse"}]


def metadata(contracted=False, action="inspect"):
    return {"action": action, "authorizes_cleanup": False, "mode": "database-enforced-read-only",
            "state_sha256": H1 if contracted else H0, "archive_state": "applied" if contracted else "absent",
            "column_present": not contracted, "company_count": 1, "permissions": [] if contracted else PERMISSIONS,
            "direct_grant_count": 0 if contracted else 14, "group_grant_count": 0, "retired_feature_occurrences": 0,
            "result": "PASS", "unrelated_metadata_preserved": True}


def serial():
    return {"mode": "database-enforced-read-only", "ready_for_phase_1": True, "database": {"bytes": 14000000},
            "schemas": [{"schema": "tenant_company_1", "structure": {"fingerprint": "f" * 64},
                         "continuity": {"available": True, "journal_balanced": True, "fingerprint": "e" * 64}}]}


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.start = (self.now-dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.end = (self.now+dt.timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.inputs = [recovery.ROLLBACK_SHA, "f" * 40, "apply", H0, executor.CONFIRMATIONS["apply"],
                       self.start, self.end, "attended-test-owner", CORE]

    def test_exact_inputs_valid(self):
        executor.validate_inputs(*self.inputs)

    def test_wrong_image_source_action_fingerprint_confirmation_owner_and_core(self):
        for index, value in ((0, "a"*40), (1, "main"), (2, "delete"), (3, ""), (4, "yes"),
                             (7, ""), (7, "x\ny"), (7, "x"*121), (8, CORE+"\n")):
            with self.subTest(index=index, value=str(value)[:20]):
                inputs = self.inputs.copy()
                inputs[index] = value
                with self.assertRaises(recovery.GateError):
                    executor.validate_inputs(*inputs)

    def test_maintenance_window_rejects_expired_future_overlong_and_bad_format(self):
        render = lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")
        for start, end in ((self.start, render(self.now-dt.timedelta(seconds=1))),
                           (render(self.now+dt.timedelta(seconds=1)), self.end),
                           (render(self.now-dt.timedelta(hours=2)), self.end), ("now", self.end)):
            with self.subTest(start=start, end=end), self.assertRaises(recovery.GateError):
                executor.validate_window(start, end)
        with self.assertRaises(recovery.GateError):
            executor.validate_window(self.start, render(self.now+dt.timedelta(seconds=60)), remaining=120)

    def test_private_durable_status_and_atomic_replacement(self):
        target = self.root / "status.json"
        executor.record(target, {"mutation_outcome": "unknown"})
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        executor.record(target, {"mutation_outcome": "confirmed_committed"})
        self.assertEqual(json.loads(target.read_text())["mutation_outcome"], "confirmed_committed")
        self.assertFalse(target.with_name("status.json.tmp").exists())

    def test_streamed_core_readonly_and_internal_deadline(self):
        def fake(args, **kwargs):
            self.assertIn("default_transaction_read_only=on", " ".join(args))
            self.assertIn("PGCONNECT_TIMEOUT=10", args)
            self.assertIn("signal.alarm(90)", kwargs["input_text"])
            self.assertIn("connections.close_all()", kwargs["input_text"])
            self.assertEqual(kwargs["timeout"], 120)
            self.assertEqual(args[-2:], ["--action", "inspect"])
            return json.dumps(metadata())
        with patch.object(recovery, "run", side_effect=fake):
            self.assertEqual(executor.cleanup_call(BEFORE["web"]["id"], CORE, self.root, "inspect")["state_sha256"], H0)

    def test_mutation_transport_passes_exact_confirmation_digest_and_release(self):
        for action in ("apply", "restore"):
            response = metadata(action == "apply", action)
            if action == "restore":
                response["archive_state"] = "restored"
            with patch.object(recovery, "run", return_value=json.dumps(response)) as run:
                executor.cleanup_call(BEFORE["web"]["id"], CORE, self.root, "write", action=action, expected=H0, release="release")
                args = run.call_args.args[0]
                self.assertIn(executor.CONFIRMATIONS[action], args)
                self.assertIn(H0, args)
                self.assertNotIn("default_transaction_read_only=off", " ".join(args))

    def test_invalid_or_uncertified_transport_response_fails(self):
        for key, value in (("mode", "write"), ("authorizes_cleanup", True), ("state_sha256", "invalid"), ("action", "apply")):
            response = metadata()
            response[key] = value
            with self.subTest(key=key), patch.object(recovery, "run", return_value=json.dumps(response)), self.assertRaises(recovery.GateError):
                executor.cleanup_call(BEFORE["web"]["id"], CORE, self.root, "bad")

    def test_continuity_rejects_unbalanced_or_absent_evidence(self):
        for scenario in ("unbalanced", "missing", "not-ready", "not-readonly"):
            response = serial()
            if scenario == "unbalanced": response["schemas"][0]["continuity"]["journal_balanced"] = False
            if scenario == "missing": response["schemas"] = []
            if scenario == "not-ready": response["ready_for_phase_1"] = False
            if scenario == "not-readonly": response["mode"] = "write"
            with self.subTest(scenario=scenario), patch.object(recovery, "run", return_value=json.dumps(response)), self.assertRaises(recovery.GateError):
                executor.continuity(BEFORE["web"]["id"], self.root, "bad")

    def test_live_witness_allows_customer_transactions_but_isolated_witness_detects_them(self):
        before, after = serial(), serial()
        after["schemas"][0]["continuity"]["fingerprint"] = "9"*64
        self.assertEqual(executor.serial_witness(before), executor.serial_witness(after))
        self.assertNotEqual(executor.serial_witness(before, include_balances=True), executor.serial_witness(after, include_balances=True))

    def test_final_review_attempts_every_check_even_after_metadata_failure(self):
        with patch.object(recovery, "snapshot", return_value=BEFORE), \
                patch.object(executor, "cleanup_call", side_effect=recovery.GateError("metadata failed")), \
                patch.object(executor, "continuity", return_value=serial()) as audit, \
                patch.object(executor, "http_check") as http:
            result = executor.final_review([], recovery.ROLLBACK_SHA, BEFORE, CORE, self.root)
            self.assertFalse(result["passed"])
            audit.assert_called_once()
            http.assert_called_once()

    def orchestrate(self, scenario, action="apply"):
        app = self.root / scenario
        (app / "deploy").mkdir(parents=True)
        (app / "deploy/.env").write_text("synthetic-only")
        encrypted = app / "synthetic.enc"
        encrypted.write_bytes(b"synthetic")
        initial_cwd = Path.cwd()
        state = {"wrote": False, "recovered": False}
        calls = []
        release = "db-backup-" + self.now.strftime("%Y%m%dT%H%M%SZ")
        def call(web, core, evidence, label, **kwargs):
            calls.append((label, kwargs))
            if kwargs.get("action"):
                self.assertTrue(state["recovered"])
                self.assertEqual(json.loads((evidence / "status.json").read_text())["mutation_outcome"], "unknown")
                state["wrote"] = True
                if scenario == "ambiguous-write":
                    raise recovery.GateError("private-error-payload")
                value = metadata(action == "apply", action)
                if action == "restore": value["archive_state"] = "restored"
                return value
            value = metadata((action == "restore") != state["wrote"])
            if action == "restore" and state["wrote"]: value["archive_state"] = "restored"
            if scenario == "initial-drift" or (scenario == "prewrite-drift" and "prewrite" in label):
                value["state_sha256"] = "3"*64
            if scenario == "postwrite-drift" and "final" in label:
                value["state_sha256"] = "4"*64
            return value
        def restored(*args, **kwargs):
            if scenario == "restore-failure": raise recovery.GateError("failed restore or disposable cleanup")
            self.assertTrue(callable(kwargs["verifier"]))
            state["recovered"] = True
            return {"project": "dbbackup_rehearsal_phase3_"+"e"*32, "restore_rto_seconds": 1, "verification": {"result": "PASS"}}
        snapshot_count = 0
        def snapshot(*args):
            nonlocal snapshot_count
            snapshot_count += 1
            return {**BEFORE, "unexpected": {}} if scenario == "container-drift" and snapshot_count > 1 else BEFORE
        window_count = 0
        def window(*args, **kwargs):
            nonlocal window_count
            window_count += 1
            if scenario == "expired-before-write" and window_count > 1:
                raise recovery.GateError("window expired")
        def http(*args):
            if scenario == "http-failure" or (scenario == "postwrite-health-failure" and state["wrote"]):
                raise recovery.GateError("health failed")
        output = io.StringIO()
        try:
            with contextlib.ExitStack() as stack:
                for target, name, kwargs in (
                    (executor.os, "geteuid", {"return_value": 0}),
                    (executor, "utc_now", {"return_value": self.now}),
                    (recovery, "PASSPHRASE", {"new": encrypted}),
                    (recovery, "HOST_HASHES", {"new": {}}),
                    (recovery, "BACKUP_ROOT", {"new": app}),
                    (recovery, "snapshot", {"side_effect": snapshot}),
                    (recovery, "capacity", {"return_value": None}),
                    (recovery, "fresh_backup", {"side_effect": recovery.GateError("backup failed")} if scenario == "backup-failure" else {"return_value": (release, encrypted)}),
                    (recovery, "restore", {"side_effect": restored}),
                    (recovery, "run", {"return_value": str(self.root)}),
                    (executor.shutil, "disk_usage", {"return_value": type("Disk", (), {"free": 1 if scenario == "disk-failure" else 2*1024**3})()}),
                    (executor, "cleanup_call", {"side_effect": call}),
                    (executor, "continuity", {"return_value": serial()}),
                    (executor, "http_check", {"side_effect": http}),
                    (executor, "validate_window", {"side_effect": window}),
                ):
                    stack.enter_context(patch.object(target, name, **kwargs))
                stack.enter_context(contextlib.redirect_stdout(output))
                inputs = self.inputs.copy()
                inputs[2:5] = [action, H1 if action == "restore" else H0, executor.CONFIRMATIONS[action]]
                if scenario == "success": executor.execute(str(app), *inputs)
                else:
                    with self.assertRaises(recovery.GateError): executor.execute(str(app), *inputs)
        finally:
            os.chdir(initial_cwd)
        self.assertNotIn("private-error-payload", output.getvalue())
        status = json.loads(next(app.glob("phase3b-cleanup-evidence/*/status.json")).read_text())
        self.assertIn("production-final-state", [name for name, _ in calls])
        return status, calls

    def test_backup_restore_capacity_and_drift_fail_before_live_write(self):
        for scenario in ("backup-failure", "restore-failure", "disk-failure", "initial-drift", "prewrite-drift", "http-failure",
                         "expired-before-write", "container-drift"):
            with self.subTest(scenario=scenario):
                status, calls = self.orchestrate(scenario)
                self.assertEqual(status["mutation_outcome"], "not_attempted")
                self.assertFalse(any(kwargs.get("action") for _, kwargs in calls))
                self.assertEqual(status["result"], "FAIL")

    def test_successful_apply_and_restore_have_one_certified_live_write(self):
        for action in ("apply", "restore"):
            with self.subTest(action=action):
                if action == "restore": self.root = self.root / "restore-case"; self.root.mkdir()
                status, calls = self.orchestrate("success", action)
                self.assertEqual(status["mutation_outcome"], "confirmed_committed")
                self.assertEqual(status["result"], "PASS")
                self.assertEqual([k["action"] for _, k in calls if k.get("action")], [action])

    def test_lost_write_response_never_retries_or_claims_rollback(self):
        status, calls = self.orchestrate("ambiguous-write")
        self.assertEqual(status["mutation_outcome"], "unknown")
        self.assertEqual(status["result"], "FAIL")
        self.assertEqual(sum(bool(k.get("action")) for _, k in calls), 1)

    def test_post_commit_drift_fails_without_automatic_restore(self):
        status, calls = self.orchestrate("postwrite-drift")
        self.assertEqual(status["mutation_outcome"], "confirmed_committed")
        self.assertEqual(status["result"], "FAIL")
        self.assertFalse(status["final_checks_passed"])
        self.assertFalse(any(k.get("action") == "restore" for _, k in calls))

    def test_post_commit_health_failure_retains_committed_outcome(self):
        status, calls = self.orchestrate("postwrite-health-failure")
        self.assertEqual(status["mutation_outcome"], "confirmed_committed")
        self.assertEqual(status["result"], "FAIL")
        self.assertFalse(status["final_checks_passed"])
        self.assertEqual(sum(bool(k.get("action")) for _, k in calls), 1)

    def test_rehearsal_refuses_production_project_or_container(self):
        for project, web in (("deploy", "e"*64), ("dbbackup_rehearsal_phase3_"+"f"*32, BEFORE["web"]["id"])):
            with patch.object(recovery, "run", return_value=web), self.assertRaises(recovery.GateError):
                executor.rehearse(["docker", "compose", "--project-name", project], {}, BEFORE, CORE, self.root,
                                  "apply", "release", metadata(), serial())

    def test_bundle_validates_without_production_execution_and_binds_source_sha(self):
        source = bundle.build("f"*40)
        result = subprocess.run([sys.executable, "-", "--validate-bundle"], input=source, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hashes"]["core"], executor.CORE_SHA256)
        args = ["/not-production", recovery.ROLLBACK_SHA, "a"*40, "apply", H0, executor.CONFIRMATIONS["apply"], self.start, self.end, "owner"]
        result = subprocess.run([sys.executable, "-", *args], input=source, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PHASE3B_EVIDENCE_DIR", result.stdout)

    def test_workflow_remote_arguments_preserve_spaces_and_shell_metacharacters(self):
        workflow = (ROOT / ".github/workflows/phase3b-controlled-cleanup.yml").read_text()
        printf = workflow.split("          printf -v remote_command ", 1)[1].split("          ssh -i", 1)[0]
        executable = self.root / "sudo"
        executable.write_text("#!"+sys.executable+"\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
        executable.chmod(0o700)
        sentinel = self.root / "must-not-exist"
        owner = "attendee; $(touch " + str(sentinel) + ")"
        values = {"APP_DIR": str(self.root / "app with spaces"), "EXPECTED_DEPLOYED_SHA": recovery.ROLLBACK_SHA,
                  "GITHUB_SHA": "f"*40, "ACTION": "apply", "EXPECTED_STATE": H0,
                  "CONFIRMATION": executor.CONFIRMATIONS["apply"], "WINDOW_START": self.start,
                  "WINDOW_END": self.end, "ROLLBACK_OWNER": owner}
        result = subprocess.run(["bash", "-c", "printf -v remote_command " + printf + '\nbash -c "$remote_command"'],
                                env={**os.environ, **values, "PATH": str(self.root)+os.pathsep+os.environ["PATH"]},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["-n", "python3", "-", *values.values()])
        self.assertFalse(sentinel.exists())

    def test_root_is_required_before_any_production_action(self):
        with patch.object(executor.os, "geteuid", return_value=1000), self.assertRaises(recovery.GateError):
            executor.execute("/not-production", *self.inputs)

    def test_shared_host_lock_contention_stops_before_execution(self):
        lock_path = self.root / "shared-recovery.lock"
        with lock_path.open("a") as held:
            executor.fcntl.flock(held, executor.fcntl.LOCK_EX | executor.fcntl.LOCK_NB)
            with patch.object(recovery, "LOCK_FILE", lock_path), patch.object(sys, "argv", ["bundle", "/synthetic", *self.inputs[:-1]]), \
                    patch.object(executor.signal, "signal"), patch.object(executor, "execute") as execute:
                with self.assertRaisesRegex(recovery.GateError, "host lock"):
                    executor.main(CORE)
                execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
