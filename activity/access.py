from functools import wraps
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from financee.security import rate_limit_response


def enabled(request, *, manager=True):
    user=getattr(request,'user',None)
    company=getattr(request,'general_settings',None)
    if not user or not user.is_authenticated or not user.is_active or not company or not getattr(request,'installation_ready',False): return False
    return not manager or (settings.TEAM_ACTIVITY_ENABLED and company.feature_enabled('team_activity') and user.has_perm('auth.view_team_activity'))


def guarded(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not request.user.is_authenticated:
            from django.shortcuts import redirect
            return redirect('authentication:login') if request.path=='/activity/' else JsonResponse({'error':'Sign in again.'},status=401)
        if not enabled(request): return JsonResponse({'error':'Team activity is unavailable for this account.'},status=403)
        from spotlight.views import scope
        from django.utils.crypto import constant_time_compare
        offered=request.headers.get('X-Activity-Scope')
        if offered and not constant_time_compare(offered,scope(request)):
            return JsonResponse({'error':'Your session changed. Reload this page.'},status=409)
        limited=rate_limit_response(request,'team_activity',limit=120,window=60)
        if limited is not None:return limited
        try:
            with transaction.atomic():
                with connection.cursor() as cur: cur.execute("SET LOCAL statement_timeout='2000ms'")
                response=view(request,*args,**kwargs)
        except DatabaseError:
            response=JsonResponse({'error':'Activity took too long to load. Try a smaller period.'},status=503)
        response['Cache-Control']='private, no-store'
        return response
    return wrapped
