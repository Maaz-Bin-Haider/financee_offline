# Generated from the exact authentication 0001-0025 history with Django 6.0.6.
"""First-release serial-only replacement for the authentication history.

The original migration files remain beside this replacement during checkpoint
4A. Existing installations that already applied them perform no operations.
Fresh installations execute this migration and create only permissions used by
the serial application; the retired quantity-company permissions are excluded.
"""

from django.db import migrations


SERIAL_PERMISSIONS = (
    ("create_payment", "Can create payment"),
    ("update_payment", "Can update payment"),
    ("delete_payment", "Can delete payment"),
    ("view_payment", "Can view payment"),
    ("create_receipt", "Can create receipt"),
    ("update_receipt", "Can update receipt"),
    ("delete_receipt", "Can delete receipt"),
    ("view_receipt", "Can view receipt"),
    ("create_purchase", "Can create purchase"),
    ("update_purchase", "Can update purchase"),
    ("delete_purchase", "Can delete purchase"),
    ("view_purchase", "Can view purchase"),
    ("create_sale", "Can create sale"),
    ("update_sale", "Can update sale"),
    ("delete_sale", "Can delete sale"),
    ("view_sale", "Can view sale"),
    ("create_purchase_return", "Can create purchase_return"),
    ("update_purchase_return", "Can update purchase_return"),
    ("delete_purchase_return", "Can delete purchase_return"),
    ("view_purchase_return", "Can view purchase_return"),
    ("create_sale_return", "Can create sale_return"),
    ("update_sale_return", "Can update sale_return"),
    ("delete_sale_return", "Can delete sale_return"),
    ("view_sale_return", "Can view sale_return"),
    ("create_item", "Can create item"),
    ("update_item", "Can update item"),
    ("view_item", "Can view item"),
    ("create_party", "Can create party"),
    ("update_party", "Can update party"),
    ("view_party", "Can view party"),
    ("view_accounts_reports_page", "Can view Accounts Reports Page"),
    ("view_detailed_ledger", "Can open detailed party ledgers"),
    ("view_trial_balance", "Can open trial balance"),
    ("view_serial_ledger", "Can Open Serial Ledger"),
    ("view_stock_summary", "Can open stock summary"),
    ("view_serial_wise_stock", "Can open serial wise stock"),
    ("view_item_history", "Can open item history report"),
    ("view_sale_wise_profit_report", "Can Open Sale-wise Profit Report"),
    ("view_company_valuation", "Can see Company valuation"),
    ("view_stock_reports_page", "Can view Stock reports page"),
    ("view_stock_worth_report", "Can see stock worth report"),
    ("view_item_detail", "Can see particular item detail"),
    ("view_last_purchasing", "Can see last purchasing of all items"),
    ("view_last_sale", "Can see last sale price for all items"),
    ("view_cash_ledger", "Can view cash detailed ledger"),
    ("view_full_party_balance", "Can view full party balance"),
    ("view_receivable", "Can view accounts receivable"),
    ("view_payable", "Can view accounts payable"),
    ("view_serial_ledger_purchase_only", "Can view serial ledger for purchase only"),
    ("view_serial_ledger_sale_only", "Can view serial ledger for sale only"),
    ("view_dash_sales_profit", "Can view dashboard sales & profit section"),
    ("view_dash_stock_overview", "Can view dashboard stock overview section"),
    ("view_dash_top_parties", "Can view dashboard top customers & vendors"),
    ("view_dash_receivables_aging", "Can view dashboard receivables aging"),
    ("view_dash_recent_transactions", "Can view dashboard recent transactions"),
    ("view_dash_expense_tracking", "Can view dashboard expense tracking"),
    ("view_dash_smart_alerts", "Can view dashboard smart alerts"),
    ("can_set_or_update_opening", "Can set or update opening"),
    ("can_manage_owner_equity", "Can manage owner equity"),
    ("can_close_period", "Can close accounting periods (month-end close)"),
    ("can_view_sales_summary", "Can view Sales Summary report"),
    ("can_view_product_profitability", "Can view Product Profitability report"),
    ("can_view_customer_profitability", "Can view Customer Profitability report"),
    ("can_view_sales_by_product", "Can view Sales by Product report"),
    ("can_view_sales_by_customer", "Can view Sales by Customer report"),
    ("can_view_sale_wise_profit", "Can view Sale-wise Profit report"),
    ("can_view_sales_trend", "Can view Sales Trend Dashboard"),
    ("can_view_invoice_register", "Can view Invoice Register"),
    ("view_contra_entry", "Can view Contra Entry section"),
    ("create_contra_entry", "Can create contra entries"),
    ("update_contra_entry", "Can update contra entries"),
    ("delete_contra_entry", "Can delete contra entries"),
    ("view_opening_stock", "Can view Opening Stock section"),
    ("create_opening_stock", "Can add opening stock"),
    ("delete_opening_stock", "Can delete opening stock"),
    ("reclassify_opening_balance", "Can reclassify Opening Balance to Capital"),
)


def add_serial_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="auth",
        model="user",
    )
    for codename, name in SERIAL_PERMISSIONS:
        Permission.objects.get_or_create(
            codename=codename,
            name=name,
            content_type=content_type,
        )


class Migration(migrations.Migration):
    # Checkpoint 4B: see tenancy/migrations/0001_serial_only.py. `replaces` is
    # removed and the replaced files are deleted; this is now an ordinary
    # initial migration.

    initial = True

    dependencies = [
        ("auth", "__latest__"),
        ("contenttypes", "__latest__"),
    ]

    operations = [
        migrations.RunPython(
            add_serial_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
