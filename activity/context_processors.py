from django.conf import settings
from .access import enabled
from spotlight.views import scope


def activity(request):
    if not enabled(request,manager=False):return {}
    from .exports import ticket
    from .reports import EXPORT_SOURCES
    token=''
    for name,(target,document) in EXPORT_SOURCES.items():
        if document and request.path==target.path and target.allowed(request):
            token=ticket(request,name);break
    return {'activity_config':{'scope':scope(request),'recording':settings.TEAM_ACTIVITY_RECORDING_ENABLED,'token':token},
            'team_activity_available':enabled(request)}
