#!/usr/bin/env python3
"""Database-free contracts for the Phase 2 quantity-runtime removal."""

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


RUNTIME_FILES = (
    "items/quantity_views.py",
    "purchase/quantity_views.py",
    "sale/quantity_views.py",
    "purchaseReturn/quantity_views.py",
    "saleReturn/quantity_views.py",
    "tenancy/audit_urls.py",
    "tenancy/audit_views.py",
    "tenancy/count_urls.py",
    "tenancy/count_views.py",
    "tenancy/quantity_tax.py",
    "tenancy/report_catalog.py",
    "tenancy/report_urls.py",
    "tenancy/report_views.py",
    "tenancy/transfer_urls.py",
    "tenancy/transfer_views.py",
    "tenancy/warehouse_urls.py",
    "tenancy/warehouse_views.py",
)

UI_FILES = (
    "templates/opening_stock_templates/quantity_opening_stock_template.html",
    "templates/purchase_return_templates/quantity_purchase_return_template.html",
    "templates/purchase_templates/quantity_purchasing_template.html",
    "templates/reports/quantity_reports.html",
    "templates/sale_return_templates/quantity_sale_return_template.html",
    "templates/sale_templates/quantity_sale_template.html",
    "templates/tenancy_templates/quantity_audit.html",
    "templates/tenancy_templates/quantity_counts.html",
    "templates/tenancy_templates/quantity_transfers.html",
    "templates/tenancy_templates/quantity_warehouses.html",
    "static/css/quantity_reports.css",
    "static/css/quantity_workflow.css",
    "static/js/quantity_counts.js",
    "static/js/quantity_opening_stock.js",
    "static/js/quantity_purchase_returns.js",
    "static/js/quantity_purchases.js",
    "static/js/quantity_reports.js",
    "static/js/quantity_sale_returns.js",
    "static/js/quantity_sales.js",
    "static/js/quantity_transfers.js",
    "static/js/quantity_warehouses.js",
    "static/js/quantity_workflow.js",
)

urls = "\n".join(read(path) for path in (
    "financee/urls.py", "items/urls.py", "purchase/urls.py",
    "purchaseReturn/urls.py", "saleReturn/urls.py",
))
business_views = "\n".join(read(path) for path in (
    "purchase/views.py", "sale/views.py", "purchaseReturn/views.py",
    "saleReturn/views.py", "opening_stock/views.py", "home/views.py",
))
capabilities = read("tenancy/capabilities.py")
middleware = read("tenancy/middleware.py")
families = read("tenancy/schema_families.py")
rollout = read("tenancy/management/commands/apply_sql_all_tenants.py")
preflight = read("tenancy/management/commands/release_preflight.py")
entrypoint = read("deploy/entrypoint.sh")
features = read("tenancy/features.py")
security = read("financee/security.py")
attachments = read("attachments/utils.py")
base = read("templates/base/base.html")
workflow = read(".github/workflows/ci.yml")
stack = read("tests/ci_phase27_stack.sh")
suite = read("tests/suite/run_all.py")

# The sidebar shows Sales Reports when the user holds ANY of the route guard's
# SALES_REPORT_PERMS. The template has to repeat that list, and a literal "..."
# placeholder once hid the link from users holding only six of the eight.
sales_report_perms = next(
    ast.literal_eval(node.value)
    for node in ast.parse(security).body
    if isinstance(node, ast.Assign)
    and any(getattr(target, "id", None) == "SALES_REPORT_PERMS"
            for target in node.targets)
)
sales_sidebar_condition = next(
    (line for line in base.splitlines()
     if line.strip().startswith("{% if perms.auth.can_view_sales_summary")),
    "",
)

