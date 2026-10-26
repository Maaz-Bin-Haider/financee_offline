# Serial-Only Consolidation — Checkpoint 3B Preparation

**Date:** 2026-09-03

**Historical preparation status:** Fresh protected production inventory and
current-image backup/isolated recovery passed before cleanup. The later final
source `bc5cdce` passed strengthened inspection `33879212477`; protected apply
run `33887331226` then reported `confirmed_committed` with final checks PASS,
and the owner accepted the live site. Phase 3B's authoritative production
closeout is `PHASE3B_PRODUCTION_RESULTS.md`. No automatic cleanup migration or
application deployment was introduced.

**Required rollback image:** deployed and owner-accepted 3A
`497b6650ed678bc462f85de6bff14692bffd6ace`.

## Verified entry gate

- GitHub `main` and the clean local starting checkout resolve to the 3A SHA.
- Workflow `33736055610` reports success for all 14 jobs at that SHA, including
  protected EC2 deployment. The separate duplicate run was cancelled earlier
  with owner approval. No later deployment appeared in the reviewed run list.
- The owner confirmed functionality and normal appearance in incognito, then
  authorized starting 3B. No application color change was needed or made.
- The existing read-only inventory contracts pass 20/20 and transport unit tests
  pass 5/5 on the local host; shell syntax passes. These are local checks, not
  evidence of current production database contents.

## Fresh inventory — protected execution PASS

[Run `33755059375`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33755059375)
was queued using the existing manual-only workflow on `main`, with explicit
expected deployed SHA `497b6650ed678bc462f85de6bff14692bffd6ace` and confirmation
`INSPECT-PHASE3-READ-ONLY`. The run's source SHA matches that same 3A commit.
Although the existing input description/default mentions Phase 2, the invocation
explicitly overrides the SHA; no old default is being used.

The unchanged wrapper checks the exact running image, ARM64 architecture and
health, executes database-enforced read-only metadata and strict continuity
audits, and checks that the container/image remain unchanged and healthy.
It shares the deployment concurrency group. It cannot restart, deploy, update
the host checkout, or remove data. No protected approval was submitted by the
agent. The owner approved it externally and subsequently reported it passed.

The reviewed run completed successfully at `2026-09-03T12:31:05Z`, with inventory
captured at 12:31:01 UTC and strict continuity at 12:31:02 UTC. All steps passed.

- All seven metadata readiness checks passed, with `authorizes_cleanup=false`.
- One active, ready serial company and one canonical registered serial v6 schema
  exist. There are 24 tenant tables; no missing, orphan, quantity, mixed, or
  noncanonical tenant schemas were reported.
- All 14 exact historical `auth.user` quantity permissions remain with their
  expected labels and 14 direct-user grant records total. This is a grant count,
  not a count of distinct users. There are zero group grants and zero matching
  codenames on other content types in this snapshot.
- The disabled-feature list remains empty: no stale or unclassified quantity
  entries and no preserved entries. No JSON rewrite is currently called for.
- The non-nullable `inventory_mode` column now has a database default. Its
  fingerprint matches the expected `'serial'::character varying` expression.
  Its three reported dependency rows identify that default and two dependency
  records for the expected serial constraint. No unexpected dependency was
  reported. This is the expected change from the earlier 3.0 snapshot.
- Strict serial discovery/continuity passed, with available continuity evidence
  and a balanced journal. This is a point-in-time audit, not a claim of unchanged
  financial balances while customers continue operating the system.
- The deployed and source SHAs both match 3A above; the same ARM64 container
  and image remained healthy. PostgreSQL reported 16.14. No production write,
  restart, checkout update or deployment ran.

The retained [artifact `9893321363`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33755059375/artifacts/9893321363)
has 90-day retention. Raw evidence is outside Git at
`/tmp/phase3b-inventory-33755059375.etNy5M/phase3-production-inventory.log`.

```text
dacdce19ec89dee649bb1e4ad6a7753bb352f3d9e895e3663854b43c746aa7d3  GitHub-reported artifact ZIP SHA-256
046ef97ca4c2bc4a428812f271aa7ec47b23bc1752306cb24c05d17503ec0e46  downloaded inventory log SHA-256
```

