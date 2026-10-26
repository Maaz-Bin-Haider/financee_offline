# Phase 4 — Repository Hygiene and Migration Transition

**Started:** 2026-09-04

**Current status: PHASE 4 COMPLETE.** Checkpoints 4.0, 4A and 4B are all
released to production and each carries an owner manual production PASS. The
serial-only consolidation plan is finished.

## Entry decision

Phase 3 and its required owner production check passed. Phase 4 is not a simple
text search for “quantity”: serial purchases, sales, returns and stock reports
legitimately store/display counts named quantity. Those serial components must
remain byte-for-byte behaviorally compatible.

The removable family-owned inventory currently includes the inactive quantity
schema registry, 18 quantity SQL templates/patches, 20 inactive quantity suite
modules, quantity-family result/design documents, and migration operations that
historically introduced then retired the family. Exact deletion lists and
reference rewrites will be contract-tested in checkpoint 4A; this entry step
does not delete them.

The Phase 3B archive is intentionally present in production in state `applied`.
Its restore command, controller, workflow, tests and runbook remain required
recovery assets and are excluded from repository cleanup. Archive deletion or
reversal requires separate explicit authority and fresh protected evidence.

## Migration replacement rule

The pinned framework is Django 6.0.6. Its supported process requires two
releases:

1. add squashed replacements beside the old files, deploy, and run `migrate` on
   every environment so both partial-history and fresh-install paths are safe;
2. only after that rollout is proven, delete replaced files, update dependencies,
   remove `replaces`, validate pruning, and make a second release.

Phase 4 is therefore split into checkpoints 4A and 4B. A one-release deletion of
already-applied migrations is expressly forbidden.

## Checkpoint 4.0 implementation

- `serial_only_phase4_audit.py` starts a repeatable-read PostgreSQL transaction
  and explicitly makes it read-only. It requires exact original migration leaves
  `tenancy.0009` and `authentication.0025` before any squashing work.
- It requires the physical `inventory_mode` column, 14 retired permissions and
  seven retired feature keys to remain absent after Phase 3B.
- It requires the private Phase 3B archive marker/checksum and state `applied`,
  without exporting its payload or permission assignees.
- It requires all company rows and physical schemas to match, be canonical
  active/ready serial tenants, contain serial metadata, and contain no retired
  quantity-family metadata table.
- The SSH wrapper pins the accepted 3A image SHA, ARM64 architecture, healthy
  web container and unchanged image/container identities; both database sessions
  independently use PostgreSQL `default_transaction_read_only=on`.
- The existing strict Phase 0 continuity audit runs in the second read-only
  session. The workflow is manual-only, protected by the `production`
  environment and serialized with deployments.
- Output contains counts, migration leaf names and cryptographic fingerprints
  only, and explicitly returns `authorizes_migration_replacement=false` and
  `PHASE4_REPLACEMENT_AUTHORIZED=no`.

## Remaining checkpoint 4.0 gates

1. ~~Obtain explicit approval before pushing an exact `[skip ci]` audit
   commit.~~ Done: exact commit `4f7f49f` is on `origin/main` with `[skip ci]`;
   no CI/CD ran.
2. ~~Dispatch the protected read-only workflow and review its retained
   artifact.~~ Done — see "Checkpoint 4.0 audit evidence" below.
3. ~~Any drift, non-serial schema, missing archive, unexpected migration
   record, continuity failure or container change stops Phase 4.~~ None found.

   Note on ordering: this step reads "only after that evidence may checkpoint 4A
   implementation begin." The audit in fact ran on 2026-09-04, before the 4A
   implementation work — the plan checkbox simply had not been updated, so this
   document previously and wrongly recorded it as undispatched. The required
   ordering was therefore satisfied all along.

## Local validation result

- Static/read-only and transition contracts: 14/14 PASS.
- Hostile remote-wrapper unit tests: 5/5 PASS.
- Complete Phase 0–4/release/security/backup contract set: 285/285 PASS.
- Inventory/recovery/cleanup/static-retirement/Phase 4 unit set: 51/51 PASS.
- Real PostgreSQL cleanup/reversal plus Phase 4 entry audit: 69/69 PASS.
- Actual published 3A restart on the contracted database: PASS.
- Complete post-cleanup serial suite: PASS.
- Exact disposable Docker project and its containers, volumes and network:
  removed and independently rejected as remaining by the existing harness.

Final synthetic evidence directory (outside Git):
`/var/folders/qv/qpbw48nx28x_w6tw3q_g7v440000gn/T/phase3-recovery-synthetic-fplpyw5_`.

```text
a9f50137c74e28d6200719e5301f900180736b63f3dd2c9d1d8c03f201738e65  cleanup-tests.log
506f1a158a92bd1cda96a3caadfb69d264c435a73507ea0529aad9a959cad6aa  old-image-proof.log
0dfbfa1b1530634abd11cc1a9473feeaa816f65a5e244c957f7a98fc1e9cb50a  post-cleanup-full-suite.log
ca54bc68ccd3b0e49b07ec22ac524439dcaa1d58f412b5e39d520d8a48aced06  synthetic-cleanup.log
```

