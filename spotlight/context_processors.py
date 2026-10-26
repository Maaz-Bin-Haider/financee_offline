from .views import enabled, scope


def spotlight(request):
    if not enabled(request):
        return {}
    company = request.general_settings
    return {'spotlight_config': {'scope': scope(request), 'storage': f'{request.user.pk}:{company.pk}',
                                'currency': company.base_currency_id}}
