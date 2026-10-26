# Serial-Only Consolidation — Checkpoint 3A Compatibility

**Date:** 2026-09-03

**Status:** Local/exact-commit validation, all 14 protected CI/CD jobs,
production deployment, and owner manual verification PASS. Checkpoint 3A is
complete. Separate checkpoint 3B discovery/preparation has started; no cleanup
has run.

**Deployed 3A SHA:** `497b6650ed678bc462f85de6bff14692bffd6ace`

**Rollback target used for the 3A release:** Phase 2 image
`e44737f1f740fa936e853a3d6bbbd068a1b6d89d`, verified by protected read-only
inventory `33732596063`. The owner confirmed the live site was fine and then
instructed “continue” to begin this local implementation.

## Change boundary

- Migration `0009_inventory_mode_compatibility` uses `SeparateDatabaseAndState`.
  The physical column, existing constraint identity, and all row values remain.
  Only a database default of `serial` is added. The field and its constraint
  leave Django's model/migration state, so ORM selects/inserts no longer need
  the physical column. Reversing this migration restores the old state and
  removes only the added default; normal image rollback does not reverse it.
- The atomic migration validates the current column type, nullability, lack of
  a pre-existing default, the exact validated serial constraint, and serial
  row values. Unexpected state fails closed. It holds an explicit table lock
  during validation/default addition, with a two-second lock timeout and
  30-second statement timeout. It does not repair unexpected metadata.
- A temporary Python-only `inventory_mode` property preserves serial callers
  and the existing display label. Explicit non-serial input still fails model
  validation/save; bulk creation also rejects it before inserting. There is
  no company-mode selector. These compatibility names are not a second mode.
- Company setup validation no longer selects the redundant column. Serial SQL
  rollout and active test-discovery queries no longer filter it. The Phase 0
  continuity audit inspects the legacy column if present (without hiding
  conflicting values), and can also inspect serial tenants when it is absent.
- Serial purchase/sale/return function bodies, serial UI sources, tenant SQL,
  and applied migrations 0001–0008 remain untouched. Currency, tax settings,
  memberships, subscriptions, and serial feature settings remain supported.
- No permission/grant deletion, feature JSON cleanup, tenant-schema removal,
  column contraction, or customer-data migration belongs to 3A. The separate
  inventory command still intentionally inspects the retained physical column.

## Test design and results

| Gate | Result |
|---|---|
| Phase 3A source/release contracts | 18/18 PASS |
| All Phase 0–3A and Phase 27–30 static/release contracts | 152/152 PASS |
| Backup/retention/operations/restore source contracts | 71/71 PASS |
| Audit transport and static-retirement unit tests | 8/8 PASS under deployed Python 3.12 |
| Live PostgreSQL compatibility checks | 36/36 PASS in final ARM64 and staging runs |
| Actual deployed Phase 2 image against forward 3A database | PASS — reads, creates, provisions, edits, rejects quantity; normal-entrypoint recovery also PASS |
| Existing preservation contracts | PASS — 12 serial functions, 212 UI files, 17 SQL/bootstrap files unchanged |
| Django model/migration state under deployed Python 3.12 | PASS — no changes detected; offline history check warns because DB is deliberately unavailable |
| Django system check and dependency consistency | PASS — 0 issues; no broken requirements |
| Complete 21-module regression | 21/21 PASS after correcting test-discovery filters |
| Focused serial / creation / runtime / isolation checks | 51/51, 15/15, 13/13, 16/16 PASS; zero serial XFAIL |
| ARM64 execution | PASS — 6 smoke, 13 runtime-removal, 36 compatibility checks and release preflight |
| Metadata inventory regression | 24/24 PASS; read-only stdin audit also works in actual Phase 2 image against expanded schema |
| Encrypted backup/restore and actual Phase 2 image rollback | PASS — synthetic restore RTO 43 seconds; old-image serial creation and return to 3A PASS |
| Production-like staging acceptance | PASS — serial, compatibility, security, continuity comparison, capacity preflight and Redis health |
| Whitespace and modified shell syntax | PASS |
| GitHub CI/CD and protected production deployment | PASS — all 14 jobs in `33736055610` |
| Owner manual production PASS for deployed 3A | PASS — 2026-09-03; functionality accepted and normal appearance confirmed in incognito |

The new compatibility gate is restricted to a uniquely named disposable Docker
stack. It executes real forward and reverse migration operations, compares
metadata snapshots and serial-schema structures, preserves the constraint OID,
and checks negative column/constraint states. A separate database connection
holds a conflicting lock to prove bounded fail-closed migration behavior.

The absent-column test drops it only inside a transaction on the disposable
database, creates a tenant and user, serves authenticated serial/admin pages,
persists shared feature settings, and runs rollout/preflight/continuity commands.
Query capture proves the application operations emit no legacy-column SQL.
The transaction is rolled back and column/default/constraint/metadata restoration
is checked. This is a test, not a production contraction migration.

The old-image test streams a synthetic fixture into the exact published Phase 2
image against the forward-migrated disposable database. The recovery rehearsal
also uses that actual production image for normal entrypoint startup and company
creation after forward migrations, then returns to the new image.

