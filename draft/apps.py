from django.apps import AppConfig
from django.db.models.signals import post_migrate


# The Draft Sale Invoice (proforma) rights, on the auth/user content type like
# every other permission in this project. confirm_draft_invoice is deliberately
# separate from create_draft_invoice: reserving goods and agreeing what they
# sell for are different jobs, and the second has to be grantable on its own.
DRAFT_PERMISSIONS = (
    ("view_draft_invoice", "Can Open Draft Invoice"),
    ("create_draft_invoice", "Can Create Draft Invoice"),
    ("update_draft_invoice", "Can Update Draft Invoice"),
    ("delete_draft_invoice", "Can Delete Draft Invoice"),
    ("confirm_draft_invoice", "Can Set Final Rates and Confirm a Draft Invoice"),
    ("view_draft_return", "Can Open Confirmed Draft Return"),
    ("create_draft_return", "Can Create Confirmed Draft Return"),
    ("update_draft_return", "Can Update Confirmed Draft Return"),
    ("delete_draft_return", "Can Delete Confirmed Draft Return"),
    ("view_pending_drafts_report", "Can Open Pending Drafts Report"),
    ("view_dash_draft_reservations", "Can View Dashboard Draft Reservations"),
)


def seed_draft_permissions(sender, using="default", **kwargs):
    """Create the draft permissions after every migrate (idempotent).

    Seeded here rather than by a new authentication migration: the Phase 4
    migration audit and the checkpoint-4B transition gate recognise only the
    two squashed initial migrations, so a new migration row would make the
    read-only history audit fail closed. The container entrypoint runs
    ``migrate`` on every start, so this runs on every deployment.
    """
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    content_type, _ = ContentType.objects.db_manager(using).get_or_create(
        app_label="auth", model="user")
    for codename, name in DRAFT_PERMISSIONS:
        Permission.objects.db_manager(using).get_or_create(
            codename=codename, content_type=content_type, defaults={"name": name})


class DraftConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'draft'

    def ready(self):
        post_migrate.connect(seed_draft_permissions, sender=self,
                             dispatch_uid="draft.seed_draft_permissions")
