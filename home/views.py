# from django.http import JsonResponse
# from django.db import connection
# from django.contrib import messages
# from django.shortcuts import render,redirect
# import json
# from django.contrib.auth.decorators import login_required


# @login_required
# def home_view(request):
#     return render(request, "home_templtes/home_template.html")

# @login_required
# def get_cash_balance(request):
#     """Fetch current cash balance from vw_trial_balance (Cash account)."""
#     if not request.user.has_perm("auth.view_accounts_reports_page"):
#         return JsonResponse({"cash_balance": 0.00})


#     with connection.cursor() as cursor:
#         cursor.execute("""
#             SELECT balance 
#             FROM vw_trial_balance 
#             WHERE name = 'Cash'
#             LIMIT 1;
#         """)
#         row = cursor.fetchone()
#     cash_balance = float(row[0]) if row else 0.0
#     return JsonResponse({"cash_balance": cash_balance})

# # Retired Function
# @login_required
# def get_party_balances(request):
#     if not request.user.has_perm("auth.view_accounts_reports_page"):
#         data= {}
#         data = json.loads(data)
#         return JsonResponse(data, safe=False)
    
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_party_balances_json();")
#         data = cursor.fetchone()[0]
#         data = json.loads(data)
#     return JsonResponse(data, safe=False)


# @login_required
# def get_expense_party_balances(request):
#     if not request.user.has_perm("auth.view_accounts_reports_page") or not request.user.has_perm("auth.view_company_valuation"):
#         data= {}
#         data = json.loads(data)
#         return JsonResponse(data, safe=False)
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_expense_party_balances_json();")
#         data = cursor.fetchone()[0]
#         data = json.loads(data)
#     return JsonResponse(data, safe=False)


# @login_required
# def get_parties(request):
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_parties_json();")
#         data = cursor.fetchone()[0]
#         data = json.loads(data)
#     return JsonResponse(data, safe=False)


# @login_required
# def get_items(request):
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_items_json();")
#         data = cursor.fetchone()[0]
#         data = json.loads(data)
#     return JsonResponse(data, safe=False)


# @login_required
# def get_party_balance_ledger_exclusing_mains(request):
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_party_balances_json_excluding(%s);",[['ABDUL MAJID BHAI', 'ABDUL REHMAN BHAI','FAISAL BHAI','WAHEED BHAI']])
#         data = cursor.fetchone()[0]
#         data = json.loads(data)
#     return JsonResponse(data, safe=False)


# @login_required
# def get_receivables_exclusing_mains(request):
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_accounts_receivable_json_excluding();")
#         data = cursor.fetchone()[0]
#         data = json.loads(data)
#     return JsonResponse(data, safe=False)

# @login_required
# def get_payables_exclusing_mains(request):
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_accounts_payable_json_excluding(%s);",[['ABDUL MAJID BHAI', 'ABDUL REHMAN BHAI','FAISAL BHAI','WAHEED BHAI']])
#         data = cursor.fetchone()[0]
#         data = json.loads(data)
#     return JsonResponse(data, safe=False)

# """
# Dashboard Views — home/views.py (REPLACEMENT FILE)
# Accounting + Inventory Management System — Redesigned Dashboard
# """

# import json
# from django.http import JsonResponse
# from django.db import connection
# from django.contrib import messages
# from django.shortcuts import render, redirect
# from django.contrib.auth.decorators import login_required, permission_required
# from django.views.decorators.http import require_GET
# from datetime import date, timedelta


# # ---------------------------------------------------------------------------
# # Helpers
# # ---------------------------------------------------------------------------

# def _run_pg_function(sql, params=None):
#     """Execute a PostgreSQL function and return parsed JSON result."""
#     with connection.cursor() as cursor:
#         cursor.execute(sql, params or [])
#         row = cursor.fetchone()
#     return json.loads(row[0]) if row and row[0] else None


# def _json_ok(data):
#     return JsonResponse({"status": "ok", "data": data}, safe=False)


# def _json_denied():
#     return JsonResponse({"status": "denied", "data": None}, status=403)


# # ---------------------------------------------------------------------------
# # Dashboard HTML View
# # ---------------------------------------------------------------------------

# @login_required
# def home_view(request):
#     """Main dashboard page — permission guard at widget level via JS/API."""
#     return render(request, "home_templtes/home_template.html")


# # ---------------------------------------------------------------------------
# # 1. Daily Sales & Profit
# #    Permission: auth.view_dash_sales_profit
# # ---------------------------------------------------------------------------