# Extracted from deployed Phase 1 commit 102e55e857bbffa8bd4318e6afaec42e048c8e67.
# These are independent regression anchors, not hashes of the candidate itself.
# Re-pinned 2026-09-30 for draft sale invoices: purchase/views.py only, where
# _serial_purchasing now lists serials reserved on a draft invoice in its
# edit/delete refusal (validate_purchase_update2/delete report them). Nothing
# else in the four serial document views changed.
SERIAL_FUNCTION_BASELINES = {
    "purchase/views.py": "ef4e0f37877b97e96b21978677e4745360c8720f1ab2a676e79f6cf5e6c04079",
    "sale/views.py": "c385a60296ef81904dfc6d99d68f6b317a209fd45aa1d5b37fd764c24b6d91d4",
    "purchaseReturn/views.py": "8355ff92824990af9c6a19a571d916886227a8886e91112d2db9e0cdd01b5875",
    "saleReturn/views.py": "06e7cd03c2be1c88cb6bbb83cef1b795e914e3ebc1cad5a098a9b414ae1cb080",
}


def function_hash(path):
    source = read(path)
    functions = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name.startswith("_serial_")]
    # Hash exact source, not ast.dump(), whose formatting varies by Python version.
    return hashlib.sha256("\n".join(
        ast.get_source_segment(source, node) for node in functions
    ).encode()).hexdigest()


def files_hash(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode() + b"\0" + (ROOT / path).read_bytes() + b"\0")
    return digest.hexdigest()


serial_ui_paths = [path.relative_to(ROOT).as_posix()
                   for directory in ("static", "templates")
                   for path in (ROOT / directory).rglob("*")
                   if path.is_file() and not path.name.startswith((".", "quantity_"))
                   and path.relative_to(ROOT).as_posix() != "templates/base/base.html"]
serial_sql_paths = [path.relative_to(ROOT).as_posix()
                    for path in (ROOT / "tenancy/sql").glob("*.sql")
                    if not path.name.startswith("quantity_")]

# Checkpoint 4A had to change build_multitenant_db.sql: seeding
# ('tenancy','0001_initial') left the squashed replacement permanently
# partially applied, so Django replayed the original chain and recreated the
# retired inventory_mode column on every fresh install. Only the Django
# migration bookkeeping changed. Hashing the bootstrap as one blob would hide
# that distinction, so its 12,248-line tenant business-schema build is pinned
# separately and must stay byte-identical to deployed Phase 1.
bootstrap = read("build_multitenant_db.sql")
BOOTSTRAP_TENANT_START = "-- 2. Example tenant schema: tenant_company_1"
BOOTSTRAP_TENANT_END = (
    "-- reset search_path back to shared after building the tenant schema"
)
bootstrap_tenant_section = bootstrap[
    bootstrap.index(BOOTSTRAP_TENANT_START):bootstrap.index(BOOTSTRAP_TENANT_END)
]

