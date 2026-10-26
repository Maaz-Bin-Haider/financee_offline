# Phase 29 Staging Acceptance and Security Results

Date: 2026-07-27

## Delivered

- Exact-source image tagging, OCI revision labeling, image-ID verification,
  isolated Compose project, production-mode settings, and disposable volumes.
- Static security contracts for cookies/proxy handling, headers, private file
  denial, attachment authorization and path containment, safe SQL identifiers,
  search-path reset, tenant permissions, redacted errors, tenant rate limits,
  immutable company family, admin locking, all-tenant preflight, protected
  production deployment, recovery dependency, and dependency pinning.
- Runtime serial, quantity, mixed-family, security, capacity, health, and
  all-tenant verification with retained CI evidence.
- A protected product-owner/engineering/operations approval job that blocks
  multi-architecture image publication.

## Local acceptance result

| Gate | Result |
|---|---:|
| Phase 29 static security contracts | 18/18 PASS |
| Runtime hardening | 5/5 PASS |
| T4 serial matrix | 51/51 PASS |
| T5 quantity workflow/report UAT | 20/20 PASS |
| T6 four-company isolation/security | 17/17 PASS |
| Selected T7 smoke | PASS |
| Initial/final release preflight | PASS |
| Redis operational health | PASS |

Selected T7 used 1,000 SKUs, 20,000 movements, and 20 concurrent sessions.
There were zero session failures, deadlocks, waiting locks, negative balances,
or accounting imbalance. All tested reports completed far below the ten-second
smoke threshold.

## Exit-gate handling

No P0/P1 defect was found by the local acceptance run. GitHub CI must reproduce
the evidence for the committed SHA. Publication then remains blocked on the
protected `staging-release-approval` environment, whose required reviewers must
represent product ownership, engineering, and operations. Those external
approvals cannot be manufactured by the implementation and are recorded by
GitHub when the job is approved.
