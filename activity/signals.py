"""Sessions have a verified membership even before/after request tenant activation."""
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from .recorder import record, client_ip


@receiver(user_logged_in, dispatch_uid='activity.signed_in')
def signed_in(sender, request, user, **kwargs):
    record(request,'sign_in','session',label='Signed in',user=user,ip=client_ip(request))


@receiver(user_logged_out, dispatch_uid='activity.signed_out')
def signed_out(sender, request, user, **kwargs):
    if user: record(request,'sign_out','session',label='Signed out',user=user)


@receiver(user_login_failed, dispatch_uid='activity.sign_in_failed')
def failed(sender, credentials, request=None, **kwargs):
    # Unknown names have no company; never assign them to the current browser user.
    name=str((credentials or {}).get('username') or '')[:150]
    try: account=get_user_model().objects.filter(username=name).first() if name else None
    except Exception: return
    if account: record(request,'sign_in_failed','session',label='Failed sign-in',user=account,ip=client_ip(request))
