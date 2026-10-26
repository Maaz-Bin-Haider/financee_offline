"""Request-scoped, read-only Spotlight API. Membership alone selects the schema."""
import json
import re
from functools import wraps
from urllib.parse import urlencode
from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.utils.crypto import salted_hmac, constant_time_compare
from django.views.decorators.http import require_GET
from financee.security import rate_limit_response
from . import policy, queries


def scope(request):
    company = getattr(request, 'tenant_company', None)
    identity = f'{request.user.pk}:{getattr(company, "pk", "")}:{request.session.session_key}'
    return salted_hmac('spotlight.session', identity).hexdigest()


def enabled(request):
    company = getattr(request, 'tenant_company', None)
    return bool(request.user.is_authenticated and request.user.is_active and company
                and getattr(request, 'tenant_is_active', False) and company.is_active
                and company.feature_enabled('spotlight')
                and company.subscription_state() not in ('blocked', 'suspended'))


def guarded(view):
    @wraps(view)
    @require_GET
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'message': 'Sign in again to search.'}, status=401)
        if not enabled(request):
            return JsonResponse({'message': 'Search is unavailable for this company.'}, status=403)
        offered = request.headers.get('X-Spotlight-Scope')
        if offered and not constant_time_compare(offered, scope(request)):
            return JsonResponse({'message': 'Your session changed. Reload this page.'}, status=409)
        limited = rate_limit_response(request, 'spotlight', limit=180, window=60)
        if limited is not None:
            return limited
        try:
            # Bound substring scans as well as returned rows; reset at transaction end.
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '1500ms'")
                response = view(request, *args, **kwargs)
        except DatabaseError:
            response = JsonResponse({'message': 'Search took too long. Try a more specific query.'}, status=503)
        except ValueError as exc:
            response = JsonResponse({'message': str(exc)}, status=400)
        response['Cache-Control'] = 'private, no-store'
        response['X-Spotlight-Scope'] = scope(request)
        return response
    return wrapped


def link(target, params=None):
    params = dict(params or {})
    if target.report:
        params['report'] = target.report
    return target.path + ('?' + urlencode(params) if params else '')


def page_row(key, target):
    return dict(kind='page', id=key, name=target.label, meta='Pages & reports', href=link(target))


def allowed_kind(request, kind):
    if kind == 'serial':
        return policy.serial_access(request)['search']
    target = policy.MASTERS.get(kind) or policy.DOCUMENTS.get(kind)
    return bool(target and target.allowed(request))


def serial_row(request, row):
    details = queries.fetch('SELECT * FROM get_serial_number_details(%s)', [row['name']])
    if not details:
        return None
    detail = details[0]
    access = policy.serial_access(request)
    row['meta'] = ' · '.join(str(detail[key] or '') for key in ('item_name', 'brand') if detail[key])
    row['state'] = 'In stock' if detail['in_stock'] else 'Out of stock'
    if access['bought']:
        row['bought'] = {key: detail[key] for key in ('vendor_name', 'purchase_price', 'purchase_date', 'purchase_invoice_id')}
    if not detail['in_stock'] and detail['current_status'] == 'Sold':
        row['state'] = 'Sold'
    elif not detail['in_stock'] and queries.fetch('SELECT EXISTS(SELECT 1 FROM purchasereturnitems WHERE serial_number=%s) AS returned', [row['name']])[0]['returned']:
        row['state'] = 'Returned to vendor'
    if access['sold'] and not detail['in_stock'] and detail['current_status'] == 'Sold':
        row['sold'] = {key: detail[key] for key in ('customer_name', 'sold_price', 'sale_date', 'sales_invoice_id')}
    if access['reserved'] and detail['is_reserved']:
        row['state'] = 'Reserved'
        row['reserved'] = {key: detail[key] for key in ('reserved_for', 'reserved_draft_id')}
    row['href'] = ''
    if policy.PAGES['serial'].allowed(request):
        row['href'] = link(policy.PAGES['serial'], {'serial': row['name']})
    elif policy.DOCUMENTS['sale'].allowed(request) and detail['sales_invoice_id']:
        row['href'] = link(policy.DOCUMENTS['sale'], {'open': detail['sales_invoice_id']})
    elif policy.DOCUMENTS['purchase'].allowed(request):
        row['href'] = link(policy.DOCUMENTS['purchase'], {'open': detail['purchase_invoice_id']})
    return row


