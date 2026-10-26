"""The Team Activity endpoints (TEAM_ACTIVITY_PLAN.md).

team_activity_page, user_year, user_day -- Phase 4: the manager's page and
    the two reads behind it. Managers only (decision 4): the page redirects
    and the reads answer 403 without view_team_activity.
team, watch -- Phase 5: every account side by side, and the watch list.
record_export -- Phase 2: a download, reported by the browser that built it.
"""

import datetime
import hashlib
import json
import zoneinfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from activity import figures, queries
from spotlight.views import scope
from .links import record_links
from activity.recorder import as_id, plain, record

PERMISSION = "auth.view_team_activity"

EXPORT_FORMATS = {"pdf": "PDF", "csv": "CSV", "xlsx": "Excel"}
TITLE_LIMIT = 120
# A double-click, or a page that saves twice: the same file once.
EXPORT_REPEAT_SECONDS = 5
# Nobody downloads thirty files a minute by hand.
EXPORTS_PER_MINUTE = 30

# The watch list's rules (TEAM_ACTIVITY_PLAN.md, section 7, default 4).
WATCH_WINDOWS = (7, 30, 90)
OLD_DOCUMENT_DAYS = 30
OPENING_HOUR = 9
FAILED_SIGN_IN_BURST = 3
WATCH_LIMIT = 500
IDLE_DAYS = 7

# Where a day's event opens its record: the screen, and the link parameter it
# reads (the Spotlight plan's record links). A deleted record has no link.
LINKS = {
    "sale": ("sale:sales", "open"),
    "purchase": ("purchase:purchasing", "open"),
    "sale_return": ("saleReturn:create_sale_return", "open"),
    "purchase_return": ("purchaseReturn:create_purchase_return", "open"),
    "payment": ("payments:payment", "open"),
    "receipt": ("receipts:receipt", "open"),
    "contra": ("contra:contra", "open"),
    "draft": ("draft:draft_page", "open"),
    "draft_return": ("draft:draft_return_page", "open"),
    "party": ("parties:partiesDash", "party"),
    "item": ("items:itemsDash", "item"),
}


def _zone():
    return zoneinfo.ZoneInfo(settings.ACTIVITY_TIMEZONE)


def _today():
    return timezone.now().astimezone(_zone()).date()


def _local(moment):
    """A stored instant as the business's wall clock, to the minute."""
    if moment is None:
        return None
    return moment.astimezone(_zone()).strftime("%Y-%m-%dT%H:%M")


def _json_error(message, status):
    return JsonResponse({"error": message}, status=status)


def _export_error(message, status):
    return JsonResponse({"recorded": False, "error": message}, status=status)


def _refusal(request):
    if not request.user.is_authenticated:
        return _json_error("Your session has ended. Sign in again.", 401)
    if not request.user.has_perm(PERMISSION):
        return _json_error("You do not have permission to view team activity.", 403)
    return None


def _user(request, user_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM (' + queries.USERS + ') people WHERE id=%(user)s',
                       {'company': request.tenant_company.pk, 'user': user_id})
        row=cursor.fetchone()
    return {'id':row[0], 'username':row[1], 'active':row[2]} if row else None




@login_required
@require_GET
def team_activity_page(request):
    if not request.user.has_perm(PERMISSION):
        messages.error(request, "You do not have permission to view Team Activity!")
        return redirect("home:home")
    tz = settings.ACTIVITY_TIMEZONE
    with connection.cursor() as cursor:
        cursor.execute(queries.USERS, {'company':request.tenant_company.pk})
        users = [{"id": r[0], "username": r[1], "active": r[2]} for r in cursor.fetchall()]
        cursor.execute(queries.FIRST_YEAR, {"tz": tz})
        first = cursor.fetchone()[0]
        cursor.execute(queries.BUSIEST)
        busiest = cursor.fetchone()
    today = _today()
    years = list(range(today.year, max(2000,min(first or today.year, today.year)) - 1, -1))
    start_user = busiest[0] if busiest else (users[0]["id"] if users else None)
    return render(request, "activity_templates/team_activity.html", {
        "activity_page": {"timezone": settings.ACTIVITY_TIMEZONE, "scope": scope(request),
            "company": request.tenant_company.name, "company_id": request.tenant_company.pk,
            "users": users, "years": years, "today": today.isoformat(),
            "user": start_user, "thresholds": list(figures.THRESHOLDS),
            "urls": {"year": reverse("activity:user_year"), "day": reverse("activity:user_day"),
                     "team": reverse("activity:team"), "watch": reverse("activity:watch")},
        },
    })


