"""Exercise the Phase 4 production wrapper with a non-networked Docker fake."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHA = "497b6650ed678bc462f85de6bff14692bffd6ace"
FAKE = '''import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["PHASE4_FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if args[:2] != ["-n", "docker"]:
    raise SystemExit(91)
args = args[2:]
scenario = os.environ.get("PHASE4_FAKE_SCENARIO", "success")
if args[:1] == ["inspect"]:
    if args[2] == "{{.Config.Image}}":
        print("wrong-image" if scenario == "wrong-image" else
              "ghcr.io/maaz-bin-haider/financee-web:" + os.environ["PHASE4_FAKE_SHA"])
    elif args[2] == "{{.State.Health.Status}}":
        print("unhealthy" if scenario == "unhealthy" else "healthy")
    elif args[2] == "{{.Image}}":
        print("sha256:fixed")
    else:
        raise SystemExit(92)
elif args[:2] == ["image", "inspect"]:
    print("amd64" if scenario == "wrong-arch" else "arm64")
elif args[:1] == ["compose"] and args[-3:] == ["ps", "-q", "web"]:
    counter = pathlib.Path(os.environ["PHASE4_FAKE_COUNTER"])
    count = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(count + 1))
    print(("b" if scenario == "container-changed" and count else "a") * 64)
elif args[:1] == ["compose"] and "exec" in args:
    if "PGOPTIONS=-c default_transaction_read_only=on" not in args:
        raise SystemExit(93)
    if args[-3:] == ["python", "-", "--strict"]:
        pathlib.Path(os.environ["PHASE4_FAKE_INPUT"]).write_text(sys.stdin.read())
        pathlib.Path(os.environ["PHASE4_FAKE_STAGE"]).write_text("<discover>")
        print('{"mode":"database-enforced-read-only"}')
        raise SystemExit(1 if scenario == "audit-failed" else 0)
    if args[-5:-1] == ["python", "-", "--strict", "--expect-state"]:
        pathlib.Path(os.environ["PHASE4_FAKE_INPUT"]).write_text(sys.stdin.read())
        pathlib.Path(os.environ["PHASE4_FAKE_STAGE"]).write_text(args[-1])
        print('{"mode":"database-enforced-read-only"}')
        raise SystemExit(1 if scenario == "audit-failed" else 0)
    if args[-4:] == ["manage.py", "serial_only_phase0_audit", "--include-continuity", "--strict-serial"]:
        print('{"continuity":"checked"}')
        raise SystemExit(1 if scenario == "continuity-failed" else 0)
    raise SystemExit(94)
else:
    raise SystemExit(95)
'''


class Phase4RemoteInventoryTests(unittest.TestCase):
    def run_wrapper(self, scenario="success", sha=SHA, tls=False, stage=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "application with spaces"
            deploy = app / "deploy"
            deploy.mkdir(parents=True)
            if tls:
                (deploy / "docker-compose.tls.yml").touch()
            fake = root / "sudo"
            fake.write_text(f"#!{sys.executable}\n" + FAKE)
            fake.chmod(0o755)
            log = root / "calls.jsonl"
            sent = root / "input.txt"
            stage_file = root / "stage.txt"
            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "deploy/phase4_inventory_remote.sh"),
                    str(app),
                    sha,
                    "f" * 40,
                    *( [stage] if stage is not None else [] ),
                ],
                input="phase4-audit-source-sentinel\n",
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "PHASE4_FAKE_LOG": str(log),
                    "PHASE4_FAKE_INPUT": str(sent),
                    "PHASE4_FAKE_STAGE": str(stage_file),
                    "PHASE4_FAKE_COUNTER": str(root / "counter"),
                    "PHASE4_FAKE_SHA": SHA,
                    "PHASE4_FAKE_SCENARIO": scenario,
                },
            )
            calls = [
                json.loads(line) for line in log.read_text().splitlines()
            ] if log.exists() else []
            body = sent.read_text() if sent.exists() else None
            self.last_stage = (
                stage_file.read_text() if stage_file.exists() else None
            )
            return result, calls, body

    def test_exact_image_receives_stdin_and_only_read_operations(self):
        result, calls, body = self.run_wrapper(tls=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(body, "phase4-audit-source-sentinel\n")
        self.assertIn("PHASE4_REPLACEMENT_AUTHORIZED=no", result.stdout)
        self.assertIn("PHASE4_PRODUCTION_CONTAINER_UNCHANGED=yes", result.stdout)
        self.assertTrue(any("docker-compose.tls.yml" in call for call in calls))
        self.assertEqual(sum("exec" in call for call in calls), 2)

    def test_identity_or_health_mismatch_stops_before_execution(self):
        for scenario in ("wrong-image", "wrong-arch", "unhealthy"):
            with self.subTest(scenario=scenario):
                result, calls, body = self.run_wrapper(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any("exec" in call for call in calls))
                self.assertIsNone(body)

    def test_audit_or_continuity_failure_still_rechecks_and_stops(self):
        for scenario in ("audit-failed", "continuity-failed"):
            with self.subTest(scenario=scenario):
                result, calls, _ = self.run_wrapper(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sum("exec" in call for call in calls), 2)
                self.assertIn(
                    "PHASE4_PRODUCTION_CONTAINER_UNCHANGED=yes", result.stdout
                )
                self.assertIn("PHASE4_ENTRY_RESULT=REVIEW_REQUIRED", result.stdout)
                self.assertNotIn("PHASE4_ENTRY_RESULT=PASS", result.stdout)

    def test_container_change_stops_success_result(self):
        result, _, _ = self.run_wrapper("container-changed")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PHASE4_ENTRY_RESULT=PASS", result.stdout)

    def test_invalid_sha_stops_before_any_docker_command(self):
        result, calls, _ = self.run_wrapper(sha="main; invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_state_is_discovered_when_no_assertion_is_given(self):
        result, _calls, _body = self.run_wrapper()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.last_stage, "<discover>")
        self.assertIn("PHASE4_EXPECT_STATE=<discover>", result.stdout)

    def test_an_asserted_state_is_forwarded_to_the_audited_source(self):
        result, _calls, _body = self.run_wrapper(stage="post-4A")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.last_stage, "post-4A")
        self.assertIn("PHASE4_EXPECT_STATE=post-4A", result.stdout)

    def test_unknown_state_is_refused_before_any_docker_command(self):
        result, calls, _body = self.run_wrapper(stage="authorize-everything")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid expected history state", result.stderr)
        self.assertEqual(calls, [])

if __name__ == "__main__":
    unittest.main()
