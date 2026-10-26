"""Synthetic review data; runs only in the dedicated review database.

Run via deploy/review_stack.py. Never reads a dump or production environment.
Repeat startup preserves the reviewer's edits; it does not reset their data.
"""
import json
import os
from pathlib import Path
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not re.fullmatch(r"financee_review_(darkmode|email|spotlight|activity|regression)(_[a-z0-9]{1,16})?",
                    os.environ.get("FINANCEE_REVIEW_PROJECT", "")):
    raise SystemExit("Review marker missing; refusing to seed.")
if (os.environ.get("DB_NAME"), os.environ.get("DB_USER"), os.environ.get("DB_HOST")) != (
        "financee_review", "review", "db"):
    raise SystemExit("Not the isolated review database; refusing to seed.")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection, transaction
from tenancy.models import BillingSettings, Company, Membership
from tenancy.utils import reset_search_path, set_search_path


def scalar(sql, *params):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def seed_business(company, actor, offset):
    set_search_path(company.schema_name)
    try:
        for name, kind in [("REVIEW CUSTOMER", "Customer"), ("REVIEW VENDOR", "Vendor"),
                           ("REVIEW RENT", "Expense")]:
            scalar("SELECT add_party_from_json(%s::jsonb)", json.dumps({
                "party_name": name, "party_type": kind, "opening_balance": 0,
                "balance_type": "Debit", "created_by_id": str(actor.pk)}))
        scalar("SELECT add_item_from_json(%s::jsonb)", json.dumps({
            "item_name": "REVIEW PHONE", "sale_price": 180 + offset,
            "brand": "DEMO", "category": "PHONES", "created_by_id": str(actor.pk)}))
        customer = scalar("SELECT party_id FROM parties WHERE party_name='REVIEW CUSTOMER'")
        vendor = scalar("SELECT party_id FROM parties WHERE party_name='REVIEW VENDOR'")
        serials = [f"REVIEW-{n:03d}" for n in range(1, 9)]
        purchase = scalar("SELECT create_purchase(%s,%s,%s::jsonb,%s)", vendor,
                          date.today() - timedelta(days=2), json.dumps([{
                              "item_name": "REVIEW PHONE", "qty": 8, "unit_price": 100 + offset,
                              "serials": [{"serial": s, "comment": "Synthetic review unit"} for s in serials]}]), actor.pk)
        sale = scalar("SELECT create_sale(%s,%s,%s::jsonb,%s)", customer,
                      date.today() - timedelta(days=1), json.dumps([{
                          "item_name": "REVIEW PHONE", "qty": 3, "unit_price": 180 + offset,
                          "serials": serials[:3]}]), actor.pk)
        scalar("SELECT create_sale_return(%s,%s::jsonb,%s)", "REVIEW CUSTOMER", json.dumps([serials[0]]), actor.pk)
        scalar("SELECT create_purchase_return(%s,%s::jsonb,%s)", "REVIEW VENDOR", json.dumps([serials[7]]), actor.pk)
        scalar("SELECT create_draft(%s,%s,%s::jsonb,%s)", customer, date.today(), json.dumps([{
            "item_name": "REVIEW PHONE", "qty": 1, "unit_price": None, "serials": [serials[3]]}]), actor.pk)
        for function, party, amount in [("make_payment", "REVIEW VENDOR", 50),
                                        ("make_receipt", "REVIEW CUSTOMER", 75)]:
            scalar(f"SELECT {function}(%s::jsonb)", json.dumps({
                "party_name": party, "amount": amount, "method": "Cash",
                "payment_date": str(date.today()), "receipt_date": str(date.today()),
                "description": "Synthetic review only", "created_by_id": str(actor.pk)}))
        with connection.cursor() as cur:
            cur.execute("UPDATE purchaseinvoices SET description=%s WHERE purchase_invoice_id=%s",
                        ["Model\tQty\nDemo phone\t8", purchase])
            cur.execute("UPDATE salesinvoices SET description=%s WHERE sales_invoice_id=%s",
                        ["Synthetic review sale", sale])
        assert scalar("SELECT COALESCE(sum(debit),0)-COALESCE(sum(credit),0) FROM journallines") == 0
    finally:
        reset_search_path()


