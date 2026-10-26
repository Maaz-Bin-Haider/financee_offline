from django.contrib.auth import get_user_model, login
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods, require_GET
from financee.security import rate_limit
from .forms import SetupForm
from .models import GeneralSettings

@require_http_methods(['GET','POST'])
@rate_limit('onboarding', limit=15, window=60, methods={'POST'})
def setup(request):
    if GeneralSettings.objects.exists():
        return redirect('authentication:login') if request.method == 'GET' else JsonResponse({'message':'Setup is already complete.'}, status=409)
    form = SetupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            with connection.cursor() as cur: cur.execute("SELECT pg_advisory_xact_lock(726104,1)")
            if GeneralSettings.objects.exists(): return JsonResponse({'message':'Setup is already complete.'}, status=409)
            if get_user_model().objects.exists():
                return JsonResponse({'message':'Existing accounts found. Repair the installation; setup will not overwrite data.'}, status=409)
            user = form.save(commit=False)
            user.is_staff = True
            user.is_superuser = True
            user.save()
            GeneralSettings.objects.create(name=form.cleaned_data['company_name'], base_currency=form.cleaned_data['currency'],
                symbol_override=form.cleaned_data['symbol_override'], timezone=form.cleaned_data['timezone'])
        login(request,user,backend='django.contrib.auth.backends.ModelBackend')
        return redirect('home:home')
    return render(request,'local/setup.html',{'form':form})

@require_GET
def health(request):
    with connection.cursor() as cur:
        cur.execute('SELECT version FROM offline_schema_version WHERE id=true')
        row = cur.fetchone()
    from django.conf import settings
    return JsonResponse({'generation':getattr(settings,'OFFLINE_GENERATION','development'),'product':'Financee_Offline','build':'0.4.0-phase4','schema':row[0] if row else None,
                         'setup_complete':GeneralSettings.objects.exists()})
