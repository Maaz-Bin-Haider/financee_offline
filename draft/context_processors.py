"""Deployment-wide draft switch for every page that extends base.html.

base.html renders the sidebar on every screen, and the draft entries have to
disappear from all of them when the feature is switched off. The per-company
flag reaches templates separately, as ``features.draft_invoices``.
"""

from draft.feature import draft_sales_enabled


def draft_feature(request):
    return {"draft_sales_enabled": draft_sales_enabled()}
