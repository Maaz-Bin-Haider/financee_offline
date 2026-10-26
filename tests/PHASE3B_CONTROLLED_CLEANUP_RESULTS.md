# Phase 3B — Local controlled-cleanup candidate

**Date:** 2026-09-03

**Historical candidate boundary:** candidate `a70f8a1` was explicitly approved
and pushed with `[skip ci]`, and protected read-only run `33773691381` passed.
The subsequently strengthened final source `bc5cdce` passed inspection
`33879212477`; protected apply run `33887331226` later completed with
`confirmed_committed`, and the owner accepted the live site. See
`PHASE3B_PRODUCTION_RESULTS.md` for authoritative production evidence. This
candidate report by itself did not authorize those later actions.

## Entry evidence and design decision

The protected production inventory and current-image database recovery passed
in runs `33755059375` and `33760176723`, respectively. Their evidence and limits
are recorded in `PHASE3B_CLEANUP_RESULTS.md`. The owner subsequently reported
“yes it working fine”, recording an overall manual live-site PASS after recovery.
That does not substitute for a post-cleanup site check or exact-target approval.

Production remains the accepted 3A image
`497b6650ed678bc462f85de6bff14692bffd6ace`. The local starting source is the
already-pushed recovery-only commit `962f36feec98f2ab1babff1fc50ec7efe34c125c`.

Migration 0009 already removed the legacy mode field from Django state while
retaining the physical column. This candidate refines the implementation plan:
physical cleanup is an **explicit maintenance transaction**, not a migration
run automatically by application startup. Historical migrations and their seed
records are unchanged. New empty databases still acquire those seeds; local
tests then explicitly clean them. Automatic fresh-install consolidation and
historical migration replacement remain separate Phase 4 work.

## Implemented controls

`tenancy/management/commands/serial_only_phase3_cleanup.py` defaults to inspection
in a database-enforced read-only, repeatable-snapshot transaction. Its standalone
stdin entry point also works inside the unmodified published 3A image.

- Exact `auth.user` content type plus the 14 historical codenames and labels
  define candidate permissions. Other content types and unrelated grants are
  preserved. The fingerprint includes exact permission/grant IDs and assignees,
  company mode/features, the full guarded column contract and archive state.
  Normal output includes only a digest, permission IDs/codes and counts; no
  company names or grant assignees are emitted.
- Mutation requires the exact inspected digest and action-specific confirmation.
  It also requires a managed backup reference dated within 30 minutes. **This
  timestamp check does not prove that a backup exists or was restored.** A future
  reviewed production wrapper must independently create/verify fresh encrypted
  backup and isolated restore before invoking the command. That wrapper was
  not part of `a70f8a1`; a subsequent local candidate is now documented in
  `PHASE3B_EXECUTOR_RESULTS.md`. Direct production invocation is not approved.
- A nonblocking advisory lock and table locks precede recomputation of the
  fingerprint. Lock waits are bounded at two seconds and individual statements
  at 30 seconds. The whole archive/delete/DDL/check operation is one transaction.
  Company reads can briefly wait during its exclusive lock; zero interruption
  is not promised, and a production maintenance window remains to be reviewed.
- The physical column must be exactly non-null varchar(16), with the known
  serial default and validated serial-only check. Unexpected type, collation,
  inheritance, identity/generated attributes, constraints or dependency rows
  block execution. Only the known default/constraint dependencies are accepted;
  column removal uses `RESTRICT`, never `CASCADE`.
- Unknown inbound permission foreign keys, custom target-table triggers/rules,
  RLS, nonordinary table kinds, unclassified quantity feature keys, archive-name
  collisions, and orphan/noncanonical/non-ready/non-serial tenants block cleanup.
  No tenant schema or tenant business object is dropped or modified.
- Before deleting anything, original permission and grant records, IDs and
  company feature lists are archived in
  `public.tenancy_phase3b_retirement_archive`. Its payload is checksummed,
  bounded to the reviewed metadata size and read back before deletion. PUBLIC
  table privileges are revoked. The archive remains inside the protected
  database; it is not exported or deleted by this command. Archive retention
  and eventual removal require a separate decision.
- Only exact retired feature-list values are filtered, preserving other values,
  duplicates and order. Unchanged lists receive no UPDATE. The reviewed live
  inventory had no stale keys, so no feature rewrite is currently expected.
- Reversal restores original permission/grant IDs and the exact supported 3A
  column/default/check semantics. It refuses reused IDs, missing assignees or
  changed feature values instead of overwriting records or recreating users.
  PostgreSQL object IDs/column ordinal are not promised to match after reversal.
  Reapply reuses the retained archive only when original target records match.
- Before/after digests check unrelated permissions/grants, users, groups,
  memberships, currency/content types, shared company fields and serial feature
  values inside the locked transaction. Tenant schema structures are additionally
  compared in synthetic tests; production continuity still requires its own audit.

No serial business view, frontend asset, tenant SQL, model, historical migration,
runtime dependency, Docker image definition or application entrypoint changed.

## Test and CI changes

