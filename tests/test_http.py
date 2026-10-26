"""
test_http.py — HTTP view-layer test for the Financee ERP.

Drives the REAL endpoints through Django's test Client (runs all middleware,
permission checks, views, stored-function calls and template rendering) as a
logged-in user of tenant_company_1. Reports any endpoint that returns >=400, or
JSON with {"status":"error"} / {"success":false}.

Run it INSIDE the web container so it shares the app's settings + DB:

    docker compose exec web python tests/test_http.py

It is self-contained: it creates its own party/item before exercising the
write endpoints, so it does not depend on the DB harness having run first.
"""
import os
import sys
import json
import time

# Make the project root (the parent of this tests/ folder) importable, so
# `financee.settings` resolves no matter the current working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from tenancy.models import Company, Membership

TAG = time.strftime("%H%M%S")
PARTY = f"HTTP CUST {TAG}"
VENDOR = f"HTTP VEND {TAG}"
ITEM = f"HTTP ITEM {TAG}"

U = get_user_model()
user = U.objects.filter(is_superuser=True).first()
if user is None:
    raise SystemExit("No superuser found. Create one before running this harness.")

# The tenant guard correctly rejects even a superuser when no active company is
# assigned. Fresh CI creates tenant memberships for ci_user* accounts, but those
# users intentionally have no broad permissions; use the superuser and attach a
# temporary membership exactly as tests/suite/test_http.py does. This keeps the
# standalone harness self-contained and avoids a misleading wall of expected
# tenant-guard 403 responses on a fresh database.
created_membership = False
try:
    user.membership
except Membership.DoesNotExist:
    company = Company.objects.filter(
        is_active=True,
    ).exclude(schema_name="").order_by("id").first()
    if company is None:
        raise SystemExit("No active provisioned company found.")
    Membership.objects.create(user=user, company=company)
    created_membership = True

# Use a host the app already trusts, so we never depend on (or modify) the
# production ALLOWED_HOSTS. Falls back to 'localhost' when '*' is allowed.
from django.conf import settings
_allowed = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*", "")]
SERVER = (_allowed[0].lstrip(".") if _allowed else "localhost")

c = Client(SERVER_NAME=SERVER)
c.force_login(user)

results = []


def hit(method, path, **kw):
    try:
        resp = getattr(c, method)(path, **kw)
        ok = resp.status_code < 400
        soft = False
        body = resp.content[:240].decode("utf-8", "replace")
        if "application/json" in resp.get("Content-Type", ""):
            try:
                j = json.loads(resp.content or "{}")
                if isinstance(j, dict) and (
                    j.get("status") in ("error", "denied") or j.get("success") is False
                ):
                    soft = True
            except Exception:
                pass
        results.append((method.upper(), path, str(resp.status_code), ok and not soft,
                        body if (not ok or soft) else ""))
    except Exception as e:
        results.append((method.upper(), path, "EXC", False, f"{type(e).__name__}: {e}"))


DR = "?from=2025-06-01&to=2025-06-07"

GETS = [
    "/home/", "/home/api/cash/", "/home/api/parties/", "/home/api/items/",
    "/home/api/dash/sales/today/", "/home/api/dash/sales/chart/", "/home/api/dash/stock/kpi/",
    "/home/api/dash/stock/low/", "/home/api/dash/stock/fast/", "/home/api/dash/stock/stale/",
    "/home/api/dash/customers/top/", "/home/api/dash/vendors/top/",
    "/home/api/dash/receivables/aging/", "/home/api/dash/transactions/recent/",
    "/home/api/dash/expenses/kpi/", "/home/api/dash/expenses/categories/",
    "/home/api/dash/expenses/descriptions/", "/home/api/dash/alerts/",
    "/accountsReports/trial-balance/", "/accountsReports/accounts-receivable/",
    "/accountsReports/accounts-payable/", "/accountsReports/stock-report/",
    "/accountsReports/stock-worth-report/", "/accountsReports/stock-summary/",
    "/accountsReports/monthly-position/",
    "/accountsReports/monthly-income/",
    "/sales-reports/", f"/sales-reports/api/summary/{DR}",
    f"/sales-reports/api/product-profitability/{DR}", f"/sales-reports/api/customer-profitability/{DR}",
    f"/sales-reports/api/sales-by-product/{DR}", f"/sales-reports/api/sales-by-customer/{DR}",
    f"/sales-reports/api/sale-wise/{DR}", f"/sales-reports/api/trend/{DR}",
    f"/sales-reports/api/invoice-register/{DR}",
    "/owner-equity/", "/owner-equity/api/transactions/", "/owner-equity/api/equity-accounts/",
    "/opening-stock/", "/opening-stock/api/list/", "/opening-stock/api/obe-status/",
    "/set-opening/", "/set-opening/api/opening-cash/",
    "/month-close/", "/month-close/api/overview/",
    "/items/items-dash/", "/items/items-list/", "/items/autocomplete-item/?term=A",
    "/parties/parties-dash/", "/parties/parties-list/",
    "/sale/sales/", "/sale/get-sale-summary/", "/purchase/purchasing/", "/purchase/get-purchase-summary/",
    "/payments/payment/", "/payments/get-old-payments/", "/receipts/receipt/", "/receipts/get-old-receipts/",
    "/contra/contra/", "/contra/get-old-contras/",
]
for p in GETS:
    hit("get", p)

# --- write endpoints (form-encoded, as the templates submit) ---
hit("post", "/parties/add-new-party/", data={"party_name": PARTY, "party_type": "Customer",
                                              "opening_balance": "0", "balance_type": "Debit"})
hit("post", "/parties/add-new-party/", data={"party_name": VENDOR, "party_type": "Vendor",
                                              "opening_balance": "0", "balance_type": "Credit"})
hit("post", "/items/add-new-item/", data={"item_name": ITEM, "sale_price": "500", "storage": "WH1"})
# payment to the vendor we just created; receipt from the customer we just created
hit("post", "/payments/payment/", data="{}", content_type="application/json")  # empty-body robustness probe
hit("post", "/payments/payment/", **{"data": json.dumps({"action": "submit", "party_name": VENDOR,
        "amount": 250, "method": "Cash", "payment_date": "2025-06-03", "description": "t"}),
        "content_type": "application/json"})
hit("post", "/receipts/receipt/", **{"data": json.dumps({"action": "submit", "party_name": PARTY,
        "amount": 350, "method": "Cash", "receipt_date": "2025-06-03", "description": "t"}),
        "content_type": "application/json"})

fails = [r for r in results if not r[3]]
print(f"\nHTTP endpoints exercised: {len(results)}   |   problems: {len(fails)}\n")
for m, p, code, ok, body in results:
    print(f"  [{'ok  ' if ok else 'FAIL'}] {code:>3} {m:4} {p}")
if fails:
    print("\n--- PROBLEM DETAIL (review each) ---")
    for m, p, code, ok, body in fails:
        print(f"\n{m} {p} -> {code}\n  {body}")

if created_membership:
    Membership.objects.filter(user=user).delete()

# This harness is a CI gate, not only a diagnostic printer. A reported problem
# must produce a non-zero process exit so `&&` chains and GitHub Actions stop.
sys.exit(1 if fails else 0)
