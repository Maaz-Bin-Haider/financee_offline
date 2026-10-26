"""Spotlight capabilities mirror the target screen, never a broader search grant."""
from dataclasses import dataclass
from django.conf import settings
from tenancy.features import feature_for_path


@dataclass(frozen=True)
class Target:
    label: str
    path: str
    perms: tuple = ()
    feature: str = ''
    report: str = ''
    words: str = ''

    def allowed(self, request):
        company = getattr(request, 'tenant_company', None)
        feature = self.feature or feature_for_path(self.path)
        if not company or (feature and not company.feature_enabled(feature)):
            return False
        if any(perm.startswith('create_') for perm in self.perms) and request.user.groups.filter(name='view_only_users').exists():
            return False
        if self.path.startswith('/draft/'):
            if not settings.DRAFT_SALES_ENABLED or request.user.groups.filter(name='view_only_users').exists():
                return False
        if self.path.startswith('/activity/') and not settings.TEAM_ACTIVITY_ENABLED:
            return False
        if self.path.startswith('/report-email/') and not settings.REPORT_EMAIL_ENABLED:
            return False
        return all(request.user.has_perm('auth.' + perm) for perm in self.perms)


DOCUMENTS = {
    'sale': Target('Sale', '/sale/sales/', ('view_sale',)),
    'purchase': Target('Purchase', '/purchase/purchasing/', ('view_purchase',)),
    'payment': Target('Payment', '/payments/payment/', ('view_payment',)),
    'receipt': Target('Receipt', '/receipts/receipt/', ('view_receipt',)),
    'contra': Target('Contra Entry', '/contra/contra/', ('view_contra_entry',)),
    'sale_return': Target('Sale Return', '/saleReturn/create-sale-return/', ('view_sale_return',)),
    'purchase_return': Target('Purchase Return', '/purchaseReturn/create-purchase-return/', ('view_purchase_return',)),
    'draft': Target('Draft Invoice', '/draft/', ('view_draft_invoice',)),
    'draft_return': Target('Confirmed Draft Return', '/draft/return/screen/', ('view_draft_return',)),
}
MASTERS = {
    'party': Target('Parties', '/parties/parties-dash/', ('view_party',)),
    'item': Target('Items', '/items/items-dash/', ('view_item',)),
}
PAGES = {
    'home': Target('Dashboard', '/home/', words='home overview'),
    **DOCUMENTS, **MASTERS,
    'add_party': Target('Add Party', '/parties/add-new-party/', ('view_party', 'create_party'), words='new customer vendor'),
    'add_item': Target('Add Item', '/items/add-new-item/', ('view_item', 'create_item'), words='new product'),
    'confirm': Target('Confirm Draft', '/draft/convert/screen/', ('confirm_draft_invoice',)),
    'pending': Target('Pending Drafts', '/draft/pending/screen/', ('view_pending_drafts_report',)),
    'opening_stock': Target('Opening Stock', '/opening-stock/', ('view_opening_stock',)),
    'opening_cash': Target('Opening Cash', '/set-opening/', ('can_set_or_update_opening',)),
    'owner_equity': Target('Owner Equity', '/owner-equity/', ('can_manage_owner_equity',)),
    'month_close': Target('Month-End Close', '/month-close/', ('can_close_period',)),
    'team_activity': Target('Team Activity','/activity/',('view_team_activity',),feature='team_activity',words='team contributions work history'),
    'email': Target('Report Email', '/report-email/', ('send_reports', 'can_view_sale_wise_profit'),
                    feature='report_email', words='mail schedule recipients'),
}
# Actual report paths, target permissions, and the existing form selector key.
for key, label, route, perm, tab, group in (
    ('ledger', 'Party Ledger', 'detailed-ledger', 'view_detailed_ledger', 'ledger', 'accounts'),
    ('ledger2', 'Detailed Ledger', 'detailed-ledger2', 'view_detailed_ledger', 'ledger2', 'accounts'),
    ('cash', 'Cash Ledger', 'cash-ledger', 'view_cash_ledger', 'cash-ledger', 'accounts'),
    ('trial', 'Trial Balance', 'trial-balance', 'view_trial_balance', 'trial', 'accounts'),
    ('receivable', 'Accounts Receivable', 'accounts-receivable', 'view_receivable', 'receivable', 'accounts'),
    ('payable', 'Accounts Payable', 'accounts-payable', 'view_payable', 'payable', 'accounts'),
    ('stock', 'Stock Report', 'stock-summary', 'view_stock_summary', 'summary', 'stock'),
    ('stock_serial', 'Stock Serial Wise', 'stock-report', 'view_serial_wise_stock', 'stock', 'stock'),
    ('worth', 'Stock Worth', 'stock-worth-report', 'view_stock_worth_report', 'worth', 'stock'),
    ('history', 'Item History', 'item-history', 'view_item_history', 'history', 'stock'),
    ('detail', 'Item Detail', 'item-detail', 'view_item_detail', 'item-detail', 'stock'),
    ('serial', 'Serial Ledger', 'serial-ledger', 'view_serial_ledger', 'serial', 'stock'),
    ('serial_purchase', 'Serial Ledger Purchase', 'serial-ledger-purchase-only', 'view_serial_ledger_purchase_only', 'serial-purchase-only', 'stock'),
    ('serial_sale', 'Serial Ledger Sale', 'serial-ledger-sale-only', 'view_serial_ledger_sale_only', 'serial-sale-only', 'stock'),
    ('serial_flag', 'Serial Ledger Sold Flag', 'serial-ledger-sold-flag', 'view_last_purchasing', 'seril-ledger-with-sold-flag', 'stock'),
    ('last_purchase', 'Item Last Purchase', 'item-last-purchase', 'view_last_purchasing', 'item-last-purchase', 'stock'),
    ('last_sale', 'Items Last Sale', 'item-last-sale', 'view_last_sale', 'item-last-sale', 'stock'),
    ('position', 'Company Position', 'monthly-position', 'view_sale_wise_profit_report', 'position', 'monthly'),
    ('income', 'Income Statement', 'monthly-income', 'view_sale_wise_profit_report', 'income', 'monthly'),
):
    page_perm = ('view_accounts_reports_page',) if group == 'accounts' else ('view_stock_reports_page',) if group == 'stock' else ()
    PAGES[key] = Target(label, '/accountsReports/' + route + '/', page_perm + (perm,), report=tab,
                        words='tb balance' if key == 'trial' else '')