def decorate(request, kind, row):
    row['kind'] = kind
    if kind == 'serial':
        return serial_row(request, row)
    target = policy.MASTERS.get(kind) or policy.DOCUMENTS.get(kind)
    row['href'] = link(target, {kind if kind in policy.MASTERS else 'open': row['id']})
    if kind in policy.DOCUMENTS:
        row['name'] = f'{target.label} #{row["id"]}'
        row['meta'] = ' · '.join(str(row[key] or '') for key in ('date', 'party', 'reference', 'description') if row.get(key))[:240]
    return row



def add_facts(request, kind, rows):
    """Use the same report functions as the target screens, after authorization."""
    if kind == 'party' and (any(policy.DOCUMENTS[key].allowed(request) for key in ('payment', 'receipt', 'contra'))
                            or any(policy.PAGES[key].allowed(request) for key in ('ledger', 'ledger2'))):
        for row in rows:
            # Legacy balance-by-name has ILIKE semantics; escape literal names,
            # and never collapse same-name rows into a misleading single balance.
            matches = queries.fetch('SELECT count(*) AS n FROM parties WHERE lower(party_name)=lower(%s)', [row['name']])[0]['n']
            if matches != 1:
                continue
            data = queries.fetch('SELECT get_party_balance_by_name(%s) AS data', [queries.escaped(row['name'])])[0]['data']
            if isinstance(data, str):
                data = json.loads(data)
            if data and data.get('found'):
                row['balance'] = str(data['balance'])
    if kind == 'item' and any(policy.PAGES[key].allowed(request) for key in ('stock', 'detail')) and rows:
        ids = [queries.record_id(row['id']) for row in rows]
        stock = {str(value['item_id']): value for value in queries.fetch(
            'SELECT item_id, quantity_in_stock, reserved_on_drafts FROM stock_summary() WHERE item_id=ANY(%s)', [ids])}
        reserved = policy.serial_access(request)['reserved']
        for row in rows:
            value = stock.get(row['id'])
            if value:
                row['in_stock'] = value['quantity_in_stock']
                if reserved:
                    row['reserved_units'] = value['reserved_on_drafts']
    return rows


def record_summary(request, kind, ident):
    if not allowed_kind(request, kind):
        return None
    if kind == 'serial':
        rows = queries.fetch("SELECT unit_id::text AS id, serial_number AS name FROM purchaseunits WHERE unit_id=%s", [ident])
        return decorate(request, kind, rows[0]) if rows else None
    if kind in policy.MASTERS:
        record = queries.master(kind, ident)
        if not record:
            return None
        row = decorate(request, kind, dict(id=str(ident), name=record[kind + '_name'], meta=record.get('party_type', record.get('brand', ''))))
        return add_facts(request, kind, [row])[0]
    # ID filter is numeric/exact and remains inside the selected tenant.
    return next((decorate(request, kind, row) for row in queries.search(kind, str(ident)) if row['id'] == str(ident)), None)


def action_record(request, action, ident):
    spec = policy.ACTIONS.get(action)
    if not spec or not spec[2].allowed(request):
        return None
    kind, types, target = spec
    record = queries.master(kind, ident)
    if not record or (kind == 'party' and types and (record['is_cash'] or record['party_type'] not in types)):
        return None
    # Existing forms save a name. Refuse ambiguity instead of silently picking
    # another record; master links themselves always use the ID resolver.
    table, name = ('parties', 'party_name') if kind == 'party' else ('items', 'item_name')
    count = queries.fetch(f'SELECT count(*) AS n FROM {table} WHERE lower({name})=lower(%s)', [record[name]])[0]['n']
    if count != 1 or any(char in record[name] for char in ('%', '_', '\\')):
        return None
    return dict(kind='action', id=action + ':' + str(ident), action=action, record=record,
                name=target.label + ' · ' + record[name], meta='Quick actions',
                href=link(target, {kind: ident, 'sp_action': action}))


