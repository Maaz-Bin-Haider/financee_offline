"""
provision_tenant
================
Create a Company (and therefore its schema) from the command line — useful for
scripted setup / CI, though the same thing happens automatically when a Company
is added through the admin.

    python manage.py provision_tenant "Acme Traders"
    python manage.py provision_tenant "Acme Traders" --owner alice
    python manage.py provision_tenant "Acme Traders" --enable sales_reports --enable excel_export
    python manage.py provision_tenant "Acme Traders" --all-features

If ``--owner`` is given, that existing user is attached to the new company via a
Membership (enforcing one-company-per-user).

Like a company added in the admin, the new company starts with the default
feature plan (``tenancy.features.default_disabled_features``). ``--enable`` and
``--disable`` adjust it key by key (enabling a sub-feature also enables its
main switch); ``--all-features`` starts from everything on instead.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenancy.features import all_feature_keys, default_disabled_features
from tenancy.models import (
    TAX_ENVIRONMENT_CHOICES,
    Company,
    Currency,
    Membership,
    PROVISIONING_READY,
)
from tenancy.utils import schema_exists


class Command(BaseCommand):
    help = "Create a tenant Company, provision its PostgreSQL schema, and optionally attach an owner."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Company / tenant display name.")
        parser.add_argument(
            "--owner",
            dest="owner",
            default=None,
            help="Username of an existing user to attach to this company.",
        )
        parser.add_argument(
            "--base-currency",
            default="PKR",
            metavar="CODE",
            help="Active ISO 4217 base currency code (default: PKR).",
        )
        parser.add_argument(
            "--tax-environment",
            choices=[value for value, _ in TAX_ENVIRONMENT_CHOICES],
            default="non_tax",
            help="Company tax environment (default: non_tax).",
        )
        parser.add_argument(
            "--all-features",
            action="store_true",
            help="Start with every feature on instead of the default plan.",
        )
        parser.add_argument(
            "--enable",
            action="append",
            default=[],
            metavar="KEY",
            help="Switch a feature on, e.g. sales_reports or stock_reports.item_detail (repeatable).",
        )
        parser.add_argument(
            "--disable",
            action="append",
            default=[],
            metavar="KEY",
            help="Switch a feature off (repeatable).",
        )

    @staticmethod
    def _disabled_features(options):
        """The new company's disabled list: the default plan (or nothing with
        --all-features), adjusted by --enable/--disable."""
        known = set(all_feature_keys())
        unknown = sorted(
            key for key in options["enable"] + options["disable"] if key not in known
        )
        if unknown:
            raise CommandError(
                "Unknown feature key(s): " + ", ".join(unknown)
                + ". Valid keys are listed in tenancy/features.py."
            )
        disabled = [] if options["all_features"] else default_disabled_features()
        for key in options["enable"]:
            # A sub-feature only works while its main switch is on.
            for part in {key, key.split(".", 1)[0]}:
                if part in disabled:
                    disabled.remove(part)
        for key in options["disable"]:
            if key not in disabled:
                disabled.append(key)
        return [key for key in all_feature_keys() if key in disabled]

    def handle(self, *args, **options):
        name = options["name"].strip()
        owner_username = options["owner"]
        base_currency_code = options["base_currency"].strip().upper()
        tax_environment = options["tax_environment"]
        disabled_features = self._disabled_features(options)

        if Company.objects.filter(name=name).exists():
            raise CommandError(f"A company named {name!r} already exists.")
        try:
            base_currency = Currency.objects.get(
                code=base_currency_code,
                is_active=True,
            )
        except Currency.DoesNotExist:
            raise CommandError(
                f"Active currency {base_currency_code!r} does not exist. "
                "Run seed_currencies or choose another ISO code."
            )

        User = get_user_model()
        owner = None
        if owner_username:
            try:
                owner = User.objects.get(username=owner_username)
            except User.DoesNotExist:
                raise CommandError(f"User {owner_username!r} does not exist.")
            if Membership.objects.filter(user=owner).exists():
                raise CommandError(
                    f"User {owner_username!r} already belongs to a company "
                    "(a user can belong to only one company)."
                )

        with transaction.atomic():
            # Saving the Company fires the post_save signal which provisions the
            # physical schema from tenant_template.sql.
            company = Company.objects.create(
                name=name,
                base_currency=base_currency,
                tax_environment=tax_environment,
                disabled_features=disabled_features,
            )
            if owner is not None:
                Membership.objects.create(user=owner, company=company)

        provisioned = schema_exists(company.schema_name)
        company.refresh_from_db()
        if company.provisioning_state != PROVISIONING_READY or not provisioned:
            raise CommandError(
                f"Company schema provisioning failed "
                f"({company.provisioning_error_code or 'schema_missing'})."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Company {company.name!r} created (schema {company.schema_name!r}, "
                f"base_currency={company.base_currency_id}, "
                f"tax_environment={company.tax_environment}, "
                f"state={company.provisioning_state}, "
                f"provisioned={provisioned}, "
                f"features_off={len(company.disabled_features)})."
            )
        )
        if owner is not None:
            self.stdout.write(
                self.style.SUCCESS(f"Attached owner {owner.username!r} to {company.name!r}.")
            )
