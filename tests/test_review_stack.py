"""Database-free checks of the destructive-command and ownership boundaries."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_stack", ROOT / "deploy/review_stack.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class ReviewSafety(unittest.TestCase):
    def test_only_review_projects(self):
        for name in ("financee_review_darkmode", "financee_review_regression_abc1"):
            self.assertEqual(review.validate_project(name), name)
        for name in ("financee", "deploy", "production", "financee_review_production",
                     "financee_review_darkmode/../../deploy", "financee_review_darkmode\n"):
            with self.assertRaises(ValueError):
                review.validate_project(name)

    def test_remove_requires_exact_confirmation_before_docker(self):
        with patch.object(review, "local_docker") as docker:
            for confirmation in ([], ["--confirm", "deploy"]):
                with self.assertRaises(ValueError):
                    review.main(["remove", "--project", "financee_review_darkmode", *confirmation])
            docker.assert_not_called()

    def test_mutating_suite_refuses_manual_review_project(self):
        with patch.object(review, "local_docker") as docker:
            with self.assertRaises(ValueError):
                review.main(["test", "--project", "financee_review_darkmode"])
            docker.assert_not_called()

    def test_commands_always_pin_project_and_standalone_compose(self):
        command = review.command({"project": "financee_review_darkmode"}, "down", "--volumes")
        self.assertIn(str(review.COMPOSE), command)
        self.assertEqual(command[command.index("--project-name") + 1], "financee_review_darkmode")
        self.assertEqual(command.count("-f"), 1)

    def test_review_hostnames_isolate_browser_cookies(self):
        self.assertEqual(review.review_hostname("financee_review_email"), "financee-review-email.localhost")
        self.assertNotEqual(review.review_hostname("financee_review_email"), review.review_hostname("financee_review_darkmode"))
        with self.assertRaises(ValueError): review.review_hostname("production")

    def test_remote_daemon_refused(self):
        with patch.dict(review.os.environ, {"DOCKER_HOST": "tcp://production:2376"}):
            with self.assertRaises(ValueError):
                review.local_docker()


if __name__ == "__main__":
    unittest.main()
