"""Best-effort tenant recording. No request field can select an actor or schema."""
import ipaddress
import logging
import re
from django.conf import settings
from django.db import connection, transaction
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
ACTIONS = frozenset(('create','update','delete','convert','cancel','release','run','export','sign_in','sign_out','sign_in_failed'))
KINDS = frozenset(('sale','purchase','sale_return','purchase_return','payment','receipt','contra','draft','draft_return','party','item','opening_stock','opening_cash','owner_equity','month_close','report','session'))
SESSION_ACTIONS = ('sign_in','sign_out','sign_in_failed')


def as_id(value):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9][0-9]{0,17}', str(value or '')):
        return None
    return int(value)


def plain(value):
    return ' '.join(str(value or '').split())[:200]


def client_ip(request):
    # Use the connection address; do not trust arbitrary forwarded headers.
    try:
        return str(ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')))
    except (ValueError, AttributeError):
        return None


def record(request, action, kind, record_id=None, label='', *, user=None,
           source='live', dedupe_key=None, repeat_seconds=0, document_date=None, ip=None):
    if not settings.TEAM_ACTIVITY_RECORDING_ENABLED or action not in ACTIONS or kind not in KINDS or source not in ('live','browser'):
        return False
    user = user if user is not None else getattr(request, 'user', None)
    if action=='update' and getattr(request,'activity_document',None)==(kind,as_id(record_id)):
        document_date=getattr(request,'activity_document_date',document_date)
    if not user or not user.is_authenticated:
        return False
    try:
        with transaction.atomic():
            actor = get_user_model().objects.filter(pk=user.pk).first()
            if not actor or (not actor.is_active and action != 'sign_in_failed'): return False
            schema = 'public'
            table = 'public.activity_events'
            with connection.cursor() as cur:
                if dedupe_key:
                    # A concurrent duplicate never delays a successful business save.
                    cur.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))',
                                [f'{schema}:activity:{user.pk}:{dedupe_key}'])
                    if not cur.fetchone()[0]: return False
                    cur.execute(f'SELECT 1 FROM {table} WHERE user_id=%s AND dedupe_key=%s AND at>clock_timestamp()-make_interval(secs=>%s) LIMIT 1',
                                [user.pk,dedupe_key,repeat_seconds])
                    if cur.fetchone(): return False
                cur.execute(f'''INSERT INTO {table}(user_id,username,action,kind,record_id,label,source,ip,dedupe_key,document_date)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    [user.pk,actor.get_username()[:150],action,kind,as_id(record_id),plain(label),source,ip,dedupe_key,document_date])
        return True
    except Exception as exc:
        # Never let a missing/drifting log abort the caller's transaction or disclose SQL.
        logger.warning('Activity recording failed (%s)', type(exc).__name__)
        return False
