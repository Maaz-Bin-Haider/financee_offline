# Phase 1: dark mode and isolated local review

Date: 2026-10-23. Status: implementation, automated checks and owner manual
review passed. The owner explicitly authorized the Phase 1 branch push and
requested that its CI be watched to completion.

## What changed

- Reused the reviewed theme port preserved on `feature/dark-mode` (`6e4fe68`)
  in focused local commits; that branch and its original commit remain intact.
- Matched Accounting's dark-by-default behavior. An explicit saved light
  preference stays light. Pre-paint login/base/suspended scripts agree with
  the sidebar toggle, including unavailable storage and cross-tab updates.
- Applied semantic colors across the existing Financee transaction, draft,
  master-data, cash-flow, report, dashboard, attachment and company modules.
  Admin and PDF/print output retain their separate fixed light treatment.
- Added a standalone, locally scoped review stack and synthetic fixtures.
  Nginx alone joins an edge network to publish the loopback review port;
  web/PostgreSQL/Redis stay on an internal network with no outgoing SMTP.

No business view, tenant SQL, public migration, posting function, permission
definition or production deployment script was changed. Report Email,
Spotlight and Team Activity have not been started. Accounting Plus Inventory
has not been modified.

## Local commits

| Commit | Increment |
| --- | --- |
| `91fdfd6` | Plan and persistent owner review/push boundaries |
| `56f6959` | Isolated review environment and synthetic tenants |
| `d8236c7` | Theme foundations, dark default and behavior checks |
| `c1195ed` | Purchases, sales, returns and drafts |
| `90ae4c9` | Master data, cash flow and alerts |
| `e9b852d` | Reports, dashboard and Financee-specific modules |
| `c2b6bc9` | Docker Desktop loopback routing through Nginx's edge network |

The checks below ran on `c2b6bc9`. The subsequent review-record commit changes
documentation only; the running review helper records the exact final checkout
commit and image in its private local handoff file.

## Automated results

- `node tests/test_dark_mode.js`: 11 behavior checks passed, including saved
  preferences, toggle state/labels, missing controls, blocked storage, cleared
  preferences, cross-tab changes and all three pre-paint scripts.
- `python3 tests/test_review_stack.py`: 5 safety tests passed. Resolved Compose
  configuration was checked for internal application networking, loopback-only
  HTTP, unexposed data-service ports and project-scoped volumes.
- Database-free serial creation/removal, metadata, compatibility, cleanup,
  executor, migration-history, ARM64 release, recovery, staging-security and
  Phase 30 release contract scripts passed. All 225 intentional UI sources are
  re-pinned; the 12 serial document implementations and 18 tenant SQL sources
  retain their previous hashes.
- Full `tests/suite/run_all.py` in `financee_review_regression`: all 22 modules
  passed, including 75/75 HTTP checks and 17/17 four-company isolation checks.
- Disposable Phase 3A compatibility checks: 20/20 passed.
- `manage.py check`, `makemigrations --check --dry-run` and `release_preflight`
  passed in the disposable stack; all active schemas verify as serial v6.

The subscription email suite intentionally exercises a failing backend and
logs its expected exception; the module passes. Test delivery is in-memory,
and the application's internal network cannot reach an external mail server.

These results do not claim a new production deployment, a full encrypted
restore drill, or a new execution of every historical old-image rehearsal.
No SQL/migration change was made that would require a new data transition.

## Browser checks

- Dark login, successful synthetic login and saved light preference across reload.
- Dark rendering on all 22 sidebar module entry points; six representative
  transaction/report/company screens also checked after switching to light.
- Toggle and labels, actual two-tab synchronization, populated purchase-history
  popup, dashboard alerts, smart descriptions, attachments and company identity.
- Synthetic suspended account sees the dark suspension page; a platform
  operator without membership reaches the separate light admin.
- No browser warning/error logs were present in the inspected current page.

Browser evidence is stored outside Git in this chat's visualization directory.
The in-app browser did not apply its requested 390px viewport override
(`innerWidth` remained 1280), so phone-size verification remains part of the
owner's manual review; desktop screenshots are not represented as mobile tests.
The override was reset. Export styling was preserved by scope/source review;
the owner should include a representative PDF in the manual pass.

## Running review system

Open `http://127.0.0.1:8180/`. The stack runs only on this Mac and uses synthetic
data, not either deployed database.

| Account | Purpose |
| --- | --- |
| `alpha_manager` | Full Financee screens for Review Alpha |
| `alpha_staff` | Alpha document workflows |
| `alpha_reader` | Alpha read-only restrictions |
| `beta_manager`, `beta_staff` | Separate Review Beta data and disabled modules |
| `suspended_user` | Subscription-suspended page |
| `review_operator` | Platform admin without a company membership |

The generated shared **local-only** account password is in `handoff.txt` under
the temporary `financee-review-<uid>/financee_review_darkmode` directory; the
helper prints its absolute path. Credentials are not committed to Git.

Both companies deliberately reuse `REVIEW PHONE`, party names, serials
`REVIEW-001` through `REVIEW-008`, and initial document numbers. Alpha and Beta
have different prices/amounts. Alpha has all modules available and a renewal
warning. Beta has Owner Equity, Month Close and Attachments switched off. The
currency setup differs, but this phase does not change pre-existing currency
rendering. Purchase/sale/return/payment/receipt/draft examples are preloaded.
Repeated startup preserves edits and does not reseed or reset the review data.

Commands from the Financee checkout:

```bash
python3 deploy/review_stack.py status --project financee_review_darkmode
python3 deploy/review_stack.py stop --project financee_review_darkmode
python3 deploy/review_stack.py start --project financee_review_darkmode
```

Do not run a mutating suite in this manual review project. Regression uses its
own `financee_review_regression` project and separate data. Removal requires an
exact project confirmation and should wait until the owner finishes review.

## Owner's manual checklist

1. Sign in as `alpha_manager`, compare the appearance with Accounting, switch
   to light and back, reload, then check another tab.
2. Check dashboard/cards, sales/purchases, both returns, draft screens, party
   and item lists, payment/receipt/contra, history popups and descriptions.
3. Check reports and the Financee-only opening/equity/month-close/attachment
   surfaces. Open one existing invoice and download a representative PDF.
4. Check a narrow/mobile browser layout and readable inputs, tables and popups.
5. Sign out and try `beta_manager`, `alpha_reader` and `suspended_user` to
   confirm the separate company/feature/read-only/subscription behavior.
6. Report any corrections. Once satisfied, give an explicit push instruction
   with the intended branch/destination; manual approval alone does not push.

## Owner approval and push handoff

On 2026-10-23 the owner reported: "manual review. passed push it and watch the
Ci to complete". The reviewed application is commit `9ec223e`; the approval
record that follows changes documentation only. Push
`codex/financee-feature-rollout` to `origin` and monitor the resulting exact
commit's GitHub Actions run to completion. Record the run URL and result in
the owner handoff. This authorizes the branch push, not a merge or protected
deployment approval.

Branch commit `41c81518ce71c19d31191fa054b0275279eb3363` was pushed and
[CI run 39970474964](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/39970474964)
completed successfully: all 13 test gates passed. The three main-only
approval/publish/deploy jobs were skipped as expected.

The owner then instructed "merge to main before starting phase 2". This
authorizes merging and pushing the approved Phase 1 history to `main`.
Preserve the small commits with a fast-forward merge, watch the resulting
main workflow, and leave protected staging/production approvals to the owner.
Keep Phase 2 gated until the preceding release gates are released.
