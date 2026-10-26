#!/usr/bin/env python3
"""Per-company feature flags: registry/model semantics, admin form round-trip,
middleware URL enforcement (group + sub-report blocking, GET redirects vs JSON
denials), UI hiding (sidebar links, report buttons, CSV buttons, attachment
widget), and the attachment upload guard.

On builds whose registry carries new-company defaults
(``tenancy.features.DEFAULT_DISABLED_FEATURES``) it also covers the default
plan, the module/dashboard/PDF/draft switches, the admin add view and actions,
and ``provision_tenant``. The Phase 3B rehearsal runs this file inside an older
image without them, so those checks are skipped there.

Everything mutates only the public-schema ``Company.disabled_features`` column
(plus a temporary superuser membership, mirroring suite/test_http.py) and
restores it in ``finally`` — no tenant business data is touched. The one
company ``provision_tenant`` creates is left behind with every feature on, like
the rest of the suite's uniquely named trail.

Run inside the web container:
    docker compose -f deploy/docker-compose.yml exec -e PYTHONPATH=/app web \
        python tests/suite/test_feature_flags.py
"""
from __future__ import annotations

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client, RequestFactory  # noqa: E402

from attachments.utils import validate_request_attachments  # noqa: E402
from tenancy import features as feature_registry  # noqa: E402
from tenancy.admin import CompanyAdminForm, _feature_field_name  # noqa: E402
from tenancy.features import (  # noqa: E402
    FEATURE_GROUPS,
    FEATURE_PATH_PREFIXES,
    all_feature_keys,
    feature_for_path,
    features_map,
)
from tenancy.models import Company, Membership  # noqa: E402

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []

# Builds with per-module switches and a new-company default plan. Older images
# (the Phase 3B rehearsal) have neither, and run only the baseline checks.
HAS_DEFAULTS = hasattr(feature_registry, "DEFAULT_DISABLED_FEATURES")

# The default plan as specified: everything else starts on.
EXPECTED_DEFAULT_OFF = {
    "accounts_reports.detailed_ledger2",
    "stock_reports.serial_ledger_sold_flag",
    "stock_reports.serial_ledger_purchase_only",
    "stock_reports.serial_ledger_sale_only",
    "stock_reports.item_detail",
    "stock_reports.item_last_purchase",
    "stock_reports.item_last_sale",
    "monthly_reports.monthly_position",
    "sales_reports",
    "draft_invoices",
    "opening_stock",
    "opening_cash",
    "owner_equity",
    "month_close",
    "excel_export",
    "attachments",
}
EXPECTED_GROUPS = {
    "dashboard", "sales", "sale_returns", "purchases", "purchase_returns",
    "payments", "receipts", "contra", "items", "parties",
    "accounts_reports", "stock_reports", "monthly_reports", "sales_reports",
    "draft_invoices", "opening_stock", "opening_cash", "owner_equity", "month_close",
    "pdf_export", "excel_export", "attachments",
}


if "reportmailer" in settings.INSTALLED_APPS:
    EXPECTED_DEFAULT_OFF.add("report_email")
    EXPECTED_GROUPS.add("report_email")

if "spotlight" in settings.INSTALLED_APPS:
    EXPECTED_DEFAULT_OFF.add("spotlight")
    EXPECTED_GROUPS.add("spotlight")

if "activity" in settings.INSTALLED_APPS:
    EXPECTED_DEFAULT_OFF.add("team_activity")
    EXPECTED_GROUPS.add("team_activity")


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))
    return bool(ok)


def make_client():
    server = "localhost"
    allowed = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*", "")]
    if allowed:
        server = allowed[0].lstrip(".")
    return Client(SERVER_NAME=server)


# ── Registry / model semantics (unsaved Company: no signals, no schema) ─────

