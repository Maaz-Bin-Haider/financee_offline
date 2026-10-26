"""
tenancy.context_processors
==========================
Expose the subscription warning banner and the per-company feature flags to
every tenant template.

``TenantSchemaMiddleware`` stamps ``request.subscription_state`` for
authenticated tenant users whose company is not blocked. Only the
``expiring`` (renewal due soon) and ``grace`` (expired, blocked soon)
states surface a banner; blocked states never reach a normal template
because the middleware short-circuits them to the suspension page.
"""
from datetime import date, timedelta

from .features import features_map
from .models import SUBSCRIPTION_EXPIRING, SUBSCRIPTION_GRACE


def company_features(request):
    """
    ``features`` — nested {group: {enabled, subs: {sub: bool}}} used both for
    template conditions and (via the ``json_script`` filter in base.html) as
    ``window.FinanceeFeatures``, which JS-built toolbars read to hide
    CSV/Excel export buttons. It must be passed to ``json_script`` as the raw
    dict — pre-serializing it with ``json.dumps`` double-encodes it into a
    string and the JS feature checks silently fail open. Off-tenant requests
    get an all-enabled map so shared pages render unchanged.
    """
    company = getattr(request, "tenant_company", None)
    return {
        "features": features_map(company),
    }


def subscription_notice(request):
    state = getattr(request, "subscription_state", None)
    if state not in (SUBSCRIPTION_EXPIRING, SUBSCRIPTION_GRACE):
        return {}

    company = getattr(request, "tenant_company", None)
    if company is None or company.paid_until is None:
        return {}

    today = date.today()
    if state == SUBSCRIPTION_GRACE:
        # Access stops the day AFTER grace_until.
        blocked_on = company.grace_until + timedelta(days=1)
        days_left = (company.grace_until - today).days + 1
    else:
        blocked_on = None
        days_left = (company.paid_until - today).days

    return {
        "subscription_notice": {
            "state": state,
            "paid_until": company.paid_until,
            "blocked_on": blocked_on,
            "days_left": max(days_left, 0),
        }
    }