The inventory classifies dependencies; it is not itself an exhaustive approval
of a physical column contract. The contraction guard still requires exact
type/default/constraint and dependency validation under a bounded lock.

## Recovery-only candidate and local verification

The new manual workflow `phase3-production-recovery.yml` requires the protected
production environment and shares `production-deploy` concurrency. It first
runs unit tests and a synthetic encrypted backup/restore on the GitHub runner.
Only afterward does it stream the reviewed Python source over SSH to EC2.
It does not update the host checkout or pull/build/deploy images there.

`deploy/phase3_recovery_remote.py` requires root, the exact owner-accepted 3A SHA
and recovery-only confirmation. It takes a nonblocking host lock, verifies hashes
of the unchanged host Compose, bootstrap, backup-status and restore helper files,
and checks every production container's running state/image and ARM64 identity.
Web/database must be healthy. The existing 3A commands audit the live database
through read-only sessions in the existing web container.

The script requires at least 1.5 GiB host memory and 1 GiB Docker free space;
after the fresh backup it checks Docker and temporary-file storage against the
greater of 1 GiB or four times the audited database size plus two encrypted
copies. The production run below passed these guards; exact capacity readings
are not included in the downloaded operational summary.
Insufficient capacity stops the gate without silently reducing thresholds.

The existing encrypted DB-backup service creates and remotely verifies a new
managed release. The new guard matches local/remote/service release metadata,
operation-time timestamp, verified state, exact basename, bytes and checksum.
The existing service retains only the newest local encrypted recovery point;
earlier remote backups remain governed by the existing retention policy.
No new destination or credentials are introduced.

A verified encrypted copy is restored through the unchanged managed helper into
a UUID-named disposable project. Web, PostgreSQL and Redis are pinned to the
actual running image IDs, with `pull_policy=never`, no published ports, an
internal network, and isolated named volumes. Limits are DB 768 MiB/0.50 CPU,
web 512 MiB/0.35 CPU, Redis 64 MiB/0.05 CPU. Merged Compose configuration and
actual running limits/image IDs are both checked. The actual 3A entrypoint runs
only in the restored stack; restored metadata and continuity must pass.

The helper process group is stopped before cleanup on timeout/interruption.
Only the newly allocated project is removed, including its volumes/network,
and removal is verified. A cleanup failure retains its private environment path
for attended cleanup and fails certification. Production is independently
rechecked after success or failure, without inheriting restored DB/Compose
environment variables. Raw logs remain root-only under the managed backup
directory; only controlled operational summaries reach GitHub logs/artifacts.

This is database-only recovery, not a media restore or a cleanup command. It
neither removes quantity metadata nor proves rollback against a future contracted
database. Both remain separate requirements.

| Local gate | Result |
|---|---|
| New recovery unit/failure tests | 16/16 PASS on host and Linux/ARM64 Python 3.12 |
| Existing inventory transport/static-retirement tests | 8/8 PASS under Linux/ARM64 |
| Phase 0–3A / 27–30 release contracts | 152/152 PASS, including serial source preservation |
| Existing backup/retention/operation/restore contracts | 71/71 PASS |
| Earlier Phase 0 recovery contracts | 22/22 PASS; historical script unchanged |
| Actual Compose merge and synthetic encrypted DB restore | PASS using published 3A ARM64 image; RTO 44 seconds |
| Restored strict serial and metadata audits | PASS; cleanup authorization remains false |
| Actual restored image/resource limits and disposable removal | PASS; independently checked containers, volumes and networks absent |
| Production recovery | PASS — protected run `33760176723`; separate production evidence below |

The local synthetic backup timestamp was `20260903T124308Z`, size 542,752
encrypted bytes. Published 3A image ID:
`sha256:6cb14f877396118ccdae4b75f0bdef95861276e8bd1d31802acf86e8a1b8c6bc`.
The local PostgreSQL image differs from production's running image; the
production gate will pin the actual host image IDs, not local/runner tags.