def check_registry_and_model():
    keys = all_feature_keys()
    serial_groups = {
        "accounts_reports", "stock_reports", "monthly_reports",
        "sales_reports", "opening_stock", "opening_cash",
        "excel_export", "attachments",
    }
    # draft_invoices is present on builds that carry the draft invoice feature,
    # the per-module switches on builds with the default plan; the Phase 3B
    # rehearsal runs this file inside an older image without either.
    chk("registry has serial-only top-level groups",
        set(FEATURE_GROUPS) in (serial_groups, serial_groups | {"draft_invoices"}, EXPECTED_GROUPS),
        sorted(FEATURE_GROUPS))
    # None marks a deliberately unrestricted path (the shared pickers).
    chk("every enforced path maps to a registered key",
        all(key is None or key in keys for _, key in FEATURE_PATH_PREFIXES),
        [key for _, key in FEATURE_PATH_PREFIXES if key is not None and key not in keys])
    chk("longest prefixes win (ledger2 before ledger)",
        feature_for_path("/accountsReports/detailed-ledger2/") == "accounts_reports.detailed_ledger2"
        and feature_for_path("/accountsReports/detailed-ledger/") == "accounts_reports.detailed_ledger")
    chk("sales report API resolves to its sub-key",
        feature_for_path("/sales-reports/api/trend/") == "sales_reports.trend")
    chk("sales report page resolves to the group",
        feature_for_path("/sales-reports/") == "sales_reports")
    chk("unenforced path resolves to None", feature_for_path("/home/") is None)

    co = Company(name=f"feat_{TAG}")
    chk("default company: everything enabled",
        all(co.feature_enabled(k) for k in keys))

    co.disabled_features = ["stock_reports"]
    chk("disabled group disables the group", not co.feature_enabled("stock_reports"))
    chk("disabled group disables its subs",
        not co.feature_enabled("stock_reports.serial_ledger"))
    chk("disabled group leaves other groups alone",
        co.feature_enabled("accounts_reports.cash_ledger"))

    co.disabled_features = ["sales_reports.trend"]
    chk("disabled sub disables only that sub",
        not co.feature_enabled("sales_reports.trend")
        and co.feature_enabled("sales_reports")
        and co.feature_enabled("sales_reports.summary"))

    co.disabled_features = ["no_such_feature"]
    chk("unknown keys fail open", co.feature_enabled("accounts_reports"))

    co.disabled_features = ["excel_export", "monthly_reports.monthly_income"]
    fmap = features_map(co)
    chk("features_map reflects single-switch feature",
        fmap["excel_export"]["enabled"] is False)
    chk("features_map reflects sub switch",
        fmap["monthly_reports"]["enabled"] is True
        and fmap["monthly_reports"]["subs"]["monthly_income"] is False
        and fmap["monthly_reports"]["subs"]["monthly_position"] is True)
    chk("features_map with no company is all-enabled",
        features_map(None)["excel_export"]["enabled"] is True)


# ── Admin form round-trip ────────────────────────────────────────────────────

def check_admin_form(company):
    form = CompanyAdminForm(instance=company)
    chk("admin form exposes a switch per feature key",
        all(_feature_field_name(k) in form.fields for k in all_feature_keys()))
    chk("admin form initial mirrors enabled state",
        all(form.fields[_feature_field_name(k)].initial == company.feature_enabled(k)
            for k in all_feature_keys()))

    # The admin form has never exposed an inventory mode (3A excluded it; 4A
    # removed the concept), so the payload must not carry one.
    data = {
        "name": company.name,
        "base_currency": company.base_currency_id,
        "tax_environment": company.tax_environment,
        "contact_email": company.contact_email or "",
        "paid_until": company.paid_until or "",
        "grace_days": company.grace_days,
        "warn_days_before": company.warn_days_before,
        "is_active": company.is_active,
        "is_suspended": company.is_suspended,
    }
    for key in all_feature_keys():
        data[_feature_field_name(key)] = True
    data[_feature_field_name("excel_export")] = False
    data[_feature_field_name("stock_reports.item_detail")] = False

    form = CompanyAdminForm(data=data, instance=company)
    if not chk("admin form validates", form.is_valid(), form.errors.as_text()):
        return
    obj = form.save(commit=False)  # not persisted; instance-only
    chk("unticked switches land in disabled_features",
        set(obj.disabled_features) == {"excel_export", "stock_reports.item_detail"},
        obj.disabled_features)


# ── Admin change view (modelform_factory validates declared fields) ─────────

