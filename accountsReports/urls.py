from django.urls import path
from .views import (
    detailed_ledger_view,
    trial_balance_view,
    stock_report_view,
    stock__worth_report_view,
    item_history_view, 
    serial_ledger_view,
    stock_summary,
    item_detail_view,
    cash_ledger_view,
    items_last_purchasing,
    receivable,
    payable,
    serial_ledger_purchase_only_view,
    serial_ledger_sale_only_view, 
    items_last_sale,
    detailed_ledger2_view,
    serial_ledger_view_sale_price_hidden,
    monthly_position_report,
    monthly_income_report
    )

app_name = "accountsReports"

urlpatterns = [
    path('detailed-ledger/',detailed_ledger_view, name="detailed_ledger"),
    path('detailed-ledger2/', detailed_ledger2_view, name="detailed_ledger2"),
    path('trial-balance/',trial_balance_view, name="trial_balance"),
    path('cash-ledger/', cash_ledger_view, name="cash_ledger"),
    path('accounts-receivable/', receivable, name="accounts_receivable"),
    path('accounts-payable/', payable, name="accounts_payable"),
    path('stock-report/',stock_report_view,name="stock_report"),
    path('stock-worth-report/',stock__worth_report_view,name="stock__worth_report"),
    path('item-history/',item_history_view,name="item_history"),
    path('item-detail/', item_detail_view, name='item_detail'),
    path('item-last-purchase/', items_last_purchasing, name='items_last_purchasing'),
    path('item-last-sale/', items_last_sale, name='items_last_sale'),
    path("serial-ledger/", serial_ledger_view, name="serial_ledger"),
    path("serial-ledger-sold-flag/", serial_ledger_view_sale_price_hidden, name="serial_ledger_with_sold_flag"),
    path("serial-ledger-purchase-only/", serial_ledger_purchase_only_view, name="serial_ledger_purchase_only"),
    path("serial-ledger-sale-only/", serial_ledger_sale_only_view, name="serial_ledger_sale_only"),
    path("stock-summary/",stock_summary,name="stock_summary"),
     # ── NEW monthly reports ──
    path('monthly-position/',           monthly_position_report,                name='monthly_position_report'),
    path('monthly-income/',             monthly_income_report,                  name='monthly_income_report'),
]
