import json
import logging
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.db import connection
from django.utils.deprecation import MiddlewareMixin
from zoneinfo import ZoneInfo
from financee.security import deny_response, has_required_permissions, required_permissions_for_path, rate_limit_response
from .models import GeneralSettings

class LocalAccessMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.general_settings = GeneralSettings.objects.select_related('base_currency').first()
        request.installation_ready = request.general_settings is not None
        if request.general_settings:
            timezone.activate(ZoneInfo(request.general_settings.timezone))
            with connection.cursor() as cur:cur.execute("SELECT set_config('TimeZone',%s,false)",[request.general_settings.timezone])
            request.local_db_timezone=True
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.installation_ready and not request.path.startswith(('/setup/', '/health/', '/static/')):
            return redirect('local_setup')
        user = request.user
        if not user.is_authenticated: return None
        if not user.is_active: return JsonResponse({'message':'Account inactive.'}, status=403)
        perms, mode = required_permissions_for_path(request.path)
        if perms and not has_required_permissions(user, perms, mode): return deny_response(request)
        path = request.path
        from .features import feature_for_path, enabled_sibling_path
        from financee.security import is_ajax_or_api
        key = feature_for_path(path)
        if key and request.general_settings and not request.general_settings.feature_enabled(key):
            if request.method == 'GET' and not is_ajax_or_api(request):
                sibling = enabled_sibling_path(request.general_settings,key.split('.',1)[0])
                return redirect(sibling or '/home/')
            return JsonResponse({'status':'denied','message':'This module is disabled in local General Settings.'},status=403)
        if path.startswith('/home/api/'): return rate_limit_response(request,'dashboard_api',limit=180,window=60)
        if path.startswith(('/accountsReports/','/sales-reports/api/')): return rate_limit_response(request,'reports',limit=90,window=60)
        if 'autocomplete' in path or 'lookup' in path: return rate_limit_response(request,'lookup',limit=240,window=60)
    def process_response(self, request, response):
        timezone.deactivate()
        if getattr(request,'local_db_timezone',False):
            with connection.cursor() as cur:cur.execute("SELECT set_config('TimeZone','UTC',false)")
        if 'application/json' in response.get('Content-Type','') and response.status_code >= 400:
            try: payload = json.loads(response.content or '{}')
            except (ValueError, TypeError): return response
            if isinstance(payload,dict):
                payload.pop('details',None)
                if response.status_code >= 500: payload = {'status':'error','message':'An unexpected error occurred.'}
                return JsonResponse(payload,status=response.status_code)
        return response
    def process_exception(self, request, exception):
        from django.http import Http404
        from django.core.exceptions import PermissionDenied
        if isinstance(exception,(Http404,PermissionDenied)): return None
        logging.getLogger(__name__).exception('Local request failed')
        if request.path.startswith('/admin/'): return None
        return JsonResponse({'status':'error','message':'An unexpected error occurred.'},status=500)
