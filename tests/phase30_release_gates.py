#!/usr/bin/env python3
"""Static fail-closed contracts for the Phase 30 production foundation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/ci.yml").read_text()
deploy = (ROOT / "deploy/phase30_foundation_deploy.sh").read_text()
pull = (ROOT / "deploy/deploy_pull.sh").read_text()
audit = (
    ROOT / "tenancy/management/commands/production_foundation_audit.py"
).read_text()

checks = {
    "release SHA is frozen and image pinned":
        "PHASE30_RELEASE_SHA" in deploy
        and 'WEB_IMAGE" == *":$PHASE30_RELEASE_SHA"' in deploy
        and "git -C .. rev-parse HEAD" in deploy,
    "change window and rollback owner required":
        "PHASE30_NOTICE_REFERENCE" in deploy
        and "PHASE30_MAINTENANCE_WINDOW" in deploy
        and "PHASE30_ROLLBACK_OWNER" in deploy,
    "backup strategy is explicit before deployment":
        "PHASE30_BACKUP_MODE" in deploy
        and '"external" || "$PHASE30_BACKUP_MODE" == "encrypted"' in deploy
        and deploy.index("BACKUP_MODE=external") < deploy.index("bash deploy_pull.sh")
        and deploy.index("bash backup_encrypted.sh") < deploy.index("bash deploy_pull.sh"),
    "production audit is read only and serial only":
        "--serial-only" in deploy
        and '"mode": "read-only-production-safe"' in audit
        and "Phase 30 forbids quantity tenants" in audit,
    "pre-deploy audit runs from candidate without entrypoint":
        '"${compose[@]}" pull web' in deploy
        and '"${compose[@]}" run --rm --no-deps -T' in deploy
        and "--entrypoint python web manage.py production_foundation_audit" in deploy,
    "before and after continuity compared":
        "continuity-before.json" in deploy
        and "--compare /tmp/phase30-continuity-before.json" in deploy
        and "continuity_unchanged" in audit,
    "T9 contracts cover platform and serial continuity":
        "authentication:login" in audit
        and "attachments:metadata" in audit
        and "inventory_mode_admin_locked" in audit
        and "subscription_states_valid" in audit
        and "get_trial_balance_json" in audit,
    "operational thresholds are fail closed":
        "PHASE30_MAX_HTTP_LATENCY_SECONDS" in deploy
        and "PHASE30_MAX_DB_CONNECTIONS" in deploy
        and "PHASE30_MAX_5XX" in deploy
        and "PHASE30_MIN_AVAILABLE_KB" in deploy
        and "PHASE30_MAX_CONTAINER_CPU_PERCENT" in deploy
        and "PHASE30_MAX_CONTAINER_MEMORY_PERCENT" in deploy,
    "post-deploy health is stabilized before measurement":
        "stable_requests" in deploy
        and '"$web_health" == "healthy"' in deploy
        and "--retry-all-errors" in deploy
        and 'logs --since "$monitoring_started_at" nginx' in deploy,
    "failure selects previous image":
        "rollback-incident.txt" in deploy
        and 'WEB_IMAGE="$previous_image"' in deploy,
    "previous image retained until controller succeeds":
        "DEFER_IMAGE_PRUNE=1" in deploy
        and 'DEFER_IMAGE_PRUNE:-0' in pull,
    "existing pull deployment retains health rollback":
        "Rolling web back to previous image" in pull,
    "production workflow invokes Phase 30 controller":
        "phase30_foundation_deploy.sh" in workflow,
    "production environment approval retained":
        "environment: production" in workflow,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
print(f"{len(checks) - len(failed)}/{len(checks)} Phase 30 release gates passed")
raise SystemExit(1 if failed else 0)