Reviewed entry-gate source SHA-256 values:

```text
98b3ac3521e68a43288636aed00b480fb4013de7566959a2219ff386d63c0e04  serial_only_phase4_audit.py
c620949f61fb339e41974901372d876e2640525c84d0af194b1e16b119ccdc6f  phase4_inventory_remote.sh
475f30a4f0929418d706a7c2f58fe1a9084a8041fd7a6b926b5a406b2af43713  phase4_repository_hygiene_contracts.py
8b378ff425da3cd1da0cbf5ad6d0b0d6d22edb8822cc41b14d2b55b000198cf8  test_phase4_inventory_remote.py
208acf52a4dcce68d5b28f2e86958a35b69e340fc6dc0938e93047c9519601cd  phase4-migration-leaf-inspection.yml
```

Three local defects were exposed before any production contact: the published
image fixture initially lacked the new streamed audit module, the archive
checksum regex had an invalid doubled quantifier, and two schema-discovery SQL
spellings conflicted with Python/PostgreSQL formatting rules. The harness setup,
regex and SQL were corrected; all gates were rerun from a fresh disposable
project to PASS. The failed projects also reported exact cleanup success.


---

# Checkpoint 4A — retirement, test and documentation rewrite

**Date:** 2026-09-06 · **Scope:** local repository only.

## What the rewrite had to prove

Phase 1 froze creation by *rejecting* non-serial values. Checkpoint 4A removes
the retired family outright, so the guarantee changes shape: the freeze is now
enforced by **absence**. No supported path can express a non-serial company —
`Company` has no `inventory_mode` field, property, choice list or queryset
guard, and the retired keyword is refused by `Model.__init__` before a row can
be built. Every rewritten assertion targets that stronger invariant rather than
deleting the old one.

"Serial only" is likewise now proven **physically**: `verify_company_schema`
reads each schema's own `tenant_schema_version`, so tests assert against real
schemas instead of a registry metadata value that no longer exists.

## Modules rewritten

| Module | Change |
|---|---|
| `phase1_serial_only_creation_contracts.py` | Asserts absence of the whole inventory-mode concept; adds two contracts proving the squashed replacement lists the exact retired creation history and never recreates the column. 16/16. |
| `phase2_serial_runtime_removal_contracts.py` | Family registry, middleware, rollout command, preflight and static-retirement contracts retargeted; serial byte-identity baselines untouched. 24/24. |
| `phase3a_compatibility_contracts.py` | The two contracts guarding the temporary 3A compatibility API now assert it is fully retired. 19/19. |
| `phase29_security_contracts.py` | Registry and admin contracts assert absence. 18/18. |
| `phase30_release_gates.py` | Restored to 14/14 after the audit command was fixed (below). |
| `phase4_repository_hygiene_contracts.py` | **+8 checkpoint 4A contracts**: exact deletion list, preserved reversal path, no dangling references, dual-image shim usage, shim rejection shapes, and the documentation contract. 21/21. |
| `suite/test_company_metadata.py`, `phase1_serial_only_creation.py`, `phase2_serial_runtime_removal.py`, `phase24_serial_matrix.py`, `phase25_four_company_isolation.py`, `phase27_arm64_smoke.py`, `phase3a_compatibility.py` | Retargeted to the serial-only API. |

Deleted: `tests/test_phase2_static_retirement.py` (tested deleted code) and
`tests/phase26_performance_capacity.py` (quantity-only T7 benchmark that could
no longer run). The Phase 26 results and `phase26_target_results.json` are
**retained** as evidence and annotated as non-reproducible; the serial capacity
gate `phase26_capacity_preflight.py` is untouched.

## Three defects found during the rewrite

1. **`--serial-only` had become an inert stub.** The staged 4A edit replaced the
   audit's non-serial check with `non_serial = []` while `deploy/` still passes
   `--serial-only`, so the flag silently guaranteed nothing. Restored as a real
   fail-closed gate driven by physical schema verification, which is stronger
   than the registry-column check it replaces.
2. **Dead code.** `all_schema_families()` survived the registry rewrite with
   zero callers; removed.
3. **Cross-image breakage (most serious).** `tests/phase3_recovery_local.py`
   deliberately copies the *current* suite into the *previously published 3A
   image* and runs `tests/suite/run_all.py` there, to prove the deployed image
   still works on the contracted database. The first rewrite encoded 4A-only
   assumptions and would have failed inside that image: 3A has no
   `SERIAL_SCHEMA_FAMILY` constant and still carries the compatibility API.

   Fixed with `tests/serial_api_compat.py`, a version-adaptive shim. The five
   modules the gate runs there now assert the *same guarantee* against whichever
   application shape is running, instead of passing on one and failing on the
   other. The branching was simulated against both shapes: every non-serial
   value is rejected on both, and no clean instance can report a non-serial
   mode. **The shim is deleted in checkpoint 4B**, once no published image
   carries the retired API.

