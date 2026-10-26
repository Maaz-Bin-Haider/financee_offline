# Phase 4: company-scoped Team Activity

Date: 2026-10-24. Branch: `codex/team-activity`, based on Spotlight handoff
`7e4e01e`. Application candidate: `703be6c`. Later handoff commits change
documentation only; the private review handoff names the exact running image.
The owner authorized the next phase locally. This does not imply Spotlight
manual approval or permission to push, merge, deploy or import production history.
Owner manual review of Team Activity is pending.

Accounting Plus Inventory was read at
`ea1f0194f2e4d2b0ec6e120086b29276c4d99365` and remains unchanged. Earlier
review branches/data were preserved. Those review stacks were not running when
this phase began; this record does not claim they are currently running.

## Delivered behavior

- Company manager dashboard with the reference contribution thresholds:
  0, 1–4, 5–10, 11–25 and 26+ work actions. Calendar/year/day views, work mix,
  weekday/hour grid, team comparison, idle/inactive actors and live watch rules.
  Sessions are separate from work totals; historical imports are approximate.
- Tenant-local successful document/master/draft actions, conversions and
  confirmed returns; payment/receipt/contra, opening stock/cash, owner equity,
  month close and reversal. Failed, denied and confirmation-only actions do not
  become successful work. Existing posting/report SQL and financial rules remain
  unchanged. Pre-edit document dates support the old-document watch rule.
- Login/logout and known-user failed logins tied to actual membership.
  Unknown usernames are never assigned to a company. Actor names are server
  snapshots; event labels omit amounts, contact details, descriptions and bodies.
- Explicit successful report-data runs, with 60-second identical-filter
  deduplication. HTML openings, lookups and automatic dashboard refreshes do not
  inflate report activity. PDF/CSV/Excel export notifications are browser-reported
  and require a signed source/user/company/session receipt plus current source
  and export permission checks. Duplicate notifications are suppressed briefly.
- Year/day navigation, keyboard calendar, both themes, phone layout and PDF/CSV
  exports. Files identify the company and timezone; CSV escapes formula-leading
  untrusted text. Links recheck source permissions/features and tenant-local
  existence, in batches by kind. Analytics access never grants record access.
- Current company membership plus legitimate local historical actor snapshots.
  A departed actor's new foreign-company profile is never joined. Old tabs clear
  their activity after an account change; stale API scope is refused.

## Storage, access and rollout

`add_team_activity.sql` is registered and appended verbatim to the tenant
template and startup hardening. It adds one tenant-local `activity_events`
table with query/deduplication indices and a trigger refusing update, delete
and truncate. Fresh/repeated startup and upgrades preserve history. The
bootstrap and independent 12 serial posting-view source anchors remain
unchanged. Tenant version is still 6. There is no public migration, model
table, extra worker or changed accounting/report calculation.

`auth.view_team_activity` is seeded idempotently without granting it.
New-company plans disable `team_activity` by default; existing feature lists
are not rewritten. Active membership/subscription, company feature and manager
permission govern the page/read APIs. `TEAM_ACTIVITY_ENABLED` controls access;
`TEAM_ACTIVITY_RECORDING_ENABLED` controls collection independently. Disabling
manager analytics does not stop ordinary staff work/session recording.
`/activity/record/` verifies the exported source's access independently rather
than requiring manager analytics. APIs are private/no-store, CSRF-protected
where applicable, bounded and rate-limited, with statement timeouts.

Recording uses schema-qualified inserts after fresh membership validation and
a nested savepoint. An unavailable log cannot abort a successful business
transaction. Tenant scope is restored after commands/exception paths. Session
addresses use the connection peer, not an untrusted forwarded header.

Historical import is preview-only by default, one company at a time, with an
explicit past timezone-aware cutoff. Execution requires `--execute --confirm`
with the exact tenant schema. No import runs in migration/startup/deployment.
It imports one attributed legacy source record at an approximate local noon,
skips unknown/nonmember attribution and already observed live records, avoids
double importing confirmed returns, and deduplicates reruns. See
`TEAM_ACTIVITY_RUNBOOK.md` for operating and rollback instructions. Production
historical import remains a separate owner-authorized action.

