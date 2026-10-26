#!/usr/bin/env python3
"""Phase 4 currency catalogue and company accounting-setup checks."""

import io
import os
import sys
import time
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.core.exceptions import ValidationError  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.db.models.deletion import ProtectedError  # noqa: E402

from financee.admin_site import financee_admin_site  # noqa: E402
from tenancy.admin import CompanyAdmin, CompanyAdminForm  # noqa: E402
from tenancy.currency_data import CURRENCY_SEED_ROWS, ISO_4217_PUBLISHED  # noqa: E402
from tenancy.models import (  # noqa: E402
    TAX_ENVIRONMENT_NON_TAX,
    TAX_ENVIRONMENT_TAX,
    Company,
    Currency,
)

RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))


def messages(exc):
    return " ".join(
        message
        for values in exc.message_dict.values()
        for message in values
    )


def main():
    seed_codes = [row[0] for row in CURRENCY_SEED_ROWS]
    chk("catalogue source is official 2026-01-01 snapshot",
        ISO_4217_PUBLISHED == "2026-01-01", ISO_4217_PUBLISHED)
    chk("seed contains 178 current List One codes",
        len(seed_codes) == 178, len(seed_codes))
    chk("seed codes are unique", len(seed_codes) == len(set(seed_codes)))
    chk("seed codes are uppercase ISO-style",
        all(len(code) == 3 and code.isalpha() and code.isupper() for code in seed_codes))

    currencies = Currency.objects.in_bulk()
    chk("database catalogue matches seed",
        set(currencies) == set(seed_codes), len(currencies))
    chk("PKR metadata is correct",
        currencies["PKR"].name == "Pakistan Rupee"
        and currencies["PKR"].minor_units == 2
        and currencies["PKR"].symbol == "₨")
    chk("zero-decimal JPY is correct", currencies["JPY"].minor_units == 0)
    chk("three-decimal KWD is correct", currencies["KWD"].minor_units == 3)
    chk("four-decimal CLF is correct", currencies["CLF"].minor_units == 4)
    chk("non-monetary units are unavailable for company selection",
        not currencies["XAU"].is_active and not currencies["XXX"].is_active)
    chk("ordinary world currencies are active",
        all(currencies[code].is_active for code in ("PKR", "USD", "EUR", "GBP", "AED")))

    before = {
        code: (value.name, value.symbol, value.minor_units, value.is_active)
        for code, value in currencies.items()
    }
    output = io.StringIO()
    call_command("seed_currencies", stdout=output)
    after = {
        code: (value.name, value.symbol, value.minor_units, value.is_active)
        for code, value in Currency.objects.in_bulk().items()
    }
    chk("currency seed command is idempotent", before == after, output.getvalue())

    companies = list(Company.objects.order_by("id"))
    chk("existing companies exist", bool(companies), len(companies))
    chk("every company has a valid base currency",
        bool(companies) and all(c.base_currency_id in currencies for c in companies),
        [(c.id, c.base_currency_id) for c in companies])
    chk("every company has a valid tax environment",
        bool(companies) and all(
            c.tax_environment in {TAX_ENVIRONMENT_NON_TAX, TAX_ENVIRONMENT_TAX}
            for c in companies
        ),
        [(c.id, c.tax_environment) for c in companies])
    bootstrap = Company.objects.filter(name="Company One").first()
    chk("legacy bootstrap company uses safe PKR/non-tax backfill",
        bootstrap is None or (
            bootstrap.base_currency_id == "PKR"
            and bootstrap.tax_environment == TAX_ENVIRONMENT_NON_TAX
        ),
        None if bootstrap is None else (
            bootstrap.base_currency_id, bootstrap.tax_environment
        ))

    activity_matches = []
    with connection.cursor() as cur:
        for value in companies:
            quoted = connection.ops.quote_name(value.schema_name)
            cur.execute(
                f"SELECT EXISTS (SELECT 1 FROM {quoted}.journalentries LIMIT 1)"
            )
            expected = bool(cur.fetchone()[0])
            activity_matches.append((
                value.schema_name,
                expected,
                value.has_financial_activity(),
            ))
    chk("financial-activity detector reads real tenant journalentries",
        all(expected == actual for _schema, expected, actual in activity_matches),
        activity_matches)

    candidate = Company(
        name=f"PHASE4 SETUP {time.time_ns()}",
        base_currency=currencies["USD"],
        tax_environment=TAX_ENVIRONMENT_TAX,
    )
    try:
        candidate.full_clean()
        chk("new company accepts active world currency and tax mode", True)
    except Exception as exc:
        chk("new company accepts active world currency and tax mode", False, repr(exc))

    inactive_candidate = Company(
        name=f"PHASE4 INACTIVE {time.time_ns()}",
        base_currency=currencies["XAU"],
        tax_environment=TAX_ENVIRONMENT_NON_TAX,
    )
    try:
        inactive_candidate.full_clean()
        chk("new company rejects inactive catalogue entry", False, "validation allowed")
    except ValidationError as exc:
        chk("new company rejects inactive catalogue entry",
            "inactive" in messages(exc).lower(), messages(exc))

    company = companies[0]
    original_currency = company.base_currency
    original_tax = company.tax_environment
    company.base_currency = currencies["USD"]
    company.tax_environment = TAX_ENVIRONMENT_TAX
    with patch.object(Company, "has_financial_activity", return_value=False):
        try:
            company.clean()
            chk("setup can be corrected before financial activity", True)
        except ValidationError as exc:
            chk("setup can be corrected before financial activity", False, messages(exc))
    with patch.object(Company, "has_financial_activity", return_value=True):
        try:
            company.clean()
            chk("setup locks after financial activity", False, "validation allowed")
        except ValidationError as exc:
            text = messages(exc).lower()
            chk("setup locks after financial activity",
                "cannot be changed" in text and "financial activity" in text, text)
    company.base_currency = original_currency
    company.tax_environment = original_tax

    try:
        with transaction.atomic():
            Company.objects.filter(pk=company.pk).update(tax_environment="invalid")
        chk("database rejects invalid tax environment", False, "update succeeded")
    except IntegrityError:
        chk("database rejects invalid tax environment", True)

    try:
        currencies["PKR"].delete()
        chk("referenced base currency is protected", False, "delete succeeded")
    except ProtectedError:
        chk("referenced base currency is protected", True)

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid IN (
                'public.tenancy_currency'::regclass,
                'public.tenancy_company'::regclass
            )
              AND conname IN (
                'tenancy_currency_valid_code',
                'tenancy_currency_valid_minor_units',
                'tenancy_company_valid_tax_environment'
              )
            """
        )
        constraint_names = {row[0] for row in cur.fetchall()}
    chk("Phase 4 database constraints exist", constraint_names == {
        "tenancy_currency_valid_code",
        "tenancy_currency_valid_minor_units",
        "tenancy_company_valid_tax_environment",
    }, constraint_names)

    admin_obj = CompanyAdmin(Company, financee_admin_site)
    with patch.object(Company, "has_financial_activity", return_value=False):
        editable = set(admin_obj.get_readonly_fields(None, company))
    with patch.object(Company, "has_financial_activity", return_value=True):
        locked = set(admin_obj.get_readonly_fields(None, company))
    chk("admin permits pre-activity setup correction",
        "base_currency" not in editable and "tax_environment" not in editable)
    chk("admin locks setup after activity",
        {"base_currency", "tax_environment"}.issubset(locked), locked)
    chk("admin displays and filters company setup",
        {"base_currency", "tax_environment"}.issubset(admin_obj.list_display)
        and {"base_currency", "tax_environment"}.issubset(admin_obj.list_filter))

    add_form = CompanyAdminForm()
    choices = set(add_form.fields["base_currency"].queryset.values_list("code", flat=True))
    chk("admin offers active currencies", {"PKR", "USD", "EUR"}.issubset(choices))
    chk("admin excludes inactive non-monetary codes", "XAU" not in choices and "XXX" not in choices)

    missing_setup_form = CompanyAdminForm(data={
        "name": f"PHASE4 REQUIRED {time.time_ns()}",
        "is_active": "on",
        "grace_days": "3",
        "warn_days_before": "7",
    })
    chk("admin requires base currency and tax selection",
        not missing_setup_form.is_valid()
        and "base_currency" in missing_setup_form.errors
        and "tax_environment" in missing_setup_form.errors,
        missing_setup_form.errors.as_json())

    print("\n" + "=" * 78)
    passed = sum(1 for _name, ok, _detail in RESULTS if ok)
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    print(f"{passed}/{len(RESULTS)} company-setup checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