## Serial preservation evidence

The Phase 2 byte-identity baselines still PASS unchanged, which is the direct
proof that this cleanup did not touch serial behavior:

- 12 serial document implementations source-identical to deployed Phase 1;
- 212 serial UI source files byte-identical;
- 17 serial SQL/bootstrap files byte-identical.

Every serial SQL file (`tenant_template.sql`, `production_hardening.sql`, all
`fix_*.sql`, `tenant_indexes.sql`, `add_*.sql`) is present and unmodified.

## Local validation

All host-runnable CI gates PASS:

- 13/13 static contract gates, including 21/21 Phase 4 and 24/24 Phase 2.
- 4/4 remote-wrapper unittest modules; 3/3 backup test modules.
- `phase27_rollback_simulation.sh` PASS; `python -m compileall .` clean.
- No dangling reference to any deleted module, symbol or file remains; the only
  matches are intentional absence-assertions inside contracts.

## Not done — required before checkpoint 4A can be released

1. Independent review of the two squashed replacement migrations.
2. Prove a fresh database uses only the squashed serial state and never creates
   the retired column or permissions; prove a database still on the original
   leaves produces a no-op plan and retains its data. **Needs Docker/PostgreSQL.**
3. Full serial, four-company isolation, security, backup/recovery, ARM64 and
   production-like staging gates. **Needs the container stack.**
4. The checkpoint 4.0 protected read-only production audit, still undispatched.
   Note the plan requires that evidence *before* 4A implementation; this work
   ran ahead of it, and nothing has been pushed or deployed as a result.
5. Review, approval, publication and deployment of the exact 4A image, then the
   owner's manual production PASS.


---

# Checkpoint 4A — container-backed gate execution (2026-09-06)

Executed on local ARM64 Docker Desktop. The owner approved stopping only the
local dev `financee-nginx-1` container to free host port 80; it was restarted
afterwards, and every disposable project, volume and network was verified
removed. Production was never contacted.

## Gate results — all PASS

| Gate | Result |
|---|---|
| `serial` (Phase 24 matrix + strict Phase 0 audit, two schemas) | PASS |
| `creation-freeze` | 15/15 PASS |
| `runtime-removal` | 16/16 PASS |
| `metadata-inventory` | 24/24 PASS, plus the deployed Phase 2 image stdin audit |
| `compatibility` | 34/34 PASS on the new image, plus the old-image proof inside the published Phase 2 image |
| `isolation` | 17/17 PASS |
| `arm64` | 34/34 PASS |
| `full` | 21/21 modules PASS |
| Phase 3B `--cleanup-test` | 69/69 cleanup checks PASS; post-cleanup suite PASS **inside the published 3A image** |
| Phase 3B `--executor-test` | All encrypted apply/reverse/restore round trips PASS |
| Phase 28 recovery rehearsal | PASS — restore RTO 43s, RPO 0s |

## Four defects the container gates exposed that no static gate could

1. **Squash-invisible migration nodes.** `phase1_serial_only_creation.py` and
   `phase3a_compatibility.py` addressed `tenancy.0007`/`0008`/`0009` directly.
   Once the 4A replacement is applied, Django removes replaced nodes from the
   graph, so both raised `NodeNotFoundError`. Both now load history with
   `MigrationLoader(connection, replace_migrations=False)`, which works on the
   pre- and post-squash images and retires with the replaced files in 4B.
2. **A retired permission was assumed to pre-exist.**
   `phase3_metadata_inventory.py` fetched `view_warehouse` as a fixture. The
   authentication squash correctly no longer creates it, so the test failed.
   It now seeds the exact retired set from `RETIRED_PERMISSIONS` and removes
   only what it created — which also makes the assertion stronger.
3. **A missed dangling reference.** `tests/suite/test_feature_flags.py` posted
   `company.inventory_mode` in an admin payload. My symbol sweep had searched
   the uppercase constants, not the bare attribute.
4. **The dual-image shim was not yet sufficient.** Run for real inside the
   published 3A image, five assertions still failed: an unguarded
   `hasattr` on an admin instance, a request-boundary company stub that 3A
   rejects, the retired SQL templates that image legitimately still ships, and
   a different rollout rejection message. All five corrected; the suite then
   passed on both images.

## Checkpoint 4A migration proof — `tests/phase4a_migration_proof.sh`

**Part 2, original leaves upgraded to 4A: PASS.** The published 3A image
migrated a disposable database to `tenancy.0009` / `authentication.0025` with a
provisioned company and 138 permissions. The 4A image then reported `No planned
migration operations.` and `No migrations to apply.`; company count, registry
digest and permission count were unchanged; the replacement was recorded and the
9 replaced rows correctly remain for the checkpoint 4B prune.

**Part 1, fresh install: FAILS for `tenancy`. This blocks the 4A release.**