for key, label, perm in (
    ('summary', 'Sales Summary', 'sales_summary'),
    ('product_profitability', 'Product Profitability', 'product_profitability'),
    ('customer_profitability', 'Customer Profitability', 'customer_profitability'),
    ('sales_by_product', 'Sales by Product', 'sales_by_product'),
    ('sales_by_customer', 'Sales by Customer', 'sales_by_customer'),
    ('sale_wise', 'Sale-wise Profit', 'sale_wise_profit'),
    ('trend', 'Sales Trend', 'sales_trend'),
    ('invoice_register', 'Invoice Register', 'invoice_register'),
):
    PAGES[key] = Target(label, '/sales-reports/', ('can_view_' + perm,),
                        feature='sales_reports.' + key, report=key)

# Quick actions open forms only; the resolver checks target scope and uniqueness.
ACTIONS = {
    'sale': ('party', ('Customer', 'Both'), Target('New sale', '/sale/sales/', ('view_sale', 'create_sale'))),
    'purchase': ('party', ('Vendor', 'Both'), Target('New purchase', '/purchase/purchasing/', ('view_purchase', 'create_purchase'))),
    'payment': ('party', ('Customer', 'Vendor', 'Both', 'Expense'), Target('New payment', '/payments/payment/', ('view_payment', 'create_payment'))),
    'receipt': ('party', ('Customer', 'Vendor', 'Both', 'Expense'), Target('New receipt', '/receipts/receipt/', ('view_receipt', 'create_receipt'))),
    'draft': ('party', ('Customer', 'Both'), Target('New draft', '/draft/', ('view_draft_invoice', 'create_draft_invoice'))),
    'ledger': ('party', (), PAGES['ledger']),
    'history': ('item', (), PAGES['history']),
    'detail': ('item', (), PAGES['detail']),
}


def serial_access(request):
    bought = DOCUMENTS['purchase'].allowed(request) or any(PAGES[key].allowed(request) for key in ('serial', 'serial_purchase', 'serial_flag'))
    sold = DOCUMENTS['sale'].allowed(request) or any(PAGES[key].allowed(request) for key in ('serial', 'serial_sale'))
    reserved = DOCUMENTS['sale'].allowed(request) or DOCUMENTS['draft'].allowed(request) or PAGES['confirm'].allowed(request)
    search = bought or sold or any(DOCUMENTS[key].allowed(request) for key in ('sale_return', 'purchase_return', 'draft')) or PAGES['serial'].allowed(request)
    return dict(search=search, bought=bought, sold=sold, reserved=reserved)
