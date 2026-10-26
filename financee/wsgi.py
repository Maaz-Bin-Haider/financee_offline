"""
WSGI config for financee project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'financee.settings')

application = get_wsgi_application()

# Subscription email scheduler: hourly scan that sends expiry/suspension
# notifications to company billing addresses. Started here (not in an
# AppConfig.ready) so it only runs in serving processes, never inside
# management commands like migrate. start_email_scheduler never raises.
from tenancy.subscription_emails import start_email_scheduler  # noqa: E402

start_email_scheduler()