def main():
    assert scalar("SELECT current_database()") == "financee_review"
    with connection.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS public.review_fixture_marker (id boolean PRIMARY KEY CHECK(id), version integer)")
        cur.execute("SELECT 1 FROM public.review_fixture_marker WHERE id=true")
        if cur.fetchone():
            print("Review fixtures already exist; preserving reviewer data.")
            return
    with transaction.atomic():
        # Fresh bootstrap only; refuse an unexpected company/user estate.
        if list(Company.objects.values_list("name", flat=True)) != ["Company One"]:
            raise ValueError("Refusing to seed an unexpected registry.")
        User = get_user_model()
        if User.objects.exists():
            raise ValueError("Refusing to seed an unexpected user estate.")
        BillingSettings.objects.update_or_create(pk=1, defaults={"emails_enabled": False})
        alpha = Company.objects.get(name="Company One")
        alpha.name = "Review Alpha"
        alpha.paid_until = date.today() + timedelta(days=4)
        alpha.save()
        beta = Company.objects.create(name="Review Beta", base_currency_id="AED",
                                      disabled_features=["owner_equity", "month_close", "attachments"])
        blocked = Company.objects.create(name="Review Suspended", is_suspended=True)
        readonly, _ = Group.objects.get_or_create(name="view_only_users")
        permissions = list(Permission.objects.filter(content_type__app_label="auth"))
        readers = [p for p in permissions if p.codename != "view_team_activity" and p.codename.startswith(("view_", "can_view_"))]
        people = [("review_operator", None, "operator"), ("alpha_manager", alpha, "manager"),
                  ("alpha_staff", alpha, "staff"), ("alpha_reader", alpha, "reader"),
                  ("beta_manager", beta, "manager"), ("beta_staff", beta, "staff"),
                  ("suspended_user", blocked, "reader")]
        users = {}
        for name, company, role in people:
            user = User.objects.create_user(name, password=os.environ["REVIEW_LOGIN_PASSWORD"],
                                           is_staff=role == "operator", is_superuser=role == "operator")
            if company:
                Membership.objects.create(user=user, company=company)
                user.user_permissions.set(readers if role == "reader" else
                    [p for p in permissions if role == "manager" or p.codename not in ("send_reports","view_team_activity")])
            if role == "reader":
                user.groups.add(readonly)
            users[name] = user
        seed_business(alpha, users["alpha_manager"], 0)
        seed_business(beta, users["beta_manager"], 100)
        if os.environ.get("FINANCEE_REVIEW_PROJECT", "").startswith("financee_review_email"):
            for company, key in ((alpha, "alpha"), (beta, "beta")):
                set_search_path(company.schema_name)
                scalar("SELECT save_report_email_settings_from_json(%s::jsonb)", json.dumps({
                    "sender_email": f"reports-{key}@example.test", "sender_name": company.name,
                    "app_password": "local-capture-only", "send_hour": 7 if key == "alpha" else 8,
                    "timezone": "Asia/Karachi" if key == "alpha" else "Asia/Dubai",
                    "is_enabled": False, "actor": f"{key}_manager",
                    "authorized_user_id": users[f"{key}_manager"].pk}))
                scalar("SELECT add_report_recipient_from_json(%s::jsonb)", json.dumps({
                    "email": f"owner-{key}@example.test", "label": company.name}))
            reset_search_path()
        if os.environ.get("FINANCEE_REVIEW_PROJECT", "").startswith("financee_review_activity"):
            # Explicit synthetic examples only; never a production historical import.
            for company, key in ((alpha,"alpha"),(beta,"beta")):
                set_search_path(company.schema_name)
                for role in ("manager","staff"):
                    actor=users[f"{key}_{role}"]
                    with connection.cursor() as cur:
                        cur.execute("""INSERT INTO activity_events(user_id,username,action,kind,label,source,at,dedupe_key)
                          SELECT %s,%s,'create',CASE WHEN n%%3=0 THEN 'item' ELSE 'sale' END,
                            'Synthetic review historical example','backfill',
                            ((CURRENT_DATE-d*2)+time '12:00') AT TIME ZONE 'Asia/Karachi',
                            'review:' || %s::text || ':' || d::text || ':' || n::text
                          FROM generate_series(1,80) d
                          CROSS JOIN LATERAL generate_series(1,CASE WHEN (d+%s)%%5=0 THEN 26 ELSE (d+%s)%%12 END) n""",
                          [actor.pk,actor.username,actor.pk,actor.pk,actor.pk])
                actor=users[f"{key}_staff"]
                with connection.cursor() as cur:
                    cur.execute("""INSERT INTO activity_events(user_id,username,action,kind,label,source,at,document_date)
                      VALUES(%s,%s,'delete','item','Synthetic review deletion','live',now()-interval '1 day',NULL),
                      (%s,%s,'update','sale','Synthetic review old-document edit','live',now(),CURRENT_DATE-60)""",
                      [actor.pk,actor.username,actor.pk,actor.username])
            reset_search_path()
        with connection.cursor() as cur:
            cur.execute("INSERT INTO public.review_fixture_marker VALUES(true,1)")
    print("Review Alpha and Beta seeded with matching serials/document numbers and different amounts.")
    print("Subscription email is disabled; Review Suspended exercises the suspension page.")


if __name__ == "__main__":
    main()
