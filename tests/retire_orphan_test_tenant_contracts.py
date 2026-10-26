#!/usr/bin/env python3
"""Static fail-closed contracts for the one-time Company 2 retirement path."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "deploy" / "retire_orphan_test_tenant.sh").read_text()
WORKFLOW = (
    ROOT / ".github" / "workflows" / "retire-orphan-test-tenant.yml"
).read_text()

checks = {
    "inspection is the default": 'RETIRE_ACTION:-inspect' in SCRIPT,
    "inspection runs the read-only estate audit": SCRIPT.index('if [[ "$action" == "inspect" ]]') < SCRIPT.index("--include-continuity"),
    "company and schema must match": 'tenant_company_${company_id}' in SCRIPT,
    "registered company blocks execution": "Company id ${company_id} is still registered" in SCRIPT,
    "registry reference blocks execution": "another registry row references" in SCRIPT,
    "quantity marker is required": "tenant_schema_metadata" in SCRIPT,
    "serial marker blocks execution": "tenant_schema_version" in SCRIPT,
    "quantity family row is required": "family = 'quantity'" in SCRIPT,
    "exact confirmation is required": "DROP-ORPHAN-TENANT-COMPANY-${company_id}" in SCRIPT,
    "off-server backup confirmation is required": "RETIRE_BACKUP_DEST_CONFIRMED_OFFSERVER" in SCRIPT,
    "direct backup precedes drop": SCRIPT.index("bash backup_database_encrypted.sh") < SCRIPT.index('DROP SCHEMA "${expected_schema}" CASCADE'),
    "host backup service precedes drop": SCRIPT.index("systemctl start financee-db-backup.service") < SCRIPT.index('DROP SCHEMA "${expected_schema}" CASCADE'),
    "remote backup must verify fresh": "REMOTE_BACKUP_STATUS=FRESH" in SCRIPT,
    "backup must be newer than operation": "Backup release predates this retirement operation" in SCRIPT,
    "drop is transactional": SCRIPT.index("BEGIN;") < SCRIPT.index('DROP SCHEMA "${expected_schema}" CASCADE') < SCRIPT.index("COMMIT;"),
    "post-change strict audit is required": "--include-continuity --strict-serial" in SCRIPT,
    "post-change serial preflight is required": "release_preflight --require-family serial" in SCRIPT,
    "workflow is manual only": "workflow_dispatch:" in WORKFLOW and "push:" not in WORKFLOW,
    "workflow hard-codes approved id": '[[ "$RETIRE_COMPANY_ID" == "2" ]]' in WORKFLOW,
    "workflow hard-codes approved schema": '[[ "$RETIRE_EXPECTED_SCHEMA" == "tenant_company_2" ]]' in WORKFLOW,
    "workflow uses production approval": "environment: production" in WORKFLOW,
    "workflow retains evidence": "retention-days: 90" in WORKFLOW,
    "workflow validates maintenance contracts": "tests/retire_orphan_test_tenant_contracts.py" in WORKFLOW,
    "workflow pins EC2 source to dispatch SHA": 'rev-parse HEAD)' in WORKFLOW and 'expected_sha' in WORKFLOW,
    "workflow preserves empty SSH arguments": "printf -v remote_command" in WORKFLOW and "'bash -s -- %q %q %q %q %q %q %q %q %q'" in WORKFLOW,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if failed:
    raise SystemExit(f"{len(failed)} retirement contract(s) failed")
print(f"Retirement contracts: {len(checks)}/{len(checks)} passed")
