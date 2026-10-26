# Phase 3B — Protected executor candidate

**Date:** 2026-09-03

**Original scope:** the owner authorized preparing and testing the protected
executor locally. That preparation did not itself authorize production work.
Subsequently, exact source `bc5cdce` passed the required strengthened read-only
inspection and separately authorized protected apply run `33887331226` completed
with `confirmed_committed`; the owner then accepted the live site. The final
production record is `PHASE3B_PRODUCTION_RESULTS.md`.

The accepted read-only target evidence is in `PHASE3B_CONTROLLED_CLEANUP_RESULTS.md`:
run `33773691381`, source `a70f8a1`, deployed image `497b665`, target digest
`f29440c28fb0acf2640e9a9794918d5adf932cf8a4a2932b0e9b9dacd114b4b4`.
Its 14 quantity permissions/14 direct grants, redundant column and absence of
stale feature entries/orphan schemas remain the proposed scope, not permanent
execution authorization. No fresh production state was assumed or queried here.

## Implemented components

- `deploy/phase3b_cleanup_remote.py`: explicit apply/restore controller with
  exact image/source/core identity, reviewed target digest, typed confirmation,
  UTC maintenance window, attending recovery owner, root/shared-host-lock,
  capacity and helper-hash gates. Fresh managed encrypted backup and isolated
  action/reverse/action rehearsal must finish and remove their resources before
  a single live mutation is sent. Production is rechecked afterward, including
  failure paths. There is no automatic retry, reversal or production restart.
- `deploy/phase3b_cleanup_bundle.py`: checksummed, exact-source-SHA-bound stdin
  transport for controller, recovery helpers and checksum-pinned core.
  Source is not copied into the production container or host checkout.
- `deploy/phase3_recovery_remote.py`: two backward-compatible additions only:
  optional subprocess stdin and optional restored-stack verifier. With no
  verifier, the previous recovery workflow retains its original audits and
  cleanup. With the new verifier, the same resource/image/isolation safeguards
  and guaranteed cleanup surround contracted-state tests. Host shell helpers,
  existing service configuration and backup destinations are unchanged.
- `phase3b-controlled-cleanup.yml`: manual-only maintenance with synthetic
  runner tests followed by protected `production` approval; serialized with
  production deployment/recovery. Inputs require an explicit digest, action,
  confirmation, exact image, window and owner. The workflow cannot run on push.
- CI adds executor contracts/units and encrypted executor rehearsal to the
  existing mandatory cleanup gate; existing publication/deployment gates remain.

Final review identified additional internal-FK cascade paths that the initial
`a70f8a1` guard did not explicitly reject: a foreign table referencing direct/
group assignments, the archive state, or company feature lists. The core now
rejects all such incoming dependencies inside its existing read-only inspection
and under transaction locks during mutation. New negative PostgreSQL fixtures
cover both assignment-delete cascades, feature-update cascades and archive-state
update cascades. It also requires the exact permission/assignment columns and
types from the reviewed bootstrap, rejecting unknown columns, custom checks and
table inheritance: otherwise an unarchived extension could be lost during
retirement/reversal. This adds only precondition reads; archive/delete/restore/column
mutation SQL is unchanged. A **new protected read-only inspection is required**
before execution approval, even if the target digest remains unchanged.

The new core is pinned to SHA-256
`9699731c843b02c213c99cb4efaa8c79d75dcd6c7fb3752d0b03816b876a1a00`.
No serial business code, UI, models, tenant SQL, migration, runtime dependency,
Docker image definition or application entrypoint changed.

## Explicit failure semantics

The controller durably records `not_attempted`, then `unknown` before sending
a mutation, and `confirmed_committed` only after the core returns success.
An uncertain response never means assumed rollback. Later failed health or
fingerprint checks leave the overall result FAIL even when mutation committed.
Private failure diagnostics and attending-owner details remain root-only;
only controlled status metadata reaches workflow output.

The worker's 90-second deadline executes inside the container, independently
of the Docker client's 120-second timeout. A local injected delay after the
archive/delete/column-drop statements demonstrated real PostgreSQL rollback
when that worker deadline fires. This does not claim that SIGKILL, host loss or
a lost response always permits certainty; those require attended inspection.

