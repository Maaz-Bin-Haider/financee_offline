"""Draft sale invoice (proforma) endpoints.

A draft reserves specific serial numbers for a named customer and moves
nothing else: no stock, no journal, no balance. Converting a tranche of it
raises a real sale invoice.

Every write goes through a stored procedure in the tenant schema
(tenancy/sql/add_draft_invoices.sql), like the rest of this system. The
procedures raise curated P0001 messages that ``user_db_error`` passes straight
to the browser; any other database error becomes a generic fallback so
internal detail never leaks.

The one endpoint that moves money -- ``convert_draft`` -- does so through
``convert_draft_tranche``, which delegates to ``create_sale``. There remains
exactly one function in this system that creates a sale and its journal.

TenantSchemaMiddleware has already activated the user's company and applied
the per-company ``draft_invoices`` feature flag before any view here runs.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from draft.feature import draft_age_warning_days, draft_sales_enabled
from financee.db_errors import user_db_error


# ---------------------------------------------------------------------------
# Shared guards
# ---------------------------------------------------------------------------

def _feature_off():
    """404 before any cursor opens, so a switched-off feature does not confirm
    that the endpoint exists."""
    return JsonResponse(
        {"success": False, "message": "Draft invoices are currently switched off."},
        status=404,
    )


def _denied(message):
    return JsonResponse({"success": False, "message": message}, status=403)


def _view_only(request):
    """The project's long-standing read-only group."""
    return request.user.groups.filter(name="view_only_users").exists()


def _guard(request, permission, action):
    """Return a response when the request may not proceed, otherwise None.

    The deployment switch is checked before the permission, so a disabled
    feature is a 404 rather than a 403. The read-only group is refused every
    draft action, reads included.
    """
    if not draft_sales_enabled():
        return _feature_off()
    if _view_only(request):
        return _denied(f"You do not have permission to {action}")
    if not request.user.has_perm(f"auth.{permission}"):
        return _denied(f"You do not have permission to {action}")
    return None


class _BadPayload(ValueError):
    pass


def _payload(request):
    """Parse a JSON body, falling back to form data as the other screens do."""
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            raise _BadPayload("Invalid request data.")
        if not isinstance(data, dict):
            raise _BadPayload("Invalid request data.")
        return data
    return request.POST.dict()


def _json_list(value):
    """A list that may arrive as a JSON string from a form post."""
    if isinstance(value, str):
        try:
            value = json.loads(value or "[]")
        except json.JSONDecodeError:
            raise _BadPayload("Invalid request data.")
    return value


def _json_or_none(value):
    """psycopg2 returns json already decoded; Django returns jsonb as text."""
    if isinstance(value, str):
        return json.loads(value)
    return value


def _positive_int(value, field):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number.")
    if number <= 0:
        raise ValueError(f"{field} must be greater than zero.")
    return number


def _date_range(data):
    start = (data.get("start_date") or "").strip() or None
    end = (data.get("end_date") or "").strip() or None
    return start, end


def _page_context(request):
    company = getattr(request, "tenant_company", None)
    return {
        "currency": getattr(company, "base_currency_id", None) or "PKR",
        "age_warning_days": draft_age_warning_days(),
    }


def _page(request, permission, denied_message, template):
    """A screen: redirect away (as every other screen here does) when the
    feature is off or the permission is missing."""
    if not draft_sales_enabled():
        messages.error(request, "Draft invoices are currently switched off.")
        return redirect("home:home")
    if not request.user.has_perm(f"auth.{permission}"):
        messages.error(request, denied_message)
        return redirect("home:home")
    return render(request, template, _page_context(request))


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

@login_required
@require_GET
def draft_page(request):
    return _page(request, "view_draft_invoice",
                 "You do not have permission to view Draft Invoices!",
                 "draft_templates/draft_template.html")


@login_required
@require_GET
def convert_page(request):
    """Gated on confirm_draft_invoice rather than view_draft_invoice: somebody
    who may reserve goods is not thereby somebody who may decide what they sell
    for."""
    return _page(request, "confirm_draft_invoice",
                 "You do not have permission to confirm Draft Invoices!",
                 "draft_templates/convert_template.html")


@login_required
@require_GET
def draft_return_page(request):
    return _page(request, "view_draft_return",
                 "You do not have permission to view Confirmed Draft Returns!",
                 "draft_templates/draft_return_template.html")


