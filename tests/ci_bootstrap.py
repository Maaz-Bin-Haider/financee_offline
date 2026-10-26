#!/usr/bin/env python3
"""CI bootstrap: give every active company one tenant user + membership.

The test suite discovers tenants through ``tenancy_membership``
(``tests/suite/_harness.py::discover_tenants``), so a freshly seeded CI
database — which has companies but no users — would otherwise report
"No active tenant memberships found." and skip every domain module.

Idempotent; safe to rerun. Run inside the web container:
    python tests/ci_bootstrap.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from tenancy.models import Company, Membership  # noqa: E402


def main():
    User = get_user_model()
    # The registry is serial-only; do not query the retained legacy column.
    companies = Company.objects.filter(
        is_active=True,
    ).exclude(schema_name="").order_by("id")
    if not companies:
        print("No active companies — nothing to bootstrap.")
        return 1
    for i, company in enumerate(companies, start=1):
        user, _ = User.objects.get_or_create(
            username=f"ci_user{i}",
            defaults={"email": f"ci_user{i}@example.com"},
        )
        user.set_password("ci-user-password")
        user.save()
        # user is a OneToOne on Membership: get_or_create keyed on the user.
        membership, created = Membership.objects.get_or_create(
            user=user, defaults={"company": company}
        )
        print(f"membership {'created' if created else 'exists'}: "
              f"{user.username} -> {membership.company.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
