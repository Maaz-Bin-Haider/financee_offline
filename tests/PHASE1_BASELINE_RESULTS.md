# Phase 1 — Serial Baseline and Test Stabilization Results

**Date:** 2026-07-25  
**Baseline commit:** `3fae032f154953c1776afadda0398c2910740e1f`  
**Branch:** `main`  
**Environment:** isolated Docker Compose project `financee_phase1`  
**Host architecture:** Apple/Docker `aarch64`  
**Docker Engine:** 29.6.1  
**Docker Compose:** v5.3.0  
**Container Python:** 3.12  
**Django:** 6.0.6  
**PostgreSQL:** 16  

## Isolation

The baseline used a separate Compose project and separate `pgdata`,
`staticfiles`, `media`, and `redisdata` volumes. The existing local Compose
stack and its data were not reset or modified.

Two fresh serial tenants were used:

- `tenant_company_1` — bootstrap company.
- `tenant_company_2` — provisioned at runtime through `provision_tenant`.

Both tenants reached serial schema version 6.

## Static Gates

- Shell syntax: passed for entrypoint, deployment scripts, and test runner.
- Docker Compose configuration: passed.
- Production image build and `collectstatic`: passed.
- Python byte compilation inside the production image: passed.
- `python manage.py check`: passed, 0 issues.
- `python manage.py makemigrations --check --dry-run`: passed, no changes.

The host Python installation is 3.14.6 and does not contain project
dependencies, so authoritative Django checks were run inside the production
Python 3.12 image.

## Comprehensive Suite

Command:

```bash
docker compose -p financee_phase1 -f deploy/docker-compose.yml \
  exec -T web python tests/suite/run_all.py
```

Result: **ALL MODULES PASSED**.

| Module | Result |
|---|---:|
| Parties | 21/21 per tenant |
| Items | 10/10 per tenant |
| Purchases | 29/29 per tenant |
| Sales | 30/30 per tenant |
| Returns | 31/31 per tenant |
| Cash movement | 31/31 per tenant |
| Opening | 20/20 per tenant |
| Owner equity | 13/13 per tenant |
| Month close | 13/13 per tenant |
| Reports | 60/60 per tenant |
| Attachments | 208/208 |
| Subscription | 40/40 |
| Subscription emails | 46/46 |
| Feature flags | 77/77 |
| HTTP | 70/70 |

The subscription-email suite intentionally exercises a failed backend import
and logs its expected exception; all 46 assertions passed.

## Additional CI Harnesses

- SQL business-function harness: 111/111 on `tenant_company_1` and 111/111 on
  `tenant_company_2`.
- Deep transaction lifecycle: 2702/2702 real checks on each tenant.
- Standalone legacy HTTP harness after stabilization: 66/66 endpoints passed.

## Baseline Defects Found and Stabilized

### Standalone HTTP harness false green

Before stabilization, `tests/test_http.py` used a superuser without tenant
membership, printed 66 tenant-guard 403 failures, and still returned exit code
0. It now attaches a temporary tenant membership and returns non-zero on any
reported problem.

### Bootstrap tenant missing required secondary indexes

Before stabilization:

- `tenant_company_1`: 24 tables, 161 functions, 14 views, 36 indexes.
- `tenant_company_2`: 24 tables, 161 functions, 13 views, 86 indexes.

The one-view difference is the previously documented hardcoded
`item_history_view` debug artifact in the bootstrap schema. The 50-index
difference was not intentional: runtime-provisioned tenants received the
indexes embedded in `tenant_template.sql`, while the bootstrap/entrypoint path
did not apply `tenant_indexes.sql`.

The web entrypoint now applies the idempotent tenant index patch after
production hardening, ensuring fresh bootstrap and existing tenants receive the
required index set before Gunicorn starts.

## Capacity Observation

Gunicorn derives its default as two workers per visible CPU. Docker Desktop
exposed 10 CPUs, so the container started 20 workers with 4 threads each. The
production `t4g.medium` has 2 vCPUs and 4 GiB RAM; production must explicitly
set and load-test `WEB_CONCURRENCY` and `GUNICORN_THREADS` during the capacity
phase rather than relying on host-derived defaults.

## Phase 1 Exit Status

**PASSED — Phase 1 complete.**

Final verification rebuilt the exact production image from the updated source
and started from newly created isolated volumes:

- Entrypoint hardening passed.
- Entrypoint tenant-index rollout passed.
- Reapplying `tenant_indexes.sql` to both tenants passed, proving idempotency.
- Both tenants have 86 indexes and schema version 6.
- Django check passed with 0 issues.
- Missing-migration check passed.
- Comprehensive suite: all 15 modules passed.
- SQL harness: 111/111 per tenant.
- Standalone HTTP harness: 66/66.
- Deep lifecycle: 2702/2702 per tenant.

The Phase 1 exit gate is satisfied. Phase 2 architecture and schema-family
design may begin; no quantity implementation code was introduced in Phase 1.
