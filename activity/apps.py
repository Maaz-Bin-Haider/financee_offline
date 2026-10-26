from django.apps import AppConfig
from django.db.models.signals import post_migrate


def seed_activity_permission(sender, using='default', **kwargs):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    content_type, _ = ContentType.objects.db_manager(using).get_or_create(app_label='auth', model='user')
    Permission.objects.db_manager(using).get_or_create(codename='view_team_activity',
        content_type=content_type, defaults={'name': 'Can view company team activity'})


class ActivityConfig(AppConfig):
    name = 'activity'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        post_migrate.connect(seed_activity_permission, sender=self, dispatch_uid='activity.seed_permission')
        from . import signals  # noqa: F401
