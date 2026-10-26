# Serial-Only Consolidation Phase 3 — Metadata Inventory Results

**Date:** 2026-09-03

**Status:** Checkpoint 3.0 local validation, protected production inventory, and
owner manual site check PASS. Compatibility checkpoint 3A subsequently deployed
and received owner acceptance; checkpoint 3B discovery/preparation has started.
The findings below remain the historical 3.0 snapshot, not a fresh 3B inventory.
Phase 3 is not complete.

**Image inspected at checkpoint 3.0:** `e44737f1f740fa936e853a3d6bbbd068a1b6d89d` (Phase 2)

**Production target:** EC2 `t4g.medium`, ARM64, `ap-south-1`

## Why this checkpoint precedes cleanup

At checkpoint 3.0, the Phase 2 Django model and multiple commands still read the physical
`inventory_mode` column. An immediate column drop would break the running
Phase 2 image and the image-only rollback contract. A first compatibility
release must stop relying on the column while keeping it usable by the old
image. Only after deployment and owner verification may a separate release
remove the column, with the compatibility image as its rollback target.

Currency, tax environment, provisioning state, subscriptions, memberships, and
serial feature settings remain part of the existing serial-company workflow.
None is designated for deletion simply because it was introduced alongside
quantity support. The physical serial tenant SQL remains unchanged.

## Inventory-only implementation

- New `serial_only_phase3_audit` command reads physical PostgreSQL metadata and
  uses no Company ORM model dependency. It also runs from stdin inside the
  already-deployed Phase 2 image; installing/deploying the command is not
  required for inspection.
- PostgreSQL enforces a read-only, repeatable-read transaction. Statement
  timeout defaults to 60 seconds, is bounded to 1–120 seconds, and lock timeout
  is two seconds. The production wrapper additionally forces session-level
  `default_transaction_read_only=on`.
- All Company rows, including inactive rows, are inventoried. Physical tenant-
  prefixed schemas are enumerated independently and classified; noncanonical,
  orphan, missing, mixed/quantity, or unready cases require review.
- The permission allowlist exactly matches the 14 seeds from authentication
  migrations 0022–0025, scoped to content type `auth.user`. It reports direct
  user and group assignment counts, checks expected seed labels, and preserves
  same-codename permissions on other content types.
- Seven exact stale feature keys are inventoried. Other keys/order/values are
  fingerprinted for preservation; malformed lists or unclassified legacy
  keys fail strict review. No feature JSON is rewritten.
- The inventory-mode column's physical contract and dependencies are captured.
  Unexpected dependency types/constraints fail strict review. Definitions and
  shared currency/tax values are represented by hashes, not exported records.
- Output excludes company names, usernames, group names, permission assignees,
  emails, financial records, secrets, and customer data. Identifiers, fixed
  schema/permission names, counts, and hashes are operational metadata.
- `inventory_review_ready=true` never authorizes cleanup; every report contains
  `authorizes_cleanup=false` and requires a compatibility release before drop.

## Protected production execution

The new **Phase 3 read-only production inventory** workflow is manual-only and
uses the protected `production` environment. Its concurrency group matches
the normal production deployment job. Inputs require the exact deployed SHA
and the confirmation `INSPECT-PHASE3-READ-ONLY`.

The runner streams the exact workflow checkout's audit source over SSH into
the existing web container. The remote wrapper verifies exactly one running
web container, expected SHA-pinned image, ARM64 architecture, and health
before execution. It then runs the existing strict Phase 0 continuity audit
in a read-only session and checks the web container/image/health afterward.
It does not pull Git or images, build, migrate, restart, create containers,
copy files into the container, or delete anything on EC2.

If inventory or continuity fails, evidence is retained and the workflow fails;
there is no bypass for the known local bootstrap/template drift on production.
If the deployed image has changed, stop and review the actual SHA rather than
silently changing the expected-image guard.

## Local verification

| Gate | Result |
|---|---|
| Phase 0–3 and Phase 27–30 static/release contracts | 134/134 PASS |
| Phase 3 read-only safety contracts (included above) | 20/20 PASS |
| Live PostgreSQL inventory and negative tests | 24/24 PASS |
| Remote wrapper unit tests (host Bash and Linux/Python 3.12) | 5/5 PASS in each environment |
| Stdin execution inside actual deployed Phase 2 image | PASS, read-only filesystem and database session |
| Django system check | PASS — 0 issues |
| Model/migration source drift check | PASS — no changes detected |
| Final diff whitespace and shell syntax | PASS |
| Production inventory | PASS — protected run `33732596063`; details below |

The live tests verify no change to public registry/permission/grant snapshots,
force PostgreSQL to reject an injected write (SQLSTATE `25006`), and exercise
inactive companies, scoped permissions, grants, privacy, malformed/stale
feature metadata, customized permission labels, unknown dependencies, orphan
quantity schemas, noncanonical schemas, and timeout bounds. All fixture
changes are confined to uniquely named disposable Docker projects, never the
production database. Both local stacks and their volumes were removed and
their cleanup was independently verified.

The standalone test ran the new audit source inside the published Phase 2
image `ghcr.io/maaz-bin-haider/financee-web:e44737f1f740fa936e853a3d6bbbd068a1b6d89d`
against a synthetic database, without running the image entrypoint. Its result
was inventory-review ready, with cleanup authorization explicitly false.
The same source passed the wrapper tests under Linux/Python 3.12. The offline
model-drift check reports an expected unavailable-database warning; it is not
represented as a production migration-history check.

