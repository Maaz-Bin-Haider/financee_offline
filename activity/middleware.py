"""Observe after a successful view and before TenantSchemaMiddleware resets scope."""
import hashlib
import json
import logging
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from . import work

logger = logging.getLogger(__name__)


class ActivityMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not settings.TEAM_ACTIVITY_RECORDING_ENABLED: return
        if request.method == 'POST' and request.resolver_match.view_name in (work.DOCUMENTS | work.EXTRAS | work.CASH):
            try:
                payload = json.loads(request.body or '{}') if request.content_type == 'application/json' else request.POST.dict()
                request.activity_payload = payload if isinstance(payload,dict) else {}
                work.capture_document_date(request,request.activity_payload)
            except Exception:
                request.activity_payload = {}

    def process_response(self, request, response):
        match=getattr(request,'resolver_match',None)
        if match and match.view_name=='authentication:current_user' and request.user.is_authenticated:
            from spotlight.views import scope
            response['X-Activity-Scope']=scope(request)
            response['Cache-Control']='private, no-store'
        if not settings.TEAM_ACTIVITY_RECORDING_ENABLED or not getattr(request, 'tenant_is_active',False): return response
        if response.status_code != 200 or not response.get('Content-Type','').startswith('application/json'): return response
        try:
            data = json.loads(response.content)
            work.observe(request,getattr(request,'activity_payload',{}),data)
            work.observe_extra(request,getattr(request,'activity_payload',{}),data)
            if isinstance(data,dict) and (data.get('success') is False or data.get('status') in ('error','denied') or data.get('error')): return response
            from .reports import REPORTS, EXPORT_SOURCES
            from .exports import ticket
            name=request.resolver_match.view_name
            target=EXPORT_SOURCES.get(name)
            if target and target[0].allowed(request):
                response['X-Activity-Export']=ticket(request,name)
                response['Cache-Control']='private, no-store'
            if name in REPORTS and REPORTS[name][0].allowed(request):
                from .recorder import record
                try: body=request.body
                except Exception: body=request.POST.urlencode().encode()
                key='run:'+hashlib.sha256(name.encode()+b'\0'+request.GET.urlencode().encode()+b'\0'+body).hexdigest()
                record(request,'run','report',label=REPORTS[name][0].label,dedupe_key=key,repeat_seconds=60)
        except Exception as exc:
            logger.warning('Activity observation failed (%s)',type(exc).__name__)
        return response