checks = {
    "12 serial document implementations are source-identical to deployed Phase 1":
        all(function_hash(path) == expected for path, expected in SERIAL_FUNCTION_BASELINES.items()),
    # Re-pinned 2026-10-23 for the deliberate Phase 1 dark-theme port.
    # SQL and the serial document implementations remain unchanged.
    # Re-pinned 2026-10-02 for per-module feature switches (223 -> 225):
    # templates/home_templtes/quick_actions.html and
    # static/js/admin_company_features.js are new; the dashboard template and
    # script gate each widget; every PDF button (document templates, report
    # templates and toolbars, draft screens, dashboard) follows pdf_export;
    # draft cross-links follow their screen switches; financee_admin.css nests
    # the admin sub-switches.
    # Previously re-pinned 2026-09-30 for draft sale invoices (212 -> 223).
    "235 serial UI source files match the purchase sizing baseline":
        len(serial_ui_paths) == 235
        and files_hash(serial_ui_paths) == "30c67947a100d5b7dbd5c8241cecf80a48af2e2906b8a17adf4e348cafc1fbbd",
    # Re-pinned 2026-09-16 for the dashboard receivables fix (tenant schema
    # version 7). These baselines exist to catch ACCIDENTAL drift in serial
    # behaviour; this change was deliberate and reviewed, so the pins move with
    # it exactly as checkpoint 4A moved the bootstrap pin. What changed:
    #   * new file tenancy/sql/fix_dashboard_expense_receivables.sql (16 -> 17)
    #   * tenant_template.sql + production_hardening.sql: vw_dash_party_ar_balance
    #     constrained to jl.account_id = p.ar_account_id
    #   * build_multitenant_db.sql: the same view change inside the example
    #     tenant section. No schema version bump — see FIXED_ISSUES.md.
    # Nothing in the serial document lifecycle (purchase/sale/return) changed —
    # the 12 serial document implementations above are still pinned to their
    # deployed Phase 1 hashes and still pass untouched. See FIXED_ISSUES.md.
    # Re-pinned 2026-09-30 for draft sale invoices (17 -> 18): new
    # tenancy/sql/add_draft_invoices.sql, appended byte-identically to the end
    # of tenant_template.sql and production_hardening.sql. It is deliberately
    # NOT in build_multitenant_db.sql (the bootstrap pin below is unchanged);
    # production_hardening.sql brings the bootstrap tenant up at first start.
    "20 serial tenant SQL files match the additive Team Activity baseline":
        len(serial_sql_paths) == 20
        and files_hash(serial_sql_paths) == "64530db0f4527e09ba5ca803f11324333ab58918359feb98af187ef323e348aa",
    # The serial gate lets only stored functions differ between the bootstrap
    # tenant (hardening) and a provisioned one (template), so the draft invoice
    # patch must stay byte-identical in all three places.
    "draft invoice SQL is folded byte-identically into the template and the hardening file":
        read("tenancy/sql/add_draft_invoices.sql") in read("tenancy/sql/tenant_template.sql")
        and read("tenancy/sql/add_draft_invoices.sql") in read("tenancy/sql/production_hardening.sql"),
    "bootstrap tenant business schema is byte-identical to the reviewed 2026-09-16 baseline":
        hashlib.sha256(bootstrap_tenant_section.encode()).hexdigest()
        == "b72da12191984c2c262b8e395403ffac8fe6a5930239589f4b35a289a4d7d2e3",
    "bootstrap no longer defeats the serial-only squashed migration":
        "CREATE TABLE IF NOT EXISTS public.tenancy_company" not in bootstrap
        and "'tenancy', '0001_initial'" not in bootstrap
        and "INSERT INTO public.tenancy_company" not in bootstrap
        and "register_bootstrap_tenant" in bootstrap,
    "first-boot tenant registration runs after migrate and cannot touch tenants":
        "register_bootstrap_tenant" in entrypoint
        and entrypoint.index("manage.py migrate")
        < entrypoint.index("register_bootstrap_tenant")
        and "Company.objects.exists()" in read(
            "tenancy/management/commands/register_bootstrap_tenant.py"),
    "quantity HTTP adapter and route modules are absent":
        all(not (ROOT / path).exists() for path in RUNTIME_FILES),
    "quantity templates and static assets are absent":
        all(not (ROOT / path).exists() for path in UI_FILES),
    "root and app URL configurations expose no quantity routes":
        "quantity" not in urls
        and "warehouse_urls" not in urls
        and "transfer_urls" not in urls
        and "count_urls" not in urls,
    "business views import no quantity adapter or dispatcher":
        "quantity_views" not in business_views
        and "dispatch_inventory_view" not in business_views,
    "business views execute no quantity SQL or templates":
        "quantity_" not in business_views,
    "serial document wrappers retain the trusted request boundary":
        business_views.count("return serial_inventory_view") == 12
        and "reject_non_serial_payload(payload)" in capabilities,
    "capability module contains no quantity runtime catalogue or parser":
        "INVENTORY_MODE_QUANTITY" not in capabilities
        and "parse_quantity_payload" not in capabilities
        and "reject_serial_payload" not in capabilities,
    "schema-family registry describes the serial family only":
        "INVENTORY_MODE_QUANTITY" not in families
        and "quantity" not in families.lower()
        and "SERIAL_SCHEMA_FAMILY" in families
        and "Unsupported schema family" in families,
    "middleware still fails closed on schema verification alone":
        "request.tenant_is_active = verification.ok" in middleware
        and "runtime_enabled" not in middleware
        and "enabled_path_prefixes" not in middleware
        and "schema_family" not in middleware,
    "tenant SQL rollout command accepts serial only":
        "choices=[SERIAL_SCHEMA_FAMILY]" in rollout
        and "Only serial tenant SQL rollout is supported" in rollout
        and "inventory_mode" not in rollout
        and "quantity" not in rollout.lower(),
    "container startup performs serial SQL maintenance only":
        "--family serial" in entrypoint
        and "--family quantity" not in entrypoint
        and "quantity_reports_dashboards.sql" not in entrypoint
        and "quantity_platform_controls.sql" not in entrypoint,
    "release preflight accepts and probes serial only":
        'choices=("serial",)' in preflight
        and "SERIAL_SCHEMA_FAMILY" in preflight
        and "inventory_mode" not in preflight
        and "quantity_run_report" not in preflight
        and "SELECT get_trial_balance_json()" in preflight,
    "serial feature registry exposes no retired controls":
        "quantity_controls" not in features
        and "purchase_reports" not in features,
    "security path map contains no retired route permissions":
        "/quantity-reports/" not in security
        and "/warehouses/quantity/" not in security
        and "/physical-counts/" not in security,
    "serial attachment lookup contains no schema-family fallback":
        "QUANTITY_DOCUMENT_CONFIG" not in attachments
        and "manage_quantity_attachments" not in attachments,
    "shared base template has no quantity branch, link or inventory-mode badge":
        "is_quantity_company" not in base
        and "quantity_" not in base
        and "Quantity Reports" not in base
        and "inventory_mode" not in base,
    "sidebar Sales Reports link accepts every SALES_REPORT_PERMS entry":
        bool(sales_report_perms)
        and all(f"perms.{perm}" in sales_sidebar_condition
                for perm in sales_report_perms)
        and "..." not in sales_sidebar_condition,
    "quantity SQL and the replaced migration history are both retired":
        not any((ROOT / "tenancy/sql").glob("quantity_*.sql"))
        # Checkpoint 4B removed the replaced files; only the squashed
        # serial-only migration remains in each app.
        and sorted(p.name for p in (ROOT / "tenancy/migrations").glob("*.py"))
        == ["0001_serial_only.py", "__init__.py"]
        and sorted(p.name for p in (ROOT / "authentication/migrations").glob("*.py"))
        == ["0001_serial_only.py", "__init__.py"],
    "mandatory Phase 2 local and CI gates are wired":
        "phase2_serial_runtime_removal_contracts.py" in workflow
        and "runtime-removal-gate:" in workflow
        and "phase2_serial_runtime_removal.py" in stack
        and "phase2_serial_runtime_removal.py" in suite,
    "test cleanup is confined to a uniquely named disposable Compose project":
        '--project-name "$test_project"' in stack
        and 'test_project="phase27_' in stack
        and 'cat > "$WEB_ENV_FILE"' in stack
        and "deploy/.env" not in stack,
    "one-shot generated static retirement is itself fully retired":
        "retire_quantity_static" not in entrypoint
        and not (ROOT / "deploy/retire_quantity_static.py").exists()
        and "test_phase2_static_retirement" not in workflow,
    "protected exact-SHA production workflow remains intact":
        "environment: production" in workflow
        and "PHASE30_RELEASE_SHA='${{ github.sha }}'" in workflow,
}

failed = [name for name, passed in checks.items() if not passed]
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
print(f"{len(checks) - len(failed)}/{len(checks)} Phase 2 contracts passed")
raise SystemExit(1 if failed else 0)