`build_multitenant_db.sql` seeds `django_migrations` with
`('tenancy','0001_initial')` and creates the initial tenancy tables. A
replacement migration is usable only when *all* or *none* of the migrations it
replaces are applied, so the tenancy replacement is permanently **partial** on
this project's bootstrap path. Django therefore drops the replacement node and
replays the original chain: `0005_company_inventory_mode` recreates the retired
`inventory_mode` column **and** its check constraint, and `check_replacements()`
records `tenancy.0001_serial_only` afterwards anyway. Measured on a fresh stack:

```text
squashed tenancy.0001_serial_only recorded        : 1
replaced tenancy.0005_company_inventory_mode ran  : 1
>>> RETIRED PHYSICAL COLUMN present               : 1
>>> retired serial-only check constraint present  : 1
>>> RETIRED PERMISSIONS present                   : 0
```

The `authentication` squash is unaffected — nothing is pre-seeded for it, so the
replacement runs and **0** retired permissions are created, exactly as intended.

Consequence: a newly provisioned deployment would carry a vestigial
`inventory_mode` column and constraint that production no longer has — schema
drift between fresh installs and production, and the opposite of what checkpoint
4A promises. Production itself is unaffected; it is already migrated and
contracted.

This needs an owner decision, because every fix touches
`build_multitenant_db.sql`, which is hash-pinned by
`deploy/phase3_recovery_remote.py` `HOST_HASHES` and cannot be changed without a
fresh source review. The proof script is therefore deliberately **not** wired
into CI yet; wiring it in before the fix would fail the build.


---

# Checkpoint 4A — bootstrap fix and final gate run (2026-09-06)

The migration proof exposed a real defect: a fresh install still created the
retired `inventory_mode` column. On the owner's decision the tenancy bootstrap
seed was dropped so the squash actually runs.

## The change

`build_multitenant_db.sql` seeded `django_migrations` with
`('tenancy','0001_initial')` and created `tenancy_company`/`tenancy_membership`.
Django uses a replacement migration only when **all** or **none** of what it
replaces is applied, so that single seeded row left the tenancy squash
permanently *partial*: Django discarded the replacement, replayed the original
chain, and `0005_company_inventory_mode` recreated the retired column and its
check constraint on every fresh install.

The bootstrap no longer creates the tenancy registry and no longer seeds that
row. `manage.py migrate` owns the entire public tenancy schema, so the
migrations are its single source of truth. The bootstrap still builds the
example `tenant_company_1` business schema; `deploy/entrypoint.sh` registers it
immediately after `migrate` with the new `register_bootstrap_tenant` command,
which **refuses to act on any database that already contains a company** and so
is a no-op on every existing deployment, production included.

Two safety pins were updated under this review:

- `HOST_HASHES['build_multitenant_db.sql']` in `deploy/phase3_recovery_remote.py`.
- The Phase 2 SQL byte-identity baseline, which previously hashed the bootstrap
  together with the tenant SQL as one blob. It is now split so the **16 serial
  tenant SQL files** and the bootstrap's **12,248-line tenant business-schema
  build** are each still pinned byte-for-byte to deployed Phase 1. That business
  section is provably unchanged (`e1d912cc…`); only the Django migration
  bookkeeping changed. The split is a stronger contract than the one it replaced.

## Migration proof — now PASS (17/17)

`tests/phase4a_migration_proof.sh`, wired into CI as `migration-replacement-gate`:

```text
PASS: fresh install never creates the retired inventory_mode column
PASS: fresh install never creates the retired serial-only constraint
PASS: fresh install never creates the 14 retired quantity permissions
PASS: the bootstrap example tenant is registered exactly once
PASS: re-running the registration is a no-op
PASS: the 4A image applies no migration to that database
PASS: the company registry is byte-identical after the upgrade
PASS: the replaced rows remain for the checkpoint 4B prune
```

## Five further defects the bootstrap change cascaded into — all fixed

1. **A third legitimate database state.** Tests assumed only pre-3B (column
   present) or post-3B (column contracted with a 3B archive). A fresh 4A install
   is neither: the column never existed, so there is no archive to find. The
   Phase 1 and company-metadata tests now accept it — with no column, no row can
   express a non-serial mode.
2. **The Phase 3 inventory** audits the pre-3B estate and requires the column.
   It now reconstructs that exact contract on its disposable stack.
3. **The Phase 3A compatibility proof** drives migration 0009, a *replaced*
   migration a fresh 4A install never executes. It now reconstructs the exact
   post-0009 physical contract first, so the real executor is still exercised
   forwards and backwards.
4. **The Phase 28 rollback target was stale.** It pinned the Phase 2 image,
   which still declares `inventory_mode` as a concrete ORM field and therefore
   cannot run against any post-3B or fresh 4A database — its container
   restart-looped. Corrected to the actually deployed 3A image `497b665`, and
   the family check now reads the physical tenant schemas instead of the dropped
   column.
5. **The synthetic recovery estate** registered the bootstrap tenant after the
   old image's entrypoint had already run `apply_sql_all_tenants`, so the live
   source got 33 indexes while its restored copy got 86 and the structural
   witnesses diverged. Registration now happens before the rollout, matching the
   entrypoint's order.