# @login_required
# @require_GET
# def api_dash_sales_today(request):
#     """Today's sales KPIs: revenue, invoice count, gross profit."""
#     if not request.user.has_perm("auth.view_dash_sales_profit"):
#         return _json_denied()
#     data = _run_pg_function("SELECT fn_dash_sales_today_kpi();")
#     return _json_ok(data)


# @login_required
# @require_GET
# def api_dash_sales_chart(request):
#     """
#     Sales chart data. Accepts optional GET params:
#       ?from=YYYY-MM-DD&to=YYYY-MM-DD  → custom range
#       (no params)                      → last 7 days
#     """
#     if not request.user.has_perm("auth.view_dash_sales_profit"):
#         return _json_denied()

#     date_from = request.GET.get("from")
#     date_to = request.GET.get("to")

#     if date_from and date_to:
#         data = _run_pg_function(
#             "SELECT fn_dash_sales_range(%s::date, %s::date);",
#             [date_from, date_to],
#         )
#     else:
#         data = _run_pg_function("SELECT fn_dash_sales_last7days();")

#     return _json_ok(data or [])


# # ---------------------------------------------------------------------------
# # 2. Stock Overview
# #    Permission: auth.view_dash_stock_overview
# # ---------------------------------------------------------------------------

# @login_required
# @require_GET
# def api_dash_stock_kpi(request):
#     """Stock summary KPIs."""
#     if not request.user.has_perm("auth.view_dash_stock_overview"):
#         return _json_denied()
#     data = _run_pg_function("SELECT fn_dash_stock_kpi();")
#     return _json_ok(data)


# @login_required
# @require_GET
# def api_dash_low_stock(request):
#     """Low stock items. Optional: ?threshold=5"""
#     if not request.user.has_perm("auth.view_dash_stock_overview"):
#         return _json_denied()
#     threshold = int(request.GET.get("threshold", 5))
#     data = _run_pg_function("SELECT fn_dash_low_stock_items(%s);", [threshold])
#     return _json_ok(data or [])


# @login_required
# @require_GET
# def api_dash_fast_moving(request):
#     """Fast-moving items. Optional: ?days=30&limit=10"""
#     if not request.user.has_perm("auth.view_dash_stock_overview"):
#         return _json_denied()
#     days = int(request.GET.get("days", 30))
#     limit = int(request.GET.get("limit", 10))
#     data = _run_pg_function("SELECT fn_dash_fast_moving_items(%s, %s);", [days, limit])
#     return _json_ok(data or [])


# @login_required
# @require_GET
# def api_dash_stale_stock(request):
#     """Items not sold in X days. Optional: ?days=30"""
#     if not request.user.has_perm("auth.view_dash_stock_overview"):
#         return _json_denied()
#     days = int(request.GET.get("days", 30))
#     data = _run_pg_function("SELECT fn_dash_stale_stock(%s);", [days])
#     return _json_ok(data or [])


# # ---------------------------------------------------------------------------
# # 3. Top Customers & Vendors
# #    Permission: auth.view_dash_top_parties
# # ---------------------------------------------------------------------------

# @login_required
# @require_GET
# def api_dash_top_customers(request):
#     """Top N customers. Optional: ?limit=5&from=YYYY-MM-DD&to=YYYY-MM-DD"""
#     if not request.user.has_perm("auth.view_dash_top_parties"):
#         return _json_denied()
#     limit = int(request.GET.get("limit", 5))
#     date_from = request.GET.get("from") or None
#     date_to = request.GET.get("to") or None
#     data = _run_pg_function(
#         "SELECT fn_dash_top_customers(%s, %s::date, %s::date);",
#         [limit, date_from, date_to],
#     )
#     return _json_ok(data or [])


# @login_required
# @require_GET
# def api_dash_top_vendors(request):
#     """Top N vendors. Optional: ?limit=5&from=YYYY-MM-DD&to=YYYY-MM-DD"""
#     if not request.user.has_perm("auth.view_dash_top_parties"):
#         return _json_denied()
#     limit = int(request.GET.get("limit", 5))
#     date_from = request.GET.get("from") or None
#     date_to = request.GET.get("to") or None
#     data = _run_pg_function(
#         "SELECT fn_dash_top_vendors(%s, %s::date, %s::date);",
#         [limit, date_from, date_to],
#     )
#     return _json_ok(data or [])


# # ---------------------------------------------------------------------------
# # 4. Receivables Aging
# #    Permission: auth.view_dash_receivables_aging
# # ---------------------------------------------------------------------------

