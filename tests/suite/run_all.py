#!/usr/bin/env python3
"""Run the whole tests/suite/ suite and aggregate results.

Each test file is executed as its own process (the SQL-layer modules run per
tenant via the harness; test_http.py boots Django), so one module's Django
import or connection state never affects another.

Run inside the web container:
    docker compose -f deploy/docker-compose.yml exec web python tests/suite/run_all.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

MODULES = [
    "test_parties.py",
    "test_items.py",
    "test_purchases.py",
    "test_sales.py",
    "test_returns.py",
    "test_cash_movement.py",
    "test_opening.py",
    "test_owner_equity.py",
    "test_month_close.py",
    "test_reports.py",
    "test_attachments.py",
    "test_drafts.py",
    "test_subscription.py",
    "test_subscription_emails.py",
    "test_report_email.py",
    "test_spotlight.py",
    "test_team_activity.py",
    "test_feature_flags.py",
    "test_company_metadata.py",
    "test_company_setup.py",
    "../phase1_serial_only_creation.py",
    "../phase2_serial_runtime_removal.py",
    "../phase24_serial_matrix.py",
    "../phase25_four_company_isolation.py",
    "test_http.py",
]


def main():
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", "/app")
    results = []
    for mod in MODULES:
        path = os.path.join(HERE, mod)
        print(f"\n########## {mod} ##########")
        proc = subprocess.run([sys.executable, path], env=env)
        results.append((mod, proc.returncode))

    print("\n" + "#" * 78)
    print("SUITE SUMMARY")
    print("#" * 78)
    failed = [m for m, rc in results if rc != 0]
    for mod, rc in results:
        print(f"  {'PASS' if rc == 0 else 'FAIL'}  {mod}")
    if failed:
        print(f"\n{len(failed)} module(s) failed: {', '.join(failed)}")
        return 1
    print("\nALL MODULES PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
