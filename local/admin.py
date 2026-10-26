from django.contrib import admin
from django.db import connection
from django.utils.html import format_html
from financee.admin_site import financee_admin_site
from .models import GeneralSettings
from .forms import GeneralSettingsForm

@admin.register(GeneralSettings, site=financee_admin_site)
class GeneralSettingsAdmin(admin.ModelAdmin):
    form = GeneralSettingsForm
    fieldsets = (
        ('Company identity',{'fields':('name','address','phone','contact_email')}),
        ('Currency and local time',{'fields':('currency_status','base_currency','symbol_override','timezone')}),
        ('Local module availability',{'fields':('enabled_modules',),'classes':('collapse',)}),
    )
    readonly_fields = ('currency_status',)
    change_form_template = 'local/generalsettings_change.html'
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    @admin.display(description='Currency status')
    def currency_status(self,obj):
        if obj is None:return ''
        with connection.cursor() as cur:
            cur.execute('SELECT EXISTS(SELECT 1 FROM journalentries)')
            locked=cur.fetchone()[0]
        return format_html('{} · Symbol: {} · {}', obj.base_currency_id,obj.currency_symbol,
            'Base currency locked after financial activity. Display symbol remains editable.' if locked else 'Base currency can change until the first financial posting. No automatic conversion.')
    def get_readonly_fields(self, request, obj=None):
        with connection.cursor() as cur:
            cur.execute('SELECT EXISTS(SELECT 1 FROM journalentries)')
            active = cur.fetchone()[0]
        return ('currency_status','base_currency') if active else ('currency_status',)
