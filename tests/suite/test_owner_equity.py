#!/usr/bin/env python3
"""Owner equity: capital injections and withdrawals, their Cash/Capital
journal effect, listing, deletion, and validation guards."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "owner_equity"


def _cap_balance(t):
    return float(t.one(
        "SELECT COALESCE(SUM(jl.credit)-SUM(jl.debit),0) FROM journallines jl "
        "JOIN chartofaccounts c ON c.account_id=jl.account_id WHERE c.account_name=%s",
        ["Owner's Capital"]) or 0)


def run(t: Tester):
    g = GROUP

    # ---- injection -------------------------------------------------------
    cap0 = _cap_balance(t)
    res = t.call_json("SELECT add_owner_equity_txn(%s::jsonb)",
                      [json.dumps({"direction": "injection", "amount": 2000, "txn_date": "2025-07-05",
                                   "description": "capital in", "created_by_id": str(t.user_id)})])
    t.check(g, "capital injection succeeds", isinstance(res, dict) and res.get("status") == "success", f"{res}")
    t.assert_tb(g, "injection")
    cap1 = _cap_balance(t)
    t.check(g, "injection raises Owner's Capital by 2000", abs(cap1 - cap0 - 2000) < 0.005, f"{cap0}->{cap1}")
    inj_id = res.get("txn_id") if isinstance(res, dict) else None

    # ---- withdrawal ------------------------------------------------------
    res = t.call_json("SELECT add_owner_equity_txn(%s::jsonb)",
                      [json.dumps({"direction": "withdrawal", "amount": 500, "txn_date": "2025-07-06",
                                   "created_by_id": str(t.user_id)})])
    t.check(g, "withdrawal succeeds", isinstance(res, dict) and res.get("status") == "success", f"{res}")
    t.assert_tb(g, "withdrawal")
    cap2 = _cap_balance(t)
    t.check(g, "withdrawal lowers Owner's Capital by 500", abs(cap1 - cap2 - 500) < 0.005, f"{cap1}->{cap2}")
    wd_id = res.get("txn_id") if isinstance(res, dict) else None

    # ---- listing ---------------------------------------------------------
    lst = t.call_json("SELECT get_owner_equity_json(%s)", [50])
    t.check(g, "get_owner_equity_json returns rows", isinstance(lst, (list, dict)))

    # ---- guards ----------------------------------------------------------
    t.err(g, "invalid direction rejected",
          "SELECT add_owner_equity_txn(%s::jsonb)",
          [json.dumps({"direction": "sideways", "amount": 10, "created_by_id": str(t.user_id)})], contains="direction")
    t.err(g, "amount <= 0 rejected",
          "SELECT add_owner_equity_txn(%s::jsonb)",
          [json.dumps({"direction": "injection", "amount": 0, "created_by_id": str(t.user_id)})], contains="amount")
    t.err(g, "unknown equity account rejected",
          "SELECT add_owner_equity_txn(%s::jsonb)",
          [json.dumps({"direction": "injection", "amount": 10, "equity_account": "No Such Equity",
                       "created_by_id": str(t.user_id)})], contains="not found")

    # ---- delete both, capital returns to start ---------------------------
    t.call_json("SELECT delete_owner_equity_txn(%s)", [wd_id])
    t.call_json("SELECT delete_owner_equity_txn(%s)", [inj_id])
    t.assert_tb(g, "owner equity delete")
    t.check(g, "Owner's Capital restored after deleting both txns", abs(_cap_balance(t) - cap0) < 0.005,
            f"cap0={cap0} now={_cap_balance(t)}")

    t.no_empty_journals(g, "end of owner equity")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
