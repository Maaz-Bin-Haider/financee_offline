"""
tenancy.features
================
Per-company feature flags, controlled from the admin panel.

Every module has a switch: the core modules (Dashboard and its widgets,
Sales, Purchases, both returns, Payments, Receipts, Contra, Items, Parties),
every report group and sub-report, the add-on modules (Draft Invoices and its
screens, Opening Stock, Opening Cash, Owner Equity, Month-End Close), PDF
generation, CSV/Excel export and document attachments. Disabled features
disappear from the tenant UI (sidebar links, dashboard widgets, in-page report
buttons, PDF/export buttons, attachment widget) and their URLs are blocked by
``TenantSchemaMiddleware``.

Storage: ``Company.disabled_features`` (public schema, JSON list of disabled
feature keys). A key is either a group (``"stock_reports"``) or
``"group.sub"`` (``"stock_reports.serial_ledger"``). Disabling a group disables
all of its sub-features regardless of their own keys. A key that is not in the
list is enabled, so the list is exactly what is switched off.

Defaults: a NEW company starts with ``default_disabled_features()`` — the
plan's default set, everything in ``DEFAULT_DISABLED_FEATURES`` switched off.
The defaults are written when the company is created (admin add form,
``provision_tenant``), never read at request time, so existing companies keep
exactly what they have. The model field keeps ``default=list`` on purpose:
changing it would need a migration, which the migration-history gates refuse.
The example "Company One" created on a fresh install keeps every feature.

No tenant SQL is involved: like subscription control, this is registry data.
"""

# ── Feature registry ────────────────────────────────────────────────────────
# group key -> {"label": ..., "subs": {sub key -> label}}. Groups without subs
# are single switches. Keep keys stable: they are persisted on Company rows.
# Order matters: the admin lists the switches in this order.
FEATURE_GROUPS = {
    # Core modules
    "dashboard": {
        "label": "Dashboard",
        "subs": {
            "sales_overview": "Sales & profit overview",
            "cash_balance": "Cash balance",
            "stock_overview": "Stock overview",
            "balances": "Party & item lists",
            "top_parties": "Top customers & vendors",
            "receivables_aging": "Receivables aging",
            "recent_transactions": "Recent transactions",
            "expenses": "Expense tracking",
            "smart_alerts": "Smart alerts",
        },
    },
    "sales": {"label": "Sales", "subs": {}},
    "sale_returns": {"label": "Sale Returns", "subs": {}},
    "purchases": {"label": "Purchases", "subs": {}},
    "purchase_returns": {"label": "Purchase Returns", "subs": {}},
    "payments": {"label": "Payments", "subs": {}},
    "receipts": {"label": "Receipts", "subs": {}},
    "contra": {"label": "Contra Entry", "subs": {}},
    "items": {"label": "Items", "subs": {}},
    "parties": {"label": "Parties", "subs": {}},
    # Reports
    "accounts_reports": {
        "label": "Accounts Reports",
        "subs": {
            # Key names follow the URLs; labels follow the UI buttons
            # (/detailed-ledger/ renders as "Party Ledger", /detailed-ledger2/
            # as "Detailed Ledger").
            "detailed_ledger": "Party Ledger",
            "detailed_ledger2": "Detailed Ledger",
            "cash_ledger": "Cash Ledger",
            "trial_balance": "Trial Balance",
            "accounts_receivable": "Accounts Receivable",
            "accounts_payable": "Accounts Payable",
        },
    },
    "stock_reports": {
        "label": "Stock Reports",
        "subs": {
            # Key names follow the URLs; labels follow the UI buttons
            # (/stock-summary/ renders as "Stock Report", /stock-report/ as
            # "Stock Serial Wise").
            "stock_summary": "Stock Report",
            "stock_report": "Stock Serial Wise",
            "serial_ledger": "Serial Ledger",
            "serial_ledger_sold_flag": "Serial Ledger Sold Flag",
            "serial_ledger_purchase_only": "Serial Ledger Purchase",
            "serial_ledger_sale_only": "Serial Ledger Sale",
            "item_history": "Item History",
            "item_detail": "Item Detail",
            "stock_worth": "Stock Worth Report",
            "item_last_purchase": "Item Last Purchase",
            "item_last_sale": "Items Last Sale",
        },
    },
    "monthly_reports": {
        "label": "Monthly Reports",
        "subs": {
            "monthly_position": "Company Position",
            "monthly_income": "Income Statement",
        },
    },
    "sales_reports": {
        "label": "Sales Reports",
        "subs": {
            "summary": "Sales Summary",
            "product_profitability": "Product Profitability",
            "customer_profitability": "Customer Profitability",
            "sales_by_product": "Sales by Product",
            "sales_by_customer": "Sales by Customer",
            "sale_wise": "Sale-wise Profit",
            "trend": "Sales Trend Dashboard",
            "invoice_register": "Invoice Register",
        },
    },
    # Add-on modules
    # Switching drafts off hides the screens, report and dashboard card only.
    # Serials already reserved on a draft stay protected by the tenant trigger.
    "draft_invoices": {
        "label": "Draft Invoices (Proforma)",
        "subs": {
            "drafts": "Draft Invoices",
            "confirm": "Confirm Draft",
            "returns": "Confirmed Draft Return",
            "pending_report": "Pending Drafts report",
            "dashboard_card": "Dashboard reservations card",
        },
    },
    "opening_stock": {"label": "Opening Stock", "subs": {}},
    "opening_cash": {"label": "Opening Cash (Set Opening)", "subs": {}},
    "owner_equity": {"label": "Owner Equity", "subs": {}},
    "month_close": {"label": "Month-End Close", "subs": {}},
    "spotlight": {"label": "Spotlight Search", "subs": {}},
    "team_activity": {"label": "Team Activity", "subs": {}},
    "report_email": {"label": "Report Email", "subs": {}},
    # Export & documents
    "pdf_export": {
        "label": "PDF generation",
        "subs": {
            "documents": "Document PDFs (sale, purchase, returns, draft proforma)",
            "reports": "Report PDFs & print (reports, owner equity, month close, dashboard)",
        },
    },
    "excel_export": {"label": "CSV / Excel export buttons", "subs": {}},
    "attachments": {"label": "Document attachments (image / PDF upload)", "subs": {}},
}

