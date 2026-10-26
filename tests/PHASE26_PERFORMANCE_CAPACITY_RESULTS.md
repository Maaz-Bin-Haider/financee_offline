# Phase 26 — Performance and Capacity Results

Date: 2026-07-27  
Result: **PASS**

> **Retained historical evidence.** The T7 benchmark harness
> `tests/phase26_performance_capacity.py` exercised the retired
> quantity-company family and was removed in checkpoint 4A of the
> serial-only consolidation. These recorded results and
> `tests/phase26_target_results.json` are preserved as evidence and are
> no longer reproducible on the serial-only system. The serial capacity
> gate `tests/phase26_capacity_preflight.py` remains active.

## Production-equivalent envelope

The T7 target ran with Docker resource limits totaling 2 vCPU and 3.875 GiB,
matching the usable envelope of the ARM64 AWS EC2 `t4g.medium` after host
overhead. PostgreSQL, Redis, Gunicorn/Django, and Nginx remained co-located.

Production defaults were tuned to:

- PostgreSQL: 120 connections, 768 MiB shared buffers, 2 GiB effective cache,
  4 MiB work memory, and 128 MiB maintenance work memory.
- Gunicorn: four gthread workers with four threads each.
- Capacity allocation: PostgreSQL 1.25 CPU/2560 MiB, web 0.65 CPU/1024 MiB,
  Redis 0.05 CPU/192 MiB, and Nginx 0.05 CPU/128 MiB.

`tests/phase26_capacity_preflight.py` passed every runtime and connection
budget check before the target run.

## T7 target evidence

Raw machine-readable evidence:
`tests/phase26_target_results.json`.

- 100,000 SKUs: exact.
- 5,000,000 stock movements: exact before representative writes.
- 100,000 closing physical units: exact.
- Dataset build and statistics: 183.9026 seconds.
- 100 simultaneous active sessions: zero failures, 1.7686 seconds wall time,
  p50 0.3643s, p95 0.5706s, p99 0.5789s.
- Representative daily load: 100 real purchase invoices plus 40 ancillary
  inventory operations in 1.1841 seconds; p95 operation 0.0129s.
- Heavy export: streamed 100,000-row, 3,477,839-byte PostgreSQL CSV in 0.1490s.
- Worst supported synchronous FIFO replay: 10,000 events in 2.6696s. The
  existing database guard rejects scopes above 10,000 for asynchronous/offline
  handling rather than monopolizing a request worker.

## Normal report timings

All tested normal reports passed the three-second target:

| Report | Seconds |
| --- | ---: |
| Trial balance | 0.0159 |
| Stock summary | 1.0453 |
| FIFO stock valuation | 0.6848 |
| Stock movement | 2.6922 |
| Inventory reconciliation | 0.4589 |
| Valuation reconciliation | 0.4315 |
| Low stock | 0.4947 |

The initial target run exposed unbounded reconciliation aggregation. The
report SQL now pages the requested balance scopes first and performs indexed
lateral movement/FIFO aggregation only for that page. The corrected target
run produced the timings above.

## Resource and integrity evidence

- Peak observed during the seed: PostgreSQL approximately 1.74 GiB of its
  2.5-GiB limit at approximately one CPU; web 187 MiB, Redis 10 MiB, Nginx
  9 MiB.
- After the run: PostgreSQL 896 MiB, web 180 MiB, Redis 10 MiB, Nginx 9 MiB.
- PostgreSQL generated bounded temporary files during the large build/report
  workload; no waiting locks or new deadlocks remained.
- Database footprint at peak dataset size: approximately 6.41 GB.
- All four containers: zero restarts, running, and `OOMKilled=false`.
- Trial balance exact, no negative stock, expected SKU/movement/unit counts,
  and no waiting locks.

`tests/phase26_host_telemetry.sh` captures CPU, RAM, swap, disk, vmstat,
container restart/OOM state, and—when AWS CLI plus instance-role permission
are available—EC2 CPU utilization and credit balance metrics. CPU credits are
an ongoing production operational metric; the constrained T7 gate does not
pretend Docker can emulate AWS burst-credit accounting.

## Regression gates

- Django system check: no issues.
- Missing migration check: no changes detected.
- Complete aggregate suite: **38/38 modules passed**.
- Phase 23 quantity certification: **20/20 passed**.
- Phase 24 serial certification: **51/51 passed**, system **111/111**, deep
  lifecycle **2702/2702**, zero XFAIL/XPASS.
- Phase 25 four-company isolation: **17/17 passed**.
- HTTP regression: **70/70 passed**.
- Standalone SQL system harness: **111/111 passed**.
- Standalone deep lifecycle: **2702/2702 passed**.

The regression run also fixed a date-sensitive Phase 16 test: its missing-cost
probe reused a previously reversed surplus scope and changed meaning after the
hard-coded date passed. It now uses a fresh empty scope and the current date.

## Capacity decision

The tuned `t4g.medium` profile passes the approved Phase 26 targets. An
immediate EC2 resize is not required for the tested workload. Production must
retain disk-space alerts (the target dataset alone reaches about 6.4 GB),
off-host backups, CPU-credit monitoring, and slow-query monitoring. Sustained
CPU-credit depletion, normal reports crossing three seconds, swap pressure, or
material growth beyond this tested profile is the resize trigger.

## Exit gate

**PASSED — Phase 26 complete. Phase 27 (CI/CD and ARM64) is next.**
