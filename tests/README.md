# Offline verification

Only the Financee_Offline disposable stack is an automated-test target.
The business harness refuses every database name except `financee_offline_test`.
No source database/remote/tenant discovery remains.

Preserved suite: parties, items, purchases, sales, returns, cash/contra, opening,
owner equity, month close, reports and the draft SQL lifecycle. Domain assertions
are inherited without financial expectation changes. Old tenant, subscription,
SMTP, cleanup/reversal/deployment assertions are deliberately removed. Their
applicable replacement coverage lives in `local/tests.py`: public-only objects,
singleton/profile/currency guards, no removed routes/models/permissions, local
onboarding, local authorization, activity and attachments. Draft HTTP permission
checks move there; draft SQL tests remain. Frontend unit checks remain under tests/.

The inherited harness marks some source-known defects XFAIL/XPASS; those must be
reported separately, never counted as normal passes. Independent Decimal-based
journal/stock/profit checks supplement those source expectations.
