"""Create only an isolated disposable regression owner through real onboarding."""
import os, secrets
os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings')
import django
django.setup()
from django.conf import settings
from django.test import Client
from local.models import GeneralSettings
assert settings.DATABASES['default']['NAME']=='financee_offline_test', 'Disposable offline test DB required'
if not GeneralSettings.objects.exists():
    password=secrets.token_urlsafe(32)
    response=Client().post('/setup/',dict(company_name='Disposable regression business',currency='USD',timezone='Asia/Karachi',username='regression_owner',password1=password,password2=password))
    assert response.status_code==302, 'Disposable onboarding failed; existing state preserved'
print('Disposable regression owner ready; no universal password.')
