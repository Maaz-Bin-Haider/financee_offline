"""Seed/update the controlled ISO 4217 currency catalogue."""

from django.core.management.base import BaseCommand

from tenancy.currencies import seed_currency_catalogue
from tenancy.currency_data import ISO_4217_PUBLISHED
from tenancy.models import Currency


class Command(BaseCommand):
    help = "Idempotently seed the public ISO 4217 currency catalogue."

    def handle(self, *args, **options):
        created, updated = seed_currency_catalogue(Currency)
        self.stdout.write(self.style.SUCCESS(
            f"ISO 4217 ({ISO_4217_PUBLISHED}): "
            f"{created} created, {updated} synchronized."
        ))