## Final local gate run — all PASS

serial · creation-freeze · runtime-removal · metadata-inventory · compatibility ·
isolation · full regression (21/21) · ARM64 · Phase 3B cleanup (69/69) · Phase 3B
executor · migration-replacement proof (17/17) · Phase 28 encrypted recovery
(RTO 44s, RPO 0s) — alongside every static contract gate and `compileall`.

Production was never contacted. Nothing was pushed or deployed.


---

# Checkpoint 4.0 — audit evidence (reviewed 2026-09-07)

Protected run **`33896979203`**, dispatched from exact source `4f7f49f`,
completed successfully on 2026-09-04 against deployed 3A image `497b665`. The
retained artifact was reviewed on 2026-09-07. It had previously been recorded in
this document as "not dispatched"; that was a bookkeeping error, now corrected.

```text
PHASE4_AUDIT_SOURCE_SHA=4f7f49f1ea32d72a4c04bd4293344bc47c22bebe
PHASE4_DEPLOYED_SHA=497b6650ed678bc462f85de6bff14692bffd6ace
PHASE4_PRODUCTION_CONTAINER_UNCHANGED=yes
PHASE4_ENTRY_RESULT=PASS
PHASE4_REPLACEMENT_AUTHORIZED=no
```

| Required condition | Observed |
|---|---|
| Exact pre-squash tenancy leaf | `0009_inventory_mode_compatibility` |
| Exact pre-squash authentication leaf | `0025_add_quantity_platform_permissions` |
| Retired physical column absent | `inventory_mode_column_present: false` |
| Retired permissions absent | `retired_permission_count: 0` |
| Retired feature keys absent | `retired_feature_occurrences: 0` |
| Phase 3B archive intact and applied | `archive_state: applied`, payload `a7b4b186…` |
| Companies / physical schemas | 1 / 1, matched, no orphan or missing |
| Serial tenant health | active, `ready`, serial v6, journal balanced |
| Non-serial / invalid schemas | none |
| Authority | `authorizes_migration_replacement: false` — evidence, not authority |

The two leaves are exactly the ones `tenancy/0001_serial_only.py` and
`authentication/0001_serial_only.py` list in `replaces`, which is the condition
Django needs to treat the replacements as fully applied on the upgrade path.

Production's tenant structure fingerprint is
`b764c48d37849463a429f099d0817982e87a0803b7c4fbea2d360cc55331b1d3` with 86
indexes — the same value the corrected synthetic recovery estate now reproduces.
That independently confirms the index-ordering fix made to
`tests/phase3_recovery_local.py`, which had produced a 33-index estate.

A fresh confirmation run **`34080323205`** was dispatched on 2026-09-07 from the
same `4f7f49f`. The agent verified the pending gate and did not submit the
approval; the owner released it and the run **PASSED**, returning an identical
state digest `3524c499…`, identical structure fingerprint `b764c48d…` (86
indexes) and `PHASE4_PRODUCTION_CONTAINER_UNCHANGED=yes`. Production is
therefore provably unchanged between the two audits, three days apart.


---

# Checkpoint 4A — independent migration review (2026-09-07)

Reviewed against the exact leaves the protected audit confirmed in production:
`tenancy.0009_inventory_mode_compatibility` and
`authentication.0025_add_quantity_platform_permissions`.

## Structural checks — both replacements

| Check | tenancy | authentication |
|---|---|---|
| `replaces` matches the on-disk chain exactly | 9/9 | 25/25 |
| Ends at the audited production leaf | yes | yes |
| Nothing replaced that is not on disk | yes | yes |
| `initial = True` | yes | yes |
| Dependencies identical to the original head | `swappable_dependency(AUTH_USER_MODEL)` | `contenttypes`/`auth` `__latest__` |

## tenancy — state equivalence proven, not assumed

The final ORM state was built twice inside the release image: once from the
original chain with `MigrationLoader(replace_migrations=False)` at
`tenancy.0009`, once from the replacement. The two states are **identical**
across all six models — fields, options, constraints and managers.

- Constraints retained: `tenancy_company_valid_tax_environment`,
  `tenancy_company_valid_provisioning_state`.
- The retired `tenancy_company_valid_inventory_mode` is absent, and neither
  `inventory_mode` nor `quantity` appears anywhere in the operations.
- Operation order folds the history correctly: six `CreateModel`s, the currency
  and tax fields, the seed/backfill data migration, the base-currency
  `AlterField`, the tax constraint, the provisioning fields, the
  ready-state backfill, then the provisioning constraint.
- The only apparent data-migration difference is original `0006`'s named
  `reverse_backfill` replaced by `migrations.RunPython.noop`. That is
  behaviourally identical: `reverse_backfill` is an empty documented `pass`.
- `makemigrations --check --dry-run` in the built image: **No changes detected.**

## authentication — permission set verified two independent ways

