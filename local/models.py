from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.core.exceptions import ValidationError
from django.db import models

class Currency(models.Model):
    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=12)
    minor_units = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ['code']
        constraints = [models.CheckConstraint(condition=models.Q(code__regex=r'^[A-Z]{3}$'), name='local_currency_code'),
                       models.CheckConstraint(condition=models.Q(minor_units__lte=4), name='local_currency_precision')]
    def __str__(self): return f'{self.code} — {self.name}'

class GeneralSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=150)
    base_currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    symbol_override = models.CharField(max_length=12, blank=True)
    timezone = models.CharField(max_length=64, default='Asia/Karachi')
    contact_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    address = models.TextField(blank=True)
    class Meta:
        verbose_name = 'General Settings'
        verbose_name_plural = 'General Settings'
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='local_one_business')]
    @property
    def currency_symbol(self): return self.symbol_override or self.base_currency.symbol
    def feature_enabled(self, key):
        from .features import all_feature_keys
        return key in all_feature_keys()
    def clean(self):
        super().clean()
        try: ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError): raise ValidationError({'timezone':'Choose a valid IANA timezone.'})
        if self.pk != 1: raise ValidationError('Only one business is allowed.')
    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
    def __str__(self): return self.name