# @login_required
# @require_GET
# def api_dash_receivables_aging(request):
#     """Receivables aging buckets: overdue / medium-risk / fresh."""
#     if not request.user.has_perm("auth.view_dash_receivables_aging"):
#         return _json_denied()
#     data = _run_pg_function("SELECT fn_dash_receivables_aging();")
#     return _json_ok(data or {})


# # ---------------------------------------------------------------------------
# # 5. Recent Transactions Feed
# #    Permission: auth.view_dash_recent_transactions
# # ---------------------------------------------------------------------------

# @login_required
# @require_GET
# def api_dash_recent_transactions(request):
#     """Last N transactions across Sales/Purchase/Receipt/Payment."""
#     if not request.user.has_perm("auth.view_dash_recent_transactions"):
#         return _json_denied()
#     limit = int(request.GET.get("limit", 10))
#     data = _run_pg_function("SELECT fn_dash_recent_transactions(%s);", [limit])
#     return _json_ok(data or [])


# # ---------------------------------------------------------------------------
# # 6. Expense Tracking
# #    Permission: auth.view_dash_expense_tracking
# # ---------------------------------------------------------------------------

# @login_required
# @require_GET
# def api_dash_expense_kpi(request):
#     """Expense KPIs: today / this month / this year."""
#     if not request.user.has_perm("auth.view_dash_expense_tracking"):
#         return _json_denied()
#     data = _run_pg_function("SELECT fn_dash_expense_kpi();")
#     return _json_ok(data)


# @login_required
# @require_GET
# def api_dash_expense_categories(request):
#     """Top expense categories. Optional: ?limit=5&from=YYYY-MM-DD&to=YYYY-MM-DD"""
#     if not request.user.has_perm("auth.view_dash_expense_tracking"):
#         return _json_denied()
#     limit = int(request.GET.get("limit", 5))
#     date_from = request.GET.get("from") or None
#     date_to = request.GET.get("to") or None
#     data = _run_pg_function(
#         "SELECT fn_dash_top_expense_categories(%s, %s::date, %s::date);",
#         [limit, date_from, date_to],
#     )
#     return _json_ok(data or [])


# @login_required
# @require_GET
# def api_dash_expense_descriptions(request):
#     """Top expenses by description/comment. Optional: ?limit=5&from=YYYY-MM-DD&to=YYYY-MM-DD"""
#     if not request.user.has_perm("auth.view_dash_expense_tracking"):
#         return _json_denied()
#     limit = int(request.GET.get("limit", 5))
#     date_from = request.GET.get("from") or None
#     date_to = request.GET.get("to") or None
#     data = _run_pg_function(
#         "SELECT fn_dash_top_expense_descriptions(%s, %s::date, %s::date);",
#         [limit, date_from, date_to],
#     )
#     return _json_ok(data or [])


# # ---------------------------------------------------------------------------
# # 7. Smart Alerts
# #    Permission: auth.view_dash_smart_alerts
# # ---------------------------------------------------------------------------

# @login_required
# @require_GET
# def api_dash_smart_alerts(request):
#     """Smart alert signals: negative cash, no sales, stale receivables, risky customers."""
#     if not request.user.has_perm("auth.view_dash_smart_alerts"):
#         return _json_denied()
#     data = _run_pg_function("SELECT fn_dash_smart_alerts();")
#     return _json_ok(data or [])


# # ---------------------------------------------------------------------------
# # Legacy / retained endpoints
# # ---------------------------------------------------------------------------

# @login_required
# def get_cash_balance(request):
#     """Fetch current cash balance from vw_trial_balance (Cash account)."""
#     if not request.user.has_perm("auth.view_accounts_reports_page"):
#         return JsonResponse({"cash_balance": 0.00})
#     with connection.cursor() as cursor:
#         cursor.execute("""
#             SELECT balance
#             FROM vw_trial_balance
#             WHERE name = 'Cash'
#             LIMIT 1;
#         """)
#         row = cursor.fetchone()
#     cash_balance = float(row[0]) if row else 0.0
#     return JsonResponse({"cash_balance": cash_balance})


# @login_required
# def get_parties(request):
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_parties_json();")
#         data = json.loads(cursor.fetchone()[0])
#     return JsonResponse(data, safe=False)


# @login_required
# def get_items(request):
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_items_json();")
#         data = json.loads(cursor.fetchone()[0])
#     return JsonResponse(data, safe=False)


