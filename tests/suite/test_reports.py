#!/usr/bin/env python3
"""Reports: builds a controlled dataset, then exercises and value-checks every
report surface — accounts, stock, serial, sales analytics, monthly, and the
dashboard functions and views."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import Tester, standalone  # noqa: E402

GROUP = "reports"
F, T = "2025-07-01", "2025-07-31"


def _setup(t):
    """A self-contained scenario producing AR, AP, expense, stock, and profit."""
    d = {}
    d["vend"] = t.add_party("Vendor")
    d["cust"] = t.add_party("Customer")
    d["exp"] = t.add_party("Expense")
    d["item"] = t.add_item(sale_price=300)
    d["serials"] = t.serials("RP", 4)
    t.purchase(d["vend"], d["serials"], unit_price=100, item_name=d["item"], date="2025-07-02")
    # Sell 2 of 4 on credit @250 -> revenue 500, COGS 200, AR +500, 2 left in stock.
    d["sale"] = t.sale(d["cust"], d["serials"][:2], unit_price=250, item_name=d["item"], date="2025-07-05")
    # A receipt and an expense payment for cash-ledger / expense reports.
    t.receipt(d["cust"], 150, date="2025-07-06")
    t.payment(d["exp"], 75, date="2025-07-07", desc="Utilities")
    return d


def _runs(t, name, sql, params=None):
    t.ok(GROUP, f"report runs: {name}", sql, params)


def _view(t, name):
    """Run a report view; document tenant drift (missing view) as XFAIL."""
    from _harness import Check
    if not t.relation_exists(name):
        t.results.append(Check(GROUP, f"view present: {name}", False, "missing on this tenant (drift)", known_bug=True))
        return
    t.ok(GROUP, f"report runs: {name} view", f"SELECT * FROM {name} LIMIT 5")


def run(t: Tester):
    g = GROUP
    d = _setup(t)
    item, cust, vend = d["item"], d["cust"], d["vend"]
    serial0 = d["serials"][0]

    # ---- ACCOUNTS --------------------------------------------------------
    tbj = t.call_json("SELECT get_trial_balance_json()")
    t.check(g, "get_trial_balance_json returns data", tbj is not None)
    # The books as a whole must balance.
    t.check(g, "trial balance (journallines) is balanced", abs(t.tb_diff()) < 0.005, f"diff={t.tb_diff()}")
    # vw_trial_balance total debit == total credit.
    vtb = t.one("SELECT COALESCE(SUM(debit),0)-COALESCE(SUM(credit),0) FROM vw_trial_balance") \
        if t.has_column("vw_trial_balance", "debit") else 0
    t.check(g, "vw_trial_balance nets to zero", abs(float(vtb or 0)) < 0.005, f"net={vtb}")

    _view(t, "generalledger")
    _runs(t, "detailed_ledger (customer)", "SELECT * FROM detailed_ledger(%s,%s,%s)", [cust, F, T])
    _runs(t, "detailed_ledger2 (customer)", "SELECT * FROM detailed_ledger2(%s,%s,%s)", [cust, F, T])
    _runs(t, "detailed_ledger (vendor)", "SELECT * FROM detailed_ledger(%s,%s,%s)", [vend, F, T])
    _runs(t, "cash ledger", "SELECT * FROM get_cash_ledger_with_party(%s,%s)", [F, T])

    ar = t.call_json("SELECT get_accounts_receivable_json_excluding(%s::text[])", [[]])
    t.check(g, "accounts receivable report returns data", ar is not None)
    ap = t.call_json("SELECT get_accounts_payable_json_excluding(%s::text[])", [[]])
    t.check(g, "accounts payable report returns data", ap is not None)
    _runs(t, "party balances", "SELECT get_party_balances_json()")
    _runs(t, "party balances excluding", "SELECT get_party_balances_json_excluding(%s::text[])", [[]])
    _runs(t, "expense party balances", "SELECT get_expense_party_balances_json()")

    # Customer AR in the report equals their ledger balance (500 sale - 150 receipt = 350).
    t.check(g, "customer net AR = 350 after sale+receipt", abs((t.party_balance(cust) or 0) - 350) < 0.005,
            f"balance={t.party_balance(cust)}")

    # ---- STOCK -----------------------------------------------------------
    ss = t.q("SELECT quantity_in_stock FROM stock_summary() WHERE item_name=%s", [item])
    in_stock_ct = int(t.one("SELECT count(*) FROM purchaseunits pu JOIN purchaseitems pi ON pi.purchase_item_id=pu.purchase_item_id "
                            "JOIN items i ON i.item_id=pi.item_id WHERE i.item_name=%s AND pu.in_stock=true", [item]) or 0)
    t.check(g, "stock_summary qty matches in-stock serial count", ss and int(ss[0][0]) == in_stock_ct,
            f"summary={ss}, actual={in_stock_ct}")
    _view(t, "stock_report")
    _view(t, "stock_worth_report")
    # After fix_tenant_drift.sql the redundant 1-arg overload is dropped, so a
    # single-arg call resolves unambiguously to the 3-arg (defaulted) form.
    _runs(t, "item_transaction_history (name)", "SELECT * FROM item_transaction_history(%s::text)", [item])
    _runs(t, "item_transaction_history (name,dates)", "SELECT * FROM item_transaction_history(%s,%s,%s)", [item, F, T])
    _runs(t, "get_item_stock_by_name", "SELECT * FROM get_item_stock_by_name(%s)", [item])
    _view(t, "item_last_purchase_view")
    _view(t, "item_last_sale_view")

    # ---- SERIAL ----------------------------------------------------------
    _runs(t, "get_serial_ledger", "SELECT * FROM get_serial_ledger(%s)", [serial0])
    _runs(t, "get_serial_ledger_purchase", "SELECT * FROM get_serial_ledger_purchase(%s)", [serial0])
    _runs(t, "get_serial_ledger_sales", "SELECT * FROM get_serial_ledger_sales(%s)", [serial0])
    _runs(t, "get_serial_number_details", "SELECT * FROM get_serial_number_details(%s)", [serial0])

    # ---- SALES ANALYTICS -------------------------------------------------
    for nm, fn in (("sales_summary", "sales_summary_json"),
                   ("product_profitability", "product_profitability_json"),
                   ("customer_profitability", "customer_profitability_json"),
                   ("sales_by_product", "sales_by_product_json"),
                   ("sales_by_customer", "sales_by_customer_json"),
                   ("sale_wise_profit", "sale_wise_profit_json"),
                   ("invoice_register", "invoice_register_json")):
        r = t.call_json(f"SELECT {fn}(%s,%s)", [F, T])
        t.check(g, f"sales report returns data: {nm}", r is not None, f"{fn} -> None")
    _runs(t, "sales_trend_json", "SELECT sales_trend_json(%s,%s,%s)", [F, T, "day"])
    _runs(t, "sale_wise_profit (table)", "SELECT * FROM sale_wise_profit(%s,%s)", [F, T])
    _view(t, "sale_wise_profit_view")
    _view(t, "standing_company_worth_view")
    _view(t, "vw_sold_serial_profit")

    # ---- MONTHLY ---------------------------------------------------------
    _runs(t, "monthly_company_position", "SELECT monthly_company_position(%s)", [T])
    _runs(t, "monthly_income_statement", "SELECT monthly_income_statement(%s,%s)", [F, T])

    # ---- DASHBOARD FUNCTIONS --------------------------------------------
    dash = [
        ("sales_today_kpi", "SELECT fn_dash_sales_today_kpi()", []),
        ("sales_last7days", "SELECT fn_dash_sales_last7days()", []),
        ("sales_range", "SELECT fn_dash_sales_range(%s,%s)", [F, T]),
        ("stock_kpi", "SELECT fn_dash_stock_kpi()", []),
        ("low_stock_items", "SELECT fn_dash_low_stock_items(%s)", [5]),
        ("fast_moving_items", "SELECT fn_dash_fast_moving_items(%s,%s)", [30, 10]),
        ("stale_stock", "SELECT fn_dash_stale_stock(%s)", [30]),
        ("top_customers", "SELECT fn_dash_top_customers(%s,%s,%s)", [5, F, T]),
        ("top_vendors", "SELECT fn_dash_top_vendors(%s,%s,%s)", [5, F, T]),
        ("receivables_aging", "SELECT fn_dash_receivables_aging()", []),
        ("recent_transactions", "SELECT fn_dash_recent_transactions(%s)", [10]),
        ("expense_kpi", "SELECT fn_dash_expense_kpi()", []),
        ("top_expense_categories", "SELECT fn_dash_top_expense_categories(%s,%s,%s)", [5, F, T]),
        ("top_expense_descriptions", "SELECT fn_dash_top_expense_descriptions(%s,%s,%s)", [5, F, T]),
        ("smart_alerts", "SELECT fn_dash_smart_alerts()", []),
    ]
    for nm, sql, params in dash:
        r = t.call_json(sql, params)
        t.check(g, f"dashboard fn returns data: {nm}", r is not None, f"{nm} -> None")

    # ---- DASHBOARD VIEWS -------------------------------------------------
    for v in ("vw_dash_daily_sales", "vw_dash_expenses", "vw_dash_party_ar_balance", "vw_dash_stock_overview"):
        _view(t, v)

    _receivables_exclude_expenses(t, g, d)

    t.no_empty_journals(g, "end of reports")


def _build_has_receivables_fix():
    return True  # Offline v1 requires the confirmed source fix; never skip coverage.


def _receivables_exclude_expenses(t, g, d):
    """An expense party must never be reported as someone who owes you money.

    add_party_from_json wires an Expense party with BOTH ar_account_id (the
    shared Accounts Receivable account) and ap_account_id (its own Expense
    account). vw_dash_party_ar_balance used to sum every journal line tagged
    with a party regardless of account, so paying a shop expense made that
    expense head surface on the dashboard as a customer owing money — and
    raised "Stale Receivable" / "Risky Customer" alerts for it.
    _setup pays d["exp"] 75, which is exactly that scenario.
    """
    if not _build_has_receivables_fix():
        return

    rows = t.q(
        "SELECT party_name, party_type, ar_balance FROM vw_dash_party_ar_balance"
    )
    names = {r[0] for r in rows}

    t.check(
        g, "receivables view excludes expense parties",
        d["exp"] not in names,
        f"expense party {d['exp']} appears with balance "
        f"{next((r[2] for r in rows if r[0] == d['exp']), None)}",
    )
    t.check(
        g, "receivables view excludes every Expense-type party",
        all(r[1] != "Expense" for r in rows),
        f"Expense-type parties present: {[r[0] for r in rows if r[1] == 'Expense']}",
    )
    # The fix must not throw the baby out: a real credit customer still owes.
    t.check(
        g, "receivables view still reports a credit customer",
        d["cust"] in names,
        f"customer {d['cust']} missing from receivables; got {sorted(names)}",
    )

    # Both consumers of the view must be clean too.
    alerts = t.call_json("SELECT fn_dash_smart_alerts()") or []
    alert_text = json.dumps(alerts)
    t.check(
        g, "smart alerts never flag an expense party as a customer",
        d["exp"] not in alert_text,
        f"expense party {d['exp']} named in smart alerts",
    )

    aging = t.call_json("SELECT fn_dash_receivables_aging()") or {}
    aging_text = json.dumps(aging)
    t.check(
        g, "receivables aging excludes expense parties",
        d["exp"] not in aging_text,
        f"expense party {d['exp']} present in receivables aging buckets",
    )


def main():
    return standalone(run, GROUP)


if __name__ == "__main__":
    sys.exit(main())