# Admin layout: every group appears in exactly one category, in this order.
FEATURE_CATEGORIES = (
    ("Core modules", (
        "dashboard", "sales", "sale_returns", "purchases", "purchase_returns",
        "payments", "receipts", "contra", "items", "parties",
    )),
    ("Reports", ("accounts_reports", "stock_reports", "monthly_reports", "sales_reports")),
    ("Add-on modules", (
        "draft_invoices", "opening_stock", "opening_cash", "owner_equity", "month_close", "report_email", "spotlight", "team_activity",
    )),
    ("Export & documents", ("pdf_export", "excel_export", "attachments")),
)

# ── Defaults for a newly created company ────────────────────────────────────
# Everything not listed here starts ON. A group listed here starts OFF with
# all its sub-features, which come on together when the group is enabled.
DEFAULT_DISABLED_FEATURES = frozenset({
    "accounts_reports.detailed_ledger2",
    "stock_reports.serial_ledger_sold_flag",
    "stock_reports.serial_ledger_purchase_only",
    "stock_reports.serial_ledger_sale_only",
    "stock_reports.item_detail",
    "stock_reports.item_last_purchase",
    "stock_reports.item_last_sale",
    "monthly_reports.monthly_position",
    "sales_reports",
    "draft_invoices",
    "opening_stock",
    "opening_cash",
    "owner_equity",
    "month_close",
    "excel_export",
    "attachments",
    "report_email",
    "spotlight",
    "team_activity",
})


def all_feature_keys():
    """Every valid key: groups plus group.sub."""
    keys = []
    for group, spec in FEATURE_GROUPS.items():
        keys.append(group)
        keys.extend(f"{group}.{sub}" for sub in spec["subs"])
    return keys


def default_disabled_features():
    """The disabled list a newly created company starts with, in registry order."""
    return [key for key in all_feature_keys() if key in DEFAULT_DISABLED_FEATURES]


def feature_on_by_default(key):
    """Whether a key starts enabled for a new company (ignoring its group)."""
    return key not in DEFAULT_DISABLED_FEATURES


# ── URL enforcement map ─────────────────────────────────────────────────────
# Exact paths are checked first: a page whose URL is also the prefix of its
# module's data endpoints (the Draft Invoices screen is "/draft/").
FEATURE_EXACT_PATHS = {
    "/draft/": "draft_invoices.drafts",
}

