"""Register the pre-built example tenant after Django owns the tenancy schema.

`build_multitenant_db.sql` still builds the example ``tenant_company_1``
business schema on first database boot, but it no longer creates the public
tenancy registry tables and no longer seeds a ``tenancy`` migration row.
Seeding ``('tenancy', '0001_initial')`` left the checkpoint 4A squashed
migration permanently *partially* applied: Django then discarded the
replacement, replayed the original chain, and ``0005_company_inventory_mode``
recreated the retired ``inventory_mode`` column on every fresh install.

Django migrations now own the whole public tenancy schema, so the registry row
for that pre-built schema must be created after ``migrate``. This command does
exactly that.

It is deliberately a first-boot-only repair: it refuses to act on any database
that already contains a company, so it can never alter an existing deployment.
Provisioning is not triggered either -- the post_save signal returns early when
the schema already exists.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from tenancy.models import PROVISIONING_READY, Company
from tenancy.utils import schema_exists, schema_has_tables

BOOTSTRAP_SCHEMA = "tenant_company_1"
BOOTSTRAP_NAME = "Company One"


class Command(BaseCommand):
    help = (
        "Register the bootstrap example tenant schema in the company registry. "
        "No-op unless the database is a freshly bootstrapped, company-less one."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema", default=BOOTSTRAP_SCHEMA,
            help="Physical schema to register (default: %(default)s).",
        )
        parser.add_argument(
            "--name", default=BOOTSTRAP_NAME,
            help="Company name to register it under (default: %(default)s).",
        )

    def handle(self, *args, **options):
        schema = options["schema"]
        name = options["name"]

        # Fail-closed guard: never touch a database that already has tenants.
        if Company.objects.exists():
            self.stdout.write(
                "register_bootstrap_tenant: registry already populated; no action."
            )
            return
        if not schema_exists(schema) or not schema_has_tables(schema):
            self.stdout.write(
                f"register_bootstrap_tenant: no populated {schema!r} schema; no action."
            )
            return

        with transaction.atomic():
            company = Company(name=name, schema_name=schema)
            # The schema is already built by the bootstrap, so record it ready
            # rather than leaving it pending. The provisioning signal is a no-op
            # because the schema exists.
            company.provisioning_state = PROVISIONING_READY
            company.save()

        self.stdout.write(self.style.SUCCESS(
            f"register_bootstrap_tenant: registered {name!r} -> {schema!r} "
            f"(id={company.pk}, state={company.provisioning_state})."
        ))