# @login_required
# def get_party_balance_ledger_exclusing_mains(request):
#     with connection.cursor() as cursor:
#         cursor.execute(
#             "SELECT get_party_balances_json_excluding(%s);",
#             [["ABDUL MAJID BHAI", "ABDUL REHMAN BHAI", "FAISAL BHAI", "WAHEED BHAI"]],
#         )
#         data = json.loads(cursor.fetchone()[0])
#     return JsonResponse(data, safe=False)


# @login_required
# def get_receivables_exclusing_mains(request):
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_accounts_receivable_json_excluding();")
#         data = json.loads(cursor.fetchone()[0])
#     return JsonResponse(data, safe=False)


# @login_required
# def get_payables_exclusing_mains(request):
#     with connection.cursor() as cursor:
#         cursor.execute(
#             "SELECT get_accounts_payable_json_excluding(%s);",
#             [["ABDUL MAJID BHAI", "ABDUL REHMAN BHAI", "FAISAL BHAI", "WAHEED BHAI"]],
#         )
#         data = json.loads(cursor.fetchone()[0])
#     return JsonResponse(data, safe=False)


# @login_required
# def get_expense_party_balances(request):
#     if not (
#         request.user.has_perm("auth.view_accounts_reports_page")
#         and request.user.has_perm("auth.view_company_valuation")
#     ):
#         return JsonResponse({}, safe=False)
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_expense_party_balances_json();")
#         data = json.loads(cursor.fetchone()[0])
#     return JsonResponse(data, safe=False)


"""
Dashboard Views — home/views.py (REPLACEMENT FILE)
Accounting + Inventory Management System — Redesigned Dashboard
"""

import json
from django.http import JsonResponse
from django.db import connection
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_GET
from datetime import date, timedelta

from draft.feature import draft_age_warning_days, draft_sales_enabled


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_pg_function(sql, params=None):
    """
    Execute a PostgreSQL function and return its JSON result as a Python object.

    psycopg2 automatically deserializes PostgreSQL JSON/JSONB columns into
    Python dict/list — so row[0] is already a native Python object.
    Calling json.loads() on it would raise TypeError. We return it directly.
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        row = cursor.fetchone()
    return row[0] if row and row[0] is not None else None


def _json_ok(data):
    return JsonResponse({"status": "ok", "data": data}, safe=False)


def _json_denied():
    return JsonResponse({"status": "denied", "data": None}, status=403)


# ---------------------------------------------------------------------------
# Dashboard HTML View
# ---------------------------------------------------------------------------

@login_required
def home_view(request):
    """Main dashboard page — permission guard at widget level via JS/API."""
    return render(request, "home_templtes/home_template.html")


# ---------------------------------------------------------------------------
# 1. Daily Sales & Profit
#    Permission: auth.view_dash_sales_profit
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_dash_sales_today(request):
    """Today's sales KPIs: revenue, invoice count, gross profit."""
    if not request.user.has_perm("auth.view_dash_sales_profit"):
        return _json_denied()
    data = _run_pg_function("SELECT fn_dash_sales_today_kpi();")
    return _json_ok(data)


@login_required
@require_GET
def api_dash_sales_chart(request):
    """
    Sales chart data. Accepts optional GET params:
      ?from=YYYY-MM-DD&to=YYYY-MM-DD  → custom range
      (no params)                      → last 7 days
    """
    if not request.user.has_perm("auth.view_dash_sales_profit"):
        return _json_denied()

    date_from = request.GET.get("from")
    date_to = request.GET.get("to")

    if date_from and date_to:
        data = _run_pg_function(
            "SELECT fn_dash_sales_range(%s::date, %s::date);",
            [date_from, date_to],
        )
    else:
        data = _run_pg_function("SELECT fn_dash_sales_last7days();")

    return _json_ok(data or [])


# ---------------------------------------------------------------------------
# 2. Stock Overview
#    Permission: auth.view_dash_stock_overview
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_dash_stock_kpi(request):
    """Stock summary KPIs."""
    if not request.user.has_perm("auth.view_dash_stock_overview"):
        return _json_denied()
    data = _run_pg_function("SELECT fn_dash_stock_kpi();")
    return _json_ok(data)


@login_required
@require_GET
def api_dash_low_stock(request):
    """Low stock items. Optional: ?threshold=5"""
    if not request.user.has_perm("auth.view_dash_stock_overview"):
        return _json_denied()
    threshold = int(request.GET.get("threshold", 5))
    data = _run_pg_function("SELECT fn_dash_low_stock_items(%s);", [threshold])
    return _json_ok(data or [])