def check_admin_views(company):
    import re

    User = get_user_model()
    superuser = User.objects.filter(is_superuser=True).first()
    client = make_client()
    client.force_login(superuser)

    url = f"/admin/tenancy/company/{company.pk}/change/"
    resp = client.get(url)
    if not chk("admin change form renders", resp.status_code == 200, resp.status_code):
        return
    html = resp.content.decode("utf-8", "ignore")
    chk("admin change form shows feature fieldsets", "Features — " in html)
    chk("admin change form shows every switch",
        all(f'name="{_feature_field_name(k)}"' in html for k in all_feature_keys()))

    # Full POST round-trip through the real admin (inlines included).
    data = {
        "name": company.name,
        "base_currency": company.base_currency_id,
        "tax_environment": company.tax_environment,
        "contact_email": company.contact_email or "",
        "paid_until": company.paid_until.isoformat() if company.paid_until else "",
        "grace_days": company.grace_days,
        "warn_days_before": company.warn_days_before,
        "_save": "Save",
    }
    if company.is_active:
        data["is_active"] = "on"
    if company.is_suspended:
        data["is_suspended"] = "on"
    for prefix in set(re.findall(r'name="([^"]+)-TOTAL_FORMS"', html)):
        data[f"{prefix}-TOTAL_FORMS"] = "0"
        data[f"{prefix}-INITIAL_FORMS"] = "0"
        data[f"{prefix}-MIN_NUM_FORMS"] = "0"
        data[f"{prefix}-MAX_NUM_FORMS"] = "1000"
    for key in all_feature_keys():
        data[_feature_field_name(key)] = "on"
    del data[_feature_field_name("excel_export")]
    del data[_feature_field_name("sales_reports.trend")]

    snapshot = list(company.disabled_features or [])
    try:
        resp = client.post(url, data)
        error_text = re.sub(r"<[^>]+>", " ", resp.content.decode("utf-8", "ignore"))
        error_text = " ".join(error_text.split())
        chk(
            "admin save redirects",
            resp.status_code == 302,
            f"{resp.status_code}: {error_text[:2000]}",
        )
        fresh = Company.objects.get(pk=company.pk)
        chk("admin save persists unticked switches",
            set(fresh.disabled_features) == {"excel_export", "sales_reports.trend"},
            fresh.disabled_features)
    finally:
        Company.objects.filter(pk=company.pk).update(disabled_features=snapshot)


# ── HTTP enforcement + UI hiding through the real middleware ────────────────

def set_features(company_pk, disabled):
    Company.objects.filter(pk=company_pk).update(disabled_features=list(disabled))


