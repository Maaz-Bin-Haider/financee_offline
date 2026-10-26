"""Successful JSON mutations only; the existing SQL/serial implementations stay intact."""
from django.db import connection, transaction
from .recorder import as_id, record

# kind, source table, key, date column, request identifier
DOCUMENTS = {
    'sale:sales': ('sale','salesinvoices','sales_invoice_id','invoice_date','sale_id'),
    'purchase:purchasing': ('purchase','purchaseinvoices','purchase_invoice_id','invoice_date','purchase_id'),
    'saleReturn:create_sale_return': ('sale_return','salesreturns','sales_return_id','return_date','return_id'),
    'purchaseReturn:create_purchase_return': ('purchase_return','purchasereturns','purchase_return_id','return_date','return_id'),
    'parties:add_new_party': ('party','parties','party_id','date_created','party_id'),
    'parties:update_party': ('party','parties','party_id','date_created','party_id'),
    'items:add_new_item': ('item','items','item_id','created_at','item_id'),
    'items:update_item': ('item','items','item_id','created_at','item_id'),
    'draft:save_draft': ('draft','draftinvoices','draft_invoice_id','draft_date','draft_invoice_id'),
    'draft:delete_draft': ('draft','draftinvoices','draft_invoice_id','draft_date','draft_invoice_id'),
    'draft:release_units': ('draft','draftinvoices','draft_invoice_id','draft_date','draft_invoice_id'),
    'draft:cancel_draft': ('draft','draftinvoices','draft_invoice_id','draft_date','draft_invoice_id'),
    'draft:convert_draft': ('draft','draftinvoices','draft_invoice_id','draft_date','draft_invoice_id'),
    'draft:save_draft_return': ('draft_return','draftreturns','draft_return_id','date_created','draft_return_id'),
    'draft:delete_draft_return': ('draft_return','draftreturns','draft_return_id','date_created','draft_return_id'),
}
NOUNS = {'sale':'Sale','purchase':'Purchase','sale_return':'Sale return','purchase_return':'Purchase return',
         'party':'Party','item':'Item','draft':'Draft','draft_return':'Confirmed draft return'}


def observe(request, payload, result):
    name = request.resolver_match.view_name
    spec = DOCUMENTS.get(name)
    if not spec or request.method != 'POST' or not isinstance(result,dict): return
    if result.get('success') is not True and result.get('status') != 'success': return
    kind,table,key,date_key,input_key = spec
    action = payload.get('action')
    ident = as_id(payload.get(input_key))
    if name.startswith(('items:','parties:')):
        action = 'update' if ':update_' in name else 'create'
    elif name.startswith('draft:'):
        tail = name.split(':')[1]
        action = {'delete_draft':'delete','delete_draft_return':'delete','release_units':'release','cancel_draft':'cancel','convert_draft':'convert'}.get(tail)
        if action is None: action = 'create' if result.get('created') else 'update'
    elif action in ('submit','save'):
        action = 'update' if ident else 'create'
    if action not in ('create','update','delete','convert','cancel','release'): return
    if action == 'release' and not result.get('released'): return
    with transaction.atomic():
        with connection.cursor() as cur:
            if action == 'create':
                ident = as_id(result.get(key) or result.get(input_key))
                if ident is None:
                    # The same thread-local PostgreSQL session executed the creation.
                    # currval for this precise schema/table sequence cannot race another
                    # user's creation and avoids a dangerous global max(id) lookup.
                    cur.execute('SELECT currval(pg_get_serial_sequence(%s,%s))', [table,key])
                    ident = as_id(cur.fetchone()[0])
            doc_date = None
            if ident and action != 'delete':
                if kind == 'draft_return':
                    cur.execute('SELECT r.return_date FROM draftreturns d JOIN salesreturns r ON r.sales_return_id=d.sales_return_id WHERE d.draft_return_id=%s',[ident])
                else:
                    cur.execute(f'SELECT {date_key}::date FROM {table} WHERE {key}=%s', [ident])
                row = cur.fetchone()
                if not row: return
                doc_date = row[0]
    label = NOUNS[kind] + (f' #{ident}' if ident else '')
    if action == 'convert' and as_id(result.get('sales_invoice_id')):
        label += f" to Sale #{as_id(result['sales_invoice_id'])}"
    record(request,action,kind,ident,label,document_date=doc_date)


EXTRAS = {
    'opening_stock:create': ('opening_stock','create','opening_stock_id'),
    'opening_stock:delete': ('opening_stock','delete','id'),
    'opening_stock:reclassify': ('opening_stock','update',None),
    'set_opening:set_opening_cash': ('opening_cash','update',None),
    'owner_equity:add_owner_equity': ('owner_equity','create','txn_id'),
    'owner_equity:delete_owner_equity': ('owner_equity','delete','txn_id'),
    'month_close:close_month': ('month_close','create',None),
    'month_close:reverse_month': ('month_close','delete',None),
}


def observe_extra(request,payload,result):
    spec = EXTRAS.get(request.resolver_match.view_name)
    if not spec or request.method != 'POST' or not isinstance(result,dict) or result.get('status') != 'success': return
    inner = result.get('result')
    if isinstance(inner,dict) and inner.get('status') not in (None,'success'): return
    kind,action,key = spec
    inner = inner if isinstance(inner,dict) else result
    ident = as_id(inner.get(key) or payload.get(key)) if key else None
    label = kind.replace('_',' ').title() + (f' #{ident}' if ident else '')
    if kind == 'month_close':
        # These are validated by the successful source operation, not actor inputs.
        label += f" · {int(payload['year']):04d}-{int(payload['month']):02d}"
    record(request,action,kind,ident,label)


CASH = {
 'payments:payment':('payment','payments','payment_id','payment_date','current_id'),
 'receipts:receipt':('receipt','receipts','receipt_id','receipt_date','current_id'),
 'contra:contra':('contra','contra_entries','contra_id','contra_date','current_id'),
}


def capture_document_date(request,payload):
    spec=DOCUMENTS.get(request.resolver_match.view_name) or CASH.get(request.resolver_match.view_name)
    if not spec:return
    kind,table,key,day,input_key=spec
    ident=as_id(payload.get(input_key))
    if not ident:return
    with transaction.atomic(),connection.cursor() as cur:
        if kind=='draft_return':
            cur.execute('SELECT r.return_date FROM draftreturns d JOIN salesreturns r ON r.sales_return_id=d.sales_return_id WHERE d.draft_return_id=%s',[ident])
        else:cur.execute(f'SELECT {day}::date FROM {table} WHERE {key}=%s',[ident])
        row=cur.fetchone()
        if row:
            request.activity_document=(kind,ident)
            request.activity_document_date=row[0]
