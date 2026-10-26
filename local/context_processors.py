from .features import features_map

def installation(request):
    profile = getattr(request, 'general_settings', None)
    return {'features':features_map(profile), 'general_settings':profile}
