"""The draft sale invoice switches.

Two switches control the feature:

* ``DRAFT_SALES_ENABLED`` (settings / environment) turns every draft surface
  off for the whole deployment: the screens, the endpoints, the sidebar
  entries, the pending report and the dashboard card.
* The per-company ``draft_invoices`` feature flag (tenancy.features, set from
  the admin) turns it off for one company. TenantSchemaMiddleware enforces it
  by URL prefix before any view here runs.

IMPORTANT: both switches hide the interface only. Neither un-guards existing
reservations. The trigger ``trg_protect_reserved_units``
(tenancy/sql/add_draft_invoices.sql) keeps refusing to sell, return or delete a
reserved unit whatever these say, because un-guarding it would let somebody sell
goods that are held for a customer. Release or convert open drafts before
switching the feature off.
"""

from django.conf import settings


def draft_sales_enabled():
    """Whether draft sale invoices are switched on for this deployment."""
    return getattr(settings, "DRAFT_SALES_ENABLED", True)


def draft_age_warning_days():
    """Days after which an open draft counts as ageing."""
    return int(getattr(settings, "DRAFT_AGE_WARNING_DAYS", 30))
