"""Browser exports are self-reported, bound to a recent authorized data response."""
import hashlib
import json
from django.conf import settings
from django.core import signing
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.crypto import constant_time_compare
from financee.security import rate_limit_response
from spotlight.views import scope
from .access import enabled
from .reports import EXPORT_SOURCES
from .recorder import record

SALT='activity.export'


def ticket(request, source):
    return signing.dumps({'scope':scope(request),'source':source},salt=SALT,compress=True)


@require_POST
def record_export(request):
    if not settings.TEAM_ACTIVITY_RECORDING_ENABLED or not enabled(request,manager=False):
        return JsonResponse({'recorded':False},status=403)
    limited=rate_limit_response(request,'activity_export',limit=30,window=60)
    if limited is not None:return limited
    try:
        if len(request.body)>4096: raise ValueError()
        data=json.loads(request.body or '{}')
        if not isinstance(data,dict) or set(data)-{'format','token'}: raise ValueError()
        fmt=data.get('format')
        if fmt not in ('pdf','csv','xlsx'):raise ValueError()
        signed=signing.loads(data.get('token',''),salt=SALT,max_age=600)
        if not constant_time_compare(signed.get('scope',''),scope(request)):raise ValueError()
        source=signed['source']; target,document=EXPORT_SOURCES[source]
        if not target.allowed(request):raise ValueError()
        if source.startswith('activity:') and not enabled(request):raise ValueError()
        feature='pdf_export.'+('documents' if document else 'reports') if fmt=='pdf' else 'excel_export'
        if not request.tenant_company.feature_enabled(feature):raise ValueError()
    except (ValueError,TypeError,KeyError,signing.BadSignature):
        return JsonResponse({'recorded':False,'error':'Generate an authorized report or document before exporting.'},status=400)
    key='export:'+hashlib.sha256(f'{fmt}:{source}'.encode()).hexdigest()
    written=record(request,'export','report',label=fmt.upper()+' · '+target.label,
                   source='browser',dedupe_key=key,repeat_seconds=5)
    response=JsonResponse({'recorded':written})
    response['Cache-Control']='private, no-store'
    return response