An older image ignores the additive history table; rollback retains its data.
The existing report-worker matching-image/older-image stop behavior is unchanged.
Generic production cleanup must not bypass append-only enforcement.

## Verification and evidence

Mutating automated tests ran only in disposable resources, principally
`financee_review_regression_activity`, never the owner's manual review database.
Evidence files remain outside Git under `/private/tmp/financee-activity-*`.

| Check | Result / evidence |
| --- | --- |
| Clean sequential suite on `da2e17b` | All 25 modules passed; 75/75 HTTP, 155/155 feature checks, 51/51 serial matrix and 17/17 four-company checks. `clean-full-regression.log` |
| Latest application `703be6c` | All 18 PostgreSQL/HTTP activity scenarios passed again after the export-label and phone-layout fixes. `final-targeted.log` |
| Activity integration coverage | Company/actor isolation, successful versus failed writes, exact serial IDs, cash redirects, savepoint failure isolation, immutable/repeated SQL, independent access/recording flags, sessions, forged/export receipts, CSRF/stale scope, concurrent companies, figures, confirmed import/rerun/books unchanged, former members, blocked users, draft conversion/return, bounded queries, pre-edit dates |
| Query sample | 12,000-row year query about 28 ms; truncated 1,000-event day uses 16 SQL queries, including permission-checked record existence. Local sample, not a production capacity claim |
| Source/release/backup contracts | All 17 scripts passed, retaining independent posting/bootstrap anchors; `contracts.log` |
| Frontend | Team Activity 15, activity export helper 8, Spotlight 7, report email 33 and dark mode 11 checks passed |
| Deployment helpers | Matching-worker/unsupported-old-worker/health rollback simulations and 51 remote helper unit tests passed |
| Historical migration transition | Fresh and legacy 3A/4A/4B upgrade, seed-without-grants, safe prune and rollback refusal passed. `migration-transition.log` |
| Immutable staging on `da2e17b` | PASS: serial flows, four-company isolation, tenant/auth security, worker health, capacity preflight and Phase 30 continuity. `staging-evidence/acceptance-summary.json` |
| Encrypted activity-only restore | Both company tables/sequences restored from encrypted dump into an isolated scratch PostgreSQL; full-row digests matched and update/delete/truncate still refused. `backup-roundtrip.log` |
| Django readiness | `check`, `makemigrations --check --dry-run` and `release_preflight` passed. `final-preflight.log` |

The first complete suite exposed stale exact feature-plan expectations (24 of
25 modules passed). The correction explicitly adds Team Activity only when
installed, preserving older-image expectations. A fresh full rerun passed.
The historical transition's first image tag had a local suffix typo; Compose
built it from the same clean `da2e17b` checkout. A network-disabled manifest of
918 application/test files proved source identity with the intended image;
`migration-source-provenance.txt` retains that evidence.

The activity-only encrypted restore covered 1,557 Alpha and 1,550 Beta events
at the time of its read-only source snapshot. It is not a new full-estate or
media recovery drill. Phase 2's full recovery evidence remains in its own
review record. Staging's encrypted-recovery item delegates to that separate
recovery gate; the staging summary is not itself a full encrypted restore.

Browser checks verified Alpha-only and Beta-only rosters, staff menu omission
and direct denial, old-tab clearing after account switch, calendar keyboard
navigation/empty-day state, light/dark rendering, a 390px phone viewport without
page-wide overflow, company-labeled PDF/CSV downloads and the correct payment
record opened from an activity link. The final PDF was rendered and visually
inspected. No business form was saved in browser testing. Browser sessions and
export notifications legitimately add synthetic local activity.

No Phase 4 GitHub CI, push, merge, deployment or production import has run.

## Review environment and checklist

