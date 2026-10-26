from .features import features_map
from .currency import currency_config

def installation(request):
    profile = getattr(request, 'general_settings', None)
    money = currency_config(profile)
    return {'features':features_map(profile), 'general_settings':profile,
            'currency_config':money, 'currency_code':money['code'],
            'currency_symbol':money['symbol'], 'currency_label':money['label'],
            'business_config': {'name':profile.name, 'address':profile.address, 'phone':profile.phone, 'email':profile.contact_email,
                                'timezone':profile.timezone, 'currency':money} if profile else {}}