`tests/phase3b_cleanup.py` is restricted to explicitly designated disposable
fixtures. It exercises archival, retirement, exact restoration/reapply, changed
approval fingerprints, missing confirmations, stale backup references, an
injected read-only write, archive corruption, restoration conflicts, dependency
drift, orphan schemas, real two-connection lock contention and injected failure
after archive/deletions/DDL. Failed mutation cases must leave original metadata
intact. Its permission fixture includes direct and group grants and an unrelated
same-codename permission on another content type.

`tests/phase3_recovery_local.py --cleanup-test` creates an isolated, resource-
bounded, UUID-named local stack from the published 3A image and local PostgreSQL
and Redis images. It creates no production backup and never calls the production
orchestrator. It checks both modified company tests before cleanup, runs the
cleanup tests, then **recreates web from the unmodified published image** so the
copied test/command files disappear. Normal image startup must succeed without
recreating the retired column or permissions. It then tests company creation,
provisioning, editing and quantity rejection on that actual image.

The current test files and command are subsequently copied back only for the
full regression suite and final read-only inspection. Business application code
remains the published image. Disposable feature flags are reset and synthetic
test accounts/companies are created for the suite. Two existing tests now verify
either the retained-column contract or certified archived contraction, preserving
their creation/admin assertions and historical migration rejection test. Raw SQL
must fail with the specific expected PostgreSQL error, not just any exception.

The harness removes only its allocated Compose project and verifies that its
containers, volumes and network are absent; its private environment and synthetic
passphrase are removed. Synthetic evidence remains outside Git. The original
no-argument backup/restore path remains separate and unchanged in behavior.

The proposed CI adds a mandatory cleanup-rehearsal job before staging approval
and image publication. It pulls the named images only on the GitHub runner and
uses synthetic data. Existing gates remain mandatory. Full CI has not run
remotely for this candidate; the approved push used `[skip ci]`. The separate
inspection workflow's source-contract and transport tests did pass remotely.

The separate manual-only `phase3b-cleanup-inspection.yml` requires protected
production approval and shares deployment concurrency. It streams the reviewed
source through the unchanged read-only transport into the exact 3A ARM64 image,
then runs strict serial continuity and unchanged-container/health checks. There
is **no apply/restore input or production write invocation**. The successful run
below captured this command's exact grant-identity/column fingerprint. It does
not grant cleanup approval, and any later mutation must revalidate it under lock.

## Local validation

| Check | Result |
|---|---|
| Full local synthetic rehearsal | PASS; final evidence recorded below |
| New cleanup/failure checks | 55/55 PASS |
| Pre-cleanup creation / company metadata | 15/15 and 14/14 PASS |
| Published 3A startup and serial company operations after cleanup | PASS |
| Full active regression after cleanup | 21/21 modules PASS; serial 51/51 with zero XFAIL, four-company isolation 16/16 |
| Post-suite read-only cleanup-state inspection | PASS; archive applied, column absent, no retired permissions/grants/features |
| Release contracts (Phase 0–3B and 27–30) | 174/174 PASS on Linux ARM64/Python 3.12.14 |
| Backup, retention, operations and restore contracts | 71/71 PASS on the same image |
| Existing recovery/inventory/static-retirement unit tests | 24/24 PASS on the same image |
| Historical Phase 0 recovery contracts / failed-health rollback simulation | 22/22 PASS / PASS |
| Workflow YAML, embedded shell, Python syntax and whitespace checks | PASS |
| Candidate-stage GitHub execution and manual acceptance | Not run at this checkpoint; subsequently PASS in run `33887331226` and owner check, documented in `PHASE3B_PRODUCTION_RESULTS.md` |

The local published ARM64 web image ID is
`sha256:6cb14f877396118ccdae4b75f0bdef95861276e8bd1d31802acf86e8a1b8c6bc`.
Local PostgreSQL 16.15 is not production PostgreSQL 16.14. Production evidence
must use actual host image IDs, as the already-tested recovery controller does;
this synthetic result is not an exact production-data rehearsal.

Final synthetic evidence directory (outside Git):
`/var/folders/qv/qpbw48nx28x_w6tw3q_g7v440000gn/T/phase3-recovery-synthetic-00v8u9f6`.
The completed harness reported `SYNTHETIC_SOURCE_CLEANED=True` for exact project
`dbbackup_rehearsal_phase3source_b68dd41faace49d18b26652898f83866`.
An independent label-scoped Docker read confirmed no remaining containers,
volumes or network for that project.

```text
c4b64ac09c8f5040f05be0453713312d6fa2f2fc69ab09c9e8152b3cc558d9a8  cleanup-tests.log
506f1a158a92bd1cda96a3caadfb69d264c435a73507ea0529aad9a959cad6aa  old-image-proof.log
9c79fa8f712888fb22f5a32cbe4176c862bf20d17ce99bf01e33f3445d3b7f2a  post-cleanup-full-suite.log
341dde2da6c7667933e5799b071d839ed1d3bf8b52a7d09ee5e0dfa671cf3eb9  post-suite-cleanup-state.json
a88eb79958520d5daa09c8f0141109c0bd3202a2bfad7471647692159c974636  synthetic-cleanup.log
```