def check_http(company):
    client = make_client()
    User = get_user_model()
    superuser = User.objects.filter(is_superuser=True).first()
    client.force_login(superuser)

    # Everything enabled: full UI, all pages reachable.
    set_features(company.pk, [])
    resp = client.get("/home/")
    html = resp.content.decode("utf-8", "ignore")
    chk("all-on: /home/ is 200", resp.status_code == 200, resp.status_code)
    chk("all-on: feature JSON embedded", 'id="financee-features"' in html)
    # Guards against double-encoding: window.FinanceeFeatures must be a JSON
    # OBJECT. If the map were pre-dumped to a string before json_script, the
    # quotes would be \"-escaped, this substring would vanish, and every JS
    # feature check would silently fail open (CSV buttons reappear).
    chk("all-on: feature JSON is an object, not a double-encoded string",
        '"excel_export": {"enabled": true' in html)
    # Multi-line {# #} comments are invalid in Django templates: the tail of
    # the comment renders as visible page text (has happened twice now).
    chk("all-on: no template-comment text leaks into the page", "#}" not in html)
    for label in ("Accounts Reports", "Stock Reports", "Monthly Reports",
                  "Sales Reports", "Opening Stock", "Set Opening"):
        chk(f"all-on: sidebar shows {label}", label in html, label)
    for path in ("/accountsReports/cash-ledger/", "/accountsReports/stock-summary/",
                 "/accountsReports/monthly-position/", "/sales-reports/",
                 "/opening-stock/", "/set-opening/"):
        resp = client.get(path)
        chk(f"all-on: GET {path} is 200", resp.status_code == 200, resp.status_code)
    resp = client.get("/accountsReports/stock-summary/")
    chk("all-on: CSV button present on stock reports",
        'id="download_csv"' in resp.content.decode("utf-8", "ignore"))
    resp = client.get("/sale/sales/")
    chk("all-on: attachment widget on sale page",
        'id="attachments_panel"' in resp.content.decode("utf-8", "ignore"))

    # Whole groups disabled: sidebar entries vanish, URLs are blocked.
    set_features(company.pk, ["accounts_reports", "stock_reports", "monthly_reports",
                              "sales_reports", "opening_stock", "opening_cash"])
    resp = client.get("/home/")
    html = resp.content.decode("utf-8", "ignore")
    chk("groups-off: /home/ still 200", resp.status_code == 200, resp.status_code)
    for label in ("Accounts Reports", "Stock Reports", "Monthly Reports",
                  "Sales Reports", "Opening Stock", "Set Opening"):
        chk(f"groups-off: sidebar hides {label}", label not in html, label)
    chk("groups-off: sidebar keeps Sales entry", ">Sales" in html.replace("</i> ", ">"))
    for path in ("/accountsReports/cash-ledger/", "/accountsReports/stock-summary/",
                 "/accountsReports/monthly-position/"):
        resp = client.get(path)
        chk(f"groups-off: GET {path} redirects home",
            resp.status_code == 302 and resp["Location"].startswith("/home"),
            f"{resp.status_code} {resp.get('Location')}")
    resp = client.get("/sales-reports/")
    chk("groups-off: sales reports page redirects home",
        resp.status_code == 302 and resp["Location"].startswith("/home"),
        f"{resp.status_code} {resp.get('Location')}")
    resp = client.get("/sales-reports/api/summary/?from=2026-01-01&to=2026-01-31")
    chk("groups-off: sales report API gets 403 JSON",
        resp.status_code == 403 and resp["Content-Type"].startswith("application/json"),
        resp.status_code)
    resp = client.post("/accountsReports/trial-balance/", data="{}",
                       content_type="application/json")
    chk("groups-off: report data POST gets 403 JSON",
        resp.status_code == 403 and resp["Content-Type"].startswith("application/json"),
        resp.status_code)
    body = resp.json()
    chk("groups-off: denial message is scrubbed and clear",
        body.get("status") == "denied" and "not enabled" in body.get("message", ""),
        body)
    for path in ("/opening-stock/", "/set-opening/"):
        resp = client.get(path)
        chk(f"groups-off: GET {path} redirects home",
            resp.status_code == 302 and resp["Location"].startswith("/home"),
            f"{resp.status_code} {resp.get('Location')}")

    # One sub-report disabled: page redirects to an enabled sibling, button hidden.
    set_features(company.pk, ["accounts_reports.cash_ledger"])
    resp = client.get("/accountsReports/cash-ledger/")
    chk("sub-off: disabled sub page redirects to enabled sibling",
        resp.status_code == 302
        and resp["Location"] == "/accountsReports/detailed-ledger/",
        f"{resp.status_code} {resp.get('Location')}")
    resp = client.post("/accountsReports/cash-ledger/", data="{}",
                       content_type="application/json")
    chk("sub-off: disabled sub data POST gets 403 JSON",
        resp.status_code == 403 and resp["Content-Type"].startswith("application/json"),
        resp.status_code)
    resp = client.get("/accountsReports/detailed-ledger/")
    html = resp.content.decode("utf-8", "ignore")
    chk("sub-off: sibling page is 200", resp.status_code == 200, resp.status_code)
    chk("sub-off: disabled report button hidden", 'id="btn-cash-ledger"' not in html)
    chk("sub-off: other report buttons still present", 'id="btn-ledger"' in html)
    resp = client.get("/home/")
    chk("sub-off: group sidebar entry survives",
        "Accounts Reports" in resp.content.decode("utf-8", "ignore"))

    # CSV/Excel export disabled: buttons disappear (PDF/Print stay).
    set_features(company.pk, ["excel_export"])
    resp = client.get("/accountsReports/stock-summary/")
    html = resp.content.decode("utf-8", "ignore")
    chk("csv-off: CSV button gone from stock reports", 'id="download_csv"' not in html)
    chk("csv-off: PDF button stays on stock reports", 'id="download_pdf"' in html)
    chk("csv-off: feature JSON object says export disabled",
        '"excel_export": {"enabled": false' in html)
    resp = client.get("/sales-reports/")
    html = resp.content.decode("utf-8", "ignore")
    chk("csv-off: CSV button gone from sales reports", 'id="sr-csv"' not in html)
    chk("csv-off: PDF button stays on sales reports", 'id="sr-pdf"' in html)
    resp = client.get("/month-close/")
    chk("csv-off: CSV button gone from month close",
        'id="mc-download-csv"' not in resp.content.decode("utf-8", "ignore"))
    resp = client.get("/owner-equity/")
    chk("csv-off: CSV button gone from owner equity",
        'id="oe-download-csv"' not in resp.content.decode("utf-8", "ignore"))

    # Attachments disabled: widget hidden, endpoints blocked, uploads rejected.
    set_features(company.pk, ["attachments"])
    resp = client.get("/sale/sales/")
    chk("att-off: attachment widget hidden on sale page",
        'id="attachments_panel"' not in resp.content.decode("utf-8", "ignore"))
    resp = client.get("/attachments/sale/1/")
    chk("att-off: attachment endpoint blocked",
        resp.status_code in (302, 403), resp.status_code)

    set_features(company.pk, [])
    resp = client.get("/attachments/sale/1/")
    # Reaches the view again: 200 with metadata, or 404 JSON when invoice 1
    # does not exist on this tenant — either proves the block was lifted.
    chk("att-on again: attachment endpoint reachable",
        resp.status_code in (200, 404), resp.status_code)


