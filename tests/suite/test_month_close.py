#!/usr/bin/env python3
"""Month/period close: preview, close, duplicate-close guard, listing, and
reverse. The close is applied to a period and then reversed so the run is
self-restoring."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "month_close"
YEAR, MONTH = 2025, 7


def _is_closed(t):
    return (t.one("SELECT count(*) FROM period_closes WHERE period_year=%s AND period_month=%s", [YEAR, MONTH]) or 0) > 0


def run(t: Tester):
    g = GROUP

    # Start from an open period (reverse if a prior run left it closed).
    if _is_closed(t):
        t.exec("SELECT reverse_period_close(%s,%s)", [YEAR, MONTH])
    t.check(g, "period starts open", not _is_closed(t))

    # ---- preview (no mutation) ------------------------------------------
    prev = t.call_json("SELECT preview_period_close(%s,%s)", [YEAR, MONTH])
    t.check(g, "preview_period_close returns figures", isinstance(prev, dict), f"{prev}")
    t.check(g, "preview did not close the period", not _is_closed(t))

    # ---- close -----------------------------------------------------------
    res = t.call_json("SELECT close_period_from_json(%s::jsonb)",
                      [json.dumps({"year": YEAR, "month": MONTH, "created_by_id": str(t.user_id)})])
    t.check(g, "close_period succeeds", isinstance(res, dict) and res.get("status") == "success", f"{res}")
    t.check(g, "period recorded in period_closes", _is_closed(t))
    t.assert_tb(g, "period close")

    # invalid month rejected
    t.err(g, "month out of range rejected",
          "SELECT close_period_from_json(%s::jsonb)", [json.dumps({"year": YEAR, "month": 13})], contains="month")
    # duplicate close rejected
    t.err(g, "closing an already-closed period rejected",
          "SELECT close_period_from_json(%s::jsonb)",
          [json.dumps({"year": YEAR, "month": MONTH})], contains="already closed")

    # listing
    t.ok(g, "get_period_closes_json runs", "SELECT get_period_closes_json()")

    # ---- reverse (restore) ----------------------------------------------
    rev = t.call_json("SELECT reverse_period_close(%s,%s)", [YEAR, MONTH])
    t.check(g, "reverse_period_close succeeds", isinstance(rev, dict), f"{rev}")
    t.check(g, "period reopened after reverse", not _is_closed(t))
    t.assert_tb(g, "period reverse")

    t.no_empty_journals(g, "end of month close")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
