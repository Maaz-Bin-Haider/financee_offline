from django.contrib import admin
from financee.admin_site import financee_admin_site
from .models import GeneralSettings

@admin.register(GeneralSettings, site=financee_admin_site)
class GeneralSettingsAdmin(admin.ModelAdmin):
    fields = ('name', 'base_currency', 'symbol_override', 'timezone', 'contact_email', 'phone', 'address')
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    def get_readonly_fields(self, request, obj=None):
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute('SELECT EXISTS(SELECT 1 FROM journalentries)')
            active = cur.fetchone()[0]
        return ('base_currency',) if active else ()
