"""The Team Activity page's SQL (TEAM_ACTIVITY_PLAN.md, Phases 4-5).

Django-free, like lookup/queries.py: system_tests/run_system_tests.py loads it
by path and runs the same statements against the real schema.

Every day is a day in the business time zone (settings.ACTIVITY_TIMEZONE),
passed as %(tz)s: events are stored in UTC, and a local midnight is turned
into the UTC instant it was with `(date::timestamp AT TIME ZONE tz)`, so each
query reads its range straight off the (user_id, at) index.

Work is every event but a session's own (sign-in, sign-out, failed sign-in).
"""

SESSION_ACTIONS = ("sign_in", "sign_out", "sign_in_failed")

_WORK = "e.action NOT IN ('sign_in', 'sign_out', 'sign_in_failed')"
_RANGE = ("e.at >= (%(start)s::timestamp AT TIME ZONE %(tz)s) "
          "AND e.at < ((%(end)s::date + 1)::timestamp AT TIME ZONE %(tz)s)")

# One row per local day in [start, end] on which the user did anything:
# work done, how much of it is backfilled (approximate), sign-ins.
DAY_COUNTS = f"""
    SELECT (e.at AT TIME ZONE %(tz)s)::date AS day,
           count(*) FILTER (WHERE {_WORK}) AS work,
           count(*) FILTER (WHERE {_WORK} AND e.source = 'backfill') AS approximate,
           count(*) FILTER (WHERE e.action = 'sign_in') AS sign_ins,
           count(*) FILTER (WHERE e.action = 'sign_in_failed') AS failed_sign_ins
    FROM activity_events e
    WHERE e.user_id = %(user)s AND {_RANGE}
    GROUP BY 1
    ORDER BY 1
"""

# What each day's work was, for the square's tooltip: a document kind, or for
# reports "run" and "export".
DAY_MIX = f"""
    SELECT (e.at AT TIME ZONE %(tz)s)::date AS day,
           CASE WHEN e.kind = 'report' THEN e.action ELSE e.kind END AS what,
           count(*) AS n
    FROM activity_events e
    WHERE e.user_id = %(user)s AND {_WORK} AND {_RANGE}
    GROUP BY 1, 2
    ORDER BY 1, 3 DESC, 2
"""

# The days anyone worked: a streak runs across the team's working days, so a
# Sunday the office is shut does not break it.
TEAM_DAYS = f"""
    SELECT DISTINCT (e.at AT TIME ZONE %(tz)s)::date AS day
    FROM activity_events e
    WHERE {_WORK} AND {_RANGE}
    ORDER BY 1
"""

# All time: the user's last work and last sign-in -- each the newest match
# read backwards off the (user_id, at) index, not a pass over all history.
_LAST_WORK = f"""(SELECT e.at FROM activity_events e
        WHERE e.user_id = {{user}} AND {_WORK} ORDER BY e.at DESC LIMIT 1)"""
_LAST_SIGN_IN = """(SELECT e.at FROM activity_events e
        WHERE e.user_id = {user} AND e.action = 'sign_in' ORDER BY e.at DESC LIMIT 1)"""

LAST_SEEN = f"""
    SELECT {_LAST_WORK.format(user="%(user)s")} AS last_work,
           {_LAST_SIGN_IN.format(user="%(user)s")} AS last_sign_in
"""

# One local day's events, in order.
DAY_EVENTS = """
    SELECT e.at AT TIME ZONE %(tz)s AS local_at, e.action, e.kind, e.record_id, e.label,
           e.source, host(e.ip)
    FROM activity_events e
    WHERE e.user_id = %(user)s
      AND e.at >= (%(day)s::timestamp AT TIME ZONE %(tz)s)
      AND e.at < ((%(day)s::date + 1)::timestamp AT TIME ZONE %(tz)s)
    ORDER BY e.at, e.event_id
    LIMIT 1001
"""

# The first year anything was recorded, for the year picker.
FIRST_YEAR = """
    SELECT extract(year FROM min(at) AT TIME ZONE %(tz)s)::int FROM activity_events
"""

# Every account, for the user picker -- inactive ones too: their history stays.
USERS = """
    SELECT * FROM (SELECT u.id, u.username, u.is_active FROM public.auth_user u
JOIN public.tenancy_membership m ON m.user_id=u.id AND m.company_id=%(company)s
UNION ALL
SELECT h.user_id, h.username, false FROM (
 SELECT DISTINCT ON (e.user_id) e.user_id, e.username FROM activity_events e
 WHERE e.user_id IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM public.tenancy_membership m WHERE m.company_id=%(company)s AND m.user_id=e.user_id)
 ORDER BY e.user_id, e.at DESC, e.event_id DESC
) h) people ORDER BY lower(username), id LIMIT 1000
"""

# Whose grid the page opens on: the busiest of the last 30 days. now(), not
# clock_timestamp(): a volatile bound cannot be read off the index.
BUSIEST = f"""
    SELECT e.user_id FROM activity_events e
    WHERE {_WORK} AND e.user_id IS NOT NULL AND e.at > now() - interval '30 days'
    GROUP BY e.user_id
    ORDER BY count(*) DESC, e.user_id
    LIMIT 1
"""


# ── Phase 5: around the grid ────────────────────────────────────────────────

# The period's work by kind (a report's runs and downloads apart).
MIX = f"""
    SELECT CASE WHEN e.kind = 'report' THEN e.action ELSE e.kind END AS what, count(*) AS n
    FROM activity_events e
    WHERE e.user_id = %(user)s AND {_WORK} AND {_RANGE}
    GROUP BY 1
    ORDER BY 2 DESC, 1
"""

