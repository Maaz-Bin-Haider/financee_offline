# Phase 25 — Four-Company Isolation and Concurrency Results

Date: 2026-07-26

## Result

Phase 25 is complete. The permanent `T6` runner provisions two fresh serial
companies and two fresh quantity companies, then drives all four at the same
time through independent PostgreSQL connections and Django clients.

Focused certification: **17/17 passed**.

## Certified behavior

- Concurrent serial purchases, sales, sale returns, purchase returns, stock,
  accounting, and legacy report contracts remain independent.
- Concurrent quantity purchases, sales, both returns, FIFO transfers, physical
  counts, all quantity reports, report APIs, and exports remain independent.
- All four trial balances remain exact and quantity stock reconciles.
- Persistent connections alternate all four tenant schemas and reset to
  `public` after every use.
- Concurrent HTTP reports, exports, attachment probes, and logouts disclose no
  foreign tenant marker.
- Guessed attachment document IDs return 404 and exception responses contain
  neither schema names nor internal errors.
- Rate-limit keys include tenant identity, so equal user/IP identities in two
  companies do not share quota.
- Schema-family mismatches fail closed.
- Quantity report JSONB is decoded before response decoration.
- Completed quantity home, attachment, and audit routes are reachable through
  the family allowlist.

## Release gates

- Focused Phase 25 matrix: **17/17 passed**.
- Aggregate suite: **38/38 modules passed**, including Phase 23's two-quantity
  certification and Phase 24's two-serial certification.
- Phase 24 nested serial gates: **51/51**, system **111/111 per tenant**, deep
  lifecycle **2702/2702 per tenant**, zero XFAIL/XPASS.
- Django migration drift: **No changes detected**.
- Django deploy check: completed with only the known environment-dependent
  HSTS, SSL-redirect, and disposable local secret warnings. Production
  redirects/HSTS are provided by Nginx/Cloudflare and the deployed secret is
  injected from the environment.
- Docker production image: built successfully for `linux/arm64`, matching the
  AWS EC2 `t4g.medium` architecture.
- Source hygiene: Python compilation and `git diff --check` passed.

## Next phase

Phase 26 — Performance and Capacity.