@require_GET
def user_year(request):
    """A user's grid: a calendar year (?year=) or the 12 months to today."""
    refused = _refusal(request)
    if refused:
        return refused
    user = _user(request, as_id(request.GET.get("user")) or 0)
    if not user:
        return _json_error("Pick a user.", 400)
    today = _today()
    year = request.GET.get("year") or None
    if year is not None:
        try:
            year = int(year)
        except ValueError:
            return _json_error("Pick a year.", 400)
        if not 2000 <= year <= today.year:
            return _json_error("Pick a year.", 400)
    start, end = figures.period(today, year)
    params = {"tz": settings.ACTIVITY_TIMEZONE, "user": user["id"],
              "start": start.isoformat(), "end": end.isoformat()}
    with connection.cursor() as cursor:
        cursor.execute(queries.DAY_COUNTS, params)
        rows = [{"day": r[0], "work": r[1], "approximate": r[2], "sign_ins": r[3], "failed_sign_ins": r[4]}
                for r in cursor.fetchall()]
        cursor.execute(queries.DAY_MIX, params)
        mix = {}
        for day, what, n in cursor.fetchall():
            mix.setdefault(day, {})[what] = n
        cursor.execute(queries.TEAM_DAYS, params)
        team_days = [r[0] for r in cursor.fetchall()]
        cursor.execute(queries.LAST_SEEN, {"user": user["id"]})
        last_work, last_sign_in = cursor.fetchone()
        cursor.execute(queries.MIX, params)
        period_mix = [{"what": what, "n": n} for what, n in cursor.fetchall()]
        cursor.execute(queries.HOURS, params)
        hours = [[weekday, hour, n] for weekday, hour, n in cursor.fetchall()]
    days = [{
        "day": row["day"].isoformat(), "work": row["work"], "level": figures.level(row["work"]),
        "approximate": row["approximate"], "sign_ins": row["sign_ins"],
        "failed_sign_ins": row["failed_sign_ins"], "what": mix.get(row["day"], {}),
    } for row in rows]
    return JsonResponse({
        "user": user, "year": year, "start": start.isoformat(), "end": end.isoformat(),
        "today": today.isoformat(), "days": days, "mix": period_mix, "hours": hours,
        "summary": dict(figures.summary(rows, team_days, today),
                        last_work=_local(last_work), last_sign_in=_local(last_sign_in)),
    })


@require_GET
def user_day(request):
    """One day of a user's events, in order: the work, and the sign-ins."""
    refused = _refusal(request)
    if refused:
        return refused
    user = _user(request, as_id(request.GET.get("user")) or 0)
    if not user:
        return _json_error("Pick a user.", 400)
    try:
        day = datetime.date.fromisoformat(request.GET.get("date") or "")
    except ValueError:
        return _json_error("Pick a day.", 400)
    with connection.cursor() as cursor:
        cursor.execute(queries.DAY_EVENTS, {"tz": settings.ACTIVITY_TIMEZONE, "user": user["id"],
                                            "day": day.isoformat()})
        rows = cursor.fetchall()
    truncated = len(rows)>1000
    rows=rows[:1000]
    links=record_links(request,[(r[2],r[1],r[3]) for r in rows])
    work, sessions = [], []
    for local_at, action, kind, record_id, label, source, ip in rows:
        event = {"time": local_at.strftime("%H:%M"), "action": action, "kind": kind,
                 "record_id": record_id, "label": label, "source": source}
        if action in queries.SESSION_ACTIONS:
            event["ip"] = ip or ""
            sessions.append(event)
        else:
            event["href"] = links.get((kind,record_id),"") if action!="delete" else ""
            work.append(event)
    return JsonResponse({
        "user": user, "day": day.isoformat(), "work": work, "sessions": sessions, "truncated": truncated,
        "first": work[0]["time"] if work else None, "last": work[-1]["time"] if work else None,
        "approximate": any(event["source"] == "backfill" for event in work),
    })


