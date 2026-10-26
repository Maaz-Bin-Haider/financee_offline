"""
tenancy.subscription_emails
===========================
Subscription notification emails, sent to the **company's** billing address
(``Company.contact_email``) — never to individual users.

Two date-driven emails per billing cycle:

* ``expired``   — sent the day the subscription lapses (state enters *grace*):
                  "you have N days to pay, access will be restricted after X".
* ``suspended`` — sent the day the grace window ends (state enters *blocked*):
                  "access is now suspended, it resumes after payment".

Plus two admin-driven emails: ``manual_suspension`` (operator ticked
Suspended in the admin) and ``test`` (settings check from the admin).

Everything is configured from the admin panel via the ``BillingSettings``
singleton: the sender account (SMTP host/port/TLS + email + app password,
e.g. a Gmail app password) and the contact details embedded in every email
(WhatsApp number, phone, free-text note).

Delivery / dedup design
-----------------------
``process_subscription_emails()`` scans all active companies. For a
date-driven email it first INSERTs a ``SubscriptionEmailLog`` row under the
unique ``(company, kind, paid_until)`` constraint and only sends when the
insert wins — so one billing cycle can never email twice, even with several
gunicorn workers scanning concurrently. A ``failed`` row is retried on the
next scan; recording a payment moves ``paid_until``, which starts a fresh
cycle with fresh dedup keys.

The scan runs hourly in a daemon thread started from ``financee/wsgi.py``
(workers coordinate through a shared-cache tick lock), and can be run
manually with ``python manage.py send_subscription_emails [--dry-run]``.
"""
import logging
import threading
import time
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import IntegrityError, connections, transaction

from .models import BillingSettings, Company, SubscriptionEmailLog

logger = logging.getLogger(__name__)

SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


# ── SMTP plumbing ────────────────────────────────────────────────────────────

def _build_connection(cfg: BillingSettings):
    """Mail connection from the admin-managed settings row.

    ``SUBSCRIPTION_EMAIL_BACKEND`` (Django setting) can override the backend —
    the test suite points it at the locmem backend to capture messages.
    """
    backend = getattr(settings, "SUBSCRIPTION_EMAIL_BACKEND", SMTP_BACKEND)
    return get_connection(
        backend=backend,
        host=cfg.smtp_host,
        port=cfg.smtp_port,
        username=cfg.sender_email,
        password=cfg.app_password,
        use_tls=cfg.use_tls,
        timeout=20,
    )


def _send(cfg, to_email, subject, text_body, html_body):
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=f"{cfg.sender_name} <{cfg.sender_email}>",
        to=[to_email],
        connection=_build_connection(cfg),
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)


# ── Email content ────────────────────────────────────────────────────────────

def _contact_lines(cfg):
    lines = []
    if cfg.whatsapp_number:
        lines.append(("WhatsApp", cfg.whatsapp_number))
    if cfg.contact_phone:
        lines.append(("Phone", cfg.contact_phone))
    if cfg.sender_email:
        lines.append(("Email", cfg.sender_email))
    if cfg.contact_note:
        lines.append(("Note", cfg.contact_note))
    return lines


def _fmt(d):
    return d.strftime("%d %b %Y") if d else "-"


