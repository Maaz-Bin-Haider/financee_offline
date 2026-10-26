"""Serial-only request boundary helpers."""

from __future__ import annotations

import json
from django.http import JsonResponse

NON_SERIAL_PAYLOAD_KEYS = frozenset({
    "variant_id", "warehouse_id", "source_warehouse_id",
    "destination_warehouse_id", "source_sale_line_id",
    "source_purchase_line_id", "counted_quantity",
})


def serial_inventory_view(request, view, *args, **kwargs):
    """Run a serial view only when middleware resolved a trusted company."""
    company = getattr(request, "tenant_company", None)
    if company is not None:
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                payload = _request_payload(request)
                reject_non_serial_payload(payload)
            except ValueError as exc:
                return JsonResponse(
                    {"status": "error", "message": str(exc)}, status=400
                )
        return view(request, *args, **kwargs)
    return JsonResponse(
        {"status": "denied", "message": "No supported company type is active."},
        status=403,
    )


def reject_non_serial_payload(payload):
    """Reject identifiers belonging to the retired non-serial API shape."""
    if not isinstance(payload, dict):
        raise ValueError("A valid JSON object is required.")

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in NON_SERIAL_PAYLOAD_KEYS:
                    raise ValueError(
                        "Unsupported inventory fields are unavailable."
                    )
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return payload


def _request_payload(request):
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        raw = request.POST.get("payload") or "{}"
    else:
        raw = request.body or b"{}"
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("A valid JSON object is required.") from exc
    return value
