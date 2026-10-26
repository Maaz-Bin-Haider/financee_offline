# Phase 3B — Protected Production Cleanup Results

**Date:** 2026-09-04

**Result:** `PASS` — the exact reviewed metadata cleanup committed successfully,
all automated final checks passed, and the owner subsequently reported that the
live site was online and working correctly. Phase 3B is complete. Phase 4 has
not started and still requires an explicit instruction.

## Exact approved scope

The owner separately approved the cleanup of the exact read-only state digest:

```text
f29440c28fb0acf2640e9a9794918d5adf932cf8a4a2932b0e9b9dacd114b4b4
```

That state contained the 14 reviewed historical quantity permissions (IDs
125–138), 14 direct-user grants, zero group grants, zero retired feature-list
occurrences, no orphan/non-serial schemas, no existing retirement archive, and
the redundant `public.tenancy_company.inventory_mode` column. The operation
archived the reviewed permission/grant identities privately, removed only those
records, and dropped only that exact column and its reviewed dependencies. No
tenant schema, customer account, membership, serial feature, serial document,
tenant business object, currency/tax/subscription field, or uploaded media was
targeted. The archive remains available for a separately reviewed reversal.

## Strengthened read-only inspection

The final executor source was pushed as exact commit
`bc5cdce9ba5b2be29ee7bcbab63967f3537f7a9f` with `[skip ci]`; no automatic
workflow or deployment ran for that push. The owner separately authorized the
manual protected read-only inspection.

[Run `33879212477`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33879212477)
completed successfully at `2026-09-04T13:41:45Z` against the unchanged accepted
Phase 3A image `497b6650ed678bc462f85de6bff14692bffd6ace`. It reconfirmed the
exact target digest above, one active ready serial company/schema, balanced
serial continuity, and the reviewed metadata counts. The web container/image
remained unchanged. The report was database-enforced read-only and explicitly
returned `authorizes_cleanup=false`; approval was obtained separately afterward.

## Protected production execution

The owner explicitly authorized the exact apply operation and supplied attending
rollback owner `Maaz`, available from 20:00–22:00 Pakistan time. Because the
workflow accepts at most one hour, the selected approved window was
`2026-09-04T15:30:00Z`–`2026-09-04T16:30:00Z` (20:30–21:30 Pakistan time).

[Run `33887331226`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33887331226)
was dispatched once from exact source `bc5cdce` with:

- action `apply` and typed confirmation `APPLY-PHASE3B-REVIEWED-METADATA`;
- expected state digest `f29440c...14b4b4` and deployed SHA `497b665...ffd6ace`;
- the UTC window above and attending owner `Maaz`.

The isolated runner rehearsal passed in 8m54s before the protected `production`
job existed. The agent stopped at that gate; the owner approved it externally.
Both jobs and every GitHub step completed successfully. The protected operation
ran from `2026-09-04T15:50:50Z` to `15:53:31Z` without an application release,
host checkout update, image pull, container restart, or tenant business SQL.

The retained operational result records:

```text
PHASE3B_BUNDLE_SOURCE_SHA=bc5cdce9ba5b2be29ee7bcbab63967f3537f7a9f
PHASE3B_RESULT=PASS
mutation_outcome=confirmed_committed
final_checks_passed=true
backup_release=db-backup-20260904T155103Z
restore_rto_seconds=50
recovery.verification.result=PASS
recovery.verification.round_trip=true
recovery.verification.published_image_startup=true
recovery.verification.serial_continuity_preserved=true
result_state_sha256=129d702094a015931d8cb7f79a12838a54cecb6d5a281ec570a075870d8e8f32
```

Before the single live transaction, the actual host created and remotely
verified the fresh managed encrypted backup, restored it using the actual
production image identities in an isolated resource-bounded project, and proved
apply/reverse/apply plus normal published-image startup. The disposable project
was removed before mutation. Execution-time identity, target digest, dependency,
capacity, window, serial-continuity and HTTP checks passed before and after the
atomic commit. No automatic retry, reversal or database restore ran.

The private raw evidence remains root-only on EC2 at the unique evidence path
reported by the controller. It is intentionally not copied into GitHub or Git.
The 90-day GitHub artifact contains controlled operational metadata only:

- artifact ID `9944227651`, size 897 bytes, expires 2026-12-03;
- GitHub artifact digest
  `sha256:2770e1d8a5667a8f47d7f84ccb6322eb02de1f1a1e34c089bb857182a654ac2e`;
- downloaded log SHA-256
  `068d88631763ec60eb9bf9ca40e7f7bc88bcde18d3cf3a6d63f1ddca4e273abd`.

No credential, backup content, customer name, raw permission assignee, or
attending-owner private host record was added to this repository.

## Mandatory owner acceptance

After the workflow PASS and confirmed commit, execution stopped for the required
manual production check. On 2026-09-04 the owner reported: “yes the site is
online fine”. This is the owner-supplied live-site acceptance; it is not a claim
that the agent independently executed every sales, purchase, return, payment or
report workflow.

Checkpoint 3B and overall Phase 3 are therefore `PASS`. Historical migration
seed replacement, removal of inactive quantity-only source/tests/documentation,
and fresh-install consolidation remain Phase 4 work. No Phase 4 action is
authorized by this closeout.