Synthetic source project `dbbackup_rehearsal_phase3source_aec1a0e1ae4e4097ab8a56bc38c31f38`
and restore project `dbbackup_rehearsal_phase3_b6e68ac7eac9492d813e328c43388db5`
were removed. The synthetic environment and passphrase were removed; retained
synthetic logs/bundle are outside Git in the temporary directory
`phase3-recovery-synthetic-gowbzzfb`.

```text
6f52f1b44579b49bdbd041b33a2b27137f9d3ef665e8bb86ab49f4dd05f9062b  synthetic-backup.log
ac911a7afa2e918d40ce03e2fdb22c95a7385303c9ceb8c9a5583435ff9e2db2  restore-private.log
59a141a1d7e5e6015f4eb1904308f1df7e5caf93875fc94e0126f76f7b3ba465  restored-serial_only_phase3_audit.json
fecc21eb5ee87840b3d406d11c7104f9bfccff39bbdc273dc1f50532adeb964a  restored-serial_only_phase0_audit.json
```

An initial Linux unit-test invocation used a `noexec` temporary filesystem,
blocking the older transport test's fake executable before any Docker call.
It passed when rerun with executable temporary test fixtures; no production
permissions changed. Adding runner-only image pulls for synthetic rehearsal
also required narrowing the static no-pull assertion to the remote execution
step; production still never pulls images. Neither issue was a production
failure. The full application suite was not rerun for this recovery-only source
change; application/model/migration/frontend/tenant SQL remain unchanged.

## Verified protected production recovery

The owner explicitly authorized pushing
`962f36feec98f2ab1babff1fc50ec7efe34c125c` to `main`. The push used `[skip ci]`;
no automatic CI/CD run started. The owner separately authorized dispatch of
[run `33760176723`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33760176723)
and approved its production gate externally. The agent did not submit that
protected approval. All run steps succeeded, including the GitHub-runner
synthetic rehearsal before SSH. The job completed at `2026-09-03T13:59:08Z`.

The downloaded operational summary and the checked-out controller establish:

- Source SHA `962f36feec98f2ab1babff1fc50ec7efe34c125c`; deployed/restore target
  remains the owner-accepted 3A SHA `497b6650ed678bc462f85de6bff14692bffd6ace`.
- New operation-time encrypted database backup release
  `db-backup-20260903T135747Z`. A separate read-only GitHub release lookup
  confirmed publication at `13:57:54Z`, non-draft/non-prerelease status, the
  encrypted asset (532,512 bytes), and its checksum asset (108 bytes) in the
  existing private backup repository. That independent lookup inspected only
  release metadata, not backup contents. Checksum/decryption/restore validation
  was performed by the protected workflow.
- Isolated restore RTO **51 seconds**, as measured by the existing restore
  helper; this is not total workflow duration or an application-wide recovery
  guarantee. It covers the database-only bundle, not uploaded media.
- Exact disposable project
  `dbbackup_rehearsal_phase3_d829a63d7e3e40529b8d69c0cb2ac91d`. Before reporting
  PASS, the controller verified its restored image IDs/resource limits, both
  strict audits, and removal of its containers, volumes and network. Its private
  temporary environment and encrypted working copy were removed afterward.
- The controller passed production read-only metadata/continuity audits before
  and after, checked unchanged production container/image identities and health,
  and passed the final HTTP check. The summary explicitly records
  `production_container_images_unchanged=true`, `result=PASS`, and
  `authorizes_cleanup=false`. This is not a before/after financial-balance
  equality claim while customers continue transacting.

The [retained artifact `9896759886`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33760176723/artifacts/9896759886)
contains the controlled operational summary, with 90-day retention. The local
download is outside Git:
`/tmp/phase3-recovery-review-33760176723.GATqry/phase3-production-recovery.log`.

```text
4ea0d5533754c4f32d6a8f036b0c0ea597c312d4ed4adab1cde38598790996f9  GitHub-reported artifact ZIP SHA-256
31e4257a6a8579ff4f657bade0e217988139b20487068320847ca7bf170005ee  downloaded recovery summary SHA-256
```

Raw backup-service, restore, audit and cleanup logs remain root-only on EC2 in
`/var/lib/financee-backup/phase3-recovery-evidence/20260903T135745Z-5ad5e9dab2584524ad2a4a68a8e1bc7d`.
They were not downloaded or added to Git. The final checks above are therefore
verified through the successful controller and summary, not claimed as a
separate direct inspection of each raw host log.

