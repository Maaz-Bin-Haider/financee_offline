# Serial-Only Consolidation Phase 2 — Runtime Removal Results

**Execution dates:** 2026-09-02 to 2026-09-03

**Target:** AWS EC2 `t4g.medium`, ARM64, `ap-south-1`

**Preservation baseline:** `102e55e857bbffa8bd4318e6afaec42e048c8e67` (Phase 1)

**Deployed Phase 2 commit:** `e44737f1f740fa936e853a3d6bbbd068a1b6d89d`

**Protected workflow:** `33728502631` — all 12 jobs PASS

**Production deployment:** PASS — controller completed at `2026-09-03T07:39:52Z`

**Owner manual Phase 2 production verification:** PASS — 2026-09-03

Phase 2 is complete. Phase 3 has not started and requires a separate explicit
owner instruction. This record does not authorize database cleanup.

## Scope and preservation evidence

Phase 2 removes the quantity HTTP runtime, not database history. It deletes
17 quantity Python adapter/route modules, 10 templates, and 12 source static
assets. It removes their URL registrations, dispatch branches, dashboard
branches, attachment fallback, feature controls, and startup SQL maintenance.
Serial document routes retain the existing trusted-company and write-payload
checks. Unsupported SQL rollout and release-preflight families fail closed.

Independent preservation anchors were extracted from the deployed Phase 1
commit above, not from the candidate:

- All 12 serial purchase, sale, purchase-return, and sale-return implementation
  functions have identical source text.
- All 212 retained serial/shared UI source files are byte-identical. The shared
  base template is explicitly excluded because its quantity-only menus and
  mode conditions are intentionally removed; serial links and feature checks
  remain.
- All 17 serial SQL/bootstrap files are byte-identical, including the serial
  tenant template and existing startup hardening/index scripts.
- No database model fields, applied migrations, tenant SQL, Dockerfile,
  Compose production configuration, dependency versions, or production
  deployment-controller code are changed.

Quantity schema descriptors are retained for inspection but have no enabled
request paths. Historical SQL, migrations, permissions, company metadata, and
inactive historical tests remain for controlled Phase 3/4 cleanup. This phase
does not drop a production schema, table, or column.

## Persistent static-volume handling

Deleting source files alone does not remove their copies from the existing
Docker static volume. `deploy/retire_quantity_static.py` therefore removes only
the fixed list of 12 retired asset names, their 12-hex hashed variants, and
optional gzip/Brotli copies. It validates all candidates before deleting,
rejects symlink/non-file targets, and never clears the volume or old serial
hashes. Three unit tests cover exact matching, nonmatches, idempotence, and
symlink rejection. Old-image rollback repopulates its own baked assets.

## Automated evidence

The local runtime tests use synthetic data in isolated Docker projects. The
protected workflow and owner production acceptance are recorded separately
below; local tests are not represented as production observations.

| Gate | Result |
|---|---|
| Phase 0/1/2 and Phase 27–30 static/release contracts, Python 3.12 | 114/114 PASS |
| Backup, retention, operations, and restore contracts | 71/71 PASS |
| Narrow static retirement unit tests | 3/3 PASS |
| Django system check | PASS — 0 issues |
| Migration drift | PASS — no changes detected |
| Serial regression matrix | 51/51 PASS, zero XFAIL |
| Per fresh serial tenant: system/deep lifecycle baseline | 111/111 and 2702/2702 PASS |
| Phase 1 live creation-freeze checks | 15/15 PASS |
| Phase 2 live runtime-removal checks | 13/13 PASS |
| Four-serial concurrent isolation/security | 16/16 PASS |
| Full active production-stack suite | 21/21 modules PASS |
| ARM64 build and execution smoke | PASS; 6/6 smoke + 13/13 Phase 2 checks |
| Encrypted backup/restore/Phase 1 image rollback/re-upgrade | PASS |
| Failed-health rollback simulation | PASS |
| Locked dependency consistency (`pip check`) | PASS |
| Production-like staging, security, and capacity preflight | PASS |
| Protected exact-SHA CI/CD | PASS — all 12 jobs in run `33728502631` |
| EC2 deployment and production-controller gates | PASS |
| Owner manual production verification | PASS — 2026-09-03 |

The full active suite includes serial parties/items, purchases, sales, returns,
cash movement, opening balances, owner equity, month close, reports, 208
attachment checks, 40 subscription checks, 46 subscription-email checks, 77
feature checks, 14 metadata checks, 30 company-setup checks, and 70 HTTP checks.
The serial matrix additionally checks two fresh schemas, deep lifecycles,
balanced journals, report contracts, and absence of quantity schema objects.

The new runtime gate proves retired URL names are absent, retired paths return
404 for a real authenticated serial tenant, serial pages still render, legacy
payload identifiers are rejected, serial payloads are accepted, fresh serial
provisioning succeeds, and quantity SQL rollout is blocked.

### Recovery rehearsal

The synthetic encrypted database/media bundle was created at
`20260903T072031Z` and was 1,003,552 bytes. Its checksum passed; a deliberately
corrupted copy was rejected. Restore RTO was 43 seconds and the complete local
rehearsal took 181 seconds. The RPO was zero for this controlled synthetic
snapshot; this does not claim a production recovery objective.

The rehearsal ran the actual Phase 1 image
`ghcr.io/maaz-bin-haider/financee-web:102e55e857bbffa8bd4318e6afaec42e048c8e67`
against the restored/forward-applied database. Django check, serial preflight,
and the serial-only registry constraint passed. The old image repopulated its
quantity static files. Switching back to Phase 2 removed those files and
preserved an older synthetic serial cached-asset sentinel. Final serial
preflight passed. Both uniquely named disposable projects and their volumes
were removed and that cleanup was independently checked.