The final compatibility checks additionally prove that the new candidate can
run the existing pre-deployment continuity audit before migration 0009 has
added the default. The initial 34 checks were expanded with that case and the
wrong-constraint-kind case, producing the final 36 checks. All final checks
passed under ARM64 and production-like staging.

The local gates use synthetic data, not production execution; the separate
protected deployment is documented below. The staging database reported
PostgreSQL 16.15; the earlier production inventory reported
16.14. No production PostgreSQL upgrade is part of this change. The database
guard validates the actual contract at migration time and fails on differences.

## Evidence retained outside Git

The recovery bundle and its reports are in `phase28-artifacts/phase3a/`.
The bundle was created at `20260903T084325Z`, with 1,003,552 encrypted bytes,
synthetic RPO zero, restore RTO 43 seconds, and total rehearsal 162 seconds.
Its old image is the exact Phase 2 SHA above. The final static-cache sentinel
survived rollback and re-upgrade; retired quantity static assets stayed absent.

Local staging evidence is in `phase29-artifacts/phase3a-local/`; its provenance
is explicitly a working-tree candidate, not an exact commit. The clean exact
commit `497b6650ed678bc462f85de6bff14692bffd6ace` subsequently passed the same
staging gate before push. That run's evidence is in
`phase29-artifacts/phase3a-exact/`. These generated directories are ignored,
not bundled into the source commit.

```text
c4a82730111ee7416551b03e12b35a5770db97467211c149faaae4baf830b712  /tmp/phase3a-full-final-20260903.log
549aa108c7cd47830d8a0e623f503aa526dfc50231d887581d8199675251e780  /tmp/phase3a-static-final-20260903.log
b1ebed6c4f43cf001bb26fc607e7d5521e72aa133f38083ebb9be7032a59b46b  /tmp/phase3a-recovery-20260903.log
e63374a9e6560f627fe7d3e6ba6d181fd039b07fafaae5a8aff72ab8cc36b3d7  /tmp/phase3a-metadata-20260903.log
da529104ee30125eb0c4ddf58e189fc074a17264cbfb24c27423bf5b071955c9  /tmp/phase3a-staging-local-20260903.log
b2a76e445dbd0ec1860b38eb374e47afa90b0ac4c9dfaf2d6e95409eef3d8f3e  /tmp/phase3a-arm64-final-run-20260903.log
8b1d78acbde1a255b7cb9d2f1783bd91f89600e55993425b6b23d3975efaa3f7  /tmp/phase3a-staging-exact-497b665.log
703e15a02e60d8d0d29890e871894717bd1af19317d5c000399ad9b9344edeba  /tmp/phase3a-static-exact-497b665.log
```

## Issues found during local validation

The first aggregate run stopped before the suite in `ci_bootstrap.py`: its tenant
discovery still filtered the now-unmapped ORM column. The same stale filter was
found in HTTP and attachment test discovery. Those test queries were corrected,
and an AST contract now checks runtime and active discovery code for recurrence.
No serial business function was changed to resolve this test setup failure.

Final review identified that an unexpected non-check constraint with the same
name would produce a generic exception while parsing its absent expression.
The guard now validates constraint kind first and emits the explicit safe
failure; a dedicated negative test proves it. No permissive fallback was added.

## Protected deployment and owner acceptance

The owner explicitly authorized pushing the exact 3A commit to `main` and
subsequently approved the protected release gates.
[Workflow `33736055610`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33736055610)
completed successfully for that SHA; all 14 jobs passed, including compatibility,
full regression, ARM64, encrypted recovery, staging, image publication and EC2
deployment. The duplicate run `33736057506` was cancelled with owner approval;
its cancellation is not a failed deployment. The reason for duplicate dispatch
was not established.

The deployment controller reported PASS at `2026-09-03T09:05:11.383Z`, after
continuity and operational gates; the deployment job completed at 09:05:12 UTC.
Two temporary HTTP 502 responses occurred during web-container replacement,
followed by a passing HTTP check. PostgreSQL, Redis and Nginx were not replaced.
Production backup mode was `EXTERNAL`; this release log does not establish a
fresh operation-time production backup/restore for checkpoint 3B. Raw host
continuity/monitoring JSON was not independently downloaded. The raw deployment
log contains a business name and remains outside Git.

The owner reported working functionality and initially raised a background-color
difference. Comparison of Phase 2 and 3A found no changes in templates, static
assets, or the home app. The owner then confirmed normal appearance in incognito.
This records overall owner manual acceptance, not independently observed
individual transaction tests. No visual code fix was applied, and cached styles
versus an extension or other normal-browser state was not conclusively diagnosed.

## Completed release boundary and next checkpoint

3A's automated and owner manual gates are complete. The owner subsequently
authorized beginning 3B discovery/preparation. This deployed 3A SHA is the
required rollback target for a separately reviewed contraction, but that rollback
still must be tested against the actual 3B candidate. Fresh inventory and verified
backup/isolated restore remain mandatory before exact-target cleanup approval.
No permissions, grants, features, columns, or tenant schemas were removed in 3A.
