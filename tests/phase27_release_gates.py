#!/usr/bin/env python3
"""Static release-contract checks for Phase 27."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/ci.yml").read_text()
deploy = (ROOT / "deploy/deploy_pull.sh").read_text()
command = (ROOT / "tenancy/management/commands/release_preflight.py").read_text()

publish_section = workflow.split("\n  publish:\n", 1)[1].split("\n  deploy:\n", 1)[0]
publish_needs_match = re.search(r"^\s+needs:\s*\[([^\]]+)\]", publish_section, re.MULTILINE)
publish_needs = (
    {item.strip() for item in publish_needs_match.group(1).split(",")}
    if publish_needs_match else set()
)
mandatory_publish_gates = {
    "checks",
    "serial-gate",
    "creation-freeze-gate",
    "runtime-removal-gate",
    "isolation-gate",
    "arm64-smoke",
    "full-regression",
    "recovery-gate",
}

checks = {
    "serial CI stage": "serial-gate:" in workflow,
    "serial-only creation CI stage": "creation-freeze-gate:" in workflow,
    "four-serial isolation CI stage": "isolation-gate:" in workflow
        and "Four-serial-company isolation gate" in workflow,
    "ARM64 execution stage": "arm64-smoke:" in workflow,
    "publish depends on mandatory gates":
        mandatory_publish_gates <= publish_needs,
    "production approval retained": "environment: production" in workflow,
    "SHA-pinned deployment retained": "github.sha" in workflow,
    "preflight lists family and version": "release_preflight" in deploy,
    "post-deploy family probes": deploy.count("release_preflight") >= 2,
    "failed health rollback retained":
        "Rolling web back to previous image" in deploy and 'PREV_IMAGE' in deploy,
    "preflight emits fingerprint": '"fingerprint"' in command,
}

for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
print(f"{sum(checks.values())}/{len(checks)} Phase 27 release gates passed")
raise SystemExit(0 if all(checks.values()) else 1)
