"""
tenancy.models
==============
Public tenant registry, company setup, subscription, and email-audit models.
Tenant business/accounting data continues to live in PostgreSQL tenant schemas
and is not represented by Django ORM models.

Company
    One row per tenant. ``schema_name`` is machine-generated as
    ``tenant_company_<pk>`` the first time the row is saved, so administrators
    never type a schema name by hand (which keeps it a safe SQL identifier).

Currency
    Controlled ISO 4217 reference data used to select each company's base
    accounting/reporting currency.

Membership
    Enforces critical business rule #1 — *a user belongs to exactly one
    company* — via a ``OneToOneField`` on the user. The database-level UNIQUE
    constraint that backs the one-to-one is the real guarantee; the admin simply
    surfaces it.

SubscriptionPayment
    Manual subscription-payment log (payments are received outside the system,
    e.g. bank transfer). Recording a payment extends the company's
    ``paid_until`` date and lifts a manual suspension, so the admin workflow is
    simply: client pays -> record payment -> access restored.
"""
import calendar
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


def add_months(day: date, months: int) -> date:
    """Calendar-aware month addition (Jan 31 + 1 month -> Feb 28/29)."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


# Company.subscription_state() values, from most to least restricted.
SUBSCRIPTION_SUSPENDED = "suspended"      # manual override: blocked
SUBSCRIPTION_BLOCKED = "blocked"          # paid_until + grace passed: blocked
SUBSCRIPTION_GRACE = "grace"              # past paid_until, inside grace days
SUBSCRIPTION_EXPIRING = "expiring"        # inside the warn window before expiry
SUBSCRIPTION_ACTIVE = "active"            # paid and outside the warn window
SUBSCRIPTION_UNRESTRICTED = "unrestricted"  # no paid_until set: not enforced

BLOCKED_STATES = frozenset({SUBSCRIPTION_SUSPENDED, SUBSCRIPTION_BLOCKED})

TAX_ENVIRONMENT_TAX = "tax"
TAX_ENVIRONMENT_NON_TAX = "non_tax"
TAX_ENVIRONMENT_CHOICES = (
    (TAX_ENVIRONMENT_NON_TAX, "Non-tax"),
    (TAX_ENVIRONMENT_TAX, "Tax-based"),
)

PROVISIONING_PENDING = "pending"
PROVISIONING_PROVISIONING = "provisioning"
PROVISIONING_READY = "ready"
PROVISIONING_FAILED = "failed"
PROVISIONING_STATE_CHOICES = (
    (PROVISIONING_PENDING, "Pending"),
    (PROVISIONING_PROVISIONING, "Provisioning"),
    (PROVISIONING_READY, "Ready"),
    (PROVISIONING_FAILED, "Failed"),
)


class Currency(models.Model):
    """Controlled public ISO 4217 currency catalogue."""

    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=12)
    minor_units = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "tenancy_currency"
        verbose_name = "Currency"
        verbose_name_plural = "Currencies"
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__regex=r"^[A-Z]{3}$"),
                name="tenancy_currency_valid_code",
            ),
            models.CheckConstraint(
                condition=models.Q(minor_units__lte=4),
                name="tenancy_currency_valid_minor_units",
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Company(models.Model):
    """A tenant. Its data lives in the schema named by ``schema_name``."""

    name = models.CharField(max_length=150, unique=True)
    # Blank on first save; filled in automatically (see save() below). Unique so
    # two companies can never share a schema.
    schema_name = models.CharField(
        max_length=63,
        unique=True,
        blank=True,
        help_text="Auto-generated PostgreSQL schema name (tenant_company_<id>).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive companies cannot have their schema activated for requests.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    base_currency = models.ForeignKey(
        Currency,
        default="PKR",
        on_delete=models.PROTECT,
        related_name="companies",
        help_text=(
            "Accounting and reporting currency. It can be changed only before "
            "the company has financial activity."
        ),
    )
    tax_environment = models.CharField(
        max_length=16,
        choices=TAX_ENVIRONMENT_CHOICES,
        default=TAX_ENVIRONMENT_NON_TAX,
        help_text=(
            "Choose whether this company operates in a tax-based or non-tax "
            "environment. It can be changed only before financial activity."
        ),
    )
    provisioning_state = models.CharField(
        max_length=16,
        choices=PROVISIONING_STATE_CHOICES,
        default=PROVISIONING_PENDING,
        help_text="Operational state of the physical tenant schema.",
    )
    provisioning_error_code = models.CharField(
        max_length=64,
        blank=True,
        help_text="Sanitized provisioning failure category; never contains SQL or secrets.",
    )

    # ── Subscription control (payments are collected outside the system) ──
    contact_email = models.EmailField(
        blank=True,
        help_text=(
            "The company's billing email. Subscription expiry/suspension "
            "notifications are sent here (not to individual users). Leave "
            "empty to skip email notifications for this company."
        ),
    )
    is_suspended = models.BooleanField(
        default=False,
        help_text=(
            "Manual override: immediately block every user of this company, "
            "regardless of the paid-until date. Recording a payment lifts it."
        ),
    )
    paid_until = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Subscription is paid up to this date (inclusive). Leave empty to "
            "disable subscription enforcement for this company."
        ),
    )
    grace_days = models.PositiveSmallIntegerField(
        default=3,
        help_text=(
            "Days of continued access after the paid-until date before the "
            "company is blocked automatically."
        ),
    )
    warn_days_before = models.PositiveSmallIntegerField(
        default=7,
        help_text=(
            "Show the company's users a renewal warning banner this many days "
            "before the paid-until date."
        ),
    )

    # ── Per-company feature flags (admin-controlled) ──
    # JSON list of DISABLED feature keys from tenancy.features.FEATURE_GROUPS:
    # a group key ("stock_reports") or "group.sub" ("sales_reports.trend").
    # Empty list (default) = every feature enabled. Managed through the grouped
    # switches on the company admin form, not edited as raw JSON.
    disabled_features = models.JSONField(
        default=list,
        blank=True,
        help_text="Feature keys switched off for this company.",
    )

    class Meta:
        db_table = "tenancy_company"
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tax_environment__in=[
                    TAX_ENVIRONMENT_TAX,
                    TAX_ENVIRONMENT_NON_TAX,
                ]),
                name="tenancy_company_valid_tax_environment",
            ),
            models.CheckConstraint(
                condition=models.Q(provisioning_state__in=[
                    PROVISIONING_PENDING,
                    PROVISIONING_PROVISIONING,
                    PROVISIONING_READY,
                    PROVISIONING_FAILED,
                ]),
                name="tenancy_company_valid_provisioning_state",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.base_currency_id:
            selected_currency = Currency.objects.filter(
                pk=self.base_currency_id
            ).only("is_active").first()
            if selected_currency is not None and not selected_currency.is_active:
                original_currency = None
                if self.pk:
                    original_currency = type(self).objects.filter(
                        pk=self.pk
                    ).values_list("base_currency_id", flat=True).first()
                if original_currency != self.base_currency_id:
                    raise ValidationError({
                        "base_currency": (
                            "Inactive currency codes cannot be selected for "
                            "new company setup."
                        )
                    })
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "base_currency_id", "tax_environment"
            ).first()
            setup_changed = original is not None and (
                original["base_currency_id"] != self.base_currency_id
                or original["tax_environment"] != self.tax_environment
            )
            if setup_changed and self.has_financial_activity():
                message = (
                    "Base currency and tax environment cannot be changed "
                    "after financial activity exists."
                )
                raise ValidationError({
                    "base_currency": message,
                    "tax_environment": message,
                })

    def has_financial_activity(self):
        """Return whether this tenant contains posted accounting entries."""
        if not self.schema_name:
            return False
        from .utils import tenant_table_has_rows
        return tenant_table_has_rows(self.schema_name, "journalentries")

    def save(self, *args, **kwargs):
        """
        Two-step save so the auto-generated schema name can embed the PK.

        On first insert we save once to obtain a PK, then derive
        ``tenant_company_<pk>`` and save again (only the schema_name column).
        The post_save signal — which provisions the physical schema — fires on
        the *second* save, by which point schema_name is populated.
        """
        # ModelForm calls full_clean(), but programmatic saves must not bypass
        # the accounting-setup locks.
        self.clean()

        creating = self._state.adding and not self.schema_name
        super().save(*args, **kwargs)
        if creating:
            self.schema_name = f"tenant_company_{self.pk}"
            super().save(update_fields=["schema_name"])

    # ── Subscription state ──────────────────────────────────────────────
    @property
    def grace_until(self):
        """Last day of access (inclusive), or None when not enforced."""
        if self.paid_until is None:
            return None
        return self.paid_until + timedelta(days=self.grace_days)

    def subscription_state(self, today=None):
        """
        One of: suspended, blocked, grace, expiring, active, unrestricted.
        ``suspended`` and ``blocked`` (see BLOCKED_STATES) deny tenant access.
        """
        today = today or date.today()
        if self.is_suspended:
            return SUBSCRIPTION_SUSPENDED
        if self.paid_until is None:
            return SUBSCRIPTION_UNRESTRICTED
        if today > self.grace_until:
            return SUBSCRIPTION_BLOCKED
        if today > self.paid_until:
            return SUBSCRIPTION_GRACE
        if today >= self.paid_until - timedelta(days=self.warn_days_before):
            return SUBSCRIPTION_EXPIRING
        return SUBSCRIPTION_ACTIVE

    @property
    def subscription_blocked(self):
        return self.subscription_state() in BLOCKED_STATES

    # ── Feature flags ───────────────────────────────────────────────────
    def feature_enabled(self, key):
        """
        True unless the key or its parent group is in ``disabled_features``.
        Unknown keys are enabled by design: a stale key left in the JSON can
        hide a feature but never break an unrelated request.
        """
        disabled = self.disabled_features or []
        if key in disabled:
            return False
        group = key.split(".", 1)[0]
        return group not in disabled


class Membership(models.Model):
    """Links a user to exactly one company (business rule #1)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membership",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenancy_membership"
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"

    def __str__(self):
        return f"{self.user} -> {self.company}"


class SubscriptionPayment(models.Model):
    """
    A manually recorded subscription payment (received outside the system).

    Saving a NEW payment atomically extends the company's ``paid_until`` by
    ``months_covered`` — from the current ``paid_until`` when it is still in
    the future, otherwise from ``date_received`` — and clears a manual
    suspension. Editing or deleting a payment later never re-shrinks
    ``paid_until``; adjust the company's date directly for corrections.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="subscription_payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date_received = models.DateField(
        default=date.today,
        help_text="The day the money actually arrived.",
    )
    months_covered = models.PositiveSmallIntegerField(
        default=1,
        help_text="How many months of service this payment buys.",
    )
    note = models.CharField(max_length=255, blank=True)
    paid_until_after = models.DateField(
        null=True,
        editable=False,
        help_text="The company's paid-until date right after this payment was applied.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenancy_subscription_payment"
        verbose_name = "Subscription payment"
        verbose_name_plural = "Subscription payments"
        ordering = ["-date_received", "-id"]

    def __str__(self):
        return f"{self.company} — {self.amount} on {self.date_received}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            company = Company.objects.select_for_update().get(pk=self.company_id)
            base = self.date_received or date.today()
            if company.paid_until and company.paid_until > base:
                base = company.paid_until
            company.paid_until = add_months(base, self.months_covered)
            company.is_suspended = False
            company.save(update_fields=["paid_until", "is_suspended"])
            self.paid_until_after = company.paid_until
            super().save(*args, **kwargs)


class BillingSettings(models.Model):
    """
    Singleton: the operator's outgoing-mail account (SMTP with an app
    password, e.g. Gmail) and the contact details embedded in every
    subscription email. Fully editable from the admin panel.
    """

    sender_name = models.CharField(
        max_length=100,
        default="Financee",
        help_text="Display name on outgoing emails.",
    )
    sender_email = models.EmailField(
        blank=True,
        help_text="The email account subscription notifications are sent from.",
    )
    app_password = models.CharField(
        max_length=128,
        blank=True,
        help_text="SMTP app password for the sender account (e.g. a Gmail app password).",
    )
    smtp_host = models.CharField(max_length=120, default="smtp.gmail.com")
    smtp_port = models.PositiveIntegerField(default=587)
    use_tls = models.BooleanField(default=True)
    emails_enabled = models.BooleanField(
        default=True,
        help_text="Master switch: untick to stop all subscription emails.",
    )

    # Contact details shown inside every subscription email.
    whatsapp_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="WhatsApp number clients should message about payments (e.g. +92 300 1234567).",
    )
    contact_phone = models.CharField(max_length=32, blank=True)
    contact_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional extra line shown in emails (e.g. office hours, bank account).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenancy_billing_settings"
        verbose_name = "Billing & email settings"
        verbose_name_plural = "Billing & email settings"

    def __str__(self):
        return f"Billing & email settings ({self.sender_email or 'sender not set'})"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce the singleton
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def smtp_ready(self):
        return bool(self.sender_email and self.app_password)


class SubscriptionEmailLog(models.Model):
    """
    One row per subscription email (attempted or sent). Doubles as the
    dedup guard: for date-driven emails the row is inserted *before* sending
    under a unique (company, kind, paid_until) constraint, so a billing cycle
    can never email twice even across gunicorn workers.
    """

    KIND_EXPIRED = "expired"
    KIND_SUSPENDED = "suspended"
    KIND_MANUAL_SUSPENSION = "manual_suspension"
    KIND_TEST = "test"
    KIND_CHOICES = [
        (KIND_EXPIRED, "Subscription expired (grace notice)"),
        (KIND_SUSPENDED, "Access suspended"),
        (KIND_MANUAL_SUSPENSION, "Access suspended (manual)"),
        (KIND_TEST, "Test email"),
    ]

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subscription_emails",
    )
    kind = models.CharField(max_length=24, choices=KIND_CHOICES)
    to_email = models.EmailField()
    paid_until = models.DateField(
        null=True,
        blank=True,
        help_text="The billing cycle this email belongs to (dedup key).",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenancy_subscription_email_log"
        verbose_name = "Subscription email"
        verbose_name_plural = "Subscription emails"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "kind", "paid_until"],
                condition=models.Q(
                    paid_until__isnull=False,
                    kind__in=["expired", "suspended"],
                ),
                name="uniq_subscription_email_per_cycle",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} -> {self.to_email} ({self.status})"