Application: `http://financee-review-activity.localhost:8185/activity/`.
Capture inbox: `http://financee-review-activity-mail.localhost:8186/`.
The production-image stack has its own synthetic database, volumes, internal
network and loopback ports. Report schedules and billing email are disabled;
all SMTP is internal Mailpit. The matching web/report-worker image and synthetic
password are recorded privately in:
`/var/folders/qv/qpbw48nx28x_w6tw3q_g7v440000gn/T/financee-review-501/financee_review_activity/handoff.txt`.
No credentials are committed.

Managers: `alpha_manager`, `beta_manager`. Ordinary actors without manager
analytics: `alpha_staff`, `beta_staff`, `alpha_reader`. Additional fixtures:
`suspended_user` and the membership-free `review_operator`.

Each company has roughly 1,550 clearly synthetic historical/sample events and
labeled live watch examples. The local command preview and explicitly confirmed
import added 11 real fixture-source history rows per company; only these review
companies were imported (`review-backfill.log`). Imports remain approximate,
and synthetic watch examples do not represent real business incidents.

1. Sign in as Alpha manager and open Team Activity. Change actor/year/day,
   inspect thresholds, work totals, separate sessions, mix, hours and team rows.
2. Select the current day and open a linked fixture payment or other document.
   Check the exact ID; navigate back without saving if only inspecting it.
3. Inspect the deletion/old-document watch examples and filters. Export day,
   team and watch lists to PDF/CSV; check company, dates and readable layout.
4. Use light/dark mode, keyboard arrows/Home/End and a phone-sized window.
   Wide sections scroll internally; the page should fit the window.
5. Switch to Beta and verify only Beta's actors/history appear. Keep an old
   Alpha tab open and verify it clears and requests a reload after switching.
6. Sign in as staff/reader: no Team Activity menu and direct access denied.
   If testing ordinary work recording, perform only disposable fixture actions,
   then inspect the resulting events as that company's manager.

Known limits: recording/export notifications are best effort; a browser event
does not prove a file reached disk. PDF uses the existing Helvetica/cp1252
renderer and has limited Unicode coverage; CSV is UTF-8. The timezone is the
explicit globally configured `ACTIVITY_TIMEZONE`, not a new per-company setting.
Day/watch/actor lists cap at 1,000/500/1,000; day truncation is visible. Watch
rules are investigation prompts, not conclusions about a person. Approximate
history cannot reconstruct original authors, edits or deleted legacy records.

Leave the manual review stack/data intact and stop for owner review. No push,
merge, deployment, production historical import or cleanup of review data is
authorized by this handoff.

## Focused local commits

| Commit | Increment |
| --- | --- |
| `b0ff2ce` | Explicit local Phase 4 authorization above unpushed Spotlight |
| `6fd89d0` | Append-only tenant history, permission and independent access gates |
| `badaa7e` | Successful document/master/draft recording without posting changes |
| `8379b4e` | Cash/opening/equity/period-close recording |
| `9ee0026` | Sessions, report runs and authorized browser export notifications |
| `90d1c95` | Explicit one-company approximate historical import and runbook |
| `82ef480` | Dashboard, exports, synthetic review fixture and isolation suite |
| `e4d169d` | Batched record links and pre-edit date evidence |
| `b8a119b` | Financee-compatible user record-link helper |
| `da2e17b` | Exact default-off feature-plan expectations |
| `4639a9a` | Company export context and concise document references |
| `703be6c` | Phone-width containment and related UI integrity pin |

Subsequent handoff commits record verification/documentation only. The private
handoff always identifies the exact final committed checkout/image running.

## Subsequent main push authorization

On 2026-10-24, after this local handoff, the owner instructed "now push to main
and watch CI to complete". This authorizes the cumulative Phase 2–4 main push
and supersedes the earlier no-push stop. Preserve the focused commits with a
fast-forward from verified `origin/main` at `da30168`; monitor the exact pushed
SHA. The verification above remains evidence for application `703be6c` and the
documentation-only handoff `4d74f11`. Record actual CI outcomes when available.
Protected environment approvals and production historical import remain with
the owner; local review data and Accounting are preserved.