# When the user works: weekday (0 Monday) by local hour.
HOURS = f"""
    SELECT extract(isodow FROM e.at AT TIME ZONE %(tz)s)::int - 1 AS weekday,
           extract(hour FROM e.at AT TIME ZONE %(tz)s)::int AS hour,
           count(*) AS n
    FROM activity_events e
    WHERE e.user_id = %(user)s AND {_WORK} AND {_RANGE}
    GROUP BY 1, 2
"""

# Every account side by side: work in the last 7 and 30 local days (today
# included), days worked in the last 30, the last work and sign-in ever. Each
# account reads its own 30 days and its two newest matches off the (user_id,
# at) index, so the table costs the same after years of history.
TEAM = f"""
    SELECT u.id, u.username, u.is_active,
           coalesce(w.last7, 0) AS last7, coalesce(w.last30, 0) AS last30,
           coalesce(w.days30, 0) AS days30,
           {_LAST_WORK.format(user="u.id")} AS last_work,
           {_LAST_SIGN_IN.format(user="u.id")} AS last_sign_in
    FROM (SELECT u.id, u.username, u.is_active FROM public.auth_user u
JOIN public.tenancy_membership m ON m.user_id=u.id AND m.company_id=%(company)s
UNION ALL
SELECT h.user_id, h.username, false FROM (
 SELECT DISTINCT ON (e.user_id) e.user_id, e.username FROM activity_events e
 WHERE e.user_id IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM public.tenancy_membership m WHERE m.company_id=%(company)s AND m.user_id=e.user_id)
 ORDER BY e.user_id, e.at DESC, e.event_id DESC
) h) u
    LEFT JOIN LATERAL (
        SELECT count(*) FILTER (WHERE e.at >= (%(from7)s::timestamp AT TIME ZONE %(tz)s)) AS last7,
               count(*) AS last30,
               count(DISTINCT (e.at AT TIME ZONE %(tz)s)::date) AS days30
        FROM activity_events e
        WHERE e.user_id = u.id AND {_WORK}
          AND e.at >= (%(from30)s::timestamp AT TIME ZONE %(tz)s)
    ) w ON true
    ORDER BY lower(u.username), u.id
"""

# Each user's work per local week (Monday) since %(weeks_from)s.
TEAM_WEEKS = f"""
    SELECT e.user_id, date_trunc('week', e.at AT TIME ZONE %(tz)s)::date AS monday, count(*) AS n
    FROM activity_events e
    WHERE {_WORK} AND e.user_id IS NOT NULL
      AND e.at >= (%(weeks_from)s::timestamp AT TIME ZONE %(tz)s)
    GROUP BY 1, 2
"""

# The watch list (section 4.4): what a manager cannot see anywhere else.
#   delete          every deletion
#   old_edit        an edit to a document dated more than %(old_days)s days
#                   before the edit (its own date: invoice, return, voucher)
#   late            work before %(open_hour)s:00 local time
#   failed_sign_in  the moment a name's failed sign-ins reach %(burst)s within
#                   ten minutes
# Live events only: backfilled history has no deletes and its times are
# approximate. Newest first; each rule stops at the list's limit on its own,
# walking back from now, before the four are merged.
WATCH = f"""
    SELECT w.type, w.at AT TIME ZONE %(tz)s AS local_at, w.username, w.kind, w.record_id, w.label,
           w.detail, w.attempts, host(w.ip)
    FROM (
        (SELECT 'delete' AS type, e.at, e.username, e.kind, e.record_id, e.label,
               NULL::date AS detail, NULL::bigint AS attempts, e.ip
        FROM activity_events e
        WHERE e.action = 'delete' AND e.source = 'live'
          AND e.at >= (%(from)s::timestamp AT TIME ZONE %(tz)s)
        ORDER BY e.at DESC LIMIT %(limit)s)
        UNION ALL
        (SELECT 'old_edit', e.at, e.username, e.kind, e.record_id, e.label, e.document_date, NULL, e.ip
        FROM activity_events e
        WHERE e.action = 'update' AND e.source = 'live'
          AND e.at >= (%(from)s::timestamp AT TIME ZONE %(tz)s)
          AND e.document_date < (e.at AT TIME ZONE %(tz)s)::date - %(old_days)s
        ORDER BY e.at DESC LIMIT %(limit)s)
        UNION ALL
        (SELECT 'late', e.at, e.username, e.kind, e.record_id, e.label, NULL, NULL, e.ip
        FROM activity_events e
        WHERE {_WORK} AND e.source = 'live'
          AND e.at >= (%(from)s::timestamp AT TIME ZONE %(tz)s)
          AND extract(hour FROM e.at AT TIME ZONE %(tz)s) < %(open_hour)s
        ORDER BY e.at DESC LIMIT %(limit)s)
        UNION ALL
        (SELECT 'failed_sign_in', f.at, f.username, 'session', NULL, f.label, NULL, f.attempts, f.ip
        FROM (
            SELECT e.at, e.username, e.label, e.ip,
                   count(*) OVER (PARTITION BY e.username ORDER BY e.at
                                  RANGE BETWEEN interval '10 minutes' PRECEDING AND CURRENT ROW) AS attempts
            FROM activity_events e
            WHERE e.action = 'sign_in_failed'
              AND e.at >= (%(from)s::timestamp AT TIME ZONE %(tz)s) - interval '10 minutes'
        ) f
        WHERE f.attempts = %(burst)s
          AND f.at >= (%(from)s::timestamp AT TIME ZONE %(tz)s)
        ORDER BY f.at DESC LIMIT %(limit)s)
    ) w
    ORDER BY w.at DESC
    LIMIT %(limit)s
"""