Tested source SHA-256 for the initial `a70f8a1` candidate:

```text
96ab8615dffc7d240a0200349e61574a83fc962a10ebeb9bf1682f5d2ccce43f  tenancy/management/commands/serial_only_phase3_cleanup.py
8ce7f17aed3887fd7844f0cc496e7c83e438113526bd8a944c34ef98124d16d7  tests/phase3b_cleanup.py
e74f5c70b1ae108742d09814adad70f65ef8681aef91b3a38e91e9b0e67f8f49  tests/phase3_recovery_local.py
```

An early local candidate had a Python syntax error in the restore INSERT
argument list. It failed before cleanup, was fixed locally, and the disposable
stack was removed. Subsequent runs passed. No production failure resulted.

## Verified protected read-only production inspection

The owner explicitly authorized pushing exact candidate
`a70f8a11d1f55d7605e6b80f1164c63fe36c0dc6` and subsequently asked to retry.
Before retrying, GitHub `main` was verified still at `962f36f`; the push then
succeeded and a read-only check confirmed `main` at `a70f8a1` with no workflow
runs for that SHA at that time. No force push or automatic deployment occurred.

The owner separately authorized queueing the read-only inspection. No existing
run was found; [run `33773691381`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33773691381)
was dispatched from `main` at the exact approved SHA, with confirmation
`INSPECT-PHASE3B-CLEANUP-STATE` and expected deployed SHA
`497b6650ed678bc462f85de6bff14692bffd6ace`. Its pending approval was explicitly
verified as the `production` environment. The agent did not submit that approval.
The protected gate was approved externally and the owner reported it passed.

GitHub reports every step successful, including the 22 source contracts,
transport unit checks, streamed read-only inspection and artifact retention.
The job completed at `2026-09-03T15:45:37Z`; the strict continuity snapshot was
captured at `15:45:34.886809Z`. The downloaded evidence confirms:

- Source SHA matches `a70f8a1`; deployed SHA remains the accepted 3A image.
  The unchanged transport verified ARM64, healthy web, and unchanged web
  container/image identity after inspection. This is not a fresh audit of every
  other production container or a claim of a later live-site check.
- One active, ready serial company and one registered serial v6 schema, with
  24 tenant tables. No missing, orphan, invalid or non-serial schemas reported.
- Exactly the 14 reviewed `auth.user` permissions, IDs 125–138, and 14 direct
  grant records; zero group grants and zero retired feature occurrences. These
  counts match the earlier inventory; counts alone do not prove unchanged
  individual grant assignments. The new digest binds those exact assignments
  without exporting assignees.
- Archive absent and physical mode column still present. Successful execution
  of the reviewed inspector validates its exact type/default/serial constraint,
  known dependencies, target-table trigger/rule/RLS and permission-FK guards.
  No exception was reported within that defined inspection scope.
- Strict serial continuity passed with available continuity evidence, balanced
  journal and consistent serial structure. This is a point-in-time result, not
  a claim of unchanged balances while customers transact.
- `PHASE3_INVENTORY_RESULT=PASS`, `PHASE3_PRODUCTION_CONTAINER_UNCHANGED=yes`,
  `authorizes_cleanup=false`, and `PHASE3_CLEANUP_AUTHORIZED=no`.

Inspected target-state SHA-256 (not an authorization token):

```text
f29440c28fb0acf2640e9a9794918d5adf932cf8a4a2932b0e9b9dacd114b4b4
```

The [retained artifact `9900997739`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33773691381/artifacts/9900997739)
has 90-day retention. Downloaded operational evidence remains outside Git at
`/tmp/phase3b-inspection-33773691381.fBa0mA/phase3b-cleanup-inspection.log`.
No credentials, customer names, raw grant assignments or backup contents were
added to the repository.

```text
c16657f0e7a83fa3dc2b15116544e5a2946d08ba4a6d6c6fb9680b8f6abacb4c  GitHub-reported artifact ZIP SHA-256
1dd66988c7fa88f51ed1cc214001af89f0540e19bd6b032764668d2641680253  downloaded inspection log SHA-256
```

## Subsequent approval and execution completion

1. **Complete:** exact candidate push explicitly approved and verified; no
   automatic CI/CD run started.
2. **Complete at candidate stage:** separately authorized protected fingerprint
   inspection passed; retained evidence and target digest were reviewed. That
   read-only result did not itself authorize cleanup.
3. **Complete later:** the strengthened write/reversal transport passed final
   local tests and protected read-only inspection `33879212477` from exact
   source `bc5cdce`.
4. **Complete later:** the owner authorized the exact target, action, attending
   owner and window. Protected run `33887331226` revalidated the fingerprint,
   created and restored a fresh backup, proved recovery, and committed once.
5. **Complete later:** final continuity/health passed and the owner reported the
   live site online and working. See `PHASE3B_PRODUCTION_RESULTS.md`.
