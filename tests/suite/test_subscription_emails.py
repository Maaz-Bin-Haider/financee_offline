#!/usr/bin/env python3
"""Subscription notification emails: BillingSettings singleton, the
expired-day and suspension-day emails with per-cycle dedup and failure retry,
manual-suspension and test emails, contact-detail embedding, and the admin
screens. Uses Django's locmem email backend — nothing is really sent.

All mutated state (company fields, settings row, log rows) is restored in
``finally``.

Run inside the web container:
    docker compose -f deploy/docker-compose.yml exec -e PYTHONPATH=/app web \
        python tests/suite/test_subscription_emails.py
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
from django.core import mail  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from tenancy.models import (  # noqa: E402
    BillingSettings,
    Company,
    SubscriptionEmailLog,
)
from tenancy.subscription_emails import (  # noqa: E402
    process_subscription_emails,
    send_manual_suspension_email,
    send_test_email,
)

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
BROKEN = "financee.no_such_backend.EmailBackend"

COMPANY_FIELDS = ("is_suspended", "paid_until", "grace_days", "warn_days_before", "contact_email")
SETTINGS_FIELDS = (
    "sender_name", "sender_email", "app_password", "smtp_host", "smtp_port",
    "use_tls", "emails_enabled", "whatsapp_number", "contact_phone", "contact_note",
)


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))
    return bool(ok)


def outbox():
    return getattr(mail, "outbox", [])


def clear_outbox():
    mail.outbox = []


def set_company(pk, **fields):
    Company.objects.filter(pk=pk).update(**fields)


def configure_settings(**overrides):
    cfg = BillingSettings.get_solo()
    values = {
        "sender_name": "Financee Billing",
        "sender_email": "billing@example.com",
        "app_password": "app-password-123",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "use_tls": True,
        "emails_enabled": True,
        "whatsapp_number": "+92 300 1234567",
        "contact_phone": "+92 42 111 222",
        "contact_note": "Office hours 9am-6pm",
    }
    values.update(overrides)
    for field, value in values.items():
        setattr(cfg, field, value)
    cfg.save()
    return cfg


def check_singleton():
    cfg = BillingSettings.get_solo()
    chk("get_solo creates/returns pk=1", cfg.pk == 1, cfg.pk)
    rogue = BillingSettings(sender_name="Rogue")
    rogue.save()
    chk("save() forces the singleton pk", rogue.pk == 1 and BillingSettings.objects.count() == 1,
        BillingSettings.objects.count())
    chk("smtp_ready false without credentials",
        not BillingSettings(sender_email="", app_password="").smtp_ready)
    chk("smtp_ready true with credentials",
        BillingSettings(sender_email="a@b.c", app_password="x").smtp_ready)


def check_scanner(company):
    today = date.today()
    email = f"billing+{TAG}@example.com"

    # Not configured -> nothing goes out.
    configure_settings(sender_email="", app_password="")
    set_company(company.pk, is_suspended=False, contact_email=email,
                paid_until=today - timedelta(days=1), grace_days=5)
    clear_outbox()
    summary = process_subscription_emails()
    chk("unconfigured SMTP: skipped, nothing sent",
        summary["sent"] == 0 and summary["skipped"].get("smtp_not_configured") == 1 and not outbox(),
        summary)

    # Master switch off -> nothing goes out.
    configure_settings(emails_enabled=False)
    summary = process_subscription_emails()
    chk("emails disabled: skipped, nothing sent",
        summary["sent"] == 0 and summary["skipped"].get("emails_disabled") == 1 and not outbox(),
        summary)

    # Expired yesterday, 5 grace days -> the "expired" email.
    cfg = configure_settings()
    clear_outbox()
    summary = process_subscription_emails()
    chk("expiry day: one email sent", summary["sent"] == 1 and len(outbox()) == 1, summary)
    if outbox():
        msg = outbox()[0]
        chk("expired email goes to the company address", msg.to == [email], msg.to)
        chk("expired email sent from configured sender",
            msg.from_email == "Financee Billing <billing@example.com>", msg.from_email)
        chk("expired subject names the company", company.name in msg.subject, msg.subject)
        grace_until = (today - timedelta(days=1)) + timedelta(days=5)
        chk("expired body states the grace deadline",
            grace_until.strftime("%d %b %Y") in msg.body, msg.body)
        chk("expired body states the grace days", "5 day(s)" in msg.body, msg.body)
        chk("expired body carries the WhatsApp number", cfg.whatsapp_number in msg.body, msg.body)
        chk("expired body carries the contact note", cfg.contact_note in msg.body, msg.body)
        html = msg.alternatives[0][0] if msg.alternatives else ""
        chk("expired email has an HTML part", "Contact us" in html and cfg.whatsapp_number in html)
    log = SubscriptionEmailLog.objects.filter(company=company, kind="expired").order_by("-id").first()
    chk("expired email logged as sent", log is not None and log.status == "sent", log)

    # Second scan of the same cycle -> dedup, no new email.
    clear_outbox()
    summary = process_subscription_emails()
    chk("expired email deduped within the cycle",
        summary["sent"] == 0 and summary["skipped"].get("already_sent") == 1 and not outbox(),
        summary)

    # Grace over -> the "suspended" email (new dedup key: same paid_until, other kind).
    set_company(company.pk, paid_until=today - timedelta(days=10), grace_days=3)
    company.refresh_from_db()
    clear_outbox()
    summary = process_subscription_emails()
    chk("suspension day: one email sent", summary["sent"] == 1 and len(outbox()) == 1, summary)
    if outbox():
        msg = outbox()[0]
        chk("suspended subject says access suspended", "suspended" in msg.subject.lower(), msg.subject)
        chk("suspended body says access resumes after payment",
            "restored immediately once the payment" in msg.body, msg.body)
        chk("suspended body carries the WhatsApp number", cfg.whatsapp_number in msg.body)
    clear_outbox()
    summary = process_subscription_emails()
    chk("suspended email deduped within the cycle",
        summary["sent"] == 0 and not outbox(), summary)

    # A recorded payment starts a new cycle -> nothing due.
    set_company(company.pk, paid_until=today + timedelta(days=30))
    summary = process_subscription_emails()
    chk("paid again: nothing due", summary["sent"] == 0
        and summary["skipped"].get("not_due", 0) >= 1, summary)

    # New cycle that later expires gets a fresh email (dedup is per cycle).
    set_company(company.pk, paid_until=today - timedelta(days=2), grace_days=30)
    clear_outbox()
    summary = process_subscription_emails()
    chk("next cycle emails again", summary["sent"] == 1 and len(outbox()) == 1, summary)

    # Missing contact email -> skipped.
    set_company(company.pk, contact_email="", paid_until=today - timedelta(days=1), grace_days=0)
    clear_outbox()
    summary = process_subscription_emails()
    chk("no contact email: skipped", summary["sent"] == 0
        and summary["skipped"].get("no_contact_email", 0) >= 1 and not outbox(), summary)

    # Manually suspended companies are left to the manual email.
    set_company(company.pk, contact_email=email, is_suspended=True)
    summary = process_subscription_emails()
    chk("manually suspended: scanner skips", summary["skipped"].get("manually_suspended", 0) >= 1, summary)
    set_company(company.pk, is_suspended=False)

    # Dry run reports without sending or logging.
    set_company(company.pk, paid_until=today - timedelta(days=60), grace_days=3)
    clear_outbox()
    summary = process_subscription_emails(dry_run=True)
    chk("dry run: reports would_send, sends nothing",
        summary["sent"] == 0 and summary["skipped"].get("would_send_suspended") == 1 and not outbox(),
        summary)
    chk("dry run: no log row created",
        not SubscriptionEmailLog.objects.filter(
            company=company, kind="suspended", paid_until=today - timedelta(days=60)).exists())


def check_failure_retry(company):
    today = date.today()
    email = f"billing+{TAG}@example.com"
    configure_settings()
    # paid_until = today-3 is a fresh cycle key not used by check_scanner.
    set_company(company.pk, is_suspended=False, contact_email=email,
                paid_until=today - timedelta(days=3), grace_days=45)

    settings.SUBSCRIPTION_EMAIL_BACKEND = BROKEN
    clear_outbox()
    summary = process_subscription_emails()
    chk("broken SMTP: failure recorded", summary["failed"] == 1 and summary["sent"] == 0, summary)
    log = SubscriptionEmailLog.objects.filter(
        company=company, kind="expired", paid_until=today - timedelta(days=3)
    ).first()
    chk("failed attempt logged with error", log is not None and log.status == "failed" and log.error, log)

    settings.SUBSCRIPTION_EMAIL_BACKEND = LOCMEM
    clear_outbox()
    summary = process_subscription_emails()
    chk("failed email retried on next scan", summary["sent"] == 1 and len(outbox()) == 1, summary)
    log.refresh_from_db()
    chk("log row flipped to sent after retry", log.status == "sent" and not log.error, log.status)


def check_manual_and_test(company):
    email = f"billing+{TAG}@example.com"
    configure_settings()
    set_company(company.pk, contact_email=email)
    company.refresh_from_db()

    clear_outbox()
    ok, detail = send_manual_suspension_email(company)
    chk("manual suspension email sends", ok and len(outbox()) == 1, detail)
    if outbox():
        msg = outbox()[0]
        chk("manual email says suspended + contact us",
            "suspended" in msg.subject.lower() and "Contact us" in (msg.alternatives[0][0] if msg.alternatives else ""),
            msg.subject)
    ok2, _ = send_manual_suspension_email(company)
    chk("manual email has no cycle dedup (can resend)", ok2 and len(outbox()) == 2)

    set_company(company.pk, contact_email="")
    company.refresh_from_db()
    ok, detail = send_manual_suspension_email(company)
    chk("manual email refused without contact email", not ok, detail)

    clear_outbox()
    ok, detail = send_test_email("operator@example.com")
    chk("test email sends", ok and len(outbox()) == 1, detail)
    chk("test email logged", SubscriptionEmailLog.objects.filter(
        kind="test", to_email="operator@example.com", status="sent").exists())


def check_admin_pages(company):
    User = get_user_model()
    superuser = User.objects.filter(is_superuser=True).first()
    client = Client(SERVER_NAME="localhost")
    client.force_login(superuser)

    resp = client.get("/admin/tenancy/billingsettings/")
    chk("billing settings changelist redirects to the singleton form",
        resp.status_code == 302 and "/change/" in resp["Location"], resp.status_code)
    resp = client.get(resp["Location"])
    chk("billing settings form renders", resp.status_code == 200, resp.status_code)
    chk("billing settings form offers the test-email button",
        b"Send a test email" in resp.content)
    chk("app password uses a password input", b'type="password"' in resp.content)

    resp = client.get("/admin/tenancy/subscriptionemaillog/")
    chk("email log changelist renders", resp.status_code == 200, resp.status_code)

    configure_settings()
    clear_outbox()
    resp = client.get("/admin/tenancy/billingsettings/send-test-email/", follow=True)
    chk("admin test-email button sends", resp.status_code == 200 and len(outbox()) == 1,
        (resp.status_code, len(outbox())))

    # Manual suspension from the admin action sends the notification.
    email = f"billing+{TAG}@example.com"
    set_company(company.pk, is_suspended=False, contact_email=email)
    clear_outbox()
    resp = client.post(
        "/admin/tenancy/company/",
        data={"action": "suspend_companies", "_selected_action": [str(company.pk)]},
        follow=True,
    )
    company.refresh_from_db()
    chk("admin suspend action suspends", resp.status_code == 200 and company.is_suspended,
        (resp.status_code, company.is_suspended))
    chk("admin suspend action emails the company",
        len(outbox()) == 1 and outbox()[0].to == [email], [m.to for m in outbox()])


def main():
    company = Company.objects.filter(is_active=True, schema_name__isnull=False).order_by("id").first()
    if company is None:
        chk("an active company exists", False, "no active tenant companies")
        return report()

    original_backend = getattr(settings, "SUBSCRIPTION_EMAIL_BACKEND", None)
    settings.SUBSCRIPTION_EMAIL_BACKEND = LOCMEM
    mail.outbox = []

    company_snapshot = {f: getattr(company, f) for f in COMPANY_FIELDS}
    settings_row = BillingSettings.objects.filter(pk=1).first()
    settings_snapshot = (
        {f: getattr(settings_row, f) for f in SETTINGS_FIELDS} if settings_row else None
    )
    log_ids_before = set(SubscriptionEmailLog.objects.values_list("id", flat=True))

    try:
        check_singleton()
        check_scanner(company)
        check_failure_retry(company)
        check_manual_and_test(company)
        check_admin_pages(company)
    finally:
        connection.close()
        Company.objects.filter(pk=company.pk).update(**company_snapshot)
        SubscriptionEmailLog.objects.exclude(id__in=log_ids_before).delete()
        if settings_snapshot is None:
            BillingSettings.objects.filter(pk=1).delete()
        else:
            BillingSettings.objects.filter(pk=1).update(**settings_snapshot)
        if original_backend is None:
            if hasattr(settings, "SUBSCRIPTION_EMAIL_BACKEND"):
                delattr(settings, "SUBSCRIPTION_EMAIL_BACKEND")
        else:
            settings.SUBSCRIPTION_EMAIL_BACKEND = original_backend

    return report()


def report():
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} subscription email checks passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