def check_upload_guard(company):
    factory = RequestFactory()
    upload = SimpleUploadedFile("x.png", b"\x89PNG-not-really", content_type="image/png")
    request = factory.post("/sale/sales/", data={"attachment_image": upload})

    request.tenant_company = Company(name="x", disabled_features=["attachments"])
    try:
        validate_request_attachments(request)
        chk("upload with attachments off raises ValidationError", False, "no exception")
    except ValidationError as exc:
        chk("upload with attachments off raises ValidationError",
            "not enabled" in str(exc), exc)

    request.tenant_company = Company(name="x", disabled_features=[])
    try:
        validate_request_attachments(request)
        chk("upload with attachments on passes the feature gate", True)
    except ValidationError as exc:
        chk("upload with attachments on passes the feature gate", False, exc)


# ── Default plan + per-module switches (builds with defaults only) ──────────

def sidebar_has(html, label):
    """A sidebar link labelled exactly ``label`` (``</i> Label </a>``)."""
    return re.search(r"</i>\s*" + re.escape(label) + r"\s*</a>", html) is not None


def check_default_registry():
    registry = feature_registry
    keys = set(all_feature_keys())
    chk("defaults: the default-off set is exactly the plan",
        set(registry.DEFAULT_DISABLED_FEATURES) == EXPECTED_DEFAULT_OFF,
        sorted(set(registry.DEFAULT_DISABLED_FEATURES) ^ EXPECTED_DEFAULT_OFF))
    chk("defaults: default_disabled_features() lists it in registry order",
        registry.default_disabled_features()
        == [key for key in all_feature_keys() if key in EXPECTED_DEFAULT_OFF])
    grouped = [group for _, groups in registry.FEATURE_CATEGORIES for group in groups]
    chk("defaults: every main feature sits in exactly one admin category",
        sorted(grouped) == sorted(FEATURE_GROUPS) and len(grouped) == len(set(grouped)),
        grouped)
    chk("defaults: no key uses a prefix the audits reserve",
        not [key for key in keys if key.startswith(("quantity", "purchase_reports"))])

    expected = {
        "/sale/sales/": "sales",
        "/saleReturn/create-sale-return/": "sale_returns",
        "/purchase/purchasing/": "purchases",
        "/purchaseReturn/create-purchase-return/": "purchase_returns",
        "/payments/payment/": "payments",
        "/receipts/receipt/": "receipts",
        "/contra/contra/": "contra",
        "/items/items-dash/": "items",
        "/parties/parties-dash/": "parties",
        "/owner-equity/": "owner_equity",
        "/month-close/": "month_close",
        "/parties/autocomplete-party": None,
        "/items/autocomplete-item/": None,
        "/home/": None,
        "/home/api/dash/stock/kpi/": "dashboard.stock_overview",
        "/home/api/cash/": "dashboard.cash_balance",
        "/home/api/parties/": "dashboard.balances",
        "/home/api/dash/alerts/": "dashboard.smart_alerts",
        "/home/api/dash/drafts/": "draft_invoices.dashboard_card",
        "/draft/": "draft_invoices.drafts",
        "/draft/save/": "draft_invoices.drafts",
        "/draft/get/": "draft_invoices",
        "/draft/summary/": "draft_invoices",
        "/draft/convert/screen/": "draft_invoices.confirm",
        "/draft/return/serial/lookup/": "draft_invoices.returns",
        "/draft/pending/": "draft_invoices.pending_report",
        "/sales-reports/": "sales_reports",
    }
    if "activity" in settings.INSTALLED_APPS:
        expected.update({"/activity/":"team_activity", "/activity/api/team/":"team_activity", "/activity/record/":None})
    wrong = {path: (feature_for_path(path), want)
             for path, want in expected.items() if feature_for_path(path) != want}
    chk("defaults: module, dashboard, draft and shared-picker paths resolve", not wrong, wrong)

    co = Company(name=f"featdef_{TAG}", disabled_features=registry.default_disabled_features())
    fmap = features_map(co)
    core = ("dashboard", "sales", "sale_returns", "purchases", "purchase_returns",
            "payments", "receipts", "contra", "items", "parties",
            "accounts_reports", "stock_reports", "monthly_reports", "pdf_export")
    addons = ("sales_reports", "draft_invoices", "opening_stock", "opening_cash",
              "owner_equity", "month_close", "excel_export", "attachments")
    chk("defaults: the plan keeps the core modules and reports on",
        all(fmap[group]["enabled"] for group in core),
        [group for group in core if not fmap[group]["enabled"]])
    chk("defaults: the plan switches the add-ons off",
        not any(fmap[group]["enabled"] for group in addons),
        [group for group in addons if fmap[group]["enabled"]])
    chk("defaults: a report group opens on its first enabled report",
        fmap["monthly_reports"]["landing"] == "/accountsReports/monthly-income/"
        and fmap["accounts_reports"]["landing"] == "/accountsReports/cash-ledger/",
        (fmap["monthly_reports"]["landing"], fmap["accounts_reports"]["landing"]))
    co.disabled_features = ["monthly_reports.monthly_position", "monthly_reports.monthly_income"]
    chk("defaults: a group with every sub-feature off counts as off",
        features_map(co)["monthly_reports"]["enabled"] is False)