# request.path prefix -> feature key. The LONGEST matching prefix wins, so the
# order below is for reading only. Sub-report pages double as their own AJAX
# data endpoints (GET renders the shared template, POST returns JSON), so one
# prefix covers both. A key of None keeps a path reachable whatever is
# switched off: the shared pickers other modules' screens depend on.
#
# The dashboard page (/home/) is deliberately unmapped: every denial redirects
# there, so blocking it would loop. Its widgets are switched off in the
# template and their data endpoints below.
FEATURE_PATH_PREFIXES = (
    # Core modules
    ("/sale/", "sales"),
    ("/saleReturn/", "sale_returns"),
    ("/purchase/", "purchases"),
    ("/purchaseReturn/", "purchase_returns"),
    ("/payments/", "payments"),
    ("/receipts/", "receipts"),
    ("/contra/", "contra"),
    ("/items/", "items"),
    ("/parties/", "parties"),
    # Shared pickers: the party picker serves Sales, Purchases, both returns,
    # Payments, Receipts, Contra, Draft Invoices, Opening Stock and the
    # ledgers; the item picker serves Purchases, Opening Stock and Stock
    # Reports. They stay up when the Parties / Items screens are switched off.
    ("/parties/autocomplete-party", None),
    ("/items/autocomplete-item/", None),
    # Dashboard widget data
    ("/home/api/dash/sales/", "dashboard.sales_overview"),
    ("/home/api/cash/", "dashboard.cash_balance"),
    ("/home/api/dash/stock/", "dashboard.stock_overview"),
    ("/home/api/party-balances/", "dashboard.balances"),
    ("/home/api/parties/", "dashboard.balances"),
    ("/home/api/items/", "dashboard.balances"),
    ("/home/api/receivable/", "dashboard.balances"),
    ("/home/api/payable/", "dashboard.balances"),
    ("/home/api/expense-party-balances/", "dashboard.balances"),
    ("/home/api/dash/customers/", "dashboard.top_parties"),
    ("/home/api/dash/vendors/", "dashboard.top_parties"),
    ("/home/api/dash/receivables/", "dashboard.receivables_aging"),
    ("/home/api/dash/transactions/", "dashboard.recent_transactions"),
    ("/home/api/dash/expenses/", "dashboard.expenses"),
    ("/home/api/dash/alerts/", "dashboard.smart_alerts"),
    # Reports
    ("/accountsReports/detailed-ledger2/", "accounts_reports.detailed_ledger2"),
    ("/accountsReports/detailed-ledger/", "accounts_reports.detailed_ledger"),
    ("/accountsReports/cash-ledger/", "accounts_reports.cash_ledger"),
    ("/accountsReports/trial-balance/", "accounts_reports.trial_balance"),
    ("/accountsReports/accounts-receivable/", "accounts_reports.accounts_receivable"),
    ("/accountsReports/accounts-payable/", "accounts_reports.accounts_payable"),
    ("/accountsReports/stock-summary/", "stock_reports.stock_summary"),
    ("/accountsReports/stock-report/", "stock_reports.stock_report"),
    ("/accountsReports/serial-ledger-sold-flag/", "stock_reports.serial_ledger_sold_flag"),
    ("/accountsReports/serial-ledger-purchase-only/", "stock_reports.serial_ledger_purchase_only"),
    ("/accountsReports/serial-ledger-sale-only/", "stock_reports.serial_ledger_sale_only"),
    ("/accountsReports/serial-ledger/", "stock_reports.serial_ledger"),
    ("/accountsReports/item-history/", "stock_reports.item_history"),
    ("/accountsReports/item-detail/", "stock_reports.item_detail"),
    ("/accountsReports/stock-worth-report/", "stock_reports.stock_worth"),
    ("/accountsReports/item-last-purchase/", "stock_reports.item_last_purchase"),
    ("/accountsReports/item-last-sale/", "stock_reports.item_last_sale"),
    ("/accountsReports/monthly-position/", "monthly_reports.monthly_position"),
    ("/accountsReports/monthly-income/", "monthly_reports.monthly_income"),
    ("/sales-reports/api/summary/", "sales_reports.summary"),
    ("/sales-reports/api/product-profitability/", "sales_reports.product_profitability"),
    ("/sales-reports/api/customer-profitability/", "sales_reports.customer_profitability"),
    ("/sales-reports/api/sales-by-product/", "sales_reports.sales_by_product"),
    ("/sales-reports/api/sales-by-customer/", "sales_reports.sales_by_customer"),
    ("/sales-reports/api/sale-wise/", "sales_reports.sale_wise"),
    ("/sales-reports/api/trend/", "sales_reports.trend"),
    ("/sales-reports/api/invoice-register/", "sales_reports.invoice_register"),
    ("/sales-reports/", "sales_reports"),
    # Add-on modules
    ("/report-email/", "report_email"),
    ("/spotlight/", "spotlight"),
    ("/activity/", "team_activity"),
    ("/opening-stock/", "opening_stock"),
    ("/set-opening/", "opening_cash"),
    ("/owner-equity/", "owner_equity"),
    ("/month-close/", "month_close"),
    ("/draft/save/", "draft_invoices.drafts"),
    ("/draft/delete/", "draft_invoices.drafts"),
    ("/draft/release/", "draft_invoices.drafts"),
    ("/draft/cancel/", "draft_invoices.drafts"),
    ("/draft/serial/", "draft_invoices.drafts"),
    ("/draft/convert/", "draft_invoices.confirm"),
    ("/draft/return/", "draft_invoices.returns"),
    ("/draft/pending/", "draft_invoices.pending_report"),
    ("/home/api/dash/drafts/", "draft_invoices.dashboard_card"),
    # get/ and summary/ load a draft for both the Draft and Confirm screens.
    ("/draft/", "draft_invoices"),
    # Export & documents (PDF and CSV are generated in the browser and have no
    # URL; their switches only hide the buttons).
    ("/attachments/", "attachments"),
)

