import json
import logging
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from zoneinfo import ZoneInfo
from financee.security import deny_response, has_required_permissions, required_permissions_for_path, rate_limit_response
from .models import GeneralSettings

class LocalAccessMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.general_settings = GeneralSettings.objects.select_related('base_currency').first()
        request.installation_ready = request.general_settings is not None
        if request.general_settings: timezone.activate(ZoneInfo(request.general_settings.timezone))
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.installation_ready and not request.path.startswith(('/setup/', '/health/', '/static/')):
            return redirect('local_setup')
        user = request.user
        if not user.is_authenticated: return None
        if not user.is_active: return JsonResponse({'message':'Account inactive.'}, status=403)
        perms, mode = required_permissions_for_path(request.path)
        if perms and not has_required_permissions(user, perms, mode): return deny_response(request)
        path = request.path
        if path.startswith('/home/api/'): return rate_limit_response(request,'dashboard_api',limit=180,window=60)
        if path.startswith(('/accountsReports/','/sales-reports/api/')): return rate_limit_response(request,'reports',limit=90,window=60)
        if 'autocomplete' in path or 'lookup' in path: return rate_limit_response(request,'lookup',limit=240,window=60)
    def process_response(self, request, response):
        timezone.deactivate()
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
