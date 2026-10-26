"""Explicit, bounded tenant import of approximate legacy attribution."""
# Trusted table/key/actor/date expressions only; no request or CLI identifier interpolation.
SOURCES = (
 ('sale','salesinvoices','sales_invoice_id','created_by','invoice_date'),
 ('purchase','purchaseinvoices','purchase_invoice_id','created_by','invoice_date'),
 ('sale_return','salesreturns','sales_return_id','created_by','return_date'),
 ('purchase_return','purchasereturns','purchase_return_id','created_by','return_date'),
 ('payment','payments','payment_id','created_by','payment_date'),
 ('receipt','receipts','receipt_id','created_by','receipt_date'),
 ('contra','contra_entries','contra_id','created_by','contra_date'),
 ('draft','draftinvoices','draft_invoice_id','created_by','draft_date'),
 ('draft_return','draftreturns','draft_return_id','created_by','date_created'),
 ('party','parties','party_id','created_by','date_created'),
 ('item','items','item_id','created_by','created_at'),
 ('owner_equity','owner_equity_transactions','txn_id','created_by_id','txn_date'),
 ('opening_cash','opening_cash','opening_cash_id','created_by_id','entry_date'),
 ('month_close','period_closes','close_id','closed_by_id','closed_at'),
)


def select_sql(spec):
    kind,table,key,actor,day = spec
    # Invoices lack a trustworthy creation instant; all imports use local noon
    # of the legacy business date and remain explicitly approximate.
    kind_sql="CASE WHEN d.is_opening THEN 'opening_stock' ELSE 'purchase' END" if kind=='purchase' else "'"+kind+"'"
    ordinary="AND d.draft_return_id IS NULL" if kind=='sale_return' else ''
    return f'''SELECT {kind_sql} AS kind, d.{key} AS record_id, d.{actor} AS user_id,
       u.username, (d.{day}::date + time '12:00') AT TIME ZONE %(tz)s AS at,
       d.{day}::date AS document_date,
       'backfill:{kind}:' || d.{key}::text AS dedupe_key
       FROM {table} d
       JOIN public.tenancy_membership m ON m.user_id=d.{actor} AND m.company_id=%(company)s
       JOIN public.auth_user u ON u.id=m.user_id
       WHERE d.{day} IS NOT NULL {ordinary}
       AND (d.{day}::date + time '12:00') AT TIME ZONE %(tz)s < %(cutoff)s
       AND NOT EXISTS(SELECT 1 FROM activity_events e WHERE e.kind={kind_sql} AND e.record_id=d.{key} AND e.source<>'backfill')'''