@guarded
def search(request):
    text = ' '.join(request.GET.get('q', '')[:150].split())
    offset_raw = request.GET.get('offset', '0')
    if not offset_raw.isascii() or not offset_raw.isdigit() or int(offset_raw) > 600:
        raise ValueError('Invalid result offset.')
    offset = int(offset_raw)
    selected = request.GET.get('kind', '')
    if selected and selected not in (*policy.MASTERS, *policy.DOCUMENTS, 'serial'):
        raise ValueError('Unknown result group.')
    groups = []
    pages = [page_row(key, target) for key, target in policy.PAGES.items() if target.allowed(request)
             and all(token in (target.label + ' ' + target.words).lower() for token in text.lower().split())]
    if not selected:
        groups.append(dict(key='pages', title='Pages & reports', results=pages[:12], next=None))
    if len(text) >= 2 or re.fullmatch(r'[1-9]', text):
        # A typed kind + number ("sale 12", "purchase return 3") disambiguates.
        aliases = {'sale': 'sale', 'sales': 'sale', 'purchase': 'purchase', 'payment': 'payment',
                   'receipt': 'receipt', 'contra': 'contra', 'draft': 'draft', 'sale return': 'sale_return',
                   'purchase return': 'purchase_return', 'draft return': 'draft_return'}
        aliases.update({'sales':'sale','purchases':'purchase','payments':'payment','receipts':'receipt','invoice':'sale','pur':'purchase','sr':'sale_return','pr':'purchase_return','pmt':'payment','rct':'receipt','con':'contra'})
        exact = re.fullmatch(r'([a-z ]+?)\s*[#-]?\s*([1-9][0-9]{0,15})', text.lower())
        named = aliases.get(exact[1].strip()) if exact else None
        numeric = text.removeprefix('#') if text.removeprefix('#').isdigit() else text
        kinds = [selected] if selected else [*policy.MASTERS, 'serial', *policy.DOCUMENTS]
        for kind in kinds:
            if not allowed_kind(request, kind) or (named and kind != named) or (kind == 'serial' and len(text) < 2):
                continue
            rows = queries.search(kind, exact[2] if named else numeric if kind in policy.DOCUMENTS else text, offset)
            shown = [result for row in rows[:queries.LIMIT] if (result := decorate(request, kind, row))]
            if shown:
                add_facts(request, kind, shown)
                groups.append(dict(key=kind, title=policy.MASTERS[kind].label if kind in policy.MASTERS else
                                   'Serials' if kind == 'serial' else policy.DOCUMENTS[kind].label + 's',
                                   results=shown, next=offset + queries.LIMIT if len(rows) > queries.LIMIT and offset + queries.LIMIT <= 600 else None))
        if not selected:
            actions = []
            for group in groups:
                if group['key'] not in policy.MASTERS:
                    continue
                for row in group['results'][:2]:
                    for action, spec in policy.ACTIONS.items():
                        if spec[0] == group['key']:
                            value = action_record(request, action, queries.record_id(row['id']))
                            if value:
                                value.pop('record')
                                actions.append(value)
            if actions:
                groups.append(dict(key='actions', title='Quick actions', results=actions[:8], next=None))
    elif not text and not selected:
        recents = []
        for token in request.GET.get('recent', '')[:1200].split(',')[:10]:
            kind, sep, raw = token.partition(':')
            try:
                if kind == 'page':
                    target = policy.PAGES.get(raw)
                    value = page_row(raw, target) if target and target.allowed(request) else None
                elif kind in (*policy.MASTERS, *policy.DOCUMENTS, 'serial'):
                    value = record_summary(request, kind, queries.record_id(raw))
                else:
                    value = None
            except ValueError:
                value = None
            if value:
                recents.append(value)
        if recents:
            groups.insert(0, dict(key='recent', title='Recently opened', results=recents, next=None))
    return JsonResponse(dict(scope=scope(request), groups=groups))


@guarded
def resolve(request):
    kind, raw = request.GET.get('kind', ''), request.GET.get('id', '')
    if kind == 'page':
        target = policy.PAGES.get(raw)
        if not target or not target.allowed(request):
            return JsonResponse({'message': 'This page is unavailable.'}, status=403)
        return JsonResponse(page_row(raw, target))
    if kind == 'action':
        value = action_record(request, request.GET.get('action', ''), queries.record_id(raw))
        if not value:
            return JsonResponse({'message': 'This action is unavailable.'}, status=403)
        return JsonResponse(value)
    if not allowed_kind(request, kind):
        return JsonResponse({'message': 'This record is unavailable.'}, status=403)
    ident = queries.record_id(raw)
    summary = record_summary(request, kind, ident)
    if not summary:
        return JsonResponse({'message': 'This record is no longer available.'}, status=404)
    if kind in policy.MASTERS:
        summary['record'] = queries.master(kind, ident)
    return JsonResponse(summary)
