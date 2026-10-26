#!/usr/bin/env python3
"""HTTP layer: drives the real Django views through the test client as a
logged-in tenant user. Verifies pages render, JSON APIs respond without server
errors (no 5xx), auth endpoints work, and a master-data write flow succeeds.
On builds with the restored dark mode it also checks that the theme toggle and
the theme scripts reach the page (the Phase 3B rehearsal runs this file inside
an older image, whose base.html only carries the retired toggle in a comment).

Run inside the web container:
    docker compose -f deploy/docker-compose.yml exec -e PYTHONPATH=/app web \
        python tests/suite/test_http.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.test import Client  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.conf import settings  # noqa: E402
from tenancy.models import Company, Membership  # noqa: E402

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))


def build_has_dark_mode():
    """Whether the RUNNING build's base.html carries the restored theme toggle."""
    try:
        base = (settings.BASE_DIR / "templates" / "base" / "base.html").read_text(encoding="utf-8")
    except OSError:
        return False
    return "data-theme-toggle" in base


THEME_SCRIPT = "localStorage.getItem('theme') !== 'light'"


# GET routes that must not raise a server error (5xx). Pages should also be 200;
# parameterised APIs may legitimately return 400, which is still not a crash.
PAGES = [
    "/home/", "/parties/parties-dash/", "/items/items-dash/",
    "/set-opening/", "/owner-equity/", "/month-close/", "/opening-stock/",
    "/sales-reports/",
]
JSON_APIS = [
    "/home/api/dash/sales/today/", "/home/api/dash/sales/chart/", "/home/api/dash/stock/kpi/",
    "/home/api/dash/stock/low/", "/home/api/dash/stock/fast/", "/home/api/dash/stock/stale/",
    "/home/api/dash/customers/top/", "/home/api/dash/vendors/top/", "/home/api/dash/receivables/aging/",
    "/home/api/dash/transactions/recent/", "/home/api/dash/expenses/kpi/",
    "/home/api/dash/expenses/categories/", "/home/api/dash/expenses/descriptions/",
    "/home/api/dash/alerts/", "/home/api/cash/", "/home/api/parties/", "/home/api/items/",
    "/home/api/party-balances/", "/home/api/receivable/", "/home/api/payable/",
    "/home/api/expense-party-balances/",
    "/parties/parties-list/", "/items/items-list/",
    "/parties/autocomplete-party?term=A", "/items/autocomplete-item/?term=A",
    "/set-opening/api/opening-cash/", "/owner-equity/api/transactions/",
    "/owner-equity/api/equity-accounts/", "/month-close/api/overview/",
    "/opening-stock/api/list/", "/opening-stock/api/obe-status/",
    "/payments/get-old-payments/", "/receipts/get-old-receipts/",
    "/contra/get-old-contras/",
]
# Report pages (accountsReports + sales-reports APIs) — assert no 5xx.
REPORTS = [
    "/accountsReports/trial-balance/", "/accountsReports/cash-ledger/",
    "/accountsReports/accounts-receivable/", "/accountsReports/accounts-payable/",
    "/accountsReports/stock-report/", "/accountsReports/stock-worth-report/",
    "/accountsReports/stock-summary/", "/accountsReports/detailed-ledger/",
    "/accountsReports/detailed-ledger2/", "/accountsReports/item-history/",
    "/accountsReports/item-detail/", "/accountsReports/item-last-purchase/",
    "/accountsReports/item-last-sale/", "/accountsReports/serial-ledger/",
    "/accountsReports/monthly-position/", "/accountsReports/monthly-income/",
    "/sales-reports/api/summary/", "/sales-reports/api/product-profitability/",
    "/sales-reports/api/customer-profitability/", "/sales-reports/api/sales-by-product/",
    "/sales-reports/api/sales-by-customer/", "/sales-reports/api/sale-wise/",
    "/sales-reports/api/trend/", "/sales-reports/api/invoice-register/",
]


def main():
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first()
    if user is None:
        chk("a superuser exists", False, "no superuser to drive the client")
        return _report()

    # Ensure the superuser has a tenant membership; clean up if we create one.
    created_membership = False
    try:
        user.membership
    except Membership.DoesNotExist:
        co = Company.objects.filter(is_active=True).first()
        if co is None:
            chk("an active company exists", False, "no active company")
            return _report()
        Membership.objects.create(user=user, company=co)
        created_membership = True

    # Every page below must be reachable, but the company may have been
    # created with the new-company default plan (some features off). Switch
    # everything on for the run and restore its own switches afterwards.
    company_pk = Membership.objects.get(user=user).company_id
    features_snapshot = list(Company.objects.get(pk=company_pk).disabled_features or [])
    Company.objects.filter(pk=company_pk).update(disabled_features=[])

    allowed = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*", "")]
    server = allowed[0].lstrip(".") if allowed else "localhost"
    c = Client(SERVER_NAME=server)
    c.force_login(user)

    try:
        # auth
        r = c.get("/authentication/current/user/")
        chk("current_user returns 200", r.status_code == 200, r.status_code)
        # login page redirects an already-authenticated user away.
        r = c.get("/authentication/login/")
        chk("login page reachable (200 or redirect)", r.status_code in (200, 302), r.status_code)

        for path in PAGES:
            r = c.get(path)
            chk(f"page 200: {path}", r.status_code == 200, r.status_code)

        for path in JSON_APIS + REPORTS:
            r = c.get(path)
            chk(f"no server error: {path}", r.status_code < 500, f"status {r.status_code}")

        if build_has_dark_mode():
            from django.contrib.staticfiles.storage import staticfiles_storage

            html = c.get("/home/").content.decode("utf-8", "ignore")
            chk("dark mode: theme script applies the stored choice before paint", THEME_SCRIPT in html)
            chk("dark mode: sidebar toggle is rendered", "data-theme-toggle" in html and 'id="themeToggle"' in html)
            chk("dark mode: dark_mode.js is loaded", "js/dark_mode" in html)
            try:
                chk("dark mode: dark_mode.js is in the static manifest",
                    bool(staticfiles_storage.url("js/dark_mode.js")))
            except ValueError as exc:
                chk("dark mode: dark_mode.js is in the static manifest", False, exc)
            login_html = Client(SERVER_NAME=server).get("/authentication/login/").content.decode("utf-8", "ignore")
            chk("dark mode: login page applies the stored choice before paint", THEME_SCRIPT in login_html)

        # write flow: create a party via the real endpoint (form-encoded)
        pname = f"HTTP PARTY {TAG}"
        r = c.post("/parties/add-new-party/", data={
            "party_name": pname, "party_type": "Customer", "contact_info": "", "address": "",
            "opening_balance": "0", "balance_type": "Debit"})
        ok = r.status_code == 200 and (r.json().get("status") == "success")
        chk("create party via HTTP succeeds", ok, r.content[:160])

        # logout
        r = c.get("/authentication/logout/")
        chk("logout responds", r.status_code in (200, 302), r.status_code)
    finally:
        Company.objects.filter(pk=company_pk).update(disabled_features=features_snapshot)
        if created_membership:
            Membership.objects.filter(user=user).delete()

    return _report()


def _report():
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    print(f"{passed}/{len(RESULTS)} HTTP checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