@login_required
@require_GET
def api_dash_fast_moving(request):
    """Fast-moving items. Optional: ?days=30&limit=10"""
    if not request.user.has_perm("auth.view_dash_stock_overview"):
        return _json_denied()
    days = int(request.GET.get("days", 30))
    limit = int(request.GET.get("limit", 10))
    data = _run_pg_function(
        "SELECT fn_dash_fast_moving_items(%s, %s);", [days, limit]
    )
    return _json_ok(data or [])


@login_required
@require_GET
def api_dash_stale_stock(request):
    """Items not sold in X days. Optional: ?days=30"""
    if not request.user.has_perm("auth.view_dash_stock_overview"):
        return _json_denied()
    days = int(request.GET.get("days", 30))
    data = _run_pg_function("SELECT fn_dash_stale_stock(%s);", [days])
    return _json_ok(data or [])


# ---------------------------------------------------------------------------
# 3. Top Customers & Vendors
#    Permission: auth.view_dash_top_parties
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_dash_top_customers(request):
    """Top N customers. Optional: ?limit=5&from=YYYY-MM-DD&to=YYYY-MM-DD"""
    if not request.user.has_perm("auth.view_dash_top_parties"):
        return _json_denied()
    limit = int(request.GET.get("limit", 5))
    date_from = request.GET.get("from") or None
    date_to = request.GET.get("to") or None
    data = _run_pg_function(
        "SELECT fn_dash_top_customers(%s, %s::date, %s::date);",
        [limit, date_from, date_to],
    )
    return _json_ok(data or [])


@login_required
@require_GET
def api_dash_top_vendors(request):
    """Top N vendors. Optional: ?limit=5&from=YYYY-MM-DD&to=YYYY-MM-DD"""
    if not request.user.has_perm("auth.view_dash_top_parties"):
        return _json_denied()
    limit = int(request.GET.get("limit", 5))
    date_from = request.GET.get("from") or None
    date_to = request.GET.get("to") or None
    data = _run_pg_function(
        "SELECT fn_dash_top_vendors(%s, %s::date, %s::date);",
        [limit, date_from, date_to],
    )
    return _json_ok(data or [])


# ---------------------------------------------------------------------------
# 4. Receivables Aging
#    Permission: auth.view_dash_receivables_aging
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_dash_receivables_aging(request):
    """Receivables aging buckets: overdue / medium-risk / fresh."""
    if not request.user.has_perm("auth.view_dash_receivables_aging"):
        return _json_denied()
    data = _run_pg_function("SELECT fn_dash_receivables_aging();")
    return _json_ok(data or {})


# ---------------------------------------------------------------------------
# 5. Recent Transactions Feed
#    Permission: auth.view_dash_recent_transactions
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_dash_recent_transactions(request):
    """Last N transactions across Sales/Purchase/Receipt/Payment."""
    if not request.user.has_perm("auth.view_dash_recent_transactions"):
        return _json_denied()
    limit = int(request.GET.get("limit", 10))
    data = _run_pg_function("SELECT fn_dash_recent_transactions(%s);", [limit])
    return _json_ok(data or [])


# ---------------------------------------------------------------------------
# 6. Expense Tracking
#    Permission: auth.view_dash_expense_tracking
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_dash_expense_kpi(request):
    """Expense KPIs: today / this month / this year."""
    if not request.user.has_perm("auth.view_dash_expense_tracking"):
        return _json_denied()
    data = _run_pg_function("SELECT fn_dash_expense_kpi();")
    return _json_ok(data)


@login_required
@require_GET
def api_dash_expense_categories(request):
    """Top expense categories. Optional: ?limit=5&from=YYYY-MM-DD&to=YYYY-MM-DD"""
    if not request.user.has_perm("auth.view_dash_expense_tracking"):
        return _json_denied()
    limit = int(request.GET.get("limit", 5))
    date_from = request.GET.get("from") or None
    date_to = request.GET.get("to") or None
    data = _run_pg_function(
        "SELECT fn_dash_top_expense_categories(%s, %s::date, %s::date);",
        [limit, date_from, date_to],
    )
    return _json_ok(data or [])


@login_required
@require_GET
def api_dash_expense_descriptions(request):
    """Top expenses by description/comment. Optional: ?limit=5&from=YYYY-MM-DD&to=YYYY-MM-DD"""
    if not request.user.has_perm("auth.view_dash_expense_tracking"):
        return _json_denied()
    limit = int(request.GET.get("limit", 5))
    date_from = request.GET.get("from") or None
    date_to = request.GET.get("to") or None
    data = _run_pg_function(
        "SELECT fn_dash_top_expense_descriptions(%s, %s::date, %s::date);",
        [limit, date_from, date_to],
    )
    return _json_ok(data or [])


