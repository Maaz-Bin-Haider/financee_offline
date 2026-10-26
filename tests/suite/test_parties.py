#!/usr/bin/env python3
"""Party master: create/update, all party types, opening-balance accounting,
expense-account auto-creation, and party lookups/balances."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "parties"


def run(t: Tester):
    g = GROUP

    # --- create every party type -----------------------------------------
    cust = t.add_party("Customer")
    vend = t.add_party("Vendor")
    both = t.add_party("Both")
    exp = t.add_party("Expense")
    for nm in (cust, vend, both, exp):
        t.check(g, f"party created: {nm[:18]}", t.party_id(nm) is not None)

    # Expense party auto-creates an Expense account in the chart of accounts.
    exp_acc = t.one("SELECT count(*) FROM chartofaccounts WHERE account_name=%s AND account_type='Expense'", [exp])
    t.check(g, "expense party creates COA expense account", exp_acc == 1, f"found {exp_acc}")

    # AR/AP account wiring by type.
    t.check(g, "customer has AR account",
            t.one("SELECT ar_account_id IS NOT NULL FROM parties WHERE party_name=%s", [cust]))
    t.check(g, "vendor has AP account",
            t.one("SELECT ap_account_id IS NOT NULL FROM parties WHERE party_name=%s", [vend]))

    # --- opening balance accounting --------------------------------------
    # Customer, debit opening 500 -> party balance +500, books stay balanced.
    c2 = t.add_party("Customer", opening_balance=500, balance_type="Debit")
    t.assert_tb(g, "customer debit opening")
    bal = t.party_balance(c2)
    t.check(g, "customer debit opening -> balance +500", abs((bal or 0) - 500) < 0.005, f"balance={bal}")

    # Vendor, credit opening 300 -> party balance -300.
    v2 = t.add_party("Vendor", opening_balance=300, balance_type="Credit")
    t.assert_tb(g, "vendor credit opening")
    bal = t.party_balance(v2)
    t.check(g, "vendor credit opening -> balance -300", abs((bal or 0) + 300) < 0.005, f"balance={bal}")

    # --- update party -----------------------------------------------------
    pid = t.party_id(c2)
    new_name = t.name("P-CUST-RENAMED")
    t.ok(g, "update party name+opening",
         "SELECT update_party_from_json(%s,%s::jsonb)",
         [pid, json.dumps({"party_name": new_name, "opening_balance": 800, "balance_type": "Debit"})])
    t.assert_tb(g, "party opening change")
    bal = t.party_balance(new_name)
    t.check(g, "updated opening -> balance +800", abs((bal or 0) - 800) < 0.005, f"balance={bal}")
    t.check(g, "old party name gone after rename", t.party_id(c2) is None)

    # --- lookups ----------------------------------------------------------
    by_name = t.call_json("SELECT get_party_by_name(%s)", [vend])
    # get_party_by_name returns a JSON array of matching parties.
    row = by_name[0] if isinstance(by_name, list) and by_name else by_name
    t.check(g, "get_party_by_name returns the party", isinstance(row, dict) and row.get("party_name") == vend,
            f"{by_name}")

    parties = t.call_json("SELECT get_parties_json()")
    t.check(g, "get_parties_json returns a list", isinstance(parties, list) and len(parties) >= 4)

    balances = t.call_json("SELECT get_party_balances_json()")
    t.check(g, "get_party_balances_json returns rows", isinstance(balances, (list, dict)))

    exp_balances = t.call_json("SELECT get_expense_party_balances_json()")
    t.check(g, "get_expense_party_balances_json returns rows", isinstance(exp_balances, (list, dict)))

    # Unknown party lookup is reported as not found (not an error).
    nf = t.call_json("SELECT get_party_balance_by_name(%s)", ["__NO_SUCH_PARTY__"])
    t.check(g, "unknown party balance -> found=false", isinstance(nf, dict) and nf.get("found") is False)

    t.no_empty_journals(g, "end of parties")


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
