"""Fixed, parameterized read queries. No posting functions or financial calculations."""
import re
from django.db import connection

LIMIT = 6
MAX_ID = 9007199254740991


def record_id(raw):
    text = str(raw or '')
    if not re.fullmatch(r'[1-9][0-9]{0,15}', text) or int(text) > MAX_ID:
        raise ValueError('A positive record ID is required.')
    return int(text)


def escaped(text):
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def fetch(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        names = [col[0] for col in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


# Identifiers below are internal constants; request values are always parameters.
DOC_SQL = {
    'sale': ('salesinvoices', 'sales_invoice_id', 'customer_id', 'invoice_date', 'total_amount', 'TRUE'),
    'purchase': ('purchaseinvoices', 'purchase_invoice_id', 'vendor_id', 'invoice_date', 'total_amount', 'TRUE'),
    'payment': ('payments', 'payment_id', 'party_id', 'payment_date', 'amount', 'TRUE'),
    'receipt': ('receipts', 'receipt_id', 'party_id', 'receipt_date', 'amount', 'TRUE'),
    'contra': ('contra_entries', 'contra_id', 'from_party_id', 'contra_date', 'amount', 'TRUE'),
    'sale_return': ('salesreturns', 'sales_return_id', 'customer_id', 'return_date', 'total_amount', 'd.draft_return_id IS NULL'),
    'purchase_return': ('purchasereturns', 'purchase_return_id', 'vendor_id', 'return_date', 'total_amount', 'TRUE'),
    'draft': ('draftinvoices', 'draft_invoice_id', 'customer_id', 'draft_date', 'NULL::numeric', 'TRUE'),
    'draft_return': ('draftreturns', 'draft_return_id', 'customer_id', 'return_date', 'total_amount', 'TRUE'),
}


def search(kind, text, offset=0):
    like = '%' + escaped(text.lower()) + '%'
    prefix = escaped(text.lower()) + '%'
    number = int(text) if re.fullmatch(r'[1-9][0-9]{0,15}', text) and int(text) <= MAX_ID else -1
    if kind in ('party', 'item'):
        table, pk, name, meta = ('parties', 'party_id', 'party_name', 'party_type') if kind == 'party' else ('items', 'item_id', 'item_name', "concat_ws(' · ',brand,category,item_code)")
        fields = name if kind == 'party' else "concat_ws(' ',item_name,item_code,brand,category)"
        tokens = text.lower().split()[:8]
        predicate = ' AND '.join(f"lower({fields}) LIKE %s ESCAPE '\\'" for _ in tokens)
        return fetch(f"SELECT {pk}::text AS id, {name} AS name, {meta} AS meta FROM {table} "
                     f"WHERE ({predicate}) OR {pk}=%s "
                     f"ORDER BY ({pk}=%s) DESC, (lower({name})=%s) DESC, (lower({name}) LIKE %s ESCAPE '\\') DESC, lower({name}), {pk} "
                     'LIMIT %s OFFSET %s', ['%' + escaped(token) + '%' for token in tokens] +
                     [number, number, text.lower(), prefix, LIMIT + 1, offset])
    if kind == 'serial':
        return fetch("SELECT unit_id::text AS id, serial_number AS name, '' AS meta FROM purchaseunits "
                     "WHERE lower(serial_number) LIKE %s ESCAPE '\\' ORDER BY (lower(serial_number)=%s) DESC, serial_number, unit_id LIMIT %s OFFSET %s",
                     [like, text.lower(), LIMIT + 1, offset])
    table, pk, party, day, amount, where = DOC_SQL[kind]
    # Draft returns keep their customer on the underlying ordinary return.
    joins = ' JOIN salesreturns sr ON sr.sales_return_id=d.sales_return_id' if kind == 'draft_return' else ''
    party = 'sr.customer_id' if kind == 'draft_return' else 'd.' + party
    day = 'return_date' if kind == 'draft_return' else day
    date_sql = 'sr.return_date' if kind == 'draft_return' else 'd.' + day
    desc_sql = 'sr.description' if kind == 'draft_return' else 'd.description'
    amount = 'sr.total_amount' if kind == 'draft_return' else 'd.' + amount if amount != 'NULL::numeric' else amount
    reference = 'd.reference_no' if kind in ('payment', 'receipt', 'contra') else "''::text"
    to_join = ' JOIN parties pto ON pto.party_id=d.to_party_id' if kind == 'contra' else ''
    party_sql = "concat_ws(' → ',p.party_name,pto.party_name)" if kind == 'contra' else 'p.party_name'
    columns = (f"SELECT d.{pk}::text AS id, {party_sql} AS party, {date_sql} AS date, {amount}::text AS amount, "
               f"coalesce({desc_sql},'') AS description, {reference} AS reference FROM {table} d {joins} {to_join} JOIN parties p ON p.party_id={party} ")
    if number > 0:
        # Numeric document lookups use the existing tenant primary-key index.
        return fetch(columns + f"WHERE ({where}) AND d.{pk}=%s", [number])
    fields = f"concat_ws(' ',{party_sql},{desc_sql},{reference},{date_sql}::text)"
    tokens = text.lower().split()[:8]
    predicate = ' AND '.join(f"lower({fields}) LIKE %s ESCAPE '\\'" for _ in tokens)
    return fetch(columns + f"WHERE ({where}) AND ({predicate}) "
                 f"ORDER BY {date_sql} DESC, d.{pk} DESC LIMIT %s OFFSET %s",
                 ['%' + escaped(token) + '%' for token in tokens] + [LIMIT + 1, offset])



def master(kind, ident):
    if kind == 'party':
        rows = fetch('SELECT party_id, party_name, party_type, contact_info, address, opening_balance, balance_type, is_cash FROM parties WHERE party_id=%s', [ident])
    else:
        rows = fetch('SELECT item_id, item_name, storage, sale_price, item_code, category, brand FROM items WHERE item_id=%s', [ident])
    return rows[0] if rows else None
