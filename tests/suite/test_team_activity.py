#!/usr/bin/env python3
"""Company activity over real HTTP/PostgreSQL; disposable companies only."""
import importlib.util
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if importlib.util.find_spec('activity') is None:
    print('SKIP: image predates company activity.'); raise SystemExit(0)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings')
import django
django.setup()
import io
import json
import time
import unittest
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, connections, transaction
from django.test import Client, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from tenancy.models import Company, Membership
from tenancy.utils import reset_search_path
from spotlight.views import scope
from activity.recorder import record
from activity import figures
from _harness import DSN, Tester


class Activity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tag=f'activity_{os.getpid()}_{int(time.time())}'
        cls.companies=[]; cls.users=[]; cls.testers=[]
        cls.permissions=list(Permission.objects.filter(content_type__app_label='auth'))
        for i in range(2):
            c=Company.objects.create(name=f'{cls.tag}_{i}',disabled_features=[]); c.refresh_from_db(); cls.companies.append(c)
            u=get_user_model().objects.create_user(username=f'{cls.tag}_{i}',password='synthetic')
            u.user_permissions.set(cls.permissions); Membership.objects.create(user=u,company=c); cls.users.append(u)
            db=psycopg2.connect(**DSN); db.autocommit=True
            t=Tester(db,c.schema_name,u.pk,cls.tag); cls.testers.append(t)
            vendor=t.add_party('Vendor',name='ACT SAME VENDOR'); customer=t.add_party('Customer',name='ACT SAME CUSTOMER')
            item=t.add_item(name='ACT SAME PHONE')
            t.purchase(vendor,['ACT-SAME-1','ACT-SAME-2','ACT-SAME-3'],unit_price=100+i*100,item_name=item)
        reset_search_path()

    @classmethod
    def tearDownClass(cls):
        reset_search_path()
        for t in cls.testers:t.conn.close()
        for c in cls.companies:
            assert c.name.startswith(cls.tag)
            with connection.cursor() as cur:cur.execute(f'DROP SCHEMA "{c.schema_name}" CASCADE')
            c.delete()
        for u in cls.users:u.delete()
        reset_search_path()

    def setUp(self):
        self.settings=override_settings(TEAM_ACTIVITY_ENABLED=True,TEAM_ACTIVITY_RECORDING_ENABLED=True,DRAFT_SALES_ENABLED=True,ALLOWED_HOSTS=["testserver","localhost"])
        self.settings.enable();cache.clear()
        for c in self.companies:
            c.disabled_features=[];c.is_suspended=False;c.save()
        for u in self.users:u.is_active=True;u.save();u.user_permissions.set(self.permissions)
        reset_search_path()

    def tearDown(self):
        self.settings.disable();reset_search_path()

    def client(self,i=0,csrf=False):
        c=Client(enforce_csrf_checks=csrf);c.force_login(get_user_model().objects.get(pk=self.users[i].pk));return c

    def rows(self,i=0):return self.testers[i].q("SELECT action,kind,record_id,user_id,source FROM activity_events WHERE kind<>'session' ORDER BY event_id")
    def post(self,c,url,data):return c.post(url,json.dumps(data),content_type='application/json')

    def test_01_roster_and_user_ids_are_company_scoped(self):
        c=self.client(); team=c.get('/activity/api/team/');self.assertEqual(team.status_code,200,team.content)
        ids={u['id'] for u in team.json()['users']};self.assertIn(self.users[0].pk,ids);self.assertNotIn(self.users[1].pk,ids)
        for api in ('year','day'):
            r=c.get('/activity/api/'+api+'/',{'user':self.users[1].pk,'date':str(date.today()),'company':self.companies[1].pk})
            self.assertEqual(r.status_code,400,r.content)
        self.assertNotIn(self.users[1].username,team.content.decode())
        with connection.cursor() as cur:cur.execute('SHOW search_path');self.assertEqual(cur.fetchone()[0],'public')

    def test_02_successful_master_and_failed_submission(self):
        c=self.client();before=len(self.rows());name=self.tag+'_newitem'
        r=c.post('/items/add-new-item/',{'item_name':name,'sale_price':200,'created_by_id':self.users[1].pk,'schema':self.companies[1].schema_name})
        self.assertEqual(r.json().get('status'),'success',r.content)
        row=self.rows()[-1];self.assertEqual(row[:2],('create','item'));self.assertEqual(row[3],self.users[0].pk);self.assertIsNotNone(row[2])
        r=c.post('/parties/add-new-party/',{'party_name':''});self.assertEqual(r.json()['status'],'error')
        self.assertEqual(len(self.rows()),before+1)

    def test_03_serial_sale_records_exact_id_and_tenant(self):
        c=self.client();r=self.post(c,'/sale/sales/',{'action':'submit','party_name':'ACT SAME CUSTOMER','sale_date':str(date.today()),'force':True,
            'items':[{'item_name':'ACT SAME PHONE','qty':1,'unit_price':180,'serials':['ACT-SAME-1']}]})
        self.assertTrue(r.json().get('success'),r.content)
        row=self.rows()[-1];self.assertEqual(row[:3],('create','sale',r.json()['sale_id']));self.assertEqual(row[3],self.users[0].pk)
        self.assertFalse(any(row[1]=='sale' for row in self.rows(1)))

    def test_04_cash_redirect_counts_only_success(self):
        c=self.client();n=len(self.rows());r=c.post('/payments/payment/',{'action':'submit','search_name':'ACT SAME VENDOR','amount':'10','payment_date':str(date.today())})
        self.assertEqual(r.status_code,302);self.assertEqual(len(self.rows()),n+1);self.assertEqual(self.rows()[-1][:2],('create','payment'))
        c.post('/payments/payment/',{'action':'submit','search_name':'ACT SAME VENDOR','amount':'-1','payment_date':str(date.today())})
        self.assertEqual(len(self.rows()),n+1)

    def test_05_record_failure_does_not_poison_successful_save(self):
        c=self.client();t=self.testers[0]
        t.exec('ALTER TABLE activity_events RENAME TO activity_events_unavailable')
        try:
            r=c.post('/parties/add-new-party/',{'party_name':self.tag+'_survives','party_type':'Customer'})
            self.assertEqual(r.json()['status'],'success',r.content)
            self.assertIsNotNone(t.party_id((self.tag+'_survives').upper()))
            req=RequestFactory().get('/');req.user=self.users[0];req.tenant_company=self.companies[0]
            with transaction.atomic():
                self.assertFalse(record(req,'create','party',1,'missing log'))
                with connection.cursor() as cur:cur.execute('SELECT 1');self.assertEqual(cur.fetchone()[0],1)
        finally:t.exec('ALTER TABLE activity_events_unavailable RENAME TO activity_events')

    def test_06_append_only_and_repeat_rollout(self):
        t=self.testers[0];n=t.one('SELECT count(*) FROM activity_events')
        for sql in ('UPDATE activity_events SET label=\'bad\'','DELETE FROM activity_events','TRUNCATE activity_events'):
            with self.assertRaises(psycopg2.Error):t.exec(sql)
        patch=Path('/app/tenancy/sql/add_team_activity.sql').read_text()
        with t.cur() as cur:cur.execute(patch);cur.execute(patch)
        self.assertEqual(t.one('SELECT count(*) FROM activity_events'),n)

    def test_07_feature_and_permission_gates_are_independent_of_recording(self):
        c=self.client();self.users[0].user_permissions.remove(Permission.objects.get(codename='view_team_activity'))
        self.assertEqual(c.get('/activity/api/team/').status_code,403)
        n=len(self.rows());r=c.post('/parties/add-new-party/',{'party_name':self.tag+'_staff','party_type':'Customer'})
        self.assertEqual(r.json()['status'],'success');self.assertEqual(len(self.rows()),n+1)
        self.users[0].user_permissions.set(self.permissions)
        company=self.companies[0];company.disabled_features=['team_activity'];company.save()
        self.assertEqual(c.get('/activity/api/team/').status_code,403)
        with override_settings(TEAM_ACTIVITY_ENABLED=False):self.assertEqual(c.get('/activity/api/team/').status_code,403)
        with override_settings(TEAM_ACTIVITY_RECORDING_ENABLED=False):
            n=len(self.rows());r=c.post('/parties/add-new-party/',{'party_name':self.tag+'_no_record','party_type':'Customer'});self.assertEqual(r.json()['status'],'success');self.assertEqual(len(self.rows()),n)

    def test_08_sessions_unknown_names_and_company_scope(self):
        a,b=self.testers;c=self.client();na=a.one("SELECT count(*) FROM activity_events WHERE action='sign_out'")
        c.logout();self.assertEqual(a.one("SELECT count(*) FROM activity_events WHERE action='sign_out'"),na+1)
        before=a.one('SELECT count(*) FROM activity_events');nb=b.one('SELECT count(*) FROM activity_events')
        c.login(username='no-such-'+self.tag,password='wrong');self.assertEqual(a.one('SELECT count(*) FROM activity_events'),before);self.assertEqual(b.one('SELECT count(*) FROM activity_events'),nb)
        c.login(username=self.users[1].username,password='wrong');self.assertEqual(b.one("SELECT count(*) FROM activity_events WHERE action='sign_in_failed'"),1)
        self.assertEqual(a.one('SELECT count(*) FROM activity_events'),before)

    def test_09_report_run_dedup_and_export_actor_source_guard(self):
        c=self.client();t=self.testers[0];before=t.one("SELECT count(*) FROM activity_events WHERE action='run'")
        r=c.post('/accountsReports/trial-balance/',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,200,r.content);token=r.get('X-Activity-Export');self.assertTrue(token)
        c.post('/accountsReports/trial-balance/',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(t.one("SELECT count(*) FROM activity_events WHERE action='run'"),before+1)
        n=len(self.rows());r=self.post(c,'/activity/record/',{'format':'csv','token':token});self.assertEqual(r.json(),{'recorded':True})
        self.post(c,'/activity/record/',{'format':'csv','token':token});self.assertEqual(len(self.rows()),n+1)
        self.assertEqual(self.rows()[-1][3:],(self.users[0].pk,'browser'))
        r=self.post(self.client(1),'/activity/record/',{'format':'pdf','token':token});self.assertEqual(r.status_code,400)
        self.assertEqual(self.post(c,'/activity/record/',{'format':'pdf','token':token,'user_id':self.users[1].pk}).status_code,400)
        company=self.companies[0];company.disabled_features=['accounts_reports.trial_balance'];company.save()
        self.assertEqual(self.post(c,'/activity/record/',{'format':'pdf','token':token}).status_code,400)

    def test_10_stale_session_and_request_validation(self):
        a=self.client();b=self.client(1)
        from django.contrib.sessions.models import Session
        # The offered HMAC belongs to the other session and must be refused.
        req=RequestFactory().get('/');req.user=self.users[0];req.tenant_company=self.companies[0];req.session=a.session
        self.assertEqual(b.get('/activity/api/team/',HTTP_X_ACTIVITY_SCOPE=scope(req)).status_code,409)
        self.assertEqual(a.get('/activity/record/').status_code,405)
        self.assertEqual(a.get('/activity/api/year/',{'user':'-1'}).status_code,400)
        self.assertEqual(a.get('/activity/api/watch/',{'days':'9999'}).status_code,400)
        self.assertEqual(self.client(csrf=True).post('/activity/record/',b'{}',content_type='application/json').status_code,403)

    def test_11_parallel_company_recording_and_dedupe(self):
        def run(i):
            connections.close_all();u=get_user_model().objects.get(pk=self.users[i].pk);req=RequestFactory().get('/');req.user=u;req.tenant_company=self.companies[i]
            try:return record(req,'run','report',label='parallel',dedupe_key='parallel-same-key',repeat_seconds=60)
            finally:connections.close_all()
        before=[len(self.rows(i)) for i in range(2)]
        with ThreadPoolExecutor(max_workers=4) as pool:out=list(pool.map(run,[0,1,0,1]))
        self.assertEqual(sum(out),2);self.assertEqual([len(self.rows(i)) for i in range(2)],[x+1 for x in before])

    def test_12_figures_thresholds_and_sessions_not_work(self):
        self.assertEqual([figures.level(n) for n in (0,1,4,5,10,11,25,26)],[0,1,1,2,2,3,3,4])
        r=self.client(1).get('/activity/api/year/',{'user':self.users[1].pk})
        self.assertEqual(r.status_code,200,r.content);self.assertEqual(r.json()['summary']['actions'],len(self.rows(1)))

    def test_13_backfill_requires_confirmation_is_idempotent_and_preserves_books(self):
        from django.core.management.base import CommandError
        from django.utils import timezone
        t=self.testers[0];c=self.companies[0];cutoff=timezone.now().isoformat()
        n=t.one('SELECT count(*) FROM activity_events');before=t.q('SELECT * FROM journallines ORDER BY line_id')
        with self.assertRaises(CommandError):call_command('backfill_team_activity',company=c.pk,cutoff=cutoff,execute=True,confirm='wrong',stdout=io.StringIO())
        preview=io.StringIO();call_command('backfill_team_activity',company=c.pk,cutoff=cutoff,stdout=preview)
        self.assertEqual(t.one('SELECT count(*) FROM activity_events'),n)
        out=io.StringIO();call_command('backfill_team_activity',company=c.pk,cutoff=cutoff,execute=True,confirm=c.schema_name,stdout=out)
        count=t.one('SELECT count(*) FROM activity_events');self.assertGreater(count,n)
        call_command('backfill_team_activity',company=c.pk,cutoff=cutoff,execute=True,confirm=c.schema_name,stdout=io.StringIO())
        self.assertEqual(t.one('SELECT count(*) FROM activity_events'),count)
        self.assertEqual(t.q('SELECT * FROM journallines ORDER BY line_id'),before)
        self.assertTrue(t.one("SELECT bool_and(source='backfill') FROM activity_events WHERE dedupe_key LIKE %s",['backfill:%']))
        with connection.cursor() as cur:cur.execute('SHOW search_path');self.assertEqual(cur.fetchone()[0],'public')

    def test_14_former_member_keeps_local_snapshot_without_foreign_profile(self):
        u=get_user_model().objects.create_user(username=self.tag+'_former',password='synthetic')
        m=Membership.objects.create(user=u,company=self.companies[0])
        req=RequestFactory().get('/');req.user=u;req.tenant_company=self.companies[0]
        old=u.username;self.assertTrue(record(req,'create','item',label='Local historical action'))
        m.company=self.companies[1];m.save();u.username=self.tag+'_FOREIGN_CURRENT';u.save()
        try:
            r=self.client().get('/activity/api/team/');self.assertEqual(r.status_code,200,r.content)
            self.assertIn(old,r.content.decode());self.assertNotIn(u.username,r.content.decode())
            row=next(v for v in r.json()['users'] if v['id']==u.pk);self.assertFalse(row['active'])
            year=self.client().get('/activity/api/year/',{'user':u.pk});self.assertEqual(year.json()['user']['username'],old)
        finally:u.delete()

    def test_15_blocked_company_and_inactive_user_cannot_read(self):
        c=self.client();self.companies[0].is_suspended=True;self.companies[0].save()
        self.assertEqual(c.get('/activity/api/team/').status_code,403)
        self.companies[0].is_suspended=False;self.companies[0].save();self.users[0].is_active=False;self.users[0].save()
        self.assertIn(c.get('/activity/api/team/').status_code,(401,403))

    def test_16_draft_conversion_and_confirmed_return_use_their_own_events(self):
        c=self.client();r=self.post(c,'/draft/save/',{'party_name':'ACT SAME CUSTOMER','draft_date':str(date.today()),'items':[
            {'item_name':'ACT SAME PHONE','qty':1,'unit_price':None,'serials':['ACT-SAME-2']}]})
        self.assertTrue(r.json().get('success'),r.content);ident=r.json()['draft_invoice_id']
        self.assertEqual(self.rows()[-1][:3],('create','draft',ident))
        r=self.post(c,'/draft/convert/',{'draft_invoice_id':ident,'invoice_date':str(date.today()),'items':[{'item_name':'ACT SAME PHONE','qty':1,'unit_price':180,'serials':['ACT-SAME-2']}]})
        self.assertTrue(r.json().get('success'),r.content);self.assertEqual(self.rows()[-1][:3],('convert','draft',ident))
        r=self.post(c,'/draft/return/save/',{'party_name':'ACT SAME CUSTOMER','return_date':str(date.today()),'serials':['ACT-SAME-2']})
        self.assertTrue(r.json().get('success'),r.content)
        self.assertEqual(self.rows()[-1][:3],('create','draft_return',r.json()['draft_return_id']))
        r=c.get('/activity/api/day/',{'user':self.users[0].pk,'date':str(date.today())});self.assertEqual(r.status_code,200,r.content)

    def test_17_query_volume_is_bounded_on_representative_history(self):
        t=self.testers[0];t.exec("INSERT INTO activity_events(user_id,username,action,kind,source,at,record_id) SELECT %s,'history','create','item','backfill',now()-n*interval '1 minute',10000000+n FROM generate_series(1,12000) n",[self.users[0].pk])
        started=time.monotonic();r=self.client().get('/activity/api/year/',{'user':self.users[0].pk})
        self.assertEqual(r.status_code,200,r.content);self.assertLess(time.monotonic()-started,5)
        self.assertLessEqual(len(r.json()['days']),372)
        elapsed=time.monotonic()-started
        client=self.client()
        with CaptureQueriesContext(connection) as captured:
            day=client.get('/activity/api/day/',{'user':self.users[0].pk,'date':str(date.today()-timedelta(days=1))})
        self.assertEqual(day.status_code,200,day.content);self.assertEqual(len(day.json()['work']),1000)
        self.assertTrue(day.json()['truncated']);self.assertLess(len(captured),50)
        print(f'ACTIVITY_PERF: year/12000 events {elapsed*1000:.1f}ms; 1000-event day {len(captured)} SQL queries')

    def test_18_old_document_watch_uses_pre_edit_date(self):
        c=self.client();r=c.post('/payments/payment/',{'action':'submit','search_name':'ACT SAME VENDOR','amount':'11','payment_date':'2025-07-03'})
        self.assertEqual(r.status_code,302);ident=self.rows()[-1][2]
        r=c.post('/payments/payment/',{'action':'submit','current_id':ident,'search_name':'ACT SAME VENDOR','amount':'12','payment_date':str(date.today())})
        self.assertEqual(r.status_code,302);self.assertEqual(self.rows()[-1][:3],('update','payment',ident))
        r=c.get('/activity/api/watch/',{'days':7});self.assertEqual(r.status_code,200,r.content)
        self.assertTrue(any(v['type']=='old_edit' and v['kind']=='payment' and v['record_id']==ident for v in r.json()['items']))


if __name__=='__main__':
    unittest.main(verbosity=2)