The chain is purely additive; no migration in it deletes a permission, so the
union of all 25 is the correct target. The "versionN" migrations (0012, 0014)
are additive `get_or_create` calls, not renames.

*Static* — parsing every permission literal and keyword form out of all 25
originals and out of the replacement, then comparing against the 14 retired
codenames in `RETIRED_PERMISSIONS`:

```text
original chain : 90 custom codenames
replacement    : 76 custom codenames
dropped        : exactly the 14 retired codenames
added          : none
relabelled     : none
```

*Empirical* — migrating two fresh disposable databases, one with the published
3A image (original chain) and one with the release image (replacement), then
diffing the real `auth.user` permission rows:

```text
original chain :  94 rows  (90 custom + 4 Django defaults)
replacement    :  80 rows  (76 custom + 4 Django defaults)
present in the chain but not the replacement : the 14 retired codenames, exactly
present in the replacement but not the chain : none
```

Both methods agree exactly. No serial permission is lost, none is relabelled,
and no new permission is introduced.

## Observations — no defects found; two notes for the record

1. Both replacements inherit
   `Permission.objects.get_or_create(codename=…, name=…, content_type=…)` from
   the originals. Because `auth_permission` is unique on
   `(content_type, codename)`, a pre-existing row with the same codename but a
   different label would raise `IntegrityError` rather than match. This cannot
   occur on a fresh install, which is the only path that executes the
   replacement, and the pattern is inherited rather than introduced.
2. `seed_and_backfill` imports application code
   (`tenancy.currencies.seed_currency_catalogue`) inside a migration, so that
   function's future behaviour would change this historical migration. This is
   copied verbatim from original `0006`; changing it here would break the
   audited equivalence, so it is recorded rather than altered.

**Review verdict: both replacements are faithful to the audited history and
safe to release under checkpoint 4A.**


---

# Checkpoint 4A — committed and verified in CI (2026-09-07)

Commit **`d8e55c6`** on branch `phase4a-serial-only-hygiene` — 116 files,
+2,108 / −20,965. Committed to a branch rather than directly to `main`, which is
left at `4f7f49f`. The commit deliberately carries no `[skip ci]`, unlike the
earlier preparation commits, because CI is the release gate for 4A.

GitHub Actions run **`34081125290`** — conclusion **success**, 13/13 test jobs:

| Job | Result |
|---|---|
| Static, Django, migration & release-contract checks | success |
| Serial regression gate | success |
| Serial-only company creation gate | success |
| Serial-only runtime removal gate | success |
| Phase 3 read-only metadata inventory gate | success |
| Phase 3A old and new image compatibility gate | success |
| Phase 3B reversible cleanup and contracted-database regression | success |
| Four-serial-company isolation gate | success |
| ARM64 image execution gate | success |
| Complete production-stack regression | success |
| Encrypted backup, restore & rollback gate | success |
| Phase 29 exact-image staging, security & UAT gate | success |
| **Checkpoint 4A migration-replacement proof** (new) | success |

`Product, engineering & operations staging approval`, `Publish signed-off
multi-architecture image` and `Deploy to EC2` were all **skipped**, as expected:
each is gated on `github.ref == 'refs/heads/main'`. Nothing was published to the
registry and nothing was deployed.

This also closes the one local gap noted earlier: the production-like Phase 29
staging and security gate, which had not been run separately on the workstation,
passed in CI on this exact commit.

**Superseded by the release below.**


---

# Checkpoint 4A — released to production (2026-09-07)

`main` fast-forwarded `4f7f49f` → **`a4f915f`**. Protected CI/CD run
**`34081803210`** — conclusion **success**, every job green:

- 13 test gates (as on the branch run), plus
- `Product, engineering & operations staging approval` — recorded,
- `Publish signed-off multi-architecture image` — published
  `ghcr.io/maaz-bin-haider/financee-web:a4f915f3e771d0769f410a3d9ee0cdb7bbc1cd00`,
- `Deploy to EC2 (manual approval)` — released by the owner through the
  `production` environment; the agent verified the pending gate and did not
  submit the approval.

## Deployment evidence — 2026-09-07 04:19 UTC

```text
Image ...:a4f915f3e771d0769f410a3d9ee0cdb7bbc1cd00 Pulled
==> Recreating web + nginx
==> Waiting for health through nginx        (two expected 502s during restart, then healthy)
==> Applying tenant SQL to all schemas (idempotent)
    applying 'tenancy/sql/tenant_indexes.sql' to 1 serial schema(s), target version 6.
      ok   -> tenant_company_1 (serial v6)
==> Post-deploy tenant family/version/fingerprint and safe-report checks
    OK tenant_company_1 family=serial version=6/6
==> Comparing all tenant balances and continuity fingerprints
==> Capturing operational thresholds
==> Pruning superseded images after all release gates passed
Phase 30 production foundation deployment PASS
```

