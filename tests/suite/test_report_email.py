#!/usr/bin/env python3
"""Report emails against real PostgreSQL in a disposable test stack only.

Creates/removes its own synthetic schemas; never runs in the manual review DB.
Old-image compatibility runs skip this module when the running image lacks it.
"""
import importlib.util
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
if importlib.util.find_spec('reportmailer') is None:
    print('SKIP: running image predates report emails.')
    raise SystemExit(0)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings')
import django
django.setup()
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import smtplib
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import psycopg2
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.core.cache import cache
from django.db import connection, connections
from django.test import Client, override_settings
from tenancy.models import Company, Membership
from tenancy.utils import set_search_path, reset_search_path
from reportmailer import service, reports
from _harness import Tester, DSN

BOOKS="""SELECT jsonb_build_object('journal',(SELECT jsonb_build_array(count(*),sum(debit),sum(credit)) FROM journallines),
 'sales',(SELECT count(*) FROM salesinvoices),'units',(SELECT count(*) FROM purchaseunits),
 'balance',get_trial_balance_json())::text"""


class CompanyReportEmails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tag=f'email_{os.getpid()}_{int(time.time())}'
        cls.day=datetime.now(timezone.utc).astimezone(service.ZoneInfo('Asia/Karachi')).date()-timedelta(days=1)
        cls.now=datetime.combine(cls.day+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc)+timedelta(hours=7)
        cls.permissions=list(Permission.objects.filter(content_type__app_label='auth',codename__in=['send_reports','can_view_sale_wise_profit']))
        assert len(cls.permissions)==2, 'post_migrate must seed send_reports'
        cls.companies=[]; cls.users=[]; cls.testers=[]
        for index,currency in enumerate(('PKR','AED')):
            company=Company.objects.create(name=f'{cls.tag}_{index}',base_currency_id=currency,disabled_features=[])
            company.refresh_from_db(); cls.companies.append(company)
            user=get_user_model().objects.create_user(username=f'{cls.tag}_{index}',password='test-only')
            user.user_permissions.set(cls.permissions)
            Membership.objects.create(user=user,company=company); cls.users.append(user)
            conn=psycopg2.connect(**DSN); conn.autocommit=True
            t=Tester(conn,company.schema_name,user.pk,cls.tag); cls.testers.append(t)
            vendor=t.add_party('Vendor',name='EMAIL SAME VENDOR')
            customer=t.add_party('Customer',name='EMAIL SAME CUSTOMER')
            item=t.add_item(name='EMAIL SAME PHONE')
            serials=['EMAIL-SAME-1','EMAIL-SAME-2','EMAIL-SAME-3']
            t.purchase(vendor,serials,unit_price=100+index*100,item_name=item,date=str(cls.day-timedelta(days=1)))
            t.sale(customer,serials[:2],unit_price=150+index*100,item_name=item,date=str(cls.day))
            t.sale_return(customer,[serials[0]])
            draft=t.exec('SELECT create_draft(%s,%s,%s::jsonb,%s)',[t.party_id(customer),cls.day,
                json.dumps([{'item_name':item,'qty':1,'unit_price':None,'serials':[serials[2]]}]),user.pk])
            t.exec('SELECT convert_draft_tranche(%s,%s::jsonb,%s,%s)',[draft,
                json.dumps([{'item_name':item,'qty':1,'unit_price':180+index*100,'serials':[serials[2]]}]),cls.day,user.pk])
        reset_search_path()

    @classmethod
    def tearDownClass(cls):
        reset_search_path()
        for t in cls.testers: t.conn.close()
        for company in cls.companies:
            assert company.name.startswith(cls.tag+'_')
            with connection.cursor() as cursor: cursor.execute(f'DROP SCHEMA "{company.schema_name}" CASCADE')
            company.delete()
        for user in cls.users: user.delete()
        reset_search_path()

    def setUp(self):
        self.enabled=override_settings(REPORT_EMAIL_ENABLED=True)
        self.enabled.enable(); cache.clear()
        for index,(company,user) in enumerate(zip(self.companies,self.users)):
            Company.objects.filter(pk=company.pk).update(disabled_features=[],is_active=True,is_suspended=False,paid_until=None)
            company.refresh_from_db()
            user.is_active=True; user.save(); user.user_permissions.set(self.permissions)
            with service.tenant(company):
                with connection.cursor() as cursor:
                    cursor.execute('TRUNCATE report_email_settings,report_email_recipients,report_email_log RESTART IDENTITY')
                service.query('SELECT save_report_email_settings_from_json(%s::jsonb)',[json.dumps({
                    'sender_email':f'sender-{index}@example.test','app_password':f'secret-{index}',
                    'authorized_user_id':user.pk,'send_hour':0,'send_minute':0,'is_enabled':True,
                    'timezone':'Asia/Karachi' if index==0 else 'Asia/Dubai'})])
                service.query('SELECT add_report_recipient_from_json(%s::jsonb)',[json.dumps({'email':f'owner-{index}@example.test'})])
        self.client=Client(SERVER_NAME='localhost'); self.client.force_login(self.users[0])
        self.ajax={'HTTP_X_REQUESTED_WITH':'XMLHttpRequest'}

    def tearDown(self):
        reset_search_path(); self.enabled.disable()

    def post(self,path,data):
        return self.client.post('/report-email/'+path,data=json.dumps(data),content_type='application/json',**self.ajax)

    def in_company(self,index,sql,params=None):
        with service.tenant(self.companies[index]), connection.cursor() as cursor:
            cursor.execute(sql,params or [])
            if not cursor.description: return None
            value=cursor.fetchone()[0]
            if cursor.description[0].type_code in (114,3802) and isinstance(value,str):
                return json.loads(value,parse_float=Decimal)
            return value

    def state(self,index=0):
        return self.in_company(index,'SELECT report_email_log_list(100,0)')

    def test_settings_secret_mask_and_actor_scope(self):
        response=self.client.get('/report-email/settings/',**self.ajax)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('secret-0',response.content.decode())
        self.assertTrue(response.json()['settings']['has_password'])
        response=self.post('settings/save/',{'sender_email':'replacement@example.test','is_enabled':False,
            'authorized_user_id':self.users[1].pk,'actor':'forged','company_id':self.companies[1].pk})
        self.assertEqual(response.status_code,200,response.content)
        raw=response.json()['settings']
        self.assertEqual(raw['authorized_user_id'],self.users[0].pk)
        self.assertEqual(raw['updated_by'],self.users[0].username)
        self.assertEqual(self.in_company(0,'SELECT app_password FROM report_email_settings'),'secret-0')
        self.assertEqual(self.in_company(1,'SELECT sender_email FROM report_email_settings'),'sender-1@example.test')
        self.assertEqual(self.post('settings/save/',{'sender_email':'replacement@example.test','app_password':''}).status_code,200)
        self.assertFalse(self.client.get('/report-email/settings/',**self.ajax).json()['settings']['has_password'])

    def test_malformed_configuration_and_csrf(self):
        for data in ([],None,{'sender_email':'x'}, {'sender_email':'a@example.test','timezone':'Not/AZone'},
                     {'sender_email':'a@example.test','smtp_host':'169.254.169.254'},
                     {'sender_email':'a@example.test','smtp_port':25},
                     {'sender_email':'a@example.test','sender_name':'x\r\nBcc: other@example.test'}):
            self.assertEqual(self.post('settings/save/',data).status_code,400,data)
        csrf=Client(SERVER_NAME='localhost',enforce_csrf_checks=True);csrf.force_login(self.users[0])
        self.assertEqual(csrf.post('/report-email/send-now/',data='{}',content_type='application/json').status_code,403)
        self.assertEqual(self.client.get('/report-email/send-now/',**self.ajax).status_code,405)

    def test_recipient_and_log_cross_company_ids(self):
        b=self.in_company(1,"SELECT add_report_recipient_from_json(%s::jsonb)",[json.dumps({'email':'second-beta@example.test'})])
        self.assertEqual(self.post('recipients/delete/',{'recipient_id':b[-1]['recipient_id']}).status_code,400)
        self.assertEqual(self.post('recipients/add/',{'email':'OWNER-0@example.test'}).status_code,400)
        self.assertEqual(self.post('recipients/update/',{'recipient_id':1,'email':'changed-alpha@example.test','is_active':False}).status_code,200)
        self.assertEqual(self.in_company(1,'SELECT email FROM report_email_recipients WHERE recipient_id=1'),'owner-1@example.test')
        self.in_company(1,"SELECT report_email_claim(%s,'manual','beta-secret-actor')",[self.day])
        body=self.client.get('/report-email/log/?company_id='+str(self.companies[1].pk),**self.ajax).content.decode()
        self.assertNotIn('beta-secret-actor',body)
        self.assertNotIn('sender-1',self.client.get('/report-email/settings/',**self.ajax).content.decode())

    def test_each_permission_and_global_and_source_feature_guards(self):
        for codename in ('send_reports','can_view_sale_wise_profit'):
            self.users[0].user_permissions.set([p for p in self.permissions if p.codename==codename])
            self.assertEqual(self.client.get('/report-email/settings/',**self.ajax).status_code,403)
            self.assertEqual(self.post('send-now/',{}).status_code,403)
        self.users[0].user_permissions.set(self.permissions)
        for flags in (['report_email'],['sales_reports'],['sales_reports.sale_wise']):
            Company.objects.filter(pk=self.companies[0].pk).update(disabled_features=flags)
            self.assertEqual(self.client.get('/report-email/settings/',**self.ajax).status_code,403)
            with self.assertRaises(service.ReportEmailError): service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)
        Company.objects.filter(pk=self.companies[0].pk).update(disabled_features=[])
        with override_settings(REPORT_EMAIL_ENABLED=False):
            self.assertEqual(self.post('send-now/',{}).status_code,403)

    def test_mail_figures_reconcile_normal_return_and_draft_conversion(self):
        sent=[]
        before=self.in_company(0,BOOKS)
        with patch.object(service,'deliver',side_effect=lambda message,raw: sent.append(message)):
            result=service.send_report(self.companies[0].pk,self.day,actor_id=self.users[0].pk)
        self.assertEqual(result['status'],'sent',result)
        screen=self.client.get('/sales-reports/api/sale-wise/',{'from':str(self.day),'to':str(self.day)},**self.ajax).json()
        self.assertEqual(screen['totals']['units'],2)
        self.assertEqual(Decimal(str(screen['totals']['revenue'])),Decimal('330'))
        self.assertEqual(Decimal(str(screen['totals']['profit'])),Decimal('130'))
        self.assertIn('PKR 130.00',sent[0].body)
        self.assertNotIn('EMAIL-SAME-1',str(sent[0].alternatives[0]))
        self.assertIn('EMAIL-SAME-3',str(sent[0].alternatives[0]))
        self.assertEqual(self.in_company(0,BOOKS),before)

    def test_manual_and_test_do_not_satisfy_schedule(self):
        with patch.object(service,'deliver') as delivered:
            self.assertEqual(self.post('send-now/',{'report_date':str(self.day)}).status_code,200)
            self.assertEqual(self.post('send-test/',{}).status_code,200)
            result=service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)
            self.assertEqual(result['status'],'sent',result)
            self.assertEqual(service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)['status'],'skipped')
            self.assertEqual(delivered.call_count,3)
        self.assertEqual({r['trigger_source'] for r in self.state()['rows']},{'manual','test','schedule'})

    def test_concurrent_workers_reserve_before_smtp(self):
        entered=threading.Event(); release=threading.Event()
        def smtp(*_): entered.set(); self.assertTrue(release.wait(5))
        def send():
            try: return service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)
            finally: connections.close_all()
        with patch.object(service,'deliver',side_effect=smtp) as delivered,ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(send); self.assertTrue(entered.wait(5))
            second=pool.submit(send)
            with self.assertRaises(service.ReportEmailError): second.result(timeout=5)
            release.set(); self.assertEqual(first.result(timeout=5)['status'],'sent')
            self.assertEqual(delivered.call_count,1)
        self.assertEqual(len(self.state()['rows']),1)

    def test_one_company_failure_does_not_stop_another(self):
        def smtp(message,raw):
            if raw['sender_email']=='sender-0@example.test': raise smtplib.SMTPAuthenticationError(535,b'bad secret-0')
        with patch.object(service,'deliver',side_effect=smtp) as delivered:
            service.tick(now=self.now)
        self.assertEqual(delivered.call_count,2)
        self.assertEqual(self.state(0)['rows'][0]['status'],'failed')
        self.assertEqual(self.state(1)['rows'][0]['status'],'sent')
        self.assertNotIn('secret-0',json.dumps(self.state(0),default=str))
        self.assertEqual(service.query('SELECT current_schema()'),'public')

    def test_unknown_outcome_holds_until_rearm_and_obeys_new_schedule(self):
        with patch.object(service,'deliver',side_effect=ConnectionError('secret-0 should never leak')):
            self.assertEqual(service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)['status'],'unknown')
        with patch.object(service,'deliver') as delivered:
            self.assertEqual(service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)['status'],'skipped')
            self.assertEqual(self.post('rearm/',{'report_date':str(self.day)}).status_code,200)
            self.in_company(0,'UPDATE report_email_settings SET send_hour=23')
            self.assertEqual(service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)['status'],'skipped')
            self.in_company(0,'UPDATE report_email_settings SET send_hour=0')
            self.assertEqual(service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)['status'],'sent')
            self.assertEqual(delivered.call_count,1)
        rows=self.state()['rows']
        self.assertTrue(any(r['superseded'] and r['status']=='unknown' for r in rows))
        self.assertTrue(any(r['trigger_source']=='rearm' for r in rows))
        self.assertNotIn('secret-0',json.dumps(rows,default=str))

    def test_partial_refusal_is_unknown_and_not_retried(self):
        with patch.object(service,'deliver',side_effect=service.PartialDelivery()):
            result=service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)
        self.assertEqual(result['status'],'unknown')
        self.assertFalse(self.in_company(0,'SELECT report_email_due(%s)',[self.day]))

    def test_crash_recovery_retry_gap_and_budget(self):
        attempt=self.in_company(0,"SELECT report_email_claim(%s,'schedule','tester')",[self.day])
        with patch.object(service,'deliver') as delivered:
            service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)
            delivered.assert_not_called()  # preparation failure waits 30 minutes
        self.assertEqual(self.state()['rows'][0]['status'],'failed')
        self.in_company(0,"UPDATE report_email_log SET created_at=clock_timestamp()-interval '31 minutes'")
        for _ in range(11):
            self.in_company(0,"INSERT INTO report_email_log(report_date,status,trigger_source,created_at) VALUES(%s,'failed','schedule',clock_timestamp()-interval '31 minutes')",[self.day])
        self.assertFalse(self.in_company(0,'SELECT report_email_due(%s)',[self.day]))
        self.in_company(0,'SELECT rearm_report_email_day(%s,%s)',[self.day,'tester'])
        self.assertTrue(self.in_company(0,'SELECT report_email_due(%s)',[self.day]))

    def test_authorizer_revocation_subscription_and_inactivity(self):
        self.users[0].user_permissions.clear()
        with self.assertRaises(service.ReportEmailError): service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)
        self.users[0].user_permissions.set(self.permissions)
        for values in ({'is_suspended':True},{'is_active':False},{'paid_until':self.day-timedelta(days=30)}):
            Company.objects.filter(pk=self.companies[0].pk).update(**values)
            with self.assertRaises(service.ReportEmailError): service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)
            Company.objects.filter(pk=self.companies[0].pk).update(is_active=True,is_suspended=False,paid_until=None)
        self.users[0].is_active=False; self.users[0].save()
        with self.assertRaises(service.ReportEmailError): service.send_report(self.companies[0].pk,trigger='schedule',now=self.now)
        self.assertEqual(self.state()['total'],0)

    def test_scope_resets_on_failure_and_patch_preserves_configuration(self):
        for index,company in enumerate(self.companies):
            before=self.in_company(index,BOOKS)
            with service.tenant(company), connection.cursor() as cursor:
                sql=(ROOT/'tenancy/sql/add_report_email.sql').read_text()
                cursor.execute(sql);cursor.execute(sql)
            self.assertEqual(self.in_company(index,BOOKS),before)
            self.assertEqual(self.in_company(index,'SELECT app_password FROM report_email_settings'),f'secret-{index}')
        with patch.object(service.reports,'fetch_report',side_effect=RuntimeError('private SQL')):
            result=service.send_report(self.companies[0].pk,self.day,actor_id=self.users[0].pk)
        self.assertEqual(result['status'],'failed')
        self.assertNotIn('private SQL',json.dumps(result))
        self.assertEqual(service.query('SELECT current_schema()'),'public')
        self.assertTrue(service.query('SELECT pg_try_advisory_lock(hashtextextended(%s,0))',[self.companies[0].schema_name+':report_email']))
        service.query('SELECT pg_advisory_unlock_all()')

    def test_capture_transport_uses_only_each_company_mail(self):
        if not service.review_transport(): self.skipTest('Local capture integration runs only in the isolated review stack.')
        for index in range(2):
            result=service.send_report(self.companies[index].pk,self.day,actor_id=self.users[index].pk)
            self.assertEqual(result['status'],'sent',result)
        with urllib.request.urlopen('http://mailpit:8025/api/v1/messages') as response:
            messages=json.load(response)['messages']
        for index in range(2):
            match=[m for m in messages if m['From']['Address']==f'sender-{index}@example.test']
            self.assertTrue(match,messages)
            self.assertEqual([r['Address'] for r in match[0]['To']],[f'owner-{index}@example.test'])
            with urllib.request.urlopen('http://mailpit:8025/api/v1/message/'+match[0]['ID']) as response: message=json.load(response)
            self.assertIn('PKR 130.00' if index==0 else 'AED 130.00',message['Text'])
            self.assertNotIn(self.companies[1-index].name,message['Text'])

    def test_no_sales_day_and_old_rearm(self):
        captured=[]
        with patch.object(service,'deliver',side_effect=lambda msg,raw:captured.append(msg)):
            result=service.send_report(self.companies[0].pk,self.day-timedelta(days=20),actor_id=self.users[0].pk)
        self.assertEqual(result['status'],'sent')
        self.assertIn('no sales',captured[0].subject)
        self.assertIn('PKR 0.00',captured[0].body)
        self.assertEqual(self.post('rearm/',{'report_date':str(self.day-timedelta(days=1))}).status_code,400)


if __name__=='__main__': unittest.main(verbosity=2)
