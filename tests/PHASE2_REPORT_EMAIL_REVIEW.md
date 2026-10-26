# Phase 2: company report emails

Date: 2026-10-23. Branch: `codex/report-emails`, based on deployed main
`da30168`. Implementation is local. Owner manual review passed on 2026-10-23
for application `c2a63b3`; the owner explicitly said **do not push** and asked
for a new session. No push, merge or deployment is authorized. Spotlight and
Team Activity remain unstarted.
Accounting Plus Inventory is an unchanged, read-only reference.

## Delivered behavior

- A Report Email screen with mailbox/app-password settings, time zone, daily
  send time, recipient management, manual/test sending and paginated history.
  It uses Financee's shared alerts, keyboard-accessible tabs and theme tokens.
  Blank passwords retain the stored value; clearing requires an explicit box.
  Saved passwords are never returned to the browser or delivery log.
- HTML, plain text and CSV versions of Financee's existing Sale-wise Profit
  report. The SQL remains `sale_wise_profit_json(day, day)`. Sale price,
  purchase cost, profit, row markup and total margin keep their existing
  meanings. Returned serials are excluded and converted drafts are included
  through the original SQL. Currency comes from the company; source cents
  remain visible even for a currency configured with zero decimal places.
- A daily worker sending yesterday's report at/after company local time,
  including empty days. Manual and test deliveries do not consume the
  scheduled slot. Older missed days can be sent manually.
- Tenant-scoped settings, recipients and durable attempt history. A committed
  claim precedes SMTP under a company advisory lock. Concurrent workers and
  restarts cannot automatically resend a completed scheduled day. Definite
  failures wait 30 minutes between retries, at most 12 for that schedule day.
  Partial or ambiguous SMTP outcomes stop retries until deliberate re-arming.
- Every route and delivery checks the company, subscription, feature switches
  and both report permissions. Scheduled delivery also rechecks the current
  membership/permissions of the last mailbox-saving member. No permission is
  auto-granted. New-company plans default Report Email off.
- A matching-image production worker with heartbeat checks, deploy/rollback
  lifecycle handling and muted report delivery during restore rehearsals.
  Older rollback images without the command leave the worker stopped.

Tenant version stays 6. There are three additive tables and an idempotent
registered patch in the tenant template/startup hardening. Public migrations,
financial posting functions and existing report SQL are unchanged. App
passwords are stored in the tenant database and consequently in its backups;
responses/logs conceal them. SMTP hosts are operator-allowlisted, with TLS on
587 or implicit TLS on 465. Billing email configuration remains separate.
See `REPORT_EMAIL_RUNBOOK.md` for operational instructions.

## Verification record

Checks ran in disposable local resources, separately from the manual review
database. Test evidence is outside Git under `/private/tmp/financee-phase2-*`.

| Check | Result |
| --- | --- |
| Full sequential `tests/suite/run_all.py` | All 23 modules passed; 75/75 HTTP, 17/17 four-company isolation |
| Real PostgreSQL report-email integration | All 15 scenarios passed, including actual local SMTP capture |
| Report-email browser helpers | 33 passed |
| Report rendering | 4 passed: source totals, currency/cents, escaping, safe CSV and empty day |
| Dark-mode helpers | 11 passed |
| Review environment safety | 6 passed |
| Serial schema matrix | 51/51 passed, including the explicit three additive report-email tables |
| Old-image compatibility | 20/20 passed |
| Historical migration transition | Passed through the old release chain and rollback/prune refusal cases |
| Source/release/backup contracts | All 17 scripts passed |
| Worker lifecycle | Matching image start, unsupported old image stop, unhealthy rejection and post-HTTP rollback passed |
| Encrypted database-only restore | Passed with conflicting inherited credentials; 5 tenant schemas verified, healthy muted worker, 50-second restore |
| Encrypted database/media recovery and rollback | Passed; 51-second restore, old-image compatibility, forward recovery, matching healthy worker with delivery disabled |
| Immutable staging acceptance | Passed on `db82641`: worker image/health, security, serial workflows, four-company isolation, capacity preflight and Phase 30 continuity |
| Final Django/schema readiness | `check`, `makemigrations --check --dry-run` and `release_preflight` passed |

The integration tests cover forged tenant/actor inputs, cross-company IDs,
permissions and feature revocation, subscriptions, method/CSRF validation,
SMTP refusal/partial acceptance, recovery after crashes, retry budget,
concurrent claims and explicit re-arming. Repeat SQL application preserves
settings, history and business balances. Unknown SMTP results intentionally
require inbox reconciliation; SMTP cannot guarantee exactly-once delivery
when acknowledgement is lost.