The container now runs the 4A image. Critically, the entrypoint's `migrate` was
a **no-op** on production, exactly as the migration-replacement proof predicted
for a database already at the original leaves — the retired column was not
recreated, and `register_bootstrap_tenant` took no action because the registry
already contains a company.

Independent public check immediately after the deploy:

```text
https://financee-swisstech.com/authentication/login/   HTTP 200
https://financee-swisstech.com/                        HTTP 200
login form present with csrfmiddlewaretoken, username, password
```

## Two operational notes

1. **The Phase 4 audit workflow pin is now stale.**
   `.github/workflows/phase4-migration-leaf-inspection.yml` and
   `deploy/phase4_inventory_remote.sh` hard-assert the accepted deployed SHA
   `497b6650ed678bc462f85de6bff14692bffd6ace`, which this release superseded.
   The read-only audit will fail closed until that pin moves to `a4f915f…`. It
   must be updated before checkpoint 4B's confirmation audit.
2. **The previous image was pruned from the EC2 host** after all release gates
   passed, which is the controller's intended behaviour — in-deploy rollback
   happens before pruning. A *later* manual rollback to `497b665` would need a
   fresh `docker pull` from GHCR, where the image still exists.

## Owner verification — Phase 4A PASS

**Owner Phase 4A result:** `PASS`. Reported 2026-09-07 after the deployment of
`a4f915f`: *"the site is live and working fine."*

Checkpoint 4A is complete. The quantity-company family is now retired in
runtime, database and repository, and the serial-only squashed replacement
migrations are deployed and recorded in production.

## Remaining — checkpoint 4B, not started

Per the plan's progress rule, 4B must not begin without an explicit
instruction. Its scope:

1. Delete the replaced migration files, update dependencies to the squashed
   migrations, and remove `replaces` so each becomes a normal migration.
2. Validate `migrate --prune` on restored and synthetic databases before any
   separately approved pruning of obsolete `django_migrations` rows.
3. Delete `tests/serial_api_compat.py` and the dual-image branches that depend
   on it, once no published image carries the retired compatibility API. Note
   the rollback target `497b665` still does, so this cannot happen until the
   accepted rollback image is a 4A-or-later build.
4. Retire the pre-3B fixture reconstruction added to the Phase 3 inventory and
   Phase 3A compatibility proofs, which exists only to exercise replaced
   migrations.
5. Reprove fresh install, upgraded original history, rollback compatibility,
   serial continuity, backup/restore and all mandatory CI/CD gates, then deploy
   4B through protected production approval.

**Blocking follow-up before 4B:** the Phase 4 audit workflow and
`deploy/phase4_inventory_remote.sh` still pin the superseded deployed SHA
`497b665` and will fail closed. Repin them to `a4f915f…` before dispatching
4B's confirmation audit.


---

# Checkpoint 4B — the migration transition (2026-09-07)

## 4B.0 — precondition audit

The protected audit was broken by our own 4A release: it pinned the superseded
deployed SHA and required the exact pre-squash chain, which production
legitimately no longer has. It gained a `--stage`: `entry` keeps the 4.0
semantics, `transition` requires the chain **plus** both recorded replacements.
Protected run **`34084347071` PASS** against deployed `a4f915f` with
`replacements_recorded=true`. Diffed against the pre-4A audit, the tenant
structure fingerprint, continuity fingerprint and archive digest are all
identical — the 4A release was provably inert on tenant data.

## 4B.1 — the transition

- All 9 `tenancy` and 25 `authentication` replaced files deleted; `replaces`
  removed from both squashes, which are now ordinary initial migrations. No
  migration outside those apps referenced them.
- The 14 retired permission codenames the deleted migrations created are frozen
  into `tests/retired_permissions_reference.json`, so the Phase 3 audit and
  Phase 3B cleanup catalogues keep an **independent** cross-check rather than
  the tooling agreeing with itself.
- `tests/phase3a_compatibility.py` lost its migration half with the migration it
  tested, and kept the application half that is still true.
- `tests/phase3a_old_image.py` and `tests/phase4a_migration_proof.sh` retired
  with the premises they tested.

## Three migration findings, all proven rather than assumed

`tests/phase4b_migration_transition.sh` (CI gate `migration-transition-gate`):

1. **A project-wide prune is refused.** Django requires per-app invocation:
   `migrate tenancy --prune`, `migrate authentication --prune`.
2. **Pruning is a one-way door.** Django drops a replacement from
   `applied_migrations` when the migrations it replaces are absent, *even though
   the replacement's own row exists*. After pruning, every `replaces`-carrying
   image — including the 4A rollback target — re-plans the whole initial
   migration and PostgreSQL refuses it. Measured: before pruning, rollback to
   both 4A and 3A applies no migration; after pruning, rollback to 4A is
   refused while 4B itself stays a no-op. **4B must therefore deploy without
   pruning.** A contract asserts nothing in the deployment path prunes.
3. **The 4A release cannot be skipped.** The same rule forward: a database still
   on the original chain has no replacement record, so the 4B release treats its
   own migration as unapplied and is refused. Production already ran 4A.

