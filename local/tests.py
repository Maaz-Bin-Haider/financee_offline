import json
import tempfile
from decimal import Decimal
from pathlib import Path
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection, transaction, IntegrityError, DatabaseError
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import resolve, Resolver404
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import GeneralSettings, Currency

PASSWORD = 'Only-for-disposable-tests-739!'

def scalar(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql,params or [])
        return cur.fetchone()[0]

class OnboardingTests(TestCase):
    def setUp(self): cache.clear()
    def payload(self):
        return dict(company_name='Local Test Company', currency='USD', symbol_override='$', timezone='Asia/Karachi', username='local_owner', password1=PASSWORD,password2=PASSWORD)
    def test_empty_business_and_no_universal_owner(self):
        self.assertEqual(get_user_model().objects.count(),0)
        self.assertEqual(GeneralSettings.objects.count(),0)
        for table in ('items','purchaseinvoices','salesinvoices','journalentries','purchaseunits','draftinvoices'):
            self.assertEqual(scalar('SELECT count(*) FROM '+table),0,table)
        self.assertEqual(scalar('SELECT count(*) FROM parties WHERE NOT is_cash'),0)
        self.assertGreater(scalar('SELECT count(*) FROM chartofaccounts'),0)
    def test_setup_redirect_and_local_owner(self):
        self.assertRedirects(self.client.get('/home/'),'/setup/',fetch_redirect_response=False)
        self.assertContains(self.client.get('/setup/'),'Set up Financee Offline')
        response=self.client.post('/setup/',self.payload())
        self.assertEqual(response.status_code,302)
        owner=get_user_model().objects.get(username='local_owner')
        self.assertTrue(owner.check_password(PASSWORD) and owner.is_superuser and owner.is_staff)
        self.assertEqual(GeneralSettings.objects.get().base_currency_id,'USD')
        self.assertEqual(self.client.post('/setup/',self.payload()).status_code,409)
    def test_weak_password_and_csrf(self):
        payload=self.payload();payload.update(password1='123',password2='123')
        self.assertContains(self.client.post('/setup/',payload),'too short')
        self.assertEqual(get_user_model().objects.count(),0)
        self.assertEqual(Client(enforce_csrf_checks=True).post('/setup/',self.payload()).status_code,403)
    def test_partial_existing_install_is_not_overwritten(self):
        get_user_model().objects.create_user('prior_owner',password=PASSWORD)
        self.assertEqual(self.client.post('/setup/',self.payload()).status_code,409)
        self.assertEqual(get_user_model().objects.count(),1)
        self.assertFalse(GeneralSettings.objects.exists())
    def test_invalid_timezone_is_rejected(self):
        data=self.payload();data['timezone']='Invalid/Nowhere'
        self.assertContains(self.client.post('/setup/',data),'valid IANA timezone')
        self.assertFalse(GeneralSettings.objects.exists())

class LocalCoreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=get_user_model().objects.create_superuser('owner',password=PASSWORD)
        cls.user=get_user_model().objects.create_user('reader',password=PASSWORD)
        cls.profile=GeneralSettings.objects.create(name='Review Company',base_currency_id='USD')
    def setUp(self): cache.clear()
    def execute(self, sql):
        with connection.cursor() as cur: cur.execute(sql)
    def grant(self,*codes):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='auth',codename__in=codes))
    def test_public_only_schema_and_removed_models(self):
        with connection.cursor() as cur:
            cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT LIKE 'pg_%' AND schema_name<>'information_schema'")
            self.assertEqual(cur.fetchall(),[('public',)])
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND (tablename LIKE 'tenancy_%' OR tablename LIKE 'report_email%')")
            self.assertEqual(cur.fetchall(),[])
        self.assertFalse(apps.is_installed('tenancy'))
        self.assertFalse(apps.is_installed('reportmailer'))
        self.assertFalse(Permission.objects.filter(codename__in=['send_reports','manage_report_email']).exists())
        self.assertEqual(scalar('SELECT version FROM offline_schema_version'),2)
    def test_removed_routes(self):
        with self.assertRaises(Resolver404): resolve('/report-email/')
        self.client.force_login(self.owner)
        for path in ('/admin/tenancy/company/','/admin/tenancy/subscriptionpayment/'):
            self.assertEqual(self.client.get(path).status_code,404)
    def test_singleton_enforced_by_database_and_admin(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GeneralSettings.objects.bulk_create([GeneralSettings(id=2,name='Second',base_currency_id='USD')])
        with self.assertRaises(DatabaseError), transaction.atomic():GeneralSettings.objects.all().delete()
        with self.assertRaises(DatabaseError), transaction.atomic():self.execute('TRUNCATE local_generalsettings')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/admin/local/generalsettings/add/').status_code,403)
        self.assertEqual(self.client.get('/admin/local/generalsettings/1/delete/').status_code,403)
    def test_all_retained_modules_enabled(self):
        from .features import all_feature_keys,features_map
        for key in all_feature_keys():self.assertTrue(self.profile.feature_enabled(key),key)
        self.assertNotIn('report_email',features_map(self.profile))
    def test_login_logout_inactive_and_normal_permissions(self):
        self.assertEqual(self.client.post('/authentication/login/',{'username':'reader','password':PASSWORD}).json()['status'],'success')
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.client.get('/purchase/purchasing/',HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,403)
        self.grant('view_purchase')
        self.assertEqual(self.client.get('/purchase/purchasing/').status_code,200)
        self.assertEqual(self.client.get('/admin/').status_code,302)
        self.client.get('/authentication/logout/')
        self.user.is_active=False;self.user.save()
        self.assertEqual(self.client.post('/authentication/login/',{'username':'reader','password':PASSWORD}).json()['status'],'error')
    def test_action_permissions_and_readonly_group(self):
        self.grant('view_purchase','view_draft_invoice','create_draft_invoice')
        self.client.force_login(self.user)
        scalar('SELECT add_party_from_json(%s::jsonb)',[json.dumps({'party_name':'Vendor','party_type':'Vendor','created_by_id':str(self.owner.pk)})])
        scalar('SELECT add_item_from_json(%s::jsonb)',[json.dumps({'item_name':'Device','sale_price':100,'created_by_id':str(self.owner.pk)})])
        payload={'action':'submit','party_name':'Vendor','purchase_date':'2026-10-01','items':[{'item_name':'Device','qty':1,'unit_price':50,'serials':[{'serial':'DENIED-1','comment':''}]}]}
        response=self.client.post('/purchase/purchasing/',data=json.dumps(payload),content_type='application/json',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertIn('permission',response.json()['message'].lower())
        viewers=Group.objects.create(name='view_only_users');self.user.groups.add(viewers)
        self.assertEqual(self.client.get('/draft/get/?nav=last').status_code,403)
        self.assertEqual(scalar('SELECT count(*) FROM purchaseinvoices'),0)
    def test_spotlight_capabilities_and_session_scope(self):
        self.client.force_login(self.user)
        response=self.client.get('/spotlight/search/?q=purchase')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('Purchase',response.content.decode())
        scope=response.json()['scope']
        self.grant('view_purchase')
        self.assertIn('Purchase',self.client.get('/spotlight/search/?q=purchase').content.decode())
        self.assertEqual(self.client.get('/spotlight/search/',HTTP_X_SPOTLIGHT_SCOPE='stale').status_code,409)
        self.client.logout();self.client.force_login(self.user)
        self.assertNotEqual(self.client.get('/spotlight/search/').json()['scope'],scope)
    def test_activity_local_actor_snapshot_and_append_only(self):
        from activity.recorder import record
        req=RequestFactory().get('/');req.user=self.user
        self.assertTrue(record(req,'create','item',1,'Created item'))
        self.user.username='renamed';self.user.save()
        self.assertEqual(scalar("SELECT username FROM activity_events WHERE kind='item'"),'reader')
        for sql in ('UPDATE activity_events SET label=label','DELETE FROM activity_events','TRUNCATE activity_events'):
            with self.assertRaises(DatabaseError),transaction.atomic():
                with connection.cursor() as cur:cur.execute(sql)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/activity/api/team/').status_code,403)
        self.grant('view_team_activity')
        self.assertEqual(self.client.get('/activity/api/team/').status_code,200)
    def test_no_request_selectable_schema_and_auth_admin(self):
        self.client.force_login(self.owner)
        response=self.client.get('/home/?tenant_schema=evil',HTTP_X_TENANT_SCHEMA='evil')
        self.assertEqual(response.status_code,200)
        self.assertEqual(scalar('SELECT current_schema()'),'public')
        self.assertContains(self.client.get('/admin/'),'General Settings')
        self.assertNotContains(self.client.get('/admin/'),'Subscription')
        self.assertEqual(self.client.get('/admin/local/generalsettings/1/change/').status_code,200)
    def test_rate_limit_is_retained(self):
        self.client.force_login(self.user)
        from financee.security import _rate_limit_key
        import time
        req=RequestFactory().get('/spotlight/search/');req.user=self.user
        cache.set(_rate_limit_key(req,'spotlight',int(time.time()//60)),180,65)
        self.assertEqual(self.client.get('/spotlight/search/').status_code,429)
    def test_attachment_paths_and_permissions(self):
        from attachments.utils import _storage_path
        upload=SimpleUploadedFile('invoice.pdf',b'%PDF-1.4 test',content_type='application/pdf')
        with tempfile.TemporaryDirectory() as d, override_settings(PRIVATE_MEDIA_ROOT=d):
            relative,absolute=_storage_path('purchase',1,'pdf',upload)
            self.assertTrue(relative.startswith('business/purchase/1/'))
            self.assertTrue(Path(d).resolve() in absolute.resolve().parents)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/attachments/purchase/1/').status_code,403)
    def test_independent_decimal_accounting_and_currency_lock(self):
        uid=self.owner.pk
        for kind,name in [('Vendor','Vendor'),('Customer','Customer')]:
            scalar('SELECT add_party_from_json(%s::jsonb)',[json.dumps({'party_name':name,'party_type':kind,'created_by_id':str(uid)})])
        scalar('SELECT add_item_from_json(%s::jsonb)',[json.dumps({'item_name':'Device','sale_price':200,'created_by_id':str(uid)})])
        vendor=scalar("SELECT party_id FROM parties WHERE party_name='Vendor'")
        customer=scalar("SELECT party_id FROM parties WHERE party_name='Customer'")
        lines=[dict(item_name='Device',qty=2,unit_price='100.25',serials=[{'serial':'A1'},{'serial':'A2'}])]
        pid=scalar('SELECT create_purchase(%s,%s,%s::jsonb,%s)',[vendor,'2026-10-01',json.dumps(lines),uid])
        self.assertEqual(scalar('SELECT total_amount FROM purchaseinvoices WHERE purchase_invoice_id=%s',[pid]),Decimal('200.50'))
        sold=[dict(item_name='Device',qty=1,unit_price='150.75',serials=['A1'])]
        sid=scalar('SELECT create_sale(%s,%s,%s::jsonb,%s)',[customer,'2026-10-02',json.dumps(sold),uid])
        self.assertEqual(scalar('SELECT total_amount FROM salesinvoices WHERE sales_invoice_id=%s',[sid]),Decimal('150.75'))
        self.assertEqual(scalar('SELECT sum(debit)-sum(credit) FROM journallines'),Decimal('0'))
        self.assertEqual(scalar('SELECT count(*) FROM purchaseunits WHERE in_stock'),1)
        self.assertEqual(scalar("SELECT sum(jl.credit-jl.debit) FROM journallines jl JOIN chartofaccounts c USING(account_id) WHERE c.account_name='Sales Revenue'"),Decimal('150.75'))
        self.assertEqual(scalar("SELECT sum(jl.debit-jl.credit) FROM journallines jl JOIN chartofaccounts c USING(account_id) WHERE c.account_name='Cost of Goods Sold'"),Decimal('100.25'))
        with self.assertRaises(DatabaseError),transaction.atomic():GeneralSettings.objects.filter(pk=1).update(base_currency_id='EUR')
        GeneralSettings.objects.filter(pk=1).update(symbol_override='US$')
        self.assertEqual(GeneralSettings.objects.get().currency_symbol,'US$')
        scalar('SELECT create_sale_return(%s,%s::jsonb,%s)',['Customer',json.dumps(['A1']),uid])
        self.assertEqual(scalar('SELECT count(*) FROM purchaseunits WHERE in_stock'),2)
        self.assertEqual(scalar('SELECT sum(debit)-sum(credit) FROM journallines'),Decimal('0'))

    def test_retained_screen_templates_render(self):
        from spotlight.policy import PAGES
        self.client.force_login(self.owner)
        for path in sorted({target.path for target in PAGES.values()}):
            with self.subTest(path=path): self.assertEqual(self.client.get(path).status_code,200)

    def test_attachment_roundtrip_is_private(self):
        from attachments.utils import save_document_attachments
        uid=self.owner.pk
        scalar('SELECT add_party_from_json(%s::jsonb)',[json.dumps({'party_name':'Vendor','party_type':'Vendor','created_by_id':str(uid)})])
        scalar('SELECT add_item_from_json(%s::jsonb)',[json.dumps({'item_name':'Device','sale_price':200,'created_by_id':str(uid)})])
        vendor=scalar("SELECT party_id FROM parties WHERE party_name='Vendor'")
        pid=scalar('SELECT create_purchase(%s,%s,%s::jsonb,%s)',[vendor,'2026-10-01',json.dumps([dict(item_name='Device',qty=1,unit_price=100,serials=[{'serial':'FILE-1'}])]),uid])
        contents=b'%PDF-1.4 disposable attachment'
        request=RequestFactory().post('/',{'attachment_pdf':SimpleUploadedFile('invoice.pdf',contents,content_type='application/pdf')})
        request.user=self.owner;request.general_settings=self.profile
        with tempfile.TemporaryDirectory() as folder, override_settings(PRIVATE_MEDIA_ROOT=folder):
            save_document_attachments(request,'purchase',pid)
            self.client.force_login(self.owner)
            response=self.client.get(f'/attachments/purchase/{pid}/pdf/download/')
            self.assertEqual(response.status_code,200)
            self.assertEqual(b''.join(response.streaming_content),contents)
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(f'/attachments/purchase/{pid}/pdf/download/').status_code,403)
            self.client.logout()
            self.assertEqual(self.client.get(f'/attachments/purchase/{pid}/pdf/download/').status_code,302)

    def test_multipart_purchase_records_activity_and_private_attachment(self):
        self.client.force_login(self.owner)
        for query, data in [('add_party_from_json',{'party_name':'Offline Vendor','party_type':'Vendor','created_by_id':str(self.owner.pk)}),
                            ('add_item_from_json',{'item_name':'Offline Device','sale_price':200,'created_by_id':str(self.owner.pk)})]:
            scalar('SELECT '+query+'(%s::jsonb)',[json.dumps(data)])
        payload={'action':'submit','party_name':'Offline Vendor','purchase_date':'2026-10-01',
                 'items':[{'item_name':'Offline Device','qty':1,'unit_price':'100.25','serials':[{'serial':'OFFLINE-FILE-1'}]}]}
        contents=b'%PDF-1.4 disposable upload'
        with tempfile.TemporaryDirectory() as folder, override_settings(PRIVATE_MEDIA_ROOT=folder):
            response=self.client.post('/purchase/purchasing/',{'payload':json.dumps(payload),
                'attachment_pdf':SimpleUploadedFile('offline.pdf',contents,content_type='application/pdf')})
            self.assertTrue(response.json().get('success'),response.content)
            pid=scalar('SELECT purchase_invoice_id FROM purchaseinvoices')
            self.assertEqual(scalar('SELECT total_amount FROM purchaseinvoices'),Decimal('100.25'))
            self.assertEqual(scalar("SELECT count(*) FROM activity_events WHERE kind='purchase' AND action='create' AND user_id=%s",[self.owner.pk]),1)
            response=self.client.get(f'/attachments/purchase/{pid}/pdf/download/')
            self.assertEqual(b''.join(response.streaming_content),contents)
            event=scalar("SELECT document_date::text FROM activity_events WHERE kind='purchase' AND action='create'")
            self.assertEqual(event,'2026-10-01')

    def test_confirmed_source_sql_contract_on_fresh_schema(self):
        import hashlib
        contract=json.loads((Path(__file__).resolve().parents[1]/'tests/sql_source_contract.json').read_text())
        with connection.cursor() as cur:
            cur.execute("""SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',
                p.prosrc, pg_get_function_result(p.oid), p.provolatile, p.proisstrict, p.prosecdef
                FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'""")
            actual={name:dict(body_sha256=hashlib.sha256(body.encode()).hexdigest(),result=result,volatility=volatility,strict=strict,security_definer=security) for name,body,result,volatility,strict,security in cur.fetchall()}
        for name,expected in contract['functions'].items():
            with self.subTest(function=name):self.assertEqual(actual.pop(name,None),expected)
        self.assertEqual(set(actual),{'local_profile_guard()','local_profile_no_truncate()','local_currency_posting_lock()'})

    def test_saved_currency_reaches_dashboard_and_transaction_pages(self):
        import re
        self.client.force_login(self.owner)
        paths=['/home/','/purchase/purchasing/','/sale/sales/','/saleReturn/create-sale-return/',
               '/purchaseReturn/create-purchase-return/','/opening-stock/','/draft/',
               '/draft/convert/screen/','/draft/return/screen/','/draft/pending/screen/']
        for code,override in [('AED',''),('USD',''),('EUR','€'),('AED','Dhs')]:
            GeneralSettings.objects.filter(pk=1).update(base_currency_id=code,symbol_override=override)
            for path in paths:
                with self.subTest(code=code,override=override,path=path):
                    response=self.client.get(path)
                    self.assertEqual(response.status_code,200)
                    html=response.content.decode()
                    config=json.loads(re.search(r'<script id="financee-currency" type="application/json">(.*?)</script>',html,re.S)[1])
                    self.assertEqual(config['code'],code)
                    self.assertEqual(config['label'],override or code)
                    self.assertNotIn('PKR',html)
                    self.assertLess(html.index('financee-currency'),html.index('js/currency.'))
        self.assertEqual(scalar('SELECT count(*) FROM journalentries'),0)

    def test_alert_labels_use_selected_currency_without_changing_amounts(self):
        from unittest.mock import patch
        from local.currency import present_dashboard_alerts
        GeneralSettings.objects.filter(pk=1).update(base_currency_id='AED',symbol_override='')
        profile=GeneralSettings.objects.select_related('base_currency').get()
        alerts=[{'title':'Stale Receivable: PKR Traders','message':'Balance PKR 123456.7890 — last activity 60 days ago.'},
                {'title':'Negative Cash Balance','message':'Cash balance is PKR -25.1250. Immediate action required.'},
                {'title':'Risky Customer','message':'High receivable PKR 50000.0001 with no payment received in the last 45 days.'},
                {'title':'No Sales Today','message':'No sales invoices have been recorded for today yet.'}]
        shown=present_dashboard_alerts(alerts,profile)
        self.assertEqual(shown[0]['title'],'Stale Receivable: PKR Traders')
        self.assertEqual(shown[0]['message'],'Balance AED 123456.7890 — last activity 60 days ago.')
        self.assertEqual(shown[1]['message'],'Cash balance is AED -25.1250. Immediate action required.')
        self.assertIn('AED 50000.0001',shown[2]['message'])
        self.assertEqual(shown[3],alerts[3])
        self.assertIn('PKR 123456.7890',alerts[0]['message'])
        self.client.force_login(self.owner)
        with patch('home.views._run_pg_function',return_value=alerts):
            response=self.client.get('/home/api/dash/alerts/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['data'],shown)

    def test_symbol_override_is_serialized_as_data_and_html_escaped(self):
        GeneralSettings.objects.filter(pk=1).update(base_currency_id='AED',symbol_override='</script>')
        self.client.force_login(self.owner)
        response=self.client.get('/home/')
        html=response.content.decode()
        self.assertIn('\\u003C/script\\u003E',html)
        self.assertNotIn('· </script>',html)

    def settings_payload(self, **changes):
        from .features import FEATURE_GROUPS
        values={'name':'Local Test Company','base_currency':'AED','symbol_override':'Dhs','timezone':'Asia/Dubai','contact_email':'accounts@example.test','phone':'+971 50 1234567','address':'Office 12, Dubai','enabled_modules':list(FEATURE_GROUPS)}
        values.update(changes);return values

    def test_owner_settings_editor_and_normal_user_denial(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/admin/local/generalsettings/1/change/').status_code,302)
        self.client.force_login(self.owner)
        response=self.client.post('/admin/local/generalsettings/1/change/',self.settings_payload())
        self.assertEqual(response.status_code,302)
        profile=GeneralSettings.objects.get()
        self.assertEqual((profile.name,profile.base_currency_id,profile.currency_symbol,profile.timezone),('Local Test Company','AED','Dhs','Asia/Dubai'))
        self.assertEqual(profile.disabled_features,[])
        self.assertEqual(self.client.get('/home/').context['business_config']['address'],'Office 12, Dubai')
        bad=self.client.post('/admin/local/generalsettings/1/change/',self.settings_payload(timezone='Not/AZone'))
        self.assertEqual(bad.status_code,200)
        self.assertEqual(GeneralSettings.objects.get().timezone,'Asia/Dubai')

    def test_local_module_guards_hide_and_deny_without_removing_permissions(self):
        self.grant('view_purchase','create_purchase')
        self.client.force_login(self.user)
        GeneralSettings.objects.filter(pk=1).update(disabled_features=['purchases','stock_reports','draft_invoices'])
        home=self.client.get('/home/').content.decode()
        self.assertNotIn('href="/purchase/purchasing/"',home)
        self.assertNotIn('href="/draft/"',home)
        self.assertEqual(self.client.get('/purchase/purchasing/',HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,403)
        self.assertEqual(self.client.post('/purchase/purchasing/',data='{}',content_type='application/json').status_code,403)
        self.assertEqual(self.client.get('/accountsReports/stock-summary/',HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,403)
        self.assertEqual(self.client.get('/draft/get/',HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,403)
        self.assertContains(self.client.get('/home/'),'themeToggle')
        self.assertTrue(get_user_model().objects.get(pk=self.user.pk).has_perm('auth.create_purchase'))
        GeneralSettings.objects.filter(pk=1).update(disabled_features=[])
        self.assertEqual(self.client.get('/purchase/purchasing/').status_code,200)

    def test_module_values_are_validated_in_model_and_database(self):
        profile=GeneralSettings.objects.get();profile.disabled_features=['subscription']
        with self.assertRaises(ValidationError):profile.save()
        with self.assertRaises(IntegrityError),transaction.atomic():GeneralSettings.objects.filter(pk=1).update(disabled_features=['subscription'])
        with self.assertRaises(IntegrityError),transaction.atomic():GeneralSettings.objects.filter(pk=1).update(disabled_features={})

    def test_base_currency_form_error_and_symbol_edit_after_posting(self):
        from .forms import GeneralSettingsForm
        self.execute("INSERT INTO journalentries(description) VALUES('Settings guard test')")
        form=GeneralSettingsForm(data=self.settings_payload(),instance=GeneralSettings.objects.get())
        self.assertFalse(form.is_valid());self.assertIn('base_currency',form.errors)
        self.client.force_login(self.owner)
        response=self.client.post('/admin/local/generalsettings/1/change/',self.settings_payload(base_currency='AED'))
        self.assertEqual(response.status_code,302)
        profile=GeneralSettings.objects.get()
        self.assertEqual(profile.base_currency_id,'USD')
        self.assertEqual(profile.symbol_override,'Dhs')

    def test_saved_timezone_applies_to_python_sql_and_is_reset(self):
        from .middleware import LocalAccessMiddleware
        from django.utils import timezone
        from django.http import HttpResponse
        GeneralSettings.objects.filter(pk=1).update(timezone='Asia/Dubai')
        request=RequestFactory().get('/home/');request.user=self.owner
        middleware=LocalAccessMiddleware(lambda request:HttpResponse())
        middleware.process_request(request)
        self.assertEqual(timezone.get_current_timezone_name(),'Asia/Dubai')
        self.assertEqual(scalar("SELECT current_setting('TimeZone')"),'Asia/Dubai')
        self.assertEqual(str(scalar("SELECT ('2026-10-26 20:30:00Z'::timestamptz)::date")),'2026-10-27')
        middleware.process_response(request,HttpResponse())
        self.assertEqual(scalar("SELECT current_setting('TimeZone')"),'UTC')

    def test_disabling_drafts_keeps_existing_serial_reservations_protected(self):
        uid=self.owner.pk
        for kind,name in [('Vendor','Vendor'),('Customer','Customer')]:
            scalar('SELECT add_party_from_json(%s::jsonb)',[json.dumps({'party_name':name,'party_type':kind,'created_by_id':str(uid)})])
        scalar('SELECT add_item_from_json(%s::jsonb)',[json.dumps({'item_name':'Device','sale_price':200,'created_by_id':str(uid)})])
        vendor=scalar("SELECT party_id FROM parties WHERE party_name='Vendor'")
        customer=scalar("SELECT party_id FROM parties WHERE party_name='Customer'")
        scalar('SELECT create_purchase(%s,%s,%s::jsonb,%s)',[vendor,'2026-10-01',json.dumps([dict(item_name='Device',qty=1,unit_price=100,serials=[{'serial':'RESERVED-1'}])]),uid])
        lines=json.dumps([dict(item_name='Device',qty=1,unit_price=150,serials=['RESERVED-1'])])
        scalar('SELECT create_draft(%s,%s,%s::jsonb,%s)',[customer,'2026-10-02',lines,uid])
        before=scalar('SELECT count(*) FROM journallines')
        GeneralSettings.objects.filter(pk=1).update(disabled_features=['draft_invoices'])
        with self.assertRaises(DatabaseError),transaction.atomic():scalar('SELECT create_sale(%s,%s,%s::jsonb,%s)',[customer,'2026-10-03',lines,uid])
        self.assertTrue(scalar("SELECT is_reserved FROM get_serial_number_details('RESERVED-1')"))
        self.assertEqual(scalar('SELECT count(*) FROM journallines'),before)

    def test_local_pdf_setting_blocks_admin_export(self):
        self.client.force_login(self.owner)
        GeneralSettings.objects.filter(pk=1).update(disabled_features=['pdf_export'])
        self.assertEqual(self.client.get(f'/admin/user-activity/{self.owner.pk}/pdf/').status_code,403)

    def test_local_database_timezone_preserves_instants_and_dst_offsets(self):
        import datetime
        from .middleware import LocalAccessMiddleware
        from django.http import HttpResponse
        for zone in ['Asia/Dubai','America/New_York']:
            GeneralSettings.objects.filter(pk=1).update(timezone=zone)
            request=RequestFactory().get('/home/');request.user=self.owner
            middleware=LocalAccessMiddleware(lambda request:HttpResponse())
            middleware.process_request(request)
            first=scalar("SELECT '2026-11-01 05:30:00Z'::timestamptz")
            second=scalar("SELECT '2026-11-01 06:30:00Z'::timestamptz")
            self.assertEqual(first.astimezone(datetime.timezone.utc),datetime.datetime(2026,11,1,5,30,tzinfo=datetime.timezone.utc))
            self.assertEqual(second-first,datetime.timedelta(hours=1))
            get_user_model().objects.filter(pk=self.user.pk).update(last_login=second)
            self.assertEqual(get_user_model().objects.get(pk=self.user.pk).last_login.astimezone(datetime.timezone.utc),datetime.datetime(2026,11,1,6,30,tzinfo=datetime.timezone.utc))
            middleware.process_response(request,HttpResponse())

    def test_admin_activity_pdf_embeds_local_unicode_font_and_identity(self):
        GeneralSettings.objects.filter(pk=1).update(base_currency_id='EUR',symbol_override='€',name='Owner PDF Test')
        self.client.force_login(self.owner)
        response=self.client.get(f'/admin/user-activity/{self.owner.pk}/pdf/')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertIn(b'/FontFile2',response.content)

class OfflinePresentationTests(TestCase):
    """Render real screens and verify all declared resources resolve locally."""
    @classmethod
    def setUpTestData(cls):
        cls.owner=get_user_model().objects.create_superuser('offline_owner',password=PASSWORD)
        GeneralSettings.objects.create(name='Offline Company',base_currency_id='AED')
    def test_active_screens_have_only_resolvable_local_resources(self):
        from html.parser import HTMLParser
        from django.contrib.staticfiles.storage import staticfiles_storage
        from urllib.parse import urlsplit
        class Resources(HTMLParser):
            def __init__(self):super().__init__();self.urls=[]
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag in ('script','link','img','source','iframe'):
                    target=attrs.get('src') or attrs.get('href')
                    if target:self.urls.append(target)
        self.client.force_login(self.owner)
        paths=['/home/','/purchase/purchasing/','/sale/sales/','/payments/payment/',
               '/receipts/receipt/','/contra/contra/','/saleReturn/create-sale-return/',
               '/purchaseReturn/create-purchase-return/','/items/items-dash/',
               '/parties/parties-dash/','/accountsReports/cash-ledger/',
               '/accountsReports/stock-summary/','/accountsReports/monthly-position/',
               '/set-opening/','/owner-equity/','/month-close/','/sales-reports/',
               '/opening-stock/','/draft/','/draft/convert/screen/',
               '/draft/return/screen/','/draft/pending/screen/','/activity/',
               '/admin/','/admin/local/generalsettings/1/change/']
        for path in paths:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                parser=Resources();parser.feed(response.content.decode())
                for resource in parser.urls:
                    url=urlsplit(resource)
                    self.assertFalse(url.netloc,resource)
                    if resource.startswith('/static/'):
                        self.assertTrue(staticfiles_storage.exists(url.path.removeprefix('/static/')),resource)
                if path=='/home/':
                    self.assertContains(response,'AED')
                    self.assertNotContains(response,'PKR')
    def test_login_works_without_remote_resources(self):
        response=self.client.get('/authentication/login/')
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'https://')
        from django.contrib.staticfiles.storage import staticfiles_storage
        self.assertContains(response,staticfiles_storage.url('vendor/sweetalert2/dist/sweetalert2.all.min.js'))
