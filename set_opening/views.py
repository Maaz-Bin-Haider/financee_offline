import json
from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required

PERM = "auth.can_set_or_update_opening"


@login_required
def set_opening_page(request):
    """Render the Set Opening section page (same shell/UI as Accounts Reports)."""
    if not request.user.has_perm(PERM):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    return render(request, "set_opening_templates/set_opening_template.html")


@login_required
def get_opening_cash(request):
    """Return the company's current opening cash-in-hand."""
    if not request.user.has_perm(PERM):
        return JsonResponse({"amount": 0, "is_set": False}, status=403)
    with connection.cursor() as cursor:
        cursor.execute("SELECT get_opening_cash_json();")
        row = cursor.fetchone()
    data = row[0] if row and row[0] else {"amount": 0, "is_set": False}
    if isinstance(data, str):
        data = json.loads(data)
    return JsonResponse(data, safe=False)


@login_required
def set_opening_cash(request):
    """Set / update the company's opening cash-in-hand.

    Posts a balanced journal entry (Debit Cash / Credit Owner's Capital) via
    set_opening_cash_from_json(); idempotent on edits (no double counting).
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    if not request.user.has_perm(PERM):
        return JsonResponse(
            {"status": "error", "message": "You do not have permission to set opening values."},
            status=403,
        )

    raw = request.POST.get("amount", None)
    if raw is None:
        try:
            raw = json.loads(request.body or "{}").get("amount")
        except (ValueError, TypeError):
            raw = None
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "message": "A valid 'amount' is required."}, status=400)
    if amount < 0:
        return JsonResponse({"status": "error", "message": "Opening cash cannot be negative."}, status=400)

    payload = json.dumps({"amount": amount, "created_by_id": request.user.id})
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_opening_cash_from_json(%s::jsonb);", [payload])
        row = cursor.fetchone()
    data = row[0] if row and row[0] else {}
    if isinstance(data, str):
        data = json.loads(data)
    return JsonResponse({"status": "success", "opening_cash": data})