@require_GET
def team(request):
    """Every account side by side: the last 7 and 30 days, the last work and
    sign-in, and a strip of the last 12 weeks."""
    refused = _refusal(request)
    if refused:
        return refused
    today = _today()
    this_monday = today - datetime.timedelta(days=today.weekday())
    weeks_from = this_monday - datetime.timedelta(weeks=11)
    tz = settings.ACTIVITY_TIMEZONE
    params = {"company": request.tenant_company.pk, "tz": tz, "from7": (today - datetime.timedelta(days=6)).isoformat(),
              "from30": (today - datetime.timedelta(days=29)).isoformat(),
              "weeks_from": weeks_from.isoformat()}
    with connection.cursor() as cursor:
        cursor.execute(queries.TEAM, params)
        rows = cursor.fetchall()
        cursor.execute(queries.TEAM_WEEKS, params)
        weekly = {}
        for user_id, monday, n in cursor.fetchall():
            weekly.setdefault(user_id, {})[monday] = n
    mondays = [weeks_from + datetime.timedelta(weeks=i) for i in range(12)]
    idle_from = today - datetime.timedelta(days=IDLE_DAYS - 1)
    users = []
    for user_id, username, active, last7, last30, days30, last_work, last_sign_in in rows:
        work_day = last_work.astimezone(_zone()).date() if last_work else None
        users.append({
            "id": user_id, "username": username, "active": active,
            "last7": last7, "last30": last30, "days30": days30,
            "last_work": _local(last_work), "last_sign_in": _local(last_sign_in),
            "weeks": [weekly.get(user_id, {}).get(monday, 0) for monday in mondays],
            "idle": bool(active and (work_day is None or work_day < idle_from)),
        })
    return JsonResponse({"today": today.isoformat(), "weeks": [m.isoformat() for m in mondays],
                         "idle_days": IDLE_DAYS, "users": users})


def watch_rows(params):
    """The watch list's rows (queries.WATCH), newest first. Its own function
    because it reads the document tables, which the Django test database does
    not have: the tests replace it, and system_tests run the SQL itself."""
    with connection.cursor() as cursor:
        cursor.execute(queries.WATCH, params)
        return cursor.fetchall()


@require_GET
def watch(request):
    """What a manager cannot see anywhere else, across the team: deletions,
    edits to old documents, work before opening time, failed sign-ins."""
    refused = _refusal(request)
    if refused:
        return refused
    try:
        days = int(request.GET.get("days") or 30)
    except ValueError:
        days = 0
    if days not in WATCH_WINDOWS:
        return _json_error("Pick 7, 30 or 90 days.", 400)
    today = _today()
    start = today - datetime.timedelta(days=days - 1)
    rows = watch_rows({"tz": settings.ACTIVITY_TIMEZONE, "from": start.isoformat(),
                       "old_days": OLD_DOCUMENT_DAYS, "open_hour": OPENING_HOUR,
                       "burst": FAILED_SIGN_IN_BURST, "limit": WATCH_LIMIT})
    links=record_links(request,[(r[3],"delete" if r[0]=="delete" else "update",r[4]) for r in rows])
    items = []
    for kind_of, local_at, username, kind, record_id, label, doc_date, attempts, ip in rows:
        items.append({
            "type": kind_of, "at": local_at.strftime("%Y-%m-%dT%H:%M"), "username": username,
            "kind": kind, "record_id": record_id, "label": label,
            "dated": doc_date.isoformat() if doc_date else None, "attempts": attempts,
            "ip": ip or "", "href": links.get((kind,record_id),"") if kind_of!="delete" else "",
        })
    return JsonResponse({
        "days": days, "from": start.isoformat(), "today": today.isoformat(), "items": items,
        "rules": {"old_days": OLD_DOCUMENT_DAYS, "open_hour": OPENING_HOUR,
                  "burst": FAILED_SIGN_IN_BURST, "limit": WATCH_LIMIT},
    })


# Every read has the same rate/tenant/permission/timeout boundary.
from .access import guarded
team_activity_page = guarded(team_activity_page)
user_year = guarded(user_year)
user_day = guarded(user_day)
team = guarded(team)
watch = guarded(watch)
from .exports import record_export
