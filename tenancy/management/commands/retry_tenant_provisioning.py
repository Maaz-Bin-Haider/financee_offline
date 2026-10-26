"""Controlled retry for a pending/failed tenant schema build."""

from django.core.management.base import BaseCommand, CommandError

from tenancy.models import (
    PROVISIONING_FAILED,
    PROVISIONING_PENDING,
    PROVISIONING_READY,
    Company,
)
from tenancy.provisioning import provision_company
from tenancy.utils import schema_exists


class Command(BaseCommand):
    help = "Retry one pending/failed company schema provisioning operation."

    def add_arguments(self, parser):
        parser.add_argument("company_id", type=int)

    def handle(self, *args, **options):
        try:
            company = Company.objects.get(pk=options["company_id"])
        except Company.DoesNotExist as exc:
            raise CommandError("Company does not exist.") from exc
        if company.provisioning_state not in {
            PROVISIONING_PENDING,
            PROVISIONING_FAILED,
        }:
            raise CommandError(
                f"Company is {company.provisioning_state!r}; only pending or "
                "failed provisioning can be retried."
            )
        if schema_exists(company.schema_name):
            raise CommandError(
                "A physical schema already exists; investigate it before retrying."
            )
        provision_company(company)
        company.refresh_from_db()
        if company.provisioning_state != PROVISIONING_READY:
            raise CommandError(
                f"Retry failed ({company.provisioning_error_code or 'unknown'})."
            )
        self.stdout.write(self.style.SUCCESS(
            f"Company {company.pk} ready: {company.schema_name} (serial)."
        ))