### Staging acceptance

The preliminary image was explicitly labeled
`local-working-tree-cbb117f8210f`; it is not represented as the Phase 1 commit
or a published Phase 2 image. Its image ID and running container image matched.
The before/after foundation audit reported unchanged tenant set and continuity.
Security unit tests passed 5/5, serial checks 51/51, creation checks 15/15,
runtime removal 13/13, and concurrent isolation 16/16. All six capacity
preflight checks, final serial preflight, and Redis health passed.

The clean release commit `e44737f1f740fa936e853a3d6bbbd068a1b6d89d` was then
rebuilt and passed the same local staging acceptance. Its source-revision
label, image ID, and running container image matched. After the owner
authorized the push, the protected exact-SHA workflow also passed.

## Protected production evidence

- [CI/CD workflow 33728502631](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33728502631)
  is completed with conclusion `success` for the exact Phase 2 SHA above.
- All 12 jobs succeeded: static/Django/migration contracts, serial regression,
  creation freeze, runtime removal, four-company isolation, ARM64 execution,
  full regression, encrypted recovery, exact-image staging, protected staging
  approval, multi-architecture publication, and protected EC2 deployment.
- The deployment log names `PHASE30_RELEASE_SHA=e44737f1f740fa936e853a3d6bbbd068a1b6d89d`.
  It reports deployment completion at `07:39:21Z`, then tenant-balance and
  continuity comparison, operational-threshold capture, and the controller's
  final `Phase 30 production foundation deployment PASS` at `07:39:52Z` on
  2026-09-03. This is a successful completion of the fail-closed controller;
  the underlying on-host JSON evidence was not separately downloaded here.
- The workflow completed at `2026-09-03T07:39:55Z`.
- The owner then reported: “the complete CI CD passed and the actual deployed
  site is working fine”. This is recorded as the Phase 2 manual production
  acceptance. No claim is made that individual transaction checklist actions
  were separately observed or reported.

## Failures, corrections, and limitations

- A full-suite attempt from before the usage interruption had no recoverable
  completion result. It was not counted; the complete suite was rerun and its
  21/21 result captured on 2026-09-03.
- Safety review blocked the inherited test harness because its default Compose
  project and `down -v` cleanup could target normal local volumes. The harness
  now uses a unique disposable project and a private temporary environment
  file. It no longer writes `deploy/.env`; the corrected full/ARM64 runs passed.
- The initial preservation test used `ast.dump()` hashes generated under host
  Python 3.14. Its formatting differs from production Python 3.12, producing a
  false failure. Independently comparing exact function source confirmed no
  serial implementation change. The test now hashes exact source segments
  from the deployed baseline and passes under Python 3.12.
- An auxiliary network-disabled Django check initially omitted dummy `DB_PORT`.
  Supplying that required setting corrected the invocation; Django reported
  zero issues and no model drift. Without a database, that auxiliary migration
  check warns that migration history cannot be queried. The focused live-stack
  checks also passed against PostgreSQL.
- The pre-existing bootstrap/template stored-function drift remains unchanged.
  The focused serial gate's two-schema strict Phase 0 audit fails closed on
  that drift; its existing five-check known-CI-drift verifier passes. This is
  not represented as a clean strict two-schema audit or silently repaired.
- The staging capacity check is a configuration/headroom preflight for the
  existing 100-session target, not a new 100-session load benchmark on EC2.
- Local tests alone do not establish production health. The completed
  production-controller run and the owner's manual acceptance provide the
  separate Phase 2 production evidence above.

## Local audit artifacts

Raw local logs are retained outside Git; they are not included in the source
commit or uploaded by this work:

- `/tmp/phase2-full-20260903.log`
- `/tmp/phase2-arm64-build-20260903.log`
- `/tmp/phase2-arm64-20260903.log`
- `/tmp/phase2-contracts-20260903.log`
- `/tmp/phase2-recovery-20260903.log`
- `/tmp/phase2-recovery-20260903/` (synthetic encrypted bundle and recovery checks)
- `/tmp/phase2-staging-20260903.log`
- `/tmp/phase2-staging-20260903/` (local working-tree image provenance and gates)
- `/tmp/phase2-exact-staging-20260903.log`
- `/tmp/phase2-exact-staging-20260903/` (committed Phase 2 image provenance and gates)

SHA-256 audit anchors for the completed local runs:

```text
c41f952c3818d1e1ff652b01c887378313b720c0c0b7ba76c284024751a9e480  phase2-full-20260903.log
fc4a2a1ba8e51d2e6e7087c37a1476e670f26b8d2426076af1636ae67b0f79ba  phase2-contracts-20260903.log
4fb18d2d5e5d3f9068076235731fe17a05b418b370800e41ef838057ad97459b  phase2-arm64-20260903.log
1fc67be5596d4549aa7bfd69ed2d411c96963507d9c977a714cee4ba4cbc390f  phase2-recovery-20260903/phase28-results.env
dbc93297e17afcbb026b4683963de25e704c6a47e8fe1ba5a583ea841e272bc0  phase2-staging-20260903/acceptance-summary.json
```

## Exit status

**PASS — Phase 2 complete.**

The implementation, authorized push, protected exact-SHA CI/CD, production
deployment, automated production gates, and owner manual acceptance are
complete. Historical database metadata/source cleanup remains deferred to
Phase 3/4. Phase 3 may start only after a separate explicit owner instruction;
any destructive database cleanup still requires its own exact-target review,
backup/restore evidence, and approval.