def check_admin_defaults(company):
    registry = feature_registry
    form = CompanyAdminForm()
    wrong = [key for key in all_feature_keys()
             if form.fields[_feature_field_name(key)].initial != registry.feature_on_by_default(key)]
    chk("admin add form: switches start at the default plan", not wrong, wrong)

    User = get_user_model()
    client = make_client()
    client.force_login(User.objects.filter(is_superuser=True).first())
    resp = client.get("/admin/tenancy/company/add/")
    if not chk("admin add view renders", resp.status_code == 200, resp.status_code):
        return
    html = resp.content.decode("utf-8", "ignore")

    def ticked(key):
        match = re.search(r'<input[^>]*name="%s"[^>]*>' % re.escape(_feature_field_name(key)), html)
        return bool(match) and "checked" in match.group(0)

    wrong = [key for key in all_feature_keys() if ticked(key) != registry.feature_on_by_default(key)]
    chk("admin add view: ticks match the default plan", not wrong, wrong)
    chk("admin add view: sub-features are tagged under their main switch",
        'data-feature-master="stock_reports"' in html and 'data-feature-parent="stock_reports"' in html)
    chk("admin add view: loads the nesting script", "admin_company_features" in html)
    for title in ("Core modules", "Reports", "Add-on modules", "Export"):
        chk(f"admin add view: shows the {title} section", f"Features — {title}" in html, title)

    snapshot = list(company.disabled_features or [])
    try:
        for action, expected in (
            ("apply_default_features", registry.default_disabled_features()),
            ("enable_all_features", []),
        ):
            resp = client.post("/admin/tenancy/company/", {
                "action": action,
                "_selected_action": [str(company.pk)],
                "index": "0",
                "select_across": "0",
            })
            fresh = Company.objects.get(pk=company.pk)
            chk(f"admin action {action} sets the company's switches",
                resp.status_code == 302 and fresh.disabled_features == expected,
                f"{resp.status_code} {fresh.disabled_features}")
    finally:
        set_features(company.pk, snapshot)