@login_required
@require_GET
def pending_report_page(request):
    return _page(request, "view_pending_drafts_report",
                 "You do not have permission to open the Pending Drafts Report!",
                 "draft_templates/pending_report_template.html")


# ---------------------------------------------------------------------------
# Draft invoice: create, update, delete, release, cancel
# ---------------------------------------------------------------------------

@login_required
@require_POST
def save_draft(request):
    """Create a draft, or rewrite one that has had nothing invoiced yet."""
    try:
        data = _payload(request)
        items = _json_list(data.get("items"))
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)

    raw_id = data.get("draft_invoice_id")
    if isinstance(raw_id, str):
        raw_id = raw_id.strip()
    permission = "update_draft_invoice" if raw_id else "create_draft_invoice"
    action = "Update a Draft Invoice" if raw_id else "Create a Draft Invoice"
    denied = _guard(request, permission, action)
    if denied:
        return denied

    draft_id = None
    if raw_id:
        try:
            draft_id = _positive_int(raw_id, "Draft invoice")
        except ValueError as exc:
            return JsonResponse({"success": False, "message": str(exc)})

    party_name = (data.get("party_name") or "").strip()
    draft_date = (data.get("draft_date") or "").strip()
    if not party_name:
        return JsonResponse({"success": False, "message": "Please select a customer."})
    if not draft_date:
        return JsonResponse({"success": False, "message": "Draft date is required."})
    if not items or not isinstance(items, list):
        return JsonResponse({"success": False, "message": "At least one item is required."})

    description = (data.get("description") or "").strip() or None

    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT party_id FROM Parties WHERE party_name = %s", [party_name])
            row = cursor.fetchone()
            if not row:
                return JsonResponse(
                    {"success": False, "message": f"Party '{party_name}' not found in Parties."})
            party_id = row[0]

            if draft_id:
                cursor.execute(
                    "SELECT update_draft(%s::bigint, %s::jsonb, %s::bigint, %s::date, %s)",
                    [draft_id, json.dumps(items), party_id, draft_date, request.user.id])
                saved_id = draft_id
            else:
                cursor.execute(
                    "SELECT create_draft(%s::bigint, %s::date, %s::jsonb, %s)",
                    [party_id, draft_date, json.dumps(items), request.user.id])
                saved_id = cursor.fetchone()[0]

            cursor.execute(
                "UPDATE DraftInvoices SET description = %s WHERE draft_invoice_id = %s",
                [description, saved_id])

        created = not draft_id
        return JsonResponse({
            "success": True,
            "draft_invoice_id": saved_id,
            "created": created,
            "message": (f"Draft invoice #{saved_id} saved."
                        if created else f"Draft invoice #{saved_id} updated."),
        })
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to save the draft invoice, try again!")})


def _draft_id_from(request):
    """(draft_id, payload, None) on success, or (None, None, error response)."""
    try:
        data = _payload(request)
    except _BadPayload as exc:
        return None, None, JsonResponse({"success": False, "message": str(exc)}, status=400)
    try:
        return _positive_int(data.get("draft_invoice_id"), "Draft invoice"), data, None
    except ValueError as exc:
        return None, None, JsonResponse({"success": False, "message": str(exc)})


@login_required
@require_POST
def delete_draft(request):
    denied = _guard(request, "delete_draft_invoice", "Delete a Draft Invoice")
    if denied:
        return denied
    draft_id, _, error = _draft_id_from(request)
    if error:
        return error

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT delete_draft(%s::bigint)", [draft_id])
        return JsonResponse({"success": True, "message": "Draft invoice deleted."})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to delete the draft invoice, try again!")})


@login_required
@require_POST
def release_units(request):
    """Take named serials off a draft, returning them to free stock."""
    denied = _guard(request, "update_draft_invoice", "Update a Draft Invoice")
    if denied:
        return denied
    draft_id, data, error = _draft_id_from(request)
    if error:
        return error
    try:
        serials = _json_list(data.get("serials"))
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    if not serials or not isinstance(serials, list):
        return JsonResponse(
            {"success": False, "message": "Select at least one serial number to release."})

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT release_draft_units(%s::bigint, %s::jsonb, %s)",
                           [draft_id, json.dumps(serials), request.user.id])
            released = cursor.fetchone()[0]
        return JsonResponse({"success": True, "released": released,
                             "message": f"{released} serial(s) released."})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to release the serial numbers, try again!")})


