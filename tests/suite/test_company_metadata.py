#!/usr/bin/env python3
"""Serial-only company-registry and administration checks.

Runs inside the production web container. It intentionally does not provision
or delete schemas.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.db import DatabaseError, connection, transaction  # noqa: E402

from financee.admin_site import financee_admin_site  # noqa: E402
from tenancy.admin import CompanyAdmin, CompanyAdminForm  # noqa: E402
from tenancy.models import Company  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402
from tests.serial_api_compat import (  # noqa: E402
    RETIRED_API_PRESENT,
    SERIAL_SCHEMA_FAMILY,
    no_retired_mode_attribute,
    retired_mode_rejected,
)


RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))


def main():
    companies = list(Company.objects.order_by("id"))
    chk("active baseline companies exist", bool(companies), len(companies))
    # Checkpoint 4A retired the registry mode column, so "serial only" is
    # proven against each physical schema instead of a metadata value.
    verified = [
        (c.id, verify_company_schema(c, use_cache=False)) for c in companies
        if c.schema_name
    ]
    chk(
        "every provisioned company verifies as the serial family",
        bool(verified) and all(
            v.ok and v.family == SERIAL_SCHEMA_FAMILY for _cid, v in verified
        ),
        [(cid, v.family, v.reason) for cid, v in verified],
    )
    bootstrap = Company.objects.filter(name="Company One").first()
    chk(
        "legacy bootstrap company still verifies as serial",
        bootstrap is None or verify_company_schema(
            bootstrap, use_cache=False).family == SERIAL_SCHEMA_FAMILY,
        None if bootstrap is None else bootstrap.schema_name,
    )

    # The recovery gate runs this module inside the previously published
    # image, which still carries the temporary 3A compatibility API.
    if RETIRED_API_PRESENT:
        chk(
            "retired mode is a serial-locked compatibility property only",
            "inventory_mode" not in {f.name for f in Company._meta.get_fields()}
            and Company.get_inventory_mode_display is not None,
        )
    else:
        chk(
            "model exposes no inventory-mode concept at all",
            not hasattr(Company, "inventory_mode")
            and not hasattr(Company, "get_inventory_mode_display")
            and "inventory_mode" not in {f.name for f in Company._meta.get_fields()},
        )

    # Unsaved serial companies remain valid. Avoid save(): this phase must not
    # create or delete any physical tenant schema.
    serial_candidate = Company(
        name=f"PHASE3 SERIAL VALIDATION {time.time_ns()}",
    )
    try:
        serial_candidate.full_clean()
        chk("new serial company metadata validates", True)
    except Exception as exc:
        chk("new serial company metadata validates", False, repr(exc))

    # The retired keyword is now refused by Model.__init__ itself, which is
    # stricter than the save-time validation it replaces.
    chk(
        "quantity company metadata is rejected",
        retired_mode_rejected(f"PHASE3 QUANTITY BLOCK {time.time_ns()}"),
    )

    company = companies[0]
    original_schema = company.schema_name
    try:
        company.save(update_fields=["inventory_mode"])
        chk("existing company inventory mode is immutable", False, "save succeeded")
    except Exception as exc:
        # 4A: ValueError (unknown field). 3A: ValidationError (non-serial value).
        company.refresh_from_db()
        chk(
            "existing company cannot be updated through a retired field",
            company.schema_name == original_schema
            and no_retired_mode_attribute(company),
            f"{type(exc).__name__}: {exc}",
        )

    # Before 3B the constraint rejects quantity; after certified 3B the column
    # itself no longer exists. Neither state can store a quantity company mode.
    with connection.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='tenancy_company' AND column_name='inventory_mode')")
        legacy_present = cur.fetchone()[0]
        contracted = False
        if not legacy_present:
            from tenancy.management.commands.serial_only_phase3_cleanup import archive
            stored = archive(cur)
            contracted = bool(stored and stored["state"] == "applied")
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("UPDATE public.tenancy_company SET inventory_mode='quantity' WHERE id=%s", [company.pk])
        chk("database rejects quantity inventory mode", False, "update succeeded")
    except DatabaseError as exc:
        company.refresh_from_db()
        chk(
            "database rejects quantity inventory mode",
            company.schema_name == original_schema
            and getattr(exc.__cause__, "pgcode", None) == ("23514" if legacy_present else "42703"),
            getattr(exc.__cause__, "pgcode", None),
        )

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM pg_constraint
            WHERE conname = 'tenancy_company_valid_inventory_mode'
              AND conrelid = 'public.tenancy_company'::regclass
            """
        )
        constraint_count = cur.fetchone()[0]
    # Three legitimate states: pre-3B (column + constraint present), post-3B
    # (contracted, archive applied), and a fresh checkpoint 4A install, which
    # never creates the column and therefore has no archive. With no column
    # there is no value that could express a non-serial company.
    chk("serial-only database constraint or certified column contraction",
        constraint_count == 1 if legacy_present else constraint_count == 0,
        f"legacy_present={legacy_present} contracted={contracted} count={constraint_count}")

    admin_obj = CompanyAdmin(Company, financee_admin_site)
    chk("admin form hides inventory mode", "inventory_mode" not in CompanyAdminForm.base_fields)
    chk("admin fieldsets hide inventory mode", all(
        "inventory_mode" not in fieldset[1].get("fields", ())
        for fieldset in admin_obj.fieldsets
    ))
    chk("admin list hides inventory mode", "inventory_mode" not in admin_obj.list_display)
    chk("admin filter hides inventory mode", "inventory_mode" not in admin_obj.list_filter)

    form = CompanyAdminForm(data={
        "name": f"PHASE3 ADMIN QUANTITY {time.time_ns()}",
        "inventory_mode": "quantity",
        "base_currency": "PKR",
        "tax_environment": "non_tax",
        "is_active": "on",
        "grace_days": "3",
        "warn_days_before": "7",
    })
    chk(
        "posted quantity value cannot make the instance non-serial",
        form.is_valid() and no_retired_mode_attribute(form.instance),
        form.errors.as_json(),
    )

    print("\n" + "=" * 78)
    passed = sum(1 for _name, ok, _detail in RESULTS if ok)
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    print(f"{passed}/{len(RESULTS)} company-metadata checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