The complete diff changes only new audit/transport/tests, CI gate wiring, and
the consolidation documents. Existing business views, templates/assets,
models, applied migrations, provisioning/middleware, and serial SQL are
unchanged. Phase 2's 12 serial document source, 212 UI-file, and 17 SQL-file
preservation contracts still pass.

The local test results above are synthetic. The separately verified production
snapshot below establishes production counts and findings; they are not inferred
from local fixtures or earlier phases.

Local evidence (not added to Git):

```text
b27bb93921b3efccae2ad43893e1f81abe17d5ffb603956b410a05ee841ccc8e  /tmp/phase3-inventory-final-20260903.log
680ea861a04cd349b03ada76ddb2b4a070a5c527439d448cc9c3fb19dee28aeb  /tmp/phase3-static-contracts-20260903.log
51fa9867fb6a91ac8d4f2779fda7ee56a85d55f148fab3ed11edaad8dac5dbf8  phase27-artifacts/metadata-inventory/phase3-deployed-image-inventory.json
```

## Verified protected production inventory — checkpoint 3.0

The owner explicitly authorized pushing inventory-only commit
`330d22e8bb378545872983351b0d58c2cb731e2d` to `main`. It was pushed with
`[skip ci]`; no automatic CI/CD run started. The owner then authorized queuing
the read-only workflow, which waited for separate protected-production approval.

[Run `33732596063`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33732596063)
completed successfully on 2026-09-03 at 08:19:12 UTC. Its exact source SHA,
successful job/steps, execution log, and downloaded operational-only artifact
were reviewed. The Phase 3 snapshot was captured at 08:19:05 UTC and the strict
Phase 0 continuity snapshot at 08:19:07 UTC.

- All seven production inventory readiness checks passed under database-enforced
  read-only execution. `authorizes_cleanup` remained `false`.
- One Company row exists, active, serial, and provisioning-ready. Its registered
  schema `tenant_company_1` is serial v6 with 24 tables. There were no missing,
  noncanonical, orphan, mixed, or quantity tenant schemas in this snapshot.
- All 14 allowlisted `auth.user` quantity permission seeds remain, with expected
  labels. Each has one direct-user grant record: 14 grant records total, not a
  count of distinct users. There are no group grants or matching codenames on
  other content types. No permission or grant was removed.
- The company's disabled-feature list has no retired or unclassified legacy
  keys, and no preserved keys. No feature metadata was rewritten.
- `inventory_mode` is a non-nullable character-varying column with no database
  default. Two dependency records identify the same expected serial constraint;
  no unexpected column dependency was reported. A compatible database default
  is required before new ORM inserts can omit this retained physical column.
- Shared currency/tax setup was fingerprinted, not changed or exported as values.
- The strict continuity audit passed; the journal was balanced and continuity
  evidence was available. This is a point-in-time snapshot, not a before/after
  financial-data equality comparison across a deployment.
- The wrapper verified the existing Phase 2 image
  `e44737f1f740fa936e853a3d6bbbd068a1b6d89d`, ARM64 architecture, and health.
  The same container and image remained healthy afterward. No deployment,
  migration, restart, permission cleanup, or schema/column deletion ran.

The retained [production artifact](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33732596063/artifacts/9884469950)
has artifact ID `9884469950` and 90-day retention. Its local downloaded log is
outside the repository; the raw inventory was not added to Git.

```text
687b1ac1d8a6b97996c1a4ac84e5744373ded753600ba8f83f405e9ee36c76a8  GitHub-reported artifact ZIP SHA-256
19056584767544a7d3dddc058cda58cc6c9d8d8f7ed4f171ab14c6d2881139c9  downloaded phase3-production-inventory.log SHA-256
```

After the evidence review, the owner reported “the site is live and fine.”
This is the owner-supplied manual site PASS for checkpoint 3.0, not a claim that
individual sales, purchase, return, or other transaction checks were observed.

## Issues found during implementation

- A source scanner initially mistook permission labels such as “Can update
  quantity warehouses” for SQL mutation statements. The test now inspects
  actual `cursor.execute` SQL arguments; it still prohibits write operations.
- Wrapper tests exposed failed `[[ ... ]]` checks not stopping under the local
  Bash version when relying only on `set -e`. Every safety guard now has an
  explicit failure exit. Wrong image, wrong architecture, unhealthy web,
  changed container, invalid SHA, and failed audit/continuity are tested.
- The optional empty EC2 app-directory input is preserved as an argument and
  accepted explicitly, avoiding the argument-loss problem encountered during
  Phase 0 maintenance.

## Exit boundary

No migration, permission removal, feature cleanup, schema/column deletion, or
production mutation belongs to the inventory checkpoint. Its authorized push,
protected execution, evidence review, and owner site verification are complete.
The owner subsequently instructed “continue” to start checkpoint 3A;
its completed deployment and owner acceptance are tracked in
`tests/PHASE3A_COMPATIBILITY_RESULTS.md`. Fresh 3B inventory run `33755059375`
subsequently passed protected execution against deployed 3A SHA
`497b6650ed678bc462f85de6bff14692bffd6ace`; its separate evidence belongs in
`tests/PHASE3B_CLEANUP_RESULTS.md`. Any subsequent push and protected deployment
require separate approval. No deletion authorization is inferred from an
inventory or site confirmation.

Phase 3 is not complete. Phase 4 is blocked until the controlled cleanup and
the owner's mandatory production verification are complete.
