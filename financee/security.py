import functools
import logging
import time

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render


logger = logging.getLogger(__name__)


PROTECTED_PREFIX_PERMS = (
    ("/sale/", ("auth.view_sale",)),
    ("/purchase/", ("auth.view_purchase",)),
    ("/payments/", ("auth.view_payment",)),
    ("/receipts/", ("auth.view_receipt",)),
    ("/items/", ("auth.view_item",)),
    ("/parties/", ("auth.view_party",)),
    ("/saleReturn/", ("auth.view_sale_return",)),
    ("/purchaseReturn/", ("auth.view_purchase_return",)),
    ("/contra/", ("auth.view_contra_entry",)),
    ("/opening-stock/", ("auth.view_opening_stock",)),
    ("/owner-equity/", ("auth.can_manage_owner_equity",)),
    ("/month-close/", ("auth.can_close_period",)),
    ("/set-opening/", ("auth.can_set_or_update_opening",)),
)

SALES_REPORT_PERMS = (
    "auth.can_view_sales_summary",
    "auth.can_view_product_profitability",
    "auth.can_view_customer_profitability",
    "auth.can_view_sales_by_product",
    "auth.can_view_sales_by_customer",
    "auth.can_view_sale_wise_profit",
    "auth.can_view_sales_trend",
    "auth.can_view_invoice_register",
)



def is_ajax_or_api(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.path.startswith(("/home/api/", "/sales-reports/api/"))
        or request.path.startswith("/spotlight/")
        or "/api/" in request.path
        or request.path.endswith((".json",))
    )


def deny_response(request, message="Access denied.", status=403):
    if is_ajax_or_api(request):
        return JsonResponse({"status": "denied", "message": message}, status=status)
    return redirect("home:home")


def required_permissions_for_path(path):
    if path.startswith("/sales-reports/"):
        return SALES_REPORT_PERMS, "any"
    for prefix, perms in PROTECTED_PREFIX_PERMS:
        if path.startswith(prefix):
            return perms, "all"
    return (), "all"


def has_required_permissions(user, perms, mode="all"):
    if not perms:
        return True
    if mode == "any":
        return any(user.has_perm(perm) for perm in perms)
    return all(user.has_perm(perm) for perm in perms)


def safe_json_error(message="An unexpected error occurred.", status=500):
    return JsonResponse({"status": "error", "message": message}, status=status)


def log_and_safe_json_error(exc, public_message="An unexpected error occurred.", status=500):
    logger.exception("Request failed: %s", exc)
    return safe_json_error(public_message, status=status)


def _rate_limit_key(request, key_prefix, bucket):
    """Build a cache key whose quota cannot leak between tenant companies."""
    identity = (
        getattr(request.user, "pk", None)
        or request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", "unknown")
    )
    return f"rl:{key_prefix}:local:{identity}:{bucket}"


def rate_limit(key_prefix, limit=60, window=60, methods=None):
    """
    Lightweight per-process/cache rate limiter.

    It is deliberately small and dependency-free. In multi-process production,
    configure a shared Django cache such as Redis so limits apply across workers.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if methods is not None and request.method.upper() not in methods:
                return view_func(request, *args, **kwargs)
            bucket = int(time.time() // window)
            key = _rate_limit_key(request, key_prefix, bucket)
            current = cache.get(key, 0)
            if current >= limit:
                return JsonResponse(
                    {"status": "error", "message": "Too many requests. Try again shortly."},
                    status=429,
                )
            cache.set(key, current + 1, timeout=window + 5)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def user_has_local_access(user):
    return bool(user and user.is_authenticated and user.is_active)


def rate_limit_response(request, key_prefix, limit=60, window=60):
    bucket = int(time.time() // window)
    key = _rate_limit_key(request, key_prefix, bucket)
    current = cache.get(key, 0)
    if current >= limit:
        return JsonResponse(
            {"status": "error", "message": "Too many requests. Try again shortly."},
            status=429,
        )
    cache.set(key, current + 1, timeout=window + 5)
    return None
