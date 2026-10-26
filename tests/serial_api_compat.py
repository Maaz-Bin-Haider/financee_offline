"""Version-adaptive helpers for tests that must run against two images.

The Phase 3 recovery gate deliberately copies the *current* test suite into the
*previously published* application image and runs it there, to prove that the
deployed image still works against the contracted database
(`tests/phase3_recovery_local.py`). That image still carries the temporary
checkpoint 3A inventory-mode compatibility API; the current image removed it in
checkpoint 4A.

Without these helpers a test can only assert one of the two shapes: it would
silently pass on one image and fail on the other. Each helper asserts the same
*guarantee* — no supported path can create a non-serial company — against
whichever application version is actually running.

Delete this module in checkpoint 4B, once every environment runs a 4A or later
image and no published image carries the retired API.
"""

from tenancy.models import Company

# 3A's schema_families module has no SERIAL_SCHEMA_FAMILY constant.
try:
    from tenancy.schema_families import SERIAL_SCHEMA_FAMILY
except ImportError:  # previously published checkpoint 3A image
    SERIAL_SCHEMA_FAMILY = "serial"

# True only while the retired compatibility API is still present (3A image).
RETIRED_API_PRESENT = hasattr(Company, "get_inventory_mode_display")


def retired_mode_rejected(name, value="quantity"):
    """Return True when the running image refuses a retired-mode company.

    Checkpoint 4A refuses the keyword in ``Model.__init__``; checkpoint 3A
    accepted the keyword and refused the value in ``full_clean()``. Either way
    the row must never validate.
    """
    from django.core.exceptions import ValidationError
    try:
        candidate = Company(name=name, inventory_mode=value)
    except TypeError:
        return True
    try:
        candidate.full_clean()
    except ValidationError:
        return True
    return False


def no_retired_mode_attribute(instance):
    """Return True when `instance` cannot report a non-serial mode.

    On 4A the attribute is absent entirely. On 3A the compatibility property
    exists but must always read as serial.
    """
    if not RETIRED_API_PRESENT:
        return not hasattr(instance, "inventory_mode")
    return getattr(instance, "inventory_mode", None) == SERIAL_SCHEMA_FAMILY


def serial_company_stub():
    """A resolved-company stub the request boundary accepts on both images.

    Checkpoint 4A's boundary only requires that middleware resolved *a*
    company; checkpoint 3A additionally read a serial mode off it. Carrying the
    serial value satisfies both and weakens neither -- the fail-closed case
    (no company at all) is asserted separately.
    """
    from types import SimpleNamespace
    return SimpleNamespace(inventory_mode=SERIAL_SCHEMA_FAMILY)


def retired_family_key_rejected():
    """Return True when the schema-family registry cannot activate quantity.

    4A raises on the retired key; 3A still returns a descriptor, which must be
    runtime-disabled with no path exceptions.
    """
    from tenancy.schema_families import schema_family
    try:
        definition = schema_family("quantity")
    except ValueError:
        return True
    return (
        not definition.runtime_enabled
        and definition.enabled_path_prefixes == ()
    )