Maintenance takes table locks briefly and can delay requests. Lock wait is two
seconds; statements are bounded at 30 seconds. A zero-interruption guarantee is
not made. The maintenance window and named attending owner still need explicit
user choices before production dispatch; neither is invented by the candidate.

## Validation and coverage

Controller unit tests exercise missing/wrong authority, source/image/core
mismatches, window expiry, missing owner, private durable status, real local
host-lock contention, shell argument quoting, malformed inspector output,
uncertified continuity, backup/restore/storage failure, target/container drift,
single-write sequencing, ambiguous write responses, post-commit drift and
post-commit health failure. Both apply and restore paths are covered. Existing
recovery tests also cover the optional verifier's failure cleanup and stdin path.

Real Docker integration uses the actual published ARM64 3A web image, local
PostgreSQL/Redis images, and only synthetic data in isolated UUID projects.
It seeds all 14 direct quantity grants, exercises streamed read/write transport,
verifies a post-DDL deadline rolls back the original state, takes a locally
encrypted backup, and performs apply → restore → apply on its restored copy.
It then cleans the synthetic source, takes a new encrypted backup of that
contracted database, and performs restore → apply → restore on another copy.
Both copies run the unmodified published image's normal startup and retain
their metadata state, serial structures and financial-continuity fingerprints.
The original default recovery path is also rerun from the first encrypted backup.

These are **not** calls to the production executor entry point, production
service manager or GitHub backup publisher. Full controller sequencing is
unit-tested with those external boundaries mocked; the transport, PostgreSQL
transactions, encryption/decryption, restore helper, resource limits and
disposable image startup are exercised for real. The future protected production
run must additionally verify a new remote backup and actual host image IDs.

| Gate | Local result |
|---|---|
| Core cleanup and failure tests | 68/68 PASS |
| Pre-cleanup company creation / metadata | 15/15 and 14/14 PASS |
| Full active serial suite after contraction | 21/21 modules PASS; serial 51/51, isolation 16/16 |
| Published 3A compatibility and final read-only contracted-state inspection | PASS |
| Release/preservation contracts, including executor | 200/200 PASS on ARM64 Linux/Python 3.12.14 |
| Backup/retention/operations/restore contracts | 71/71 PASS on the same image |
| Historical Phase 0 recovery contracts / failed-health rollback simulation | 22/22 PASS / PASS |
| Controller/recovery/inventory/static-retirement unit tests | 46/46 PASS on ARM64 Linux/Python 3.12.14 |
| Encrypted apply and reversal round trips, default recovery path | PASS; final-source evidence recorded below |
| Syntax, workflow YAML/embedded shell, whitespace checks | PASS |
| Production execution / GitHub maintenance workflow | Subsequently PASS in protected run `33887331226`; see `PHASE3B_PRODUCTION_RESULTS.md` |

The local PostgreSQL image is 16.15; the inspected production host reported
16.14. No equivalence is assumed from tags: the production controller pins
actual running image IDs. Published ARM64 web image ID remains
`sha256:6cb14f877396118ccdae4b75f0bdef95861276e8bd1d31802acf86e8a1b8c6bc`.

Earlier executor and 55-/62-check regression rehearsals passed before final
guard review. The final strengthened-source evidence is recorded below; the
earlier local results are not used as substitutes for rerunning this candidate.

Final full-regression evidence directory (outside Git):
`/var/folders/qv/qpbw48nx28x_w6tw3q_g7v440000gn/T/phase3-recovery-synthetic-xqv3ekae`.
The completed harness reported cleanup of exact project
`dbbackup_rehearsal_phase3source_c0147167f84c473a847c52f161485c6c`.

```text
6a10f92425c7e0448d49abfb5d2f5d220dbbda50d664b247b776f54df36249a0  cleanup-tests.log
8efd461a28c4fe63bef17f919b950b327e159d96190423197c4f0214844df1fb  post-cleanup-full-suite.log
f933aab6321ff3dec84d91072cfdcaf8c71efb60fd1e7d8e337194ccaa7e4adb  post-suite-cleanup-state.json
```