# ---------------------------------------------------------------------------
# 7. Smart Alerts
#    Permission: auth.view_dash_smart_alerts
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_dash_smart_alerts(request):
    """Smart alert signals: negative cash, no sales, stale receivables, risky customers."""
    if not request.user.has_perm("auth.view_dash_smart_alerts"):
        return _json_denied()
    data = _run_pg_function("SELECT fn_dash_smart_alerts();")
    return _json_ok(data or [])


# ---------------------------------------------------------------------------
# 8. Draft Reservations
#    Permission: auth.view_dash_draft_reservations
#    (the per-company draft_invoices flag is enforced by the middleware)
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_dash_draft_reservations(request):
    """Open drafts and the stock they are holding. The limit is clamped rather
    than trusted."""
    if not draft_sales_enabled():
        return _json_denied()
    if not request.user.has_perm("auth.view_dash_draft_reservations"):
        return _json_denied()
    try:
        limit = int(request.GET.get("limit", 5))
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 100))
    data = _run_pg_function(
        "SELECT fn_dash_draft_reservations(%s, %s);",
        [limit, draft_age_warning_days()])
    return _json_ok(data or {})


# ---------------------------------------------------------------------------
# Legacy / retained endpoints
# ---------------------------------------------------------------------------

@login_required
def get_cash_balance(request):
    """Fetch current cash balance from vw_trial_balance (Cash account)."""
    if not request.user.has_perm("auth.view_accounts_reports_page"):
        return JsonResponse({"cash_balance": 0.00})
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT balance
            FROM vw_trial_balance
            WHERE name = 'Cash'
            LIMIT 1;
        """)
        row = cursor.fetchone()
    cash_balance = float(row[0]) if row else 0.0
    return JsonResponse({"cash_balance": cash_balance})


@login_required
def get_parties(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT get_parties_json();")
        row = cursor.fetchone()
    data = row[0] if row else {}
    return JsonResponse(data, safe=False)


@login_required
def get_parties_add_party_section(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT get_parties_json();")
        data = json.loads(cursor.fetchone()[0])
    return JsonResponse(data, safe=False)


@login_required
def get_items(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT get_items_json();")
        row = cursor.fetchone()
    data = row[0] if row else {}
    return JsonResponse(data, safe=False)


@login_required
def get_party_balance_ledger_exclusing_mains(request):
    if not (
        request.user.has_perm("auth.view_accounts_reports_page")
        and request.user.has_perm("auth.view_company_valuation")
    ):
        return JsonResponse({}, safe=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT get_party_balances_json_excluding(%s);",
            [["ABDUL MAJID BHAI", "ABDUL REHMAN BHAI", "FAISAL BHAI", "WAHEED BHAI"]],
        )
        row = cursor.fetchone()
    data = row[0] if row else {}
    return JsonResponse(data, safe=False)


@login_required
def get_receivables_exclusing_mains(request):
    if not (
        request.user.has_perm("auth.view_accounts_reports_page")
        and request.user.has_perm("auth.view_company_valuation")
    ):
        return JsonResponse({}, safe=False)
    with connection.cursor() as cursor:
        cursor.execute("SELECT get_accounts_receivable_json_excluding();")
        row = cursor.fetchone()
    data = row[0] if row else {}
    return JsonResponse(data, safe=False)


@login_required
def get_payables_exclusing_mains(request):
    if not (
        request.user.has_perm("auth.view_accounts_reports_page")
        and request.user.has_perm("auth.view_company_valuation")
    ):
        return JsonResponse({}, safe=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT get_accounts_payable_json_excluding(%s);",
            [["ABDUL MAJID BHAI", "ABDUL REHMAN BHAI", "FAISAL BHAI", "WAHEED BHAI"]],
        )
        row = cursor.fetchone()
    data = row[0] if row else {}
    return JsonResponse(data, safe=False)


@login_required
def get_expense_party_balances(request):
    if not (
        request.user.has_perm("auth.view_accounts_reports_page")
        and request.user.has_perm("auth.view_company_valuation")
    ):
        return JsonResponse({}, safe=False)
    with connection.cursor() as cursor:
        cursor.execute("SELECT get_expense_party_balances_json();")
        row = cursor.fetchone()
    data = row[0] if row else {}
    return JsonResponse(data, safe=False)