The owner's initial “its passed” reported the workflow result. The subsequent
“yes it working fine” records the owner's manual live-site PASS after recovery,
not final 3B acceptance or independently observed transaction-by-transaction
verification. At this preparation checkpoint the controlled cleanup remained
unauthorized. It was later completed only after the additional approvals and
gates recorded in `PHASE3B_PRODUCTION_RESULTS.md`; see also
`PHASE3B_EXECUTOR_RESULTS.md`.
This successful recovery establishes readiness to prepare it, not permission to
remove records or reuse this recovery point indefinitely. Evidence freshness and
exact cleanup preconditions must be checked again at destructive execution.

## Required implementation and operational safeguards

1. Review the fresh inventory, then prepare recovery using the current 3A image.
   The existing Phase 0 recovery script defaults to an older audit image and its
   workflow uses a different concurrency group from production deployment. Do
   not run it unchanged or assume the historical recovery evidence is fresh.
   Preserve resource/capacity limits for the 4 GiB ARM64 production host, unique
   disposable stack targeting, isolated credentials, and explicit reset to the
   production environment after restore. New tooling requires local failure
   tests, exact source approval, and protected execution.
2. Design an exact-target archive and restoration path for reviewed permission
   rows and direct/group grants, including identifiers and original metadata.
   Account/grant mappings must remain in protected storage, never source control
   or normal workflow logs. Archive retention/removal is a separate decision.
   Prove restoration, conflict handling and transaction rollback before deletion.
3. Scope permissions by exact `auth.user` content type, codename, reviewed label
   and candidate identity. Preserve same-codename permissions on other content
   types, unrelated grants, users, memberships and subscriptions. Recheck the
   candidate set at execution; changed/customized or unexpected dependencies stop
   cleanup rather than silently expanding its targets.
4. Remove only reviewed retired feature-list entries, retaining all other values
   and order. If the fresh inventory still has no stale entries, do not rewrite
   company JSON merely to normalize it. Archive and verify originals if needed.
5. Contract only the redundant public `inventory_mode` column and its exact
   known default/constraint after bounded, fail-closed dependency checks. Never
   use `CASCADE` to overcome an unexpected dependency. Preserve shared currency,
   tax, provisioning and serial feature metadata and all serial tenant objects.
   Define and test reversal separately from image-only rollback.
6. Test actual deployed 3A normal startup, authenticated serial workflows and
   company creation on the contracted database, then re-upgrade. Check that
   old-image migration startup does not recreate retired metadata. Synthetic
   fresh databases must pass historical migrations before explicit cleanup.
   Automatic fresh-install retirement/migration replacement remains Phase 4;
   applied historical migrations remain untouched at this operational checkpoint.
7. Pass serial source-preservation, full regression, isolation, ARM64, encrypted
   restore, exact-image staging, and failure/lock-contention tests. Prove the
   pre-deployment audit also works on the uncontracted production database.
8. Obtain exact-commit push approval and all protected release gates. A fresh
   operation-time production backup with verified isolated restore and reviewed
   exact-target cleanup approval must precede destructive execution. Revalidate
   all execution-time preconditions; an older inventory cannot authorize newly
   appearing records or dependencies. Serial continuity and health must pass
   afterward. The owner then manually verifies production before Phase 4.

The subsequent executor candidate implements this as no-image-change attended
maintenance: its dedicated runner job performs full regression, core failure,
executor recovery and release-contract tests before protected production
approval; the actual-host image/backup/round-trip checks precede the live write.
It does not publish another application image or claim an image staging release.
This implementation refinement and remaining approvals are documented in
`PHASE3B_EXECUTOR_RESULTS.md` and `../PHASE3B_MAINTENANCE_RUNBOOK.md`.

No tenant-schema drop is planned based on the old inventory. Any newly found
orphan requires independent classification and exact-target authorization;
the earlier Company 2 permission cannot be reused. These are gate requirements,
not claims of executed cleanup. The companion local-candidate report identifies
which controls are implemented/tested and which production gates remain pending.
