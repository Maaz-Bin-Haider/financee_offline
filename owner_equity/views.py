import json
from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required

PERM = "auth.can_manage_owner_equity"


@login_required
def owner_equity_page(request):
    """Render the Owner Equity page (same shell/UI as the other sections)."""
    if not request.user.has_perm(PERM):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    return render(request, "owner_equity_templates/owner_equity_template.html")


@login_required
def get_owner_equity(request):
    """Return recent owner-equity transactions plus totals."""
    if not request.user.has_perm(PERM):
        return JsonResponse({"transactions": []}, status=403)
    with connection.cursor() as cursor:
        cursor.execute("SELECT get_owner_equity_json(%s);", [100])
        row = cursor.fetchone()
    data = row[0] if row and row[0] else {"transactions": []}
    if isinstance(data, str):
        data = json.loads(data)
    return JsonResponse(data, safe=False)


@login_required
def get_equity_accounts(request):
    """List Equity-type accounts for the account dropdown (default: Owner's Capital)."""
    if not request.user.has_perm(PERM):
        return JsonResponse({"accounts": []}, status=403)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT account_name FROM chartofaccounts "
            "WHERE account_type = 'Equity' ORDER BY account_code;"
        )
        names = [r[0] for r in cursor.fetchall()]
    return JsonResponse({"accounts": names}, safe=False)


@login_required
def add_owner_equity(request):
    """Record an owner withdrawal or capital injection (posts a no-party journal entry)."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    if not request.user.has_perm(PERM):
        return JsonResponse(
            {"status": "error", "message": "You do not have permission to manage owner equity."},
            status=403,
        )

    try:
        body = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        body = {}

    direction = (body.get("direction") or "").strip().lower()
    if direction not in ("withdrawal", "injection"):
        return JsonResponse({"status": "error", "message": "direction must be withdrawal or injection."}, status=400)

    try:
        amount = float(body.get("amount"))
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "message": "A valid 'amount' is required."}, status=400)
    if amount <= 0:
        return JsonResponse({"status": "error", "message": "Amount must be greater than 0."}, status=400)

    payload = json.dumps({
        "direction": direction,
        "amount": amount,
        "txn_date": body.get("txn_date") or "",
        "equity_account": body.get("equity_account") or "",
        "description": body.get("description") or "",
        "created_by_id": request.user.id,
    })

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT add_owner_equity_txn(%s::jsonb);", [payload])
            row = cursor.fetchone()
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

    data = row[0] if row and row[0] else {}
    if isinstance(data, str):
        data = json.loads(data)
    return JsonResponse({"status": "success", "result": data})


@login_required
def delete_owner_equity(request):
    """Delete a transaction and its journal entry."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    if not request.user.has_perm(PERM):
        return JsonResponse({"status": "error", "message": "Permission denied."}, status=403)

    try:
        body = json.loads(request.body or "{}")
        txn_id = int(body.get("txn_id"))
    except (ValueError, TypeError):
        return JsonResponse({"status": "error", "message": "A valid 'txn_id' is required."}, status=400)

    with connection.cursor() as cursor:
        cursor.execute("SELECT delete_owner_equity_txn(%s);", [txn_id])
        row = cursor.fetchone()
    data = row[0] if row and row[0] else {}
    if isinstance(data, str):
        data = json.loads(data)
    status = 200 if data.get("status") == "success" else 404
    return JsonResponse(data, status=status)
