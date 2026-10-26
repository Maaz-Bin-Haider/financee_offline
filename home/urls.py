# from django.urls import path
# from . import views

# app_name = "home"

# urlpatterns = [
#     path('', views.home_view, name='home'),
#     path('api/cash/', views.get_cash_balance, name='get_cash_balance'),
#     path('api/parties/', views.get_parties, name='get_parties'),
#     path('api/items/', views.get_items, name='get_items'),
#     path('api/party-balances/', views.get_party_balance_ledger_exclusing_mains, name='get_party_balances'),
#     path('api/receivable/',views.get_receivables_exclusing_mains, name='get_receivables'),
#     path('api/payable/',views.get_payables_exclusing_mains, name='get_payables'),
#     path('api/expense-party-balances/', views.get_expense_party_balances, name='get_expense_party_balances'),
# ]

"""
home/urls.py — Dashboard URL Configuration
"""

from django.urls import path
from . import views

app_name = "home"

urlpatterns = [
    # ── Main Dashboard ────────────────────────────────────────────────────
    path("", views.home_view, name="home"),

    # ── 1. Daily Sales & Profit ──────────────────────────────────────────
    path("api/dash/sales/today/",   views.api_dash_sales_today,   name="dash_sales_today"),
    path("api/dash/sales/chart/",   views.api_dash_sales_chart,   name="dash_sales_chart"),

    # ── 2. Stock Overview ────────────────────────────────────────────────
    path("api/dash/stock/kpi/",     views.api_dash_stock_kpi,     name="dash_stock_kpi"),
    path("api/dash/stock/low/",     views.api_dash_low_stock,     name="dash_low_stock"),
    path("api/dash/stock/fast/",    views.api_dash_fast_moving,   name="dash_fast_moving"),
    path("api/dash/stock/stale/",   views.api_dash_stale_stock,   name="dash_stale_stock"),

    # ── 3. Top Parties ───────────────────────────────────────────────────
    path("api/dash/customers/top/", views.api_dash_top_customers, name="dash_top_customers"),
    path("api/dash/vendors/top/",   views.api_dash_top_vendors,   name="dash_top_vendors"),

    # ── 4. Receivables Aging ─────────────────────────────────────────────
    path("api/dash/receivables/aging/", views.api_dash_receivables_aging, name="dash_receivables_aging"),

    # ── 5. Recent Transactions ───────────────────────────────────────────
    path("api/dash/transactions/recent/", views.api_dash_recent_transactions, name="dash_recent_transactions"),

    # ── 6. Expense Tracking ──────────────────────────────────────────────
    path("api/dash/expenses/kpi/",          views.api_dash_expense_kpi,          name="dash_expense_kpi"),
    path("api/dash/expenses/categories/",   views.api_dash_expense_categories,   name="dash_expense_categories"),
    path("api/dash/expenses/descriptions/", views.api_dash_expense_descriptions, name="dash_expense_descriptions"),

    # ── 7. Smart Alerts ──────────────────────────────────────────────────
    path("api/dash/alerts/",        views.api_dash_smart_alerts,  name="dash_smart_alerts"),
    path("api/dash/drafts/",        views.api_dash_draft_reservations, name="dash_draft_reservations"),

    # ── Legacy endpoints (retained for backward compat) ──────────────────
    path("api/cash/",              views.get_cash_balance,                      name="get_cash_balance"),
    path("api/parties/",           views.get_parties,                           name="get_parties"),
    path("api/parties/parties-dash/", views.get_parties_add_party_section, name="get_parties_parties_dash"),
    path("api/items/",             views.get_items,                             name="get_items"),
    path("api/party-balances/",    views.get_party_balance_ledger_exclusing_mains, name="get_party_balances"),
    path("api/receivable/",        views.get_receivables_exclusing_mains,       name="get_receivables"),
    path("api/payable/",           views.get_payables_exclusing_mains,          name="get_payables"),
    path("api/expense-party-balances/", views.get_expense_party_balances,       name="get_expense_party_balances"),
]