_PREFIXES_LONGEST_FIRST = tuple(
    sorted(FEATURE_PATH_PREFIXES, key=lambda entry: len(entry[0]), reverse=True)
)


def feature_for_path(path):
    """Feature key guarding this path, or None when the path is unrestricted."""
    # Recording a permitted export does not grant manager analytics access.
    if path == '/activity/record/': return None
    if path in FEATURE_EXACT_PATHS:
        return FEATURE_EXACT_PATHS[path]
    for prefix, key in _PREFIXES_LONGEST_FIRST:
        if path.startswith(prefix):
            return key
    return None


# ── Fallback pages ──────────────────────────────────────────────────────────
# When a user lands on a disabled sub-feature PAGE (plain GET) we redirect to
# the first enabled sibling of the same group instead of erroring, so sidebar
# entry points keep working when only some subs are disabled. The sidebar
# links each report group to this first enabled page too.
GROUP_LANDING_PATHS = {
    "accounts_reports": (
        ("cash_ledger", "/accountsReports/cash-ledger/"),
        ("detailed_ledger", "/accountsReports/detailed-ledger/"),
        ("detailed_ledger2", "/accountsReports/detailed-ledger2/"),
        ("trial_balance", "/accountsReports/trial-balance/"),
        ("accounts_receivable", "/accountsReports/accounts-receivable/"),
        ("accounts_payable", "/accountsReports/accounts-payable/"),
    ),
    "stock_reports": (
        ("stock_summary", "/accountsReports/stock-summary/"),
        ("stock_report", "/accountsReports/stock-report/"),
        ("serial_ledger", "/accountsReports/serial-ledger/"),
        ("serial_ledger_sold_flag", "/accountsReports/serial-ledger-sold-flag/"),
        ("serial_ledger_purchase_only", "/accountsReports/serial-ledger-purchase-only/"),
        ("serial_ledger_sale_only", "/accountsReports/serial-ledger-sale-only/"),
        ("item_history", "/accountsReports/item-history/"),
        ("item_detail", "/accountsReports/item-detail/"),
        ("stock_worth", "/accountsReports/stock-worth-report/"),
        ("item_last_purchase", "/accountsReports/item-last-purchase/"),
        ("item_last_sale", "/accountsReports/item-last-sale/"),
    ),
    "monthly_reports": (
        ("monthly_position", "/accountsReports/monthly-position/"),
        ("monthly_income", "/accountsReports/monthly-income/"),
    ),
    "draft_invoices": (
        ("drafts", "/draft/"),
        ("confirm", "/draft/convert/screen/"),
        ("returns", "/draft/return/screen/"),
        ("pending_report", "/draft/pending/screen/"),
    ),
}


def enabled_sibling_path(company, group):
    """First enabled sub-feature page of the group, or None."""
    for sub, path in GROUP_LANDING_PATHS.get(group, ()):
        if company.feature_enabled(f"{group}.{sub}"):
            return path
    return None


def features_map(company=None):
    """
    Nested {group: {"enabled", "applicable", "subs", "landing"}} for templates
    and the frontend. A group with sub-features counts as enabled only while
    at least one of them is on. ``landing`` is the first enabled page of a
    report group ("" when it has none). With no company (public pages, no
    membership) everything is enabled so shared screens render normally.
    """
    result = {}
    for group, spec in FEATURE_GROUPS.items():
        subs = {
            sub: (company.feature_enabled(f"{group}.{sub}") if company else True)
            for sub in spec["subs"]
        }
        group_on = company.feature_enabled(group) if company else True
        if subs:
            group_on = group_on and any(subs.values())
        if company:
            landing = enabled_sibling_path(company, group)
        else:
            landing = next(iter(GROUP_LANDING_PATHS.get(group, ())), (None, None))[1]
        result[group] = {
            # "enabled" must stay the first key: tests read the page JSON.
            "enabled": group_on,
            "applicable": True,
            "subs": subs,
            "landing": landing or "",
        }
    return result
