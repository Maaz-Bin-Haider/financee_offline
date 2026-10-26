from django.apps import AppConfig

class LocalConfig(AppConfig):
    name = 'local'
    verbose_name = 'Installation'
    default_auto_field = 'django.db.models.BigAutoField'