def check_provision_defaults():
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    from tenancy.management.commands.provision_tenant import Command

    registry = feature_registry
    name = f"FF Defaults {TAG}"
    call_command("provision_tenant", name, stdout=StringIO())
    company = Company.objects.get(name=name)
    try:
        chk("provision_tenant: a new company starts with the default plan",
            company.disabled_features == registry.default_disabled_features(),
            company.disabled_features)
    finally:
        # Later suite modules exercise every feature on every company.
        set_features(company.pk, [])

    def options(**overrides):
        base = {"all_features": False, "enable": [], "disable": []}
        base.update(overrides)
        return base

    got = Command._disabled_features(options(enable=["sales_reports.trend"], disable=["contra"]))
    chk("provision_tenant: --enable of a sub-feature also enables its main switch",
        "sales_reports" not in got and "sales_reports.trend" not in got and "contra" in got, got)
    chk("provision_tenant: --all-features starts from everything on",
        Command._disabled_features(options(all_features=True)) == [])
    try:
        Command._disabled_features(options(enable=["no_such_feature"]))
        chk("provision_tenant: unknown feature keys are refused", False, "accepted")
    except CommandError:
        chk("provision_tenant: unknown feature keys are refused", True)


def check_http_defaults(company):
    registry = feature_registry
    client = make_client()
    User = get_user_model()
    client.force_login(User.objects.filter(is_superuser=True).first())

    def page(path):
        resp = client.get(path)
        return resp, resp.content.decode("utf-8", "ignore")

    def redirects(resp, target):
        return resp.status_code == 302 and resp["Location"].startswith(target)

    def json_denied(resp):
        return resp.status_code == 403 and resp["Content-Type"].startswith("application/json")

    # The default plan.
    set_features(company.pk, registry.default_disabled_features())
    resp, html = page("/home/")
    chk("plan: /home/ is 200", resp.status_code == 200, resp.status_code)
    for label in ("Dashboard", "Sales", "Purchases", "Payments", "Receipts", "Contra Entry",
                  "Sale Return", "Purchase Return", "Items", "Parties",
                  "Accounts Reports", "Stock Reports", "Monthly Reports"):
        chk(f"plan: sidebar shows {label}", sidebar_has(html, label), label)
    for label in ("Sales Reports", "Opening Stock", "Set Opening", "Owner Equity",
                  "Month-End Close", "Draft Invoices", "Confirm Draft",
                  "Confirmed Draft Return", "Pending Drafts"):
        chk(f"plan: sidebar hides {label}", not sidebar_has(html, label), label)
    chk("plan: Monthly Reports opens on the Income Statement",
        'href="/accountsReports/monthly-income/"' in html)
    for path in ("/sales-reports/", "/owner-equity/", "/month-close/", "/opening-stock/",
                 "/set-opening/", "/draft/"):
        resp = client.get(path)
        chk(f"plan: GET {path} redirects home", redirects(resp, "/home"),
            f"{resp.status_code} {resp.get('Location')}")
    resp = client.get("/accountsReports/monthly-position/")
    chk("plan: Company Position redirects to the Income Statement",
        redirects(resp, "/accountsReports/monthly-income/"),
        f"{resp.status_code} {resp.get('Location')}")
    resp, html = page("/accountsReports/stock-summary/")
    chk("plan: stock reports keep the default reports",
        'id="btn-history"' in html and 'id="btn-worth"' in html)
    chk("plan: stock reports hide the extra reports",
        'id="btn-item-detail"' not in html and 'id="btn-item-last-sale"' not in html)
    chk("plan: report PDF on, CSV off",
        'id="download_pdf"' in html and 'id="download_csv"' not in html)
    resp, html = page("/sale/sales/")
    chk("plan: sale page keeps its PDF and has no attachment widget",
        "downloadInvoicePDF()" in html and 'id="attachments_panel"' not in html)

    # A core module switched off: page, form POST and quick action are gone,
    # while the shared party picker keeps serving the other screens.
    set_features(company.pk, ["sales", "parties"])
    resp, html = page("/home/")
    chk("module-off: sidebar hides Sales", not sidebar_has(html, "Sales"))
    chk("module-off: quick action New Sale hidden", "New Sale" not in html)
    resp = client.get("/sale/sales/")
    chk("module-off: GET /sale/sales/ redirects home", redirects(resp, "/home"),
        f"{resp.status_code} {resp.get('Location')}")
    resp = client.post("/sale/sales/", {})
    chk("module-off: POST /sale/sales/ gets 403 JSON", json_denied(resp), resp.status_code)
    resp = client.get("/parties/parties-dash/")
    chk("module-off: parties screen redirects home", redirects(resp, "/home"),
        f"{resp.status_code} {resp.get('Location')}")
    resp = client.get("/parties/autocomplete-party?term=a", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    chk("module-off: the shared party picker still answers", resp.status_code == 200,
        resp.status_code)

    # Dashboard widgets.
    set_features(company.pk, ["dashboard.stock_overview"])
    resp, html = page("/home/")
    chk("widget-off: stock overview is not rendered",
        'id="low-stock-table"' not in html and 'id="kpi-total-units"' not in html)
    chk("widget-off: the other widgets stay", 'id="sales-chart"' in html)
    resp = client.get("/home/api/dash/stock/kpi/")
    chk("widget-off: its data endpoint gets 403 JSON", json_denied(resp), resp.status_code)
    set_features(company.pk, ["dashboard"])
    resp, html = page("/home/")
    chk("dashboard-off: /home/ is a plain welcome page",
        resp.status_code == 200 and "Welcome" in html and "home_script" not in html,
        resp.status_code)
    chk("dashboard-off: the sidebar calls it Home", sidebar_has(html, "Home"))

    # PDF generation.
    set_features(company.pk, ["pdf_export.documents"])
    resp, html = page("/sale/sales/")
    chk("pdf-docs-off: sale PDF button gone", "downloadInvoicePDF()" not in html)
    resp, html = page("/accountsReports/stock-summary/")
    chk("pdf-docs-off: report PDF stays", 'id="download_pdf"' in html)
    set_features(company.pk, ["pdf_export"])
    resp, html = page("/accountsReports/stock-summary/")
    chk("pdf-off: report PDF button gone", 'id="download_pdf"' not in html)
    chk("pdf-off: feature JSON says PDF is off", '"pdf_export": {"enabled": false' in html)
    resp, html = page("/home/")
    chk("pdf-off: dashboard PDF buttons gone", "data-pdf=" not in html and "fa-file-pdf" not in html)

    # Draft sub-features: each screen has its own switch.
    set_features(company.pk, ["draft_invoices.confirm"])
    resp = client.get("/draft/convert/screen/")
    chk("draft-confirm-off: Confirm Draft redirects to Draft Invoices",
        resp.status_code == 302 and resp["Location"] == "/draft/",
        f"{resp.status_code} {resp.get('Location')}")
    resp = client.post("/draft/convert/", data="{}", content_type="application/json")
    chk("draft-confirm-off: conversion gets 403 JSON", json_denied(resp), resp.status_code)
    resp, html = page("/home/")
    chk("draft-confirm-off: sidebar keeps Draft Invoices, hides Confirm Draft",
        sidebar_has(html, "Draft Invoices") and not sidebar_has(html, "Confirm Draft"))

    set_features(company.pk, [])


# ── Driver ───────────────────────────────────────────────────────────────────

def main():
    User = get_user_model()
    superuser = User.objects.filter(is_superuser=True).first()
    if superuser is None:
        chk("a superuser exists", False, "no superuser available")
        return report()

    company = Company.objects.filter(is_active=True).exclude(schema_name="").order_by("id").first()
    if company is None:
        chk("an active company exists", False, "no active tenant companies")
        return report()

    snapshot = list(company.disabled_features or [])
    original_membership = None
    created_membership = False
    try:
        original_membership = superuser.membership
        if original_membership.company_id != company.pk:
            Membership.objects.filter(user=superuser).update(company=company)
    except Membership.DoesNotExist:
        Membership.objects.create(user=superuser, company=company)
        created_membership = True
    connection.close()

    try:
        # Start from everything on, whatever an earlier module left behind.
        set_features(company.pk, [])
        check_registry_and_model()
        check_admin_form(Company.objects.get(pk=company.pk))
        check_admin_views(Company.objects.get(pk=company.pk))
        check_http(company)
        check_upload_guard(company)
        if HAS_DEFAULTS:
            check_default_registry()
            check_admin_defaults(Company.objects.get(pk=company.pk))
            check_provision_defaults()
            check_http_defaults(company)
    finally:
        connection.close()
        Company.objects.filter(pk=company.pk).update(disabled_features=snapshot)
        if created_membership:
            Membership.objects.filter(user=superuser).delete()
        elif original_membership is not None and original_membership.company_id != company.pk:
            Membership.objects.filter(user=superuser).update(
                company=original_membership.company_id
            )

    return report()


def report():
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} feature-flag checks passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