A corollary the recovery gate exposed: a **fresh** 4B install has no pre-4B
rollback path at all, because it never had the replaced rows. Only an upgraded
database retains one. The Phase 28 rehearsal now seeds its estate through the 3A
and 4A releases so it models production's real history, and its rollback target
moved from 3A to the 4A release.

## Local validation — all green

Static: every contract gate, 8/8 hostile wrapper tests, 3/3 backup modules,
rollback simulation, `compileall`.
Containers: serial · creation-freeze · runtime-removal · metadata-inventory ·
compatibility · isolation · full regression · ARM64 · 3B cleanup (73/73) · 3B
executor · **4B migration transition (30/30)** · Phase 28 encrypted recovery
(RTO 44s, RPO 0s).

## Remaining

Push, release and deploy 4B through protected CI/CD **without pruning**, then
the owner's manual production verification and the final Phase 4 PASS. Pruning
stays a separate, later, separately approved one-way step.


---

# Phase 4 — complete (2026-09-07)

The 4B release deployed as `5f42cd1` and the owner recorded the final Phase 4
PASS: *"the site is live and working fine."*

## The 4B release

Protected run **`34102647406`** — all 13 test gates green, including the new
`migration-transition-gate` and the Phase 29 staging/security gate; staging
approval recorded; image published; owner-approved EC2 deployment completed at
09:09 UTC with a Phase 30 controller PASS.

```text
Image ...:5f42cd1c871dc0e93b205b92eb5e8eb5f04a034b Pulled
==> Recreating web + nginx           health through nginx recovered
==> Applying tenant SQL to all schemas (idempotent)
      ok   -> tenant_company_1 (serial v6)
OK tenant_company_1 family=serial version=6/6 fingerprint=808e73deb5fbb472
Phase 30 production foundation deployment PASS
```

The tenant fingerprint is **identical before and after** the deployment; the
migration plan was the predicted no-op. Independent public check immediately
afterwards returned HTTP 200 for both the login page and the root, with a
complete login form.

**No migration pruning ran.** The single `Pruning superseded images` line in the
deploy log is Docker image reclamation, not `migrate --prune`. Production still
carries all 36 migration rows and its rollback path to the 4A release.

## Final state

- Phases 0–4 all carry an owner production PASS.
- The quantity-company family is retired in runtime, database and repository.
- The serial-only squashed migrations are deployed as ordinary initial
  migrations, with the replaced files removed.
- Serial behaviour is unchanged throughout: the Phase 2 byte-identity baselines
  for the serial view functions, UI files, tenant SQL and the bootstrap's
  business-schema build all still pass.

## Open by design — not gaps in the plan

1. **The read-only Phase 4 audit pins deployed SHAs by hand** and therefore
   fails closed after every release. It has now gone stale twice. Deriving the
   pin from the actually deployed image would remove a recurring manual step.
2. **`migrate --prune` of the 36 stale rows** is a separately approved one-way
   step. It permanently removes the rollback path to every `replaces`-carrying
   image, so it wants its own decision and maintenance window.
3. **`tests/serial_api_compat.py` and the pre-3B fixture reconstruction** stay
   in place. The Phase 3B cleanup rehearsal still needs a pre-3B database, which
   only the 3A image produces. This is cleanup, not a correctness gap — every
   gate passes with them present.


---

# Checkpoint 4C — prune built, proven reversible, deliberately not run

`serial_only_phase4c_prune` removes the 34 replaced `django_migrations` rows
under the Phase 3B guard pattern, and archives them first so the operation is
reversible rather than the one-way door the plan assumed.

- `tests/phase4c_prune.py` — **17/17** on real PostgreSQL: every refusal path
  (missing/wrong confirmation, stale digest, missing/expired backup reference),
  exact 34-row removal, and a full apply → restore → reapply → restore round trip
  returning the estate byte-identical.
- `tests/phase4c_prune_rollback.sh` — **6/6**, and the reason the prune was
  skipped.

## The hazard

A rollback against a pruned database does not fail cleanly:

```text
after 4B:          authentication=26  tenancy=10
after prune:       authentication=1   tenancy=1
after 4A attempt:  authentication=27  tenancy=1     ← crashed midway
```

The `authentication` replacement is pure `RunPython`, so it re-applies and
re-records its rows before the `tenancy` replacement dies on `CREATE TABLE`,
leaving a half-applied history and an application that will not start. `restore`
is therefore a reset rather than an insert, so it repairs that state as well as
the clean pruned one, and `inspect` reports on a damaged history rather than
refusing it. Measured: before pruning the 4A rollback target starts cleanly;
after pruning it is refused and leaves 28 rows; after restoring it starts
cleanly again from a repaired 36.

## Decision

**Skipped (owner, 2026-09-07).** The benefit is 34 inert bookkeeping rows that
affect no code, schema or behaviour. The cost is turning the standard rollback
path into a trap. The tooling is retained as a proven, reversible capability; it
is not wired into CI and has never touched production.
