"""The Team Activity page's figures, from the rows its queries return
(TEAM_ACTIVITY_PLAN.md, sections 4.4-4.5). Pure: no database, no Django.
"""

import datetime

# The shades (decision 3): one scale for every user, from the team's own
# days -- quartiles 4, 10 and 25 on the Aug-17 dump. A day's level is the
# number of these it reaches: 0 blank, 1 for 1-4, ..., 4 for 26 or more.
THRESHOLDS = (1, 5, 11, 26)


def level(count):
    return sum(1 for step in THRESHOLDS if count >= step)


def period(today, year=None):
    """The days a grid covers: a calendar year, or the 12 months to today.

    The 12 months start on the Monday 52 weeks before this week's, so the
    grid is 53 whole columns ending with today's week."""
    if year:
        return datetime.date(year, 1, 1), min(datetime.date(year, 12, 31), today)
    this_monday = today - datetime.timedelta(days=today.weekday())
    return this_monday - datetime.timedelta(weeks=52), today


def streaks(user_days, team_days, today):
    """(current, longest) runs of the team's working days the user worked.

    A streak runs across the days anyone worked, so a Sunday the office is
    shut does not break it. Today, if the user has not worked yet, does not
    end the current streak -- the day is not over."""
    team = sorted(day for day in team_days if day <= today)
    worked = set(user_days)
    longest = run = 0
    for day in team:
        run = run + 1 if day in worked else 0
        longest = max(longest, run)
    current = 0
    for day in reversed(team):
        if day in worked:
            current += 1
        elif day == today:
            continue
        else:
            break
    return current, longest


def summary(days, team_days, today):
    """The figures above the grid, from DAY_COUNTS rows as dicts."""
    worked = [row for row in days if row["work"]]
    actions = sum(row["work"] for row in worked)
    current, longest = streaks([row["day"] for row in worked], team_days, today)
    return {
        "actions": actions,
        "active_days": len(worked),
        "per_active_day": round(actions / len(worked), 1) if worked else 0,
        "current_streak": current,
        "longest_streak": longest,
        "approximate": sum(row["approximate"] for row in worked),
        "busiest": max(worked, key=lambda row: (row["work"], row["day"]))["day"].isoformat() if worked else None,
    }
