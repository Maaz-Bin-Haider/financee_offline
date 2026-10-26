"""Explicit Financee report runs and export sources; opening HTML is not a run."""
from spotlight.policy import PAGES, DOCUMENTS, MASTERS, Target

ACCOUNT_KEYS = {
 'detailed_ledger':'ledger','detailed_ledger2':'ledger2','cash_ledger':'cash','trial_balance':'trial',
 'accounts_receivable':'receivable','accounts_payable':'payable','stock_summary':'stock','stock_report':'stock_serial',
 'stock__worth_report':'worth','item_history':'history','item_detail':'detail','items_last_purchasing':'last_purchase',
 'items_last_sale':'last_sale','serial_ledger':'serial','serial_ledger_with_sold_flag':'serial_flag',
 'serial_ledger_purchase_only':'serial_purchase','serial_ledger_sale_only':'serial_sale',
 'monthly_position_report':'position','monthly_income_report':'income',
}
REPORTS = {'accountsReports:'+name:(PAGES[key],False) for name,key in ACCOUNT_KEYS.items()}
REPORTS.update({'sales_reports:api_'+key:(PAGES[key],False) for key in (
 'summary','product_profitability','customer_profitability','sales_by_product','sales_by_customer','sale_wise','trend','invoice_register')})
REPORTS.update({'draft:pending_report':(PAGES['pending'],False),
 'owner_equity:get_owner_equity':(PAGES['owner_equity'],False),
 'month_close:get_overview':(PAGES['month_close'],False),'month_close:preview':(PAGES['month_close'],False)})
EXPORT_SOURCES = dict(REPORTS)
for name,kind in {'sale:get_sale':'sale','sale:get_sale_summary':'sale',
 'purchase:get_purchase':'purchase','purchase:get_purchase_summary':'purchase',
 'saleReturn:get_sale_return':'sale_return','saleReturn:get_sale_return_summary':'sale_return',
 'purchaseReturn:get_purchase_return':'purchase_return','purchaseReturn:get_purchase_return_summary':'purchase_return',
 'payments:get_payment':'payment','payments:get_old_payments':'payment','payments:get_payments_date_wise':'payment',
 'receipts:get_receipt':'receipt','receipts:get_old_receipts':'receipt','receipts:get_receipts_date_wise':'receipt',
 'contra:get_contra':'contra','contra:get_old_contras':'contra','contra:get_contras_date_wise':'contra',
 'draft:get_draft':'draft','draft:draft_summary':'draft','draft:get_draft_return':'draft_return','draft:draft_return_summary':'draft_return'}.items():
    EXPORT_SOURCES[name]=(DOCUMENTS[kind],True)
for name,kind in {'parties:parties_list':'party','items:items_list':'item'}.items():
    EXPORT_SOURCES[name]=(MASTERS[kind],False)
for name in ('user_year','user_day','team','watch'):
    EXPORT_SOURCES['activity:'+name]=(Target('Team Activity','/activity/',('view_team_activity',),feature='team_activity'),False)
# Dashboard JSON feeds refresh automatically; they are not user-run reports.
# They may still supply an authorized export receipt.
for name,feature,perm in (
 ('dash_sales_today','sales_overview','view_dash_sales_profit'),('dash_sales_chart','sales_overview','view_dash_sales_profit'),
 ('dash_low_stock','stock_overview','view_dash_stock_overview'),('dash_fast_moving','stock_overview','view_dash_stock_overview'),
 ('dash_stale_stock','stock_overview','view_dash_stock_overview'),('dash_recent_transactions','recent_transactions','view_dash_recent_transactions'),
 ('dash_top_customers','top_parties','view_dash_top_parties'),('dash_top_vendors','top_parties','view_dash_top_parties'),
 ('dash_expense_categories','expenses','view_dash_expense_tracking'),('dash_expense_descriptions','expenses','view_dash_expense_tracking'),
 ('dash_receivables_aging','receivables_aging','view_dash_receivables_aging')):
    EXPORT_SOURCES['home:'+name]=(Target('Dashboard','/home/',(perm,),feature='dashboard.'+feature),False)

# Successful JSON writes can also supply a receipt for the document just made.
from .work import DOCUMENTS as WRITES
for name,spec in WRITES.items():
    if spec[0] in DOCUMENTS: EXPORT_SOURCES[name]=(DOCUMENTS[spec[0]],True)