def build_email(kind, company, cfg):
    """Return (subject, text_body, html_body) for one email kind."""
    contact = _contact_lines(cfg)
    grace_until = company.grace_until

    if kind == SubscriptionEmailLog.KIND_EXPIRED:
        subject = f"{cfg.sender_name}: Subscription expired — {company.name}"
        headline = "Your subscription has expired"
        paragraphs = [
            f"The subscription for {company.name} expired on {_fmt(company.paid_until)}.",
            (
                f"You have {company.grace_days} day(s) to complete the payment. "
                f"After {_fmt(grace_until)}, access for all of your users will be "
                "restricted until the payment is received."
            ),
            "If you have already made the payment, please contact us so we can confirm it.",
        ]
    elif kind in (SubscriptionEmailLog.KIND_SUSPENDED, SubscriptionEmailLog.KIND_MANUAL_SUSPENSION):
        subject = f"{cfg.sender_name}: Account access suspended — {company.name}"
        headline = "Your account access is suspended"
        if kind == SubscriptionEmailLog.KIND_SUSPENDED:
            paragraphs = [
                (
                    f"The subscription for {company.name} expired on "
                    f"{_fmt(company.paid_until)} and the payment window ended on "
                    f"{_fmt(grace_until)}."
                ),
                "Access for all of your users is now suspended.",
                "Access will be restored immediately once the payment is received.",
            ]
        else:
            paragraphs = [
                f"Access to {company.name} has been suspended.",
                "Please contact us to arrange the payment and restore access.",
            ]
    elif kind == SubscriptionEmailLog.KIND_TEST:
        subject = f"{cfg.sender_name}: Test email — settings are working"
        headline = "Email settings are working"
        paragraphs = [
            "This is a test message from the Financee admin panel.",
            "If you received it, the sender account and app password are configured correctly.",
        ]
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unknown email kind: {kind}")

    text_lines = [headline, ""] + paragraphs
    if contact:
        text_lines += ["", "Contact us:"]
        text_lines += [f"  {label}: {value}" for label, value in contact]
    text_lines += ["", f"— {cfg.sender_name}"]
    text_body = "\n".join(text_lines)

    para_html = "".join(
        f'<p style="margin:0 0 12px;color:#374151;font-size:14px;line-height:1.6;">{p}</p>'
        for p in paragraphs
    )
    contact_html = ""
    if contact:
        rows = "".join(
            '<tr><td style="padding:3px 14px 3px 0;color:#94a3b8;font-size:13px;">{}</td>'
            '<td style="padding:3px 0;color:#1f2937;font-size:13px;font-weight:600;">{}</td></tr>'.format(label, value)
            for label, value in contact
        )
        contact_html = (
            '<div style="margin-top:18px;padding:14px 16px;background:#f8fafc;'
            'border:1px solid #e5e9f2;border-radius:10px;">'
            '<div style="color:#51657b;font-size:13px;font-weight:700;margin-bottom:6px;">Contact us</div>'
            f'<table style="border-collapse:collapse;">{rows}</table></div>'
        )
    html_body = (
        '<div style="background:#f4f6f9;padding:26px 14px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e5e9f2;'
        'border-radius:14px;padding:28px 30px;">'
        f'<div style="color:#2563eb;font-weight:700;font-size:16px;margin-bottom:16px;">{cfg.sender_name}</div>'
        f'<h2 style="margin:0 0 14px;color:#0f172a;font-size:19px;">{headline}</h2>'
        f"{para_html}{contact_html}"
        f'<p style="margin:22px 0 0;color:#94a3b8;font-size:12px;">— {cfg.sender_name}</p>'
        "</div></div>"
    )
    return subject, text_body, html_body


# ── Sending with the log as the audit + dedup record ────────────────────────

def _send_logged(cfg, company, kind, to_email, log_row):
    try:
        subject, text_body, html_body = build_email(kind, company, cfg)
        _send(cfg, to_email, subject, text_body, html_body)
    except Exception as exc:
        logger.exception("Subscription email failed (%s -> %s)", kind, to_email)
        log_row.status = SubscriptionEmailLog.STATUS_FAILED
        log_row.error = str(exc)[:2000]
        log_row.save(update_fields=["status", "error"])
        return False
    log_row.status = SubscriptionEmailLog.STATUS_SENT
    log_row.error = ""
    log_row.save(update_fields=["status", "error"])
    return True


def _claim_cycle_row(company, kind, to_email):
    """
    Insert-first dedup. Returns the log row to send with, or None when this
    cycle's email was already sent / is being sent by another worker.
    A previously FAILED row is reclaimed so delivery is retried.
    """
    try:
        with transaction.atomic():
            return SubscriptionEmailLog.objects.create(
                company=company,
                kind=kind,
                to_email=to_email,
                paid_until=company.paid_until,
                status=SubscriptionEmailLog.STATUS_PENDING,
            )
    except IntegrityError:
        updated = SubscriptionEmailLog.objects.filter(
            company=company,
            kind=kind,
            paid_until=company.paid_until,
            status=SubscriptionEmailLog.STATUS_FAILED,
        ).update(status=SubscriptionEmailLog.STATUS_PENDING, to_email=to_email)
        if updated:
            return SubscriptionEmailLog.objects.get(
                company=company, kind=kind, paid_until=company.paid_until
            )
        return None