@login_required
@require_POST
def cancel_draft(request):
    """Release everything still reserved and close the draft."""
    denied = _guard(request, "delete_draft_invoice", "Cancel a Draft Invoice")
    if denied:
        return denied
    draft_id, _, error = _draft_id_from(request)
    if error:
        return error

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cancel_draft(%s::bigint, %s)", [draft_id, request.user.id])
            released = cursor.fetchone()[0]
        return JsonResponse({"success": True, "released": released,
                             "message": f"Draft cancelled; {released} serial(s) released."})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to cancel the draft invoice, try again!")})


# ---------------------------------------------------------------------------
# Conversion -- the only endpoint here that moves money
# ---------------------------------------------------------------------------

@login_required
@require_POST
def convert_draft(request):
    """Turn a tranche of a draft into a real, credit sale invoice.

    Gated on confirm_draft_invoice, separate from create_draft_invoice:
    reserving goods and agreeing what they sell for are different jobs.
    """
    denied = _guard(request, "confirm_draft_invoice",
                    "Set Final Rates and Confirm a Draft Invoice")
    if denied:
        return denied
    draft_id, data, error = _draft_id_from(request)
    if error:
        return error
    try:
        items = _json_list(data.get("items"))
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    invoice_date = (data.get("invoice_date") or "").strip()

    if not items or not isinstance(items, list):
        return JsonResponse(
            {"success": False,
             "message": "Select at least one serial number to convert into a sale invoice."})
    if not invoice_date:
        return JsonResponse({"success": False, "message": "Sale date is required."})

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT convert_draft_tranche(%s::bigint, %s::jsonb, %s::date, %s)",
                [draft_id, json.dumps(items), invoice_date, request.user.id])
            invoice_id = cursor.fetchone()[0]
        return JsonResponse({"success": True, "sales_invoice_id": invoice_id,
                             "message": f"Sale invoice {invoice_id} created from this draft."})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to convert the draft invoice, try again!")})


# ---------------------------------------------------------------------------
# Draft invoice: read paths
# ---------------------------------------------------------------------------

_DRAFT_NAVIGATION = {
    "current": "SELECT get_current_draft(%s::bigint)",
    "previous": "SELECT get_previous_draft(%s::bigint)",
    "next": "SELECT get_next_draft(%s::bigint)",
}


@login_required
@require_GET
def get_draft(request):
    """Navigate drafts. ?nav=last|current|previous|next and ?draft_invoice_id="""
    denied = _guard(request, "view_draft_invoice", "View Draft Invoices")
    if denied:
        return denied

    nav = (request.GET.get("nav") or "current").strip().lower()
    if nav not in ("last", "current", "previous", "next"):
        return JsonResponse({"success": False, "message": "Unknown navigation direction."})

    try:
        with connection.cursor() as cursor:
            if nav == "last":
                cursor.execute("SELECT get_last_draft_id()")
                last_id = cursor.fetchone()[0]
                if last_id is None:
                    return JsonResponse({"success": True, "draft": None})
                cursor.execute(_DRAFT_NAVIGATION["current"], [last_id])
            else:
                try:
                    draft_id = _positive_int(
                        request.GET.get("draft_invoice_id"), "Draft invoice")
                except ValueError as exc:
                    return JsonResponse({"success": False, "message": str(exc)})
                cursor.execute(_DRAFT_NAVIGATION[nav], [draft_id])
            row = cursor.fetchone()
        return JsonResponse({"success": True, "draft": _json_or_none(row[0] if row else None)})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to load the draft invoice, try again!")})


@login_required
@require_POST
def draft_summary(request):
    denied = _guard(request, "view_draft_invoice", "View Draft Invoices")
    if denied:
        return denied
    try:
        start, end = _date_range(_payload(request))
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT get_draft_summary(%s::date, %s::date)", [start, end])
            row = cursor.fetchone()
        return JsonResponse({"success": True, "drafts": _json_or_none(row[0]) or []})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to load draft invoices, try again!")})


