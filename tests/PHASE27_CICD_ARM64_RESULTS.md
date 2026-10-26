# Phase 27 — CI/CD and ARM64 Results

Date started: 2026-07-27
Date completed: 2026-07-27
Status: **PASSED — PHASE 27 COMPLETE**

## Delivered

- Separate, diagnosable GitHub Actions jobs for:
  - serial regression;
  - complete quantity certification;
  - four-company isolation;
  - native ARM64 execution;
  - complete aggregate regression.
- Publication is blocked on static, serial, quantity, isolation, ARM64, and
  aggregate gates.
- The published release remains immutable-SHA pinned, multi-architecture
  (`linux/amd64`, `linux/arm64`), GHCR-hosted, and manual-production-approval
  gated.
- Every failed domain job uploads its own stack/container artifacts.
- `release_preflight` enumerates every active tenant and fails closed on
  provisioning state, registered/physical family mismatch, minimum version,
  missing required objects, safe report execution, or differing real schema
  fingerprints within a family.
- Pull deployment runs family/version/fingerprint/safe-report checks before
  and after deployment.
- Failed health checks still restore the previous image. The rollback path is
  now executable in a fast fake-runtime simulation.
- ARM64 smoke executes the real production image, public migrations, serial
  provisioning, quantity provisioning, mixed-family fingerprint checks, and
  the login HTTP endpoint.

## Local evidence

- Phase 27 release-contract checks: **11/11 passed**.
- Failed-health rollback simulation: passed and selected the previous image.
- Native Docker server architecture: `arm64`.
- ARM64 migration/provisioning/HTTP/family preflight: **5/5 passed**.
- Two independent serial schemas produced the same real object fingerprint.
- Quantity schema verified as family `quantity`, version 22.
- Phase 25 four-company isolation rerun: **17/17 passed**.
- Django system checks: no issues.
- Missing migration check: no changes detected.
- Shell syntax, Python compilation, Compose rendering, and diff whitespace
  validation passed.

## External T8 evidence

- Pull request: `#1`, merged after all mandatory jobs passed.
- Final clean branch/pull-request runs: `30265388247` and `30265392131`.
- Main merge SHA: `783186e553d3884cb3ce5decbcfe8d004f4e516a`.
- Main workflow run: `30266140481`.
- Main static, serial, quantity, four-company isolation, aggregate regression,
  and ARM64 execution jobs: passed.
- Immutable-SHA and `latest` multi-architecture manifests: published.
- Production EC2 deployment: correctly paused at the protected `production`
  environment boundary, was explicitly approved by `Maaz-Bin-Haider`, and
  then deployed the tested SHA successfully.
- Production post-deploy preflight: `Euronext`, family `serial`, schema version
  `6/6`, fingerprint `808e73deb5fbb472`; health and deployment completed.
- Failed-health rollback was exercised by the local fake-runtime simulation.

The T8 exit gate passed. Phase 28 — Backup, Restore, Migration, and Rollback
Rehearsal — is next.