def process_subscription_emails(today=None, dry_run=False):
    """
    Scan every active company and send the due date-driven emails.

    Returns a summary dict: {"sent": n, "failed": n, "skipped": {reason: n}}.
    Manually suspended companies are skipped — the operator-triggered
    ``manual_suspension`` email already covered them.
    """
    today = today or date.today()
    summary = {"sent": 0, "failed": 0, "skipped": {}}

    def skip(reason):
        summary["skipped"][reason] = summary["skipped"].get(reason, 0) + 1

    cfg = BillingSettings.get_solo()
    if not cfg.emails_enabled:
        skip("emails_disabled")
        return summary
    if not cfg.smtp_ready:
        skip("smtp_not_configured")
        return summary

    for company in Company.objects.filter(is_active=True):
        if company.paid_until is None:
            skip("no_paid_until")
            continue
        if company.is_suspended:
            skip("manually_suspended")
            continue

        if today > company.grace_until:
            kind = SubscriptionEmailLog.KIND_SUSPENDED
        elif today > company.paid_until:
            kind = SubscriptionEmailLog.KIND_EXPIRED
        else:
            skip("not_due")
            continue

        if not company.contact_email:
            skip("no_contact_email")
            continue

        if dry_run:
            already = SubscriptionEmailLog.objects.filter(
                company=company,
                kind=kind,
                paid_until=company.paid_until,
                status=SubscriptionEmailLog.STATUS_SENT,
            ).exists()
            skip("already_sent" if already else f"would_send_{kind}")
            continue

        log_row = _claim_cycle_row(company, kind, company.contact_email)
        if log_row is None:
            skip("already_sent")
            continue

        if _send_logged(cfg, company, kind, company.contact_email, log_row):
            summary["sent"] += 1
        else:
            summary["failed"] += 1

    return summary


def send_manual_suspension_email(company):
    """Operator suspended a company from the admin: notify its billing email.

    Returns (ok, detail). Never raises — the admin surfaces the outcome.
    """
    cfg = BillingSettings.get_solo()
    if not cfg.emails_enabled or not cfg.smtp_ready:
        return False, "emails disabled or sender not configured"
    if not company.contact_email:
        return False, "company has no contact email"
    log_row = SubscriptionEmailLog.objects.create(
        company=company,
        kind=SubscriptionEmailLog.KIND_MANUAL_SUSPENSION,
        to_email=company.contact_email,
        paid_until=company.paid_until,
        status=SubscriptionEmailLog.STATUS_PENDING,
    )
    ok = _send_logged(cfg, company, SubscriptionEmailLog.KIND_MANUAL_SUSPENSION,
                      company.contact_email, log_row)
    return ok, (log_row.error or "sent")


def send_test_email(to_email):
    """Admin settings check. Returns (ok, detail)."""
    cfg = BillingSettings.get_solo()
    if not cfg.smtp_ready:
        return False, "sender email / app password not configured"
    log_row = SubscriptionEmailLog.objects.create(
        company=None,
        kind=SubscriptionEmailLog.KIND_TEST,
        to_email=to_email,
        status=SubscriptionEmailLog.STATUS_PENDING,
    )
    ok = _send_logged(cfg, Company(name="Test"), SubscriptionEmailLog.KIND_TEST,
                      to_email, log_row)
    return ok, (log_row.error or "sent")


# ── Hourly background scheduler (started from financee/wsgi.py) ─────────────

_scheduler_lock = threading.Lock()
_scheduler_started = False

TICK_CACHE_KEY = "subscription_email_tick"
TICK_SECONDS = 3600           # scan hourly; dedup makes reruns free
TICK_LOCK_TIMEOUT = 3300      # shared-cache lock so one worker scans per hour


def _scheduler_loop():
    time.sleep(30)  # let the container finish booting/migrating
    while True:
        try:
            # With Redis this coordinates across workers/containers; with the
            # locmem fallback each process ticks, and the DB unique constraint
            # still guarantees single delivery.
            if cache.add(TICK_CACHE_KEY, "1", timeout=TICK_LOCK_TIMEOUT):
                summary = process_subscription_emails()
                if summary["sent"] or summary["failed"]:
                    logger.info("Subscription email scan: %s", summary)
        except Exception:
            logger.exception("Subscription email scan crashed; retrying next tick")
        finally:
            connections.close_all()
        time.sleep(TICK_SECONDS)


def start_email_scheduler():
    """Start the daemon scan thread once per process. Never raises."""
    global _scheduler_started
    try:
        with _scheduler_lock:
            if _scheduler_started:
                return
            _scheduler_started = True
        thread = threading.Thread(
            target=_scheduler_loop, name="subscription-email-scheduler", daemon=True
        )
        thread.start()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Could not start the subscription email scheduler")