@login_required
@require_POST
def serial_lookup(request):
    """What a serial is, and whether it can be reserved: does it exist, is it
    in stock, and is it already held for somebody else."""
    denied = _guard(request, "view_draft_invoice", "View Draft Invoices")
    if denied:
        return denied
    try:
        serial = (_payload(request).get("serial") or "").strip()
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    if not serial:
        return JsonResponse({"success": False, "message": "Serial number is required."})

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT item_name, in_stock, purchase_price, current_status, "
                "       is_reserved, reserved_for, reserved_draft_id "
                "FROM get_serial_number_details(%s)", [serial])
            row = cursor.fetchone()
        if not row:
            return JsonResponse({"success": False, "message": f"Serial '{serial}' not found."})

        item_name, in_stock, purchase_price, status, reserved, reserved_for, draft_id = row
        if reserved:
            return JsonResponse({
                "success": False,
                "reserved": True,
                "reserved_for": reserved_for,
                "reserved_draft_id": draft_id,
                "message": f'Serial "{serial}" is already reserved for '
                           f'"{reserved_for}" on draft invoice #{draft_id}.',
            })
        if not in_stock:
            return JsonResponse({
                "success": False,
                "message": f'Serial "{serial}" is not available in stock, so it '
                           f'cannot be reserved. It may already be sold or returned '
                           f'to the vendor.',
            })
        return JsonResponse({
            "success": True,
            "serial": serial,
            "item_name": item_name,
            "purchase_price": float(purchase_price) if purchase_price is not None else None,
            "current_status": status,
        })
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, f"Invalid serial number '{serial}'.")})


# ---------------------------------------------------------------------------
# Pending drafts report
# ---------------------------------------------------------------------------

@login_required
@require_POST
def pending_report(request):
    denied = _guard(request, "view_pending_drafts_report", "Open the Pending Drafts Report")
    if denied:
        return denied
    try:
        start, end = _date_range(_payload(request))
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT draft_pending_report(%s::date, %s::date, %s::integer)",
                           [start, end, draft_age_warning_days()])
            row = cursor.fetchone()
        return JsonResponse(_json_or_none(row[0]), safe=False)
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to build the pending drafts report.")})


# ---------------------------------------------------------------------------
# Confirmed draft return
# ---------------------------------------------------------------------------

@login_required
@require_POST
def save_draft_return(request):
    try:
        data = _payload(request)
        serials = _json_list(data.get("serials"))
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)

    raw_id = data.get("draft_return_id")
    if isinstance(raw_id, str):
        raw_id = raw_id.strip()
    permission = "update_draft_return" if raw_id else "create_draft_return"
    action = ("Update a Confirmed Draft Return" if raw_id
              else "Create a Confirmed Draft Return")
    denied = _guard(request, permission, action)
    if denied:
        return denied

    return_id = None
    if raw_id:
        try:
            return_id = _positive_int(raw_id, "Confirmed draft return")
        except ValueError as exc:
            return JsonResponse({"success": False, "message": str(exc)})

    party_name = (data.get("party_name") or "").strip()
    return_date = (data.get("return_date") or "").strip()
    description = (data.get("description") or "").strip() or None

    if not serials or not isinstance(serials, list):
        return JsonResponse(
            {"success": False, "message": "At least one serial number is required."})
    # Validated here and again in the procedure: the date must reach the books.
    if not return_date:
        return JsonResponse({"success": False, "message": "Return date is required."})
    if not return_id and not party_name:
        return JsonResponse({"success": False, "message": "Please select a customer."})

    try:
        with transaction.atomic(), connection.cursor() as cursor:
            if return_id:
                cursor.execute(
                    "SELECT update_draft_return(%s::bigint, %s::jsonb, %s::date, %s)",
                    [return_id, json.dumps(serials), return_date, request.user.id])
                saved_id = return_id
            else:
                cursor.execute(
                    "SELECT create_draft_return(%s, %s::jsonb, %s::date, %s)",
                    [party_name, json.dumps(serials), return_date, request.user.id])
                saved_id = cursor.fetchone()[0]
            # The accounting document is the SalesReturns row, so the note lives
            # there -- where the party and detailed ledgers already read it.
            cursor.execute(
                "UPDATE SalesReturns SET description = %s WHERE draft_return_id = %s",
                [description, saved_id])

        created = not return_id
        return JsonResponse({
            "success": True,
            "draft_return_id": saved_id,
            "created": created,
            "message": (f"Confirmed draft return #{saved_id} saved."
                        if created else f"Confirmed draft return #{saved_id} updated."),
        })
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to save the confirmed draft return, try again!")})


@login_required
@require_POST
def delete_draft_return(request):
    denied = _guard(request, "delete_draft_return", "Delete a Confirmed Draft Return")
    if denied:
        return denied
    try:
        return_id = _positive_int(_payload(request).get("draft_return_id"),
                                  "Confirmed draft return")
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    except ValueError as exc:
        return JsonResponse({"success": False, "message": str(exc)})

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT delete_draft_return(%s::bigint)", [return_id])
        return JsonResponse({"success": True, "message": "Confirmed draft return deleted."})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to delete the confirmed draft return, try again!")})