The full regression and migration-transition runs used candidate `d86b739`.
Subsequent targeted checks cover the UI status/labels, currency precision,
restore credential handling and narrow email layout. The final recovery drill
passed on `1c4af61` with its raw restore output and numeric timing retained.
Staging and the refreshed manual review build used `db82641`, containing the
final application code. Subsequent handoff/checkpoint edits are documentation
only; the review helper rebuilds from the final clean committed checkout.
The exact running review image is recorded in the private local handoff.

No new GitHub CI run, real-provider SMTP delivery, production migration or
deployment is claimed. The local SMTP service captures all test mail. The
historical destructive cleanup gate has not been rerun against production.

## Browser evidence and review environment

Application: `http://financee-review-email.localhost:8181/report-email/`.
Capture inbox: `http://financee-review-email-mail.localhost:8182/`.

The project uses its own database, credentials, volumes and internal network.
Only Nginx publishes loopback ports. SMTP always targets internal Mailpit,
regardless of the mailbox host configured in the UI. Project-specific browser
hostnames prevent the Phase 1 review stack from overwriting its cookies.

| Account | Purpose |
| --- | --- |
| `alpha_manager` | Configure/send for Alpha: PKR, Karachi, Alpha mailbox/recipient |
| `beta_manager` | Configure/send for Beta: AED, Dubai, Beta mailbox/recipient |
| `alpha_staff`, `alpha_reader`, `beta_staff` | No report-send permission |
| `suspended_user` | Suspended company access |
| `review_operator` | Platform admin without a company membership |

The shared synthetic password and exact image/commit are in the private
temporary `financee-review-<uid>/financee_review_email/handoff.txt`; credentials
are not committed. The owner receives the absolute path at handoff.

Both companies deliberately share item/party names, document IDs and serials
but have different prices and currencies. For seeded day 2026-10-22, Alpha has
2 units, sales PKR 360, cost PKR 200, profit PKR 160; Beta has 2 units, sales
AED 560, cost AED 400, profit AED 160. Returned serial `REVIEW-001` is absent;
`REVIEW-002` and `REVIEW-003` appear. The unconverted draft remains reserved.

Browser checks verified both companies' mailbox/recipient/history views,
separate captured test messages with reconciled figures, CSV presence, light
and dark views, and arrow-key tab navigation. The real local worker delivered
Alpha's scheduled report separately from its test message. Alpha is left
enabled with that delivered day; Beta is paused. Desktop app views were
checked. A new captured message verified the corrected phone email summary
wraps within its preview; application phone layout remains an owner manual
check. After rebuilding/restarting the real review worker, Alpha still had
exactly one unsuperseded scheduled delivery for 2026-10-22. The helper preserved
all existing review data and captured messages.

## Owner manual checklist

1. Open Alpha's mailbox, recipients and history; switch light/dark mode and
   reload. Check narrow app layout on your preferred phone/browser size.
2. Send a test and a manual report. Inspect HTML, text and download the CSV
   from the capture inbox. Compare totals and serials with Sale-wise Profit
   for 2026-10-22. Use a different/empty day as well.
3. Sign into Beta and verify its AED figures, recipients and history remain
   separate from Alpha. Its schedule begins paused.
4. Edit recipients/schedule and save. Confirm blank password preserves the
   saved value; verify unsaved inputs survive a 30-second status refresh.
5. Exercise a schedule in local time and confirm test/manual deliveries remain
   separate. Alpha's already-delivered scheduled day must not resend just
   because the worker restarted.
6. Check staff/reader restrictions and the suspended-company screen. Use the
   synthetic operator account for feature/permission configuration if needed.

Stop after this phase. Keep the review stack and its data intact. Push only
after the owner explicitly instructs it; follow protected CI/release gates
before starting Spotlight.

## Focused local history

| Commit | Increment |
| --- | --- |
| `557dee3` | Phase 2 authorization and baseline |
| `6893d96` | Tenant configuration and durable reservations |
| `9b631d1` | Existing report SQL rendering and currencies |
| `386d06d` | Guarded screens, endpoints and delivery service |
| `4bd23cf` | Matching worker, deploy/rollback and local mail capture |
| `8312a57` | JSONB fix and isolation/recovery integration scenarios |
| `a7a8977` | Preserve unsaved settings during status refresh |
| `522f3d0` | Roll back after worker-health failure |
| `d86b739` | Account explicitly for additive tables in serial matrix |
| `3c3d261` | Isolate review browser cookies |
| `2c90cb9` | Verify permission seeding in historical migration transition |
| `2314dca` | Correct overdue schedule display |
| `cd003e4` | Preserve source cents with zero-decimal currencies |
| `8abdc67` | Muted matching worker in both restore paths |
| `213b044` | TLS and empty-log labels |
| `ee66eb1` | Reject inherited credential overrides during restore |
| `1c4af61` | Preserve recovery output and validate numeric RTO |
| `f079246` | Operating runbook and engineering context |
| `4b54e10` | Narrow-screen email summary layout |

Later review-record commits document validation and the owner gate. The
private handoff identifies the exact final checkout/image used for review.
