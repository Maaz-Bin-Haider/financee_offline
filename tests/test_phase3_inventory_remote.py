"""Exercise the production wrapper with a strict, non-networked Docker fake."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHA = "e44737f1f740fa936e853a3d6bbbd068a1b6d89d"
FAKE = '''import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["PHASE3_FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if args[:2] != ["-n", "docker"]:
    raise SystemExit(91)
args = args[2:]
scenario = os.environ.get("PHASE3_FAKE_SCENARIO", "success")
if args[:1] == ["inspect"]:
    if args[2] == "{{.Config.Image}}":
        print("wrong-image" if scenario == "wrong-image" else
              "ghcr.io/maaz-bin-haider/financee-web:" + os.environ["PHASE3_FAKE_SHA"])
    elif args[2] == "{{.State.Health.Status}}":
        print("unhealthy" if scenario == "unhealthy" else "healthy")
    elif args[2] == "{{.Image}}":
        print("sha256:fixed")
    else:
        raise SystemExit(92)
elif args[:2] == ["image", "inspect"]:
    print("amd64" if scenario == "wrong-arch" else "arm64")
elif args[:1] == ["compose"] and args[-3:] == ["ps", "-q", "web"]:
    count_file = pathlib.Path(os.environ["PHASE3_FAKE_COUNTER"])
    count = int(count_file.read_text()) if count_file.exists() else 0
    count_file.write_text(str(count + 1))
    print(("b" if scenario == "container-changed" and count else "a") * 64)
elif args[:1] == ["compose"] and "exec" in args:
    if "PGOPTIONS=-c default_transaction_read_only=on" not in args:
        raise SystemExit(93)
    if args[-3:] == ["python", "-", "--strict"]:
        pathlib.Path(os.environ["PHASE3_FAKE_INPUT"]).write_text(sys.stdin.read())
        print('{"mode":"database-enforced-read-only"}')
        raise SystemExit(1 if scenario == "audit-failed" else 0)
    if args[-4:] == ["manage.py", "serial_only_phase0_audit", "--include-continuity", "--strict-serial"]:
        print('{"continuity":"checked"}')
        raise SystemExit(1 if scenario == "continuity-failed" else 0)
    raise SystemExit(94)
else:
    raise SystemExit(95)
'''


class RemoteInventoryTests(unittest.TestCase):
    def run_wrapper(self, scenario="success", sha=SHA, tls=False):
        with tempfile.TemporaryDirectory() as tmp:
            task_root = Path(tmp)
            app = task_root / "application with spaces"
            deploy = app / "deploy"
            deploy.mkdir(parents=True)
            if tls:
                (deploy / "docker-compose.tls.yml").touch()
            fake = task_root / "sudo"
            fake.write_text(f"#!{sys.executable}\n" + FAKE)
            fake.chmod(0o755)
            log = task_root / "calls.jsonl"
            sent = task_root / "input.txt"
            result = subprocess.run(
                ["bash", str(ROOT / "deploy/phase3_inventory_remote.sh"), str(app), sha, "f" * 40],
                input="audit-source-sentinel\n", text=True, capture_output=True,
                env={**os.environ, "PATH": str(task_root) + os.pathsep + os.environ["PATH"],
                     "PHASE3_FAKE_LOG": str(log), "PHASE3_FAKE_INPUT": str(sent),
                     "PHASE3_FAKE_COUNTER": str(task_root / "counter"),
                     "PHASE3_FAKE_SHA": SHA, "PHASE3_FAKE_SCENARIO": scenario},
            )
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            body = sent.read_text() if sent.exists() else None
            return result, calls, body

    def test_exact_image_receives_stdin_and_only_read_operations(self):
        result, calls, body = self.run_wrapper(tls=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(body, "audit-source-sentinel\n")
        self.assertIn("PHASE3_CLEANUP_AUTHORIZED=no", result.stdout)
        self.assertIn("PHASE3_PRODUCTION_CONTAINER_UNCHANGED=yes", result.stdout)
        self.assertTrue(any("docker-compose.tls.yml" in call for call in calls))
        self.assertEqual(sum("exec" in call for call in calls), 2)

    def test_image_architecture_and_health_mismatch_stop_before_execution(self):
        for scenario in ("wrong-image", "wrong-arch", "unhealthy"):
            with self.subTest(scenario=scenario):
                result, calls, body = self.run_wrapper(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any("exec" in call for call in calls))
                self.assertIsNone(body)

    def test_audit_or_continuity_failure_still_checks_container_and_stops(self):
        for scenario in ("audit-failed", "continuity-failed"):
            with self.subTest(scenario=scenario):
                result, calls, _ = self.run_wrapper(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sum("exec" in call for call in calls), 2)
                self.assertIn("PHASE3_PRODUCTION_CONTAINER_UNCHANGED=yes", result.stdout)
                self.assertIn("PHASE3_INVENTORY_RESULT=REVIEW_REQUIRED", result.stdout)
                self.assertNotIn("PHASE3_INVENTORY_RESULT=PASS", result.stdout)

    def test_container_change_stops_success_result(self):
        result, _, _ = self.run_wrapper("container-changed")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PHASE3_INVENTORY_RESULT=PASS", result.stdout)

    def test_invalid_sha_stops_before_any_docker_command(self):
        result, calls, _ = self.run_wrapper(sha="main; invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