_RETURN_NAVIGATION = {
    "current": "SELECT get_current_draft_return(%s::bigint)",
    "previous": "SELECT get_previous_draft_return(%s::bigint)",
    "next": "SELECT get_next_draft_return(%s::bigint)",
}


@login_required
@require_GET
def get_draft_return(request):
    denied = _guard(request, "view_draft_return", "View Confirmed Draft Returns")
    if denied:
        return denied

    nav = (request.GET.get("nav") or "current").strip().lower()
    if nav not in ("last", "current", "previous", "next"):
        return JsonResponse({"success": False, "message": "Unknown navigation direction."})

    try:
        with connection.cursor() as cursor:
            if nav == "last":
                cursor.execute("SELECT get_last_draft_return_id()")
                last_id = cursor.fetchone()[0]
                if last_id is None:
                    return JsonResponse({"success": True, "draft_return": None})
                cursor.execute(_RETURN_NAVIGATION["current"], [last_id])
            else:
                try:
                    return_id = _positive_int(
                        request.GET.get("draft_return_id"), "Confirmed draft return")
                except ValueError as exc:
                    return JsonResponse({"success": False, "message": str(exc)})
                cursor.execute(_RETURN_NAVIGATION[nav], [return_id])
            row = cursor.fetchone()
        return JsonResponse(
            {"success": True, "draft_return": _json_or_none(row[0] if row else None)})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to load the confirmed draft return, try again!")})


@login_required
@require_POST
def draft_return_summary(request):
    denied = _guard(request, "view_draft_return", "View Confirmed Draft Returns")
    if denied:
        return denied
    try:
        start, end = _date_range(_payload(request))
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT get_draft_return_summary(%s::date, %s::date)", [start, end])
            row = cursor.fetchone()
        return JsonResponse({"success": True, "returns": _json_or_none(row[0]) or []})
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, "Failed to load confirmed draft returns, try again!")})


@login_required
@require_POST
def draft_return_lookup(request):
    """Whether a serial may be returned on this document, and at what price.

    A serial sold on an ordinary invoice belongs on the Sale Return screen; the
    database refuses it here either way, but saying so before the attempt is
    better than surfacing the refusal afterwards.
    """
    denied = _guard(request, "view_draft_return", "View Confirmed Draft Returns")
    if denied:
        return denied
    try:
        serial = (_payload(request).get("serial") or "").strip()
    except _BadPayload as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    if not serial:
        return JsonResponse({"success": False, "message": "Serial number is required."})

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT d.item_name, d.sold_price, d.customer_name, d.current_status, "
                "       (si.draft_invoice_id IS NOT NULL) AS from_draft, si.draft_invoice_id, "
                "       d.is_reserved, d.reserved_for, d.reserved_draft_id "
                "FROM get_serial_number_details(%s) d "
                "LEFT JOIN SalesInvoices si ON si.sales_invoice_id = d.sales_invoice_id",
                [serial])
            row = cursor.fetchone()
        if not row:
            return JsonResponse({"success": False, "message": f"Serial '{serial}' not found."})

        (item_name, sold_price, customer, status, from_draft, draft_id,
         reserved, reserved_for, reserved_draft_id) = row
        if reserved:
            return JsonResponse({
                "success": False,
                "message": f'Serial "{serial}" is reserved on draft invoice '
                           f'#{reserved_draft_id} for "{reserved_for}", not sold, so there '
                           f'is nothing to return. Use Release Serials on the Draft '
                           f'Invoices screen instead.',
            })
        if status != "Sold":
            return JsonResponse({
                "success": False,
                "message": f'Serial "{serial}" is not currently sold, so it cannot be returned.',
            })
        if not from_draft:
            return JsonResponse({
                "success": False,
                "message": f'Serial "{serial}" was sold on an ordinary sale invoice, '
                           f'not from a draft. Use the Sale Return screen to return it.',
            })
        return JsonResponse({
            "success": True,
            "serial": serial,
            "item_name": item_name,
            "sold_price": float(sold_price) if sold_price is not None else None,
            "customer_name": customer,
            "draft_invoice_id": draft_id,
        })
    except Exception as exc:
        return JsonResponse(
            {"success": False,
             "message": user_db_error(exc, f"Invalid serial number '{serial}'.")})
