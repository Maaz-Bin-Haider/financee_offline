# Functional Test Suite

Phase 26 capacity work also provides a non-destructive production preflight:

```bash
docker compose -f deploy/docker-compose.yml exec -T web \
  python tests/phase26_capacity_preflight.py
```

It exits non-zero when the effective runtime cannot safely begin the T7
100-session capacity test. See `PHASE26_PERFORMANCE_CAPACITY_RESULTS.md`.

The clean two-tenant serial baseline captured before the (since retired)
quantity-company implementation is recorded in
`tests/PHASE1_BASELINE_RESULTS.md`. The system is serial-only; see
`SERIAL_ONLY_REMOVAL_PLAN.md`.

Three complementary harnesses that together exercise **every** business operation,
the HTTP layer, and high-risk real-world serial lifecycles.

| File | What it tests | How |
|---|---|---|
| `test_system.py` | All stored-function entry types (create/update/delete for sale, purchase, sale-return, purchase-return, payment, receipt, contra) + parties, items, opening stock, opening cash, owner equity, month close + **every** report function & view | Direct SQL per tenant schema (mirrors the middleware's `search_path`) |
| `test_http.py` | The real HTTP endpoints (permissions, view logic, JSON, templates) for reports, lists, dashboard, and the main write flows | Django test `Client` as a logged-in tenant user |
| `suite/test_attachments.py` | Document attachment coverage for sale, purchase, sale return, purchase return, payment, receipt, and contra flows: uploads, replacement/preservation, authenticated metadata/preview/download, invalid file validation, cleanup, and bypass rules | Django test `Client` plus real tenant SQL setup |
| `test_transaction_lifecycle_deep.py` | Real-world serial lifecycles: purchase -> sale -> sale return -> resale -> second return -> purchase return, mixed purchase invoice updates with sold and unsold serials, partial returns, sale-return update/delete after resale, sale invoice update/delete after returns, cash-sale vs credit-sale returns, multi-item mixed serial invoices, duplicate/wrong-party return guards, and all accounting/stock/monthly/sales/dashboard reports after each entry | Direct SQL per active tenant schema with unique parties/items/serials |

## Setup (one time)

Keep this `tests/` folder in your **project root** (next to `manage.py`). You do
**not** need to rebuild the image — the runner copies the tests into the running
web container for you. The runner also auto-detects your compose file whether it
sits in the project root or in `./deploy`.

## Run

```bash
chmod +x tests/run_tests.sh
./tests/run_tests.sh            # copy tests into the container + run both harnesses
./tests/run_tests.sh --reset    # ALSO wipe + re-provision tenants first (clean signal)
```

If your compose file or web service has non-standard names, override them:

```bash
COMPOSE_FILE=deploy/docker-compose.yml WEB_SERVICE=web ./tests/run_tests.sh
```

Or run a harness manually (after the runner has copied the folder in once):

```bash
docker compose -f deploy/docker-compose.yml exec web python tests/test_system.py
docker compose -f deploy/docker-compose.yml exec web python tests/test_http.py
docker compose -f deploy/docker-compose.yml exec web python tests/test_transaction_lifecycle_deep.py
```

> **`--reset` erases tenant data.** It drops and rebuilds every tenant schema
> from the template. Shared `public` data (users, the company list) is kept.
> Use it for a pristine `112/112` signal; omit it to test against current data.

## Reading the output

- `test_system.py` prints `N/M passed` per tenant and a de-duplicated list of
  distinct failure types. A clean run is `112/112 passed` on each tenant.
- `test_http.py` lists every endpoint with `[ok]` / `[FAIL]` and the response
  body for any problem.
- `test_transaction_lifecycle_deep.py` prints every lifecycle and report checkpoint.
  It intentionally fails on duplicate returns or invalid serial-state transitions
  instead of treating them as harmless no-ops. It also asserts financial
  invariants (trial balance balances, no orphaned journal lines, stock/sold
  coherence) at every checkpoint, not just that the reports run.
  - Confirmed-but-unfixed defects are marked `known_bug=True` and print as
    `[XFAIL]`; they are excluded from the pass/fail exit code so the suite stays
    green while tracking them. When a fix lands the same check prints `[XPASS]`
    ("KNOWN BUGS NOW PASSING"), signalling that the `known_bug` flag should be
    removed. See the "Known Bugs" section of `TRANSACTION_LIFECYCLE_FLOW_RESULTS.md`.
- `TRANSACTION_LIFECYCLE_FLOW_RESULTS.md` records the exact flow matrix and latest
  pass/fail status from the deep lifecycle harness.

## Re-running on the same database

The harness creates fresh master records each run (names carry a time tag), so
repeated runs don't collide on parties/items. **But** two operations are
single-shot by design and may report a conflict on a second run against the same
data: **opening cash** (a singleton row) and **month close** (one close per
period). For a perfectly clean signal, use `--reset`, which drops and
re-provisions the tenant schemas from the template before running.
