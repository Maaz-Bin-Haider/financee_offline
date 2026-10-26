#!/usr/bin/env python3
"""Subscription control: paid-until/grace state machine, payment recording,
middleware enforcement (suspension page, JSON denial, exemptions), and the
renewal warning banner.

Everything mutates only public-schema registry fields (Company /
SubscriptionPayment / a throwaway user+membership) and restores them in
``finally`` — no tenant business data is touched.

Run inside the web container:
    docker compose -f deploy/docker-compose.yml exec -e PYTHONPATH=/app web \
        python tests/suite/test_subscription.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from tenancy.models import (  # noqa: E402
    BLOCKED_STATES,
    Company,
    Membership,
    SubscriptionPayment,
    add_months,
)

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []

SUBSCRIPTION_FIELDS = ("is_suspended", "paid_until", "grace_days", "warn_days_before")


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))
    return bool(ok)


def make_client():
    server = "localhost"
    allowed = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*", "")]
    if allowed:
        server = allowed[0].lstrip(".")
    return Client(SERVER_NAME=server)


# ── Pure state-machine checks (unsaved Company: no signals, no schema) ──────

def check_state_machine():
    today = date.today()

    def state(**fields):
        return Company(name="X", **fields).subscription_state(today)

    chk("no paid_until -> unrestricted", state(paid_until=None) == "unrestricted")
    chk("manual suspension wins over paid future date",
        state(is_suspended=True, paid_until=today + timedelta(days=90)) == "suspended")
    chk("suspended with no paid_until", state(is_suspended=True) == "suspended")
    chk("paid far in the future -> active",
        state(paid_until=today + timedelta(days=30), warn_days_before=7) == "active")
    chk("inside warn window -> expiring",
        state(paid_until=today + timedelta(days=7), warn_days_before=7) == "expiring")
    chk("just outside warn window -> active",
        state(paid_until=today + timedelta(days=8), warn_days_before=7) == "active")
    chk("paid_until today -> expiring (still allowed)",
        state(paid_until=today, warn_days_before=7) == "expiring")
    chk("day after paid_until -> grace",
        state(paid_until=today - timedelta(days=1), grace_days=3) == "grace")
    chk("last grace day -> grace",
        state(paid_until=today - timedelta(days=3), grace_days=3) == "grace")
    chk("past grace -> blocked",
        state(paid_until=today - timedelta(days=4), grace_days=3) == "blocked")
    chk("zero grace: day after paid_until -> blocked",
        state(paid_until=today - timedelta(days=1), grace_days=0) == "blocked")
    chk("BLOCKED_STATES covers suspended+blocked",
        BLOCKED_STATES == {"suspended", "blocked"})

    chk("add_months: Jan 31 + 1 clamps to Feb end",
        add_months(date(2025, 1, 31), 1) == date(2025, 2, 28))
    chk("add_months: leap year Feb clamp",
        add_months(date(2024, 1, 31), 1) == date(2024, 2, 29))
    chk("add_months: year rollover",
        add_months(date(2025, 12, 15), 2) == date(2026, 2, 15))
    chk("add_months: plain month add",
        add_months(date(2025, 7, 6), 3) == date(2025, 10, 6))


# ── Payment recording against a real company row ────────────────────────────

def check_payment_recording(company, superuser):
    today = date.today()
    payment_ids = []
    try:
        # Expired + manually suspended company: one payment restores access.
        Company.objects.filter(pk=company.pk).update(
            is_suspended=True, paid_until=today - timedelta(days=40), grace_days=3
        )
        payment = SubscriptionPayment(
            company_id=company.pk, amount=100, date_received=today,
            months_covered=1, note=f"test {TAG}", created_by=superuser,
        )
        payment.save()
        payment_ids.append(payment.pk)
        fresh = Company.objects.get(pk=company.pk)
        chk("payment on expired company extends from date_received",
            fresh.paid_until == add_months(today, 1), fresh.paid_until)
        chk("payment lifts manual suspension", fresh.is_suspended is False)
        chk("payment snapshots paid_until_after",
            payment.paid_until_after == fresh.paid_until, payment.paid_until_after)
        chk("state after payment is not blocked",
            fresh.subscription_state() not in BLOCKED_STATES, fresh.subscription_state())

        # Second payment while still paid: extends from current paid_until.
        base = fresh.paid_until
        payment2 = SubscriptionPayment(
            company_id=company.pk, amount=200, date_received=today,
            months_covered=2, note=f"test {TAG}", created_by=superuser,
        )
        payment2.save()
        payment_ids.append(payment2.pk)
        fresh = Company.objects.get(pk=company.pk)
        chk("payment on active company extends from paid_until",
            fresh.paid_until == add_months(base, 2), fresh.paid_until)

        # Re-saving an existing payment must not extend again.
        before = fresh.paid_until
        payment2.note = "edited"
        payment2.save()
        fresh = Company.objects.get(pk=company.pk)
        chk("editing a payment does not re-extend paid_until",
            fresh.paid_until == before, fresh.paid_until)
    finally:
        SubscriptionPayment.objects.filter(pk__in=payment_ids).delete()


# ── HTTP enforcement through the real middleware ─────────────────────────────

def set_subscription(company_pk, **fields):
    Company.objects.filter(pk=company_pk).update(**fields)


def check_http_enforcement(company, superuser):
    User = get_user_model()
    username = f"sub_test_{TAG}"
    user = User.objects.create_user(username=username, password="x-not-used")
    Membership.objects.create(user=user, company=company)
    connection.close()

    client = make_client()
    client.force_login(user)
    today = date.today()

    try:
        # Unrestricted: no paid_until -> full access, no banner.
        set_subscription(company.pk, is_suspended=False, paid_until=None)
        resp = client.get("/home/")
        chk("unrestricted company: /home/ is 200", resp.status_code == 200, resp.status_code)
        chk("unrestricted company: no banner",
            b"subscriptionBanner" not in resp.content)

        # Active (outside warn window): no banner.
        set_subscription(company.pk, paid_until=today + timedelta(days=60), warn_days_before=7)
        resp = client.get("/home/")
        chk("active subscription: /home/ is 200", resp.status_code == 200, resp.status_code)
        chk("active subscription: no banner", b"subscriptionBanner" not in resp.content)

        # Expiring: banner shown.
        set_subscription(company.pk, paid_until=today + timedelta(days=3), warn_days_before=7)
        resp = client.get("/home/")
        chk("expiring: /home/ is 200", resp.status_code == 200, resp.status_code)
        chk("expiring: warning banner rendered",
            b"subscription-banner expiring" in resp.content)

        # Grace: still accessible, red-ish banner.
        set_subscription(company.pk, paid_until=today - timedelta(days=1), grace_days=5)
        resp = client.get("/home/")
        chk("grace: /home/ is 200", resp.status_code == 200, resp.status_code)
        chk("grace: grace banner rendered",
            b"subscription-banner grace" in resp.content)

        # Blocked by date: suspension page, 403.
        set_subscription(company.pk, paid_until=today - timedelta(days=30), grace_days=3)
        resp = client.get("/home/")
        chk("blocked: /home/ is 403", resp.status_code == 403, resp.status_code)
        chk("blocked: suspension page rendered",
            b"Account Suspended" in resp.content)
        chk("blocked: page mentions payment", b"payment" in resp.content)

        # Blocked: AJAX/API requests get scrubbed JSON, not HTML.
        resp = client.get("/home/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        chk("blocked: AJAX gets 403 JSON", resp.status_code == 403
            and resp["Content-Type"].startswith("application/json"), resp.status_code)
        body = resp.json()
        chk("blocked: JSON carries the subscription message",
            body.get("status") == "denied" and "subscription" in body.get("message", "").lower(), body)

        # Blocked: other feature prefixes are blocked too.
        resp = client.get("/sale/sales/")
        chk("blocked: /sale/ also suspended", resp.status_code == 403, resp.status_code)

        # Blocked: logout stays reachable (exempt prefix).
        resp = client.get("/authentication/logout/")
        chk("blocked: logout still works", resp.status_code in (200, 302), resp.status_code)
        client.force_login(user)

        # Manual suspension alone blocks even with a fully paid subscription.
        set_subscription(company.pk, is_suspended=True, paid_until=today + timedelta(days=60))
        resp = client.get("/home/")
        chk("manual suspension blocks despite paid_until", resp.status_code == 403, resp.status_code)

        # Superuser (operator) is never locked out.
        original_membership = None
        try:
            original_membership = superuser.membership
        except Membership.DoesNotExist:
            pass
        Membership.objects.update_or_create(user=superuser, defaults={"company": company})
        connection.close()
        su_client = make_client()
        su_client.force_login(superuser)
        resp = su_client.get("/home/")
        chk("superuser exempt from suspension", resp.status_code == 200, resp.status_code)
        if original_membership is not None:
            Membership.objects.update_or_create(
                user=superuser, defaults={"company": original_membership.company}
            )
        else:
            Membership.objects.filter(user=superuser).delete()

        # Payment restores access end-to-end.
        payment = SubscriptionPayment(
            company_id=company.pk, amount=100, date_received=today,
            months_covered=1, note=f"http test {TAG}", created_by=superuser,
        )
        payment.save()
        try:
            resp = client.get("/home/")
            chk("recording a payment restores access", resp.status_code == 200, resp.status_code)
        finally:
            payment.delete()
    finally:
        connection.close()
        Membership.objects.filter(user=user).delete()
        User.objects.filter(pk=user.pk).delete()


def main():
    User = get_user_model()
    superuser = User.objects.filter(is_superuser=True).first()
    if superuser is None:
        chk("a superuser exists", False, "no superuser available")
        return report()

    company = Company.objects.filter(is_active=True, schema_name__isnull=False).order_by("id").first()
    if company is None:
        chk("an active company exists", False, "no active tenant companies")
        return report()

    snapshot = {f: getattr(company, f) for f in SUBSCRIPTION_FIELDS}
    try:
        check_state_machine()
        check_payment_recording(company, superuser)
        check_http_enforcement(company, superuser)
    finally:
        connection.close()
        Company.objects.filter(pk=company.pk).update(**snapshot)

    return report()


def report():
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} subscription checks passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