Final executor evidence directory (outside Git):
`/var/folders/qv/qpbw48nx28x_w6tw3q_g7v440000gn/T/phase3-recovery-synthetic-2v5r_i3c`.
Apply and restore round trips passed, including actual published-image restart
and unchanged isolated serial/financial-continuity fingerprints. The managed
helper measured database-restore RTOs of 44 seconds before apply and 45 seconds
before reversal; these are not full workflow durations or production RTO claims.
The original no-callback recovery path also passed, with helper RTO 45 seconds.
The injected in-container deadline occurred after destructive DDL and exact
original metadata was verified restored by PostgreSQL transaction rollback.

Final disposable executor projects:

```text
dbbackup_rehearsal_phase3source_d07eae4453424bceaa307fc3e17f682a
dbbackup_rehearsal_phase3_857d1294666e40c7acabb7154c4d901d
dbbackup_rehearsal_phase3_8b9b6d08a59949f0b6f8a6e379dd6e45
dbbackup_rehearsal_phase3_3832104e5d134eab9b6a60e12ed96b48
```

The harness confirmed removal, and independent exact-label Docker queries
confirmed no containers, volumes or networks remain for those four projects
or the final full-regression source project. Private synthetic environments and
passphrases were removed. Logs and encrypted synthetic fixtures remain outside Git.

```text
d1ffbda374424870eb470d10c169b9aa436bda93ea2a0ae4a21a75d74e414d2f  executor-summary.json
bd0642b99399f303e796f40f0e004ccd6c5ad4f958218923ebd54919fdae74d6  synthetic-deadline.log
5e0b597f211c57a5e2e54da7086fe9fab75401f08a2df6fc1415f274ba17a265  synthetic-cleanup.log
```

Final source SHA-256:

```text
e6fdcb8df2beea664aeaf484f913226fc83a1e0f89e09a84357a34b17f930d95  deploy/phase3b_cleanup_remote.py
026116458109e59407f5fbdcecc27beebb5f6e00951c673bc7d04faf4a7317ad  deploy/phase3b_cleanup_bundle.py
fde8ff392be14ff52000f26b3b931b3b629f4698343059813b59efb5c1552268  deploy/phase3_recovery_remote.py
9699731c843b02c213c99cb4efaa8c79d75dcd6c7fb3752d0b03816b876a1a00  tenancy/management/commands/serial_only_phase3_cleanup.py
bf7e930f04cfbe1ae8cb2eaf986c336371bc52b7a12420c2c8893a02cf950ae3  tests/phase3b_cleanup.py
2d940c1841ae7e61c76d5133f806a30fd4338e1d7f8fac330bc28ddb0cc74c02  tests/phase3b_executor_local.py
924e46307d93f6dd5da617f2aa9f750f65bc420a70ba5ad7dce9495640d21a36  tests/phase3_recovery_local.py
```

A direct source comparison with `a70f8a1` verified that `make_archive`, `apply`,
`restore` and `operate` are byte-identical function bodies. Only inspection
preconditions changed in the core. This narrows the behavior change but does
not waive the required new read-only production inspection.

## Release boundary

The operator procedure is `PHASE3B_MAINTENANCE_RUNBOOK.md`. Because this is an
explicit maintenance transaction with no image change, its dedicated runner
gate executes full serial regression, core failures, executor encrypted recovery,
release/backup contracts and controller units before the protected production
gate. The actual production-image recovery/round-trip rehearsal runs after that
approval but **before** any live mutation. This is a documented refinement of
the earlier image-release/staging plan, not a bypass of production approval.

Those subsequent gates completed on 2026-09-04: exact source `bc5cdce` was
pushed with `[skip ci]`, strengthened protected inspection `33879212477` passed,
and the owner separately approved the exact scope, window, attending owner and
workflow. Protected run `33887331226` passed rehearsal and actual-host recovery,
reported `confirmed_committed`, and passed final checks. The owner then reported
the live site online and working. See `PHASE3B_PRODUCTION_RESULTS.md`.

No blanket future cleanup, reversal, archive deletion or Phase 4 authority is
inferred from that one completed operation.
