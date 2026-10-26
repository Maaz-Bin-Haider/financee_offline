#!/usr/bin/env python3
"""Real PostgreSQL/HTTP Spotlight isolation and permission contracts."""
import importlib.util
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if importlib.util.find_spec('spotlight') is None:
    print('SKIP: image predates Spotlight.'); raise SystemExit(0)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'financee.settings')
import django
django.setup()
from concurrent.futures import ThreadPoolExecutor
import json
import time
import unittest
import psycopg2
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.core.cache import cache
from django.db import connection, connections
from django.test import Client, override_settings
from tenancy.models import Company, Membership
from tenancy.utils import reset_search_path
from spotlight import queries, policy
from _harness import Tester, DSN


class Spotlight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tag = f'spotlight_{os.getpid()}_{int(time.time())}'
        cls.companies, cls.users, cls.testers = [], [], []
        cls.permissions = list(Permission.objects.filter(content_type__app_label='auth'))
        for index, currency in enumerate(('PKR', 'AED')):
            company = Company.objects.create(name=f'{cls.tag}_{index}', base_currency_id=currency, disabled_features=[])
            company.refresh_from_db(); cls.companies.append(company)
            user = get_user_model().objects.create_user(username=f'{cls.tag}_{index}', password='synthetic')
            user.user_permissions.set(cls.permissions)
            Membership.objects.create(user=user, company=company); cls.users.append(user)
            conn = psycopg2.connect(**DSN); conn.autocommit = True
            t = Tester(conn, company.schema_name, user.pk, cls.tag); cls.testers.append(t)
            vendor = t.add_party('Vendor', name='SP SAME VENDOR')
            customer = t.add_party('Customer', name='SP SAME CUSTOMER')
            item = t.add_item(name='SP SAME PHONE')
            t.purchase(vendor, ['SP-SAME-1', 'SP-SAME-2'], unit_price=100+index*100, item_name=item)
            t.sale(customer, ['SP-SAME-1'], unit_price=150+index*100, item_name=item)
            t.exec('SELECT create_draft(%s,CURRENT_DATE,%s::jsonb,%s)', [t.party_id(customer), json.dumps([
                {'item_name':item, 'qty':1, 'unit_price':None, 'serials':['SP-SAME-2']}]), user.pk])
        reset_search_path()

    @classmethod
    def tearDownClass(cls):
        reset_search_path()
        for t in cls.testers: t.conn.close()
        for company in cls.companies:
            assert company.name.startswith(cls.tag)
            with connection.cursor() as cur: cur.execute(f'DROP SCHEMA "{company.schema_name}" CASCADE')
            company.delete()
        for user in cls.users: user.delete()
        reset_search_path()

    def setUp(self):
        self.override = override_settings(REPORT_EMAIL_ENABLED=True, DRAFT_SALES_ENABLED=True)
        self.override.enable(); cache.clear()
        for company, user in zip(self.companies, self.users):
            Company.objects.filter(pk=company.pk).update(disabled_features=[], is_active=True, is_suspended=False)
            user.user_permissions.set(self.permissions); user.groups.clear()
        self.client = Client(SERVER_NAME='localhost'); self.client.force_login(self.users[0])

    def tearDown(self):
        reset_search_path(); self.override.disable()

    def get(self, endpoint='search', **data):
        return self.client.get('/spotlight/' + endpoint + '/', data)

    def rows(self, **data):
        response = self.get(**data)
        self.assertEqual(response.status_code, 200, response.content[:400])
        return [row for group in response.json()['groups'] for row in group['results']]

    def test_01_company_scope_and_no_financial_writes(self):
        before = [t.exec('SELECT get_trial_balance_json()') for t in self.testers]
        for index, user in enumerate(self.users):
            self.client.force_login(user)
            rows = self.rows(q='SP-SAME-1')
            serial = next(row for row in rows if row['kind'] == 'serial')
            self.assertEqual(str(serial['bought']['purchase_price']), str(100+index*100)+'.00')
            self.assertEqual(str(serial['sold']['sold_price']), str(150+index*100)+'.00')
            docs = self.rows(q='sale 1')
            self.assertEqual(next(row['amount'] for row in docs if row['kind']=='sale'), str(150+index*100)+'.00')
        self.assertEqual(before, [t.exec('SELECT get_trial_balance_json()') for t in self.testers])
        with connection.cursor() as cur:
            cur.execute('SHOW search_path'); self.assertEqual(cur.fetchone()[0], 'public')

    def test_02_field_permissions(self):
        user = self.users[0]
        user.user_permissions.set(Permission.objects.filter(codename='view_sale'))
        serial = next(row for row in self.rows(q='SP-SAME-1') if row['kind']=='serial')
        self.assertNotIn('bought', serial); self.assertIn('sold', serial)
        self.assertFalse(any(row['kind']=='purchase' for row in self.rows(q='SP SAME')))
        user.user_permissions.set(Permission.objects.filter(codename='view_purchase'))
        serial = next(row for row in self.rows(q='SP-SAME-2') if row['kind']=='serial')
        self.assertNotIn('sold', serial); self.assertNotIn('reserved', serial)
        self.assertEqual(serial['state'], 'In stock')

    def test_03_features_and_membership(self):
        company = self.companies[0]
        Company.objects.filter(pk=company.pk).update(disabled_features=['purchases', 'stock_reports', 'draft_invoices'])
        serial = next(row for row in self.rows(q='SP-SAME-1') if row['kind']=='serial')
        self.assertNotIn('bought', serial)
        self.assertEqual(self.get('resolve', kind='purchase', id='1').status_code, 403)
        Company.objects.filter(pk=company.pk).update(disabled_features=['spotlight'])
        self.assertEqual(self.get().status_code, 403)
        Company.objects.filter(pk=company.pk).update(disabled_features=[], is_suspended=True)
        self.assertEqual(self.get().status_code, 403)
        anon = Client(SERVER_NAME='localhost')
        self.assertEqual(anon.get('/spotlight/search/').status_code, 401)

    def test_04_id_input_wildcards_and_missing(self):
        for raw in ('0', '-1', '1.0', '1e2', '²', '9007199254740992', '1 OR 1=1'):
            self.assertEqual(self.get('resolve', kind='party', id=raw).status_code, 400)
        self.assertEqual(self.get('resolve', kind='party', id='90000000').status_code, 404)
        self.assertEqual(self.get('resolve', kind='other', id='1').status_code, 403)
        self.assertEqual([r for r in self.rows(q='%%') if r['kind']!='page'], [])
        self.assertEqual([r for r in self.rows(q='__') if r['kind']!='page'], [])
        self.assertEqual(self.get(offset='-1').status_code, 400)
        self.assertEqual(self.client.post('/spotlight/search/').status_code, 405)

    def test_05_forged_scope_is_ignored_and_session_bound(self):
        self.assertEqual(self.get(q='sale 1', company=self.companies[1].pk, schema=self.companies[1].schema_name).status_code, 200)
        response = self.get()
        token = response['X-Spotlight-Scope']
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.client.force_login(self.users[1])
        response = self.client.get('/spotlight/search/', HTTP_X_SPOTLIGHT_SCOPE=token)
        self.assertEqual(response.status_code, 409)

    def test_06_recents_and_page_registry(self):
        rows = self.rows(recent='page:email,sale:1,party:9999999,page:gst')
        self.assertTrue(any(row['id']=='email' for row in rows))
        Company.objects.filter(pk=self.companies[0].pk).update(disabled_features=['report_email','sales_reports.sale_wise'])
        rows = self.rows(recent='page:email')
        self.assertFalse(any(row['id'] in ('email','sale_wise') for row in rows))
        self.assertFalse(any('gst' in row.get('href','') or 'activity' in row.get('href','') for row in rows))
        for row in self.rows():
            self.assertNotEqual(self.client.get(row['href']).status_code, 404, row)

    def test_07_master_ids_actions_and_permissions(self):
        rows = self.rows(q='SP SAME CUSTOMER')
        party = next(row for row in rows if row['kind']=='party')
        result = self.get('resolve', kind='party', id=party['id']).json()
        self.assertEqual(str(result['record']['party_id']), party['id'])
        action = self.get('resolve', kind='action', action='sale', id=party['id'])
        self.assertEqual(action.status_code, 200)
        vendor = next(row for row in self.rows(q='SP SAME VENDOR') if row['kind']=='party')
        self.assertEqual(self.get('resolve', kind='action', action='sale', id=vendor['id']).status_code, 403)
        self.users[0].user_permissions.clear()
        self.assertEqual(self.get('resolve', kind='action', action='sale', id=party['id']).status_code, 403)

    def test_08_readonly_draft_and_concurrency(self):
        group, _ = Group.objects.get_or_create(name='view_only_users')
        self.users[0].groups.add(group)
        rows = self.rows(q='draft')
        self.assertFalse(any(row['id'] in ('draft','confirm','pending') for row in rows))
        party = next(row for row in self.rows(q='SP SAME CUSTOMER') if row['kind']=='party')
        self.assertEqual(self.get('resolve', kind='action', action='sale', id=party['id']).status_code, 403)
        def request(user):
            try:
                client = Client(SERVER_NAME='localhost'); client.force_login(user)
                response = client.get('/spotlight/search/', {'q':'sale 1'})
                return next(row['amount'] for group in response.json()['groups'] for row in group['results'] if row['kind']=='sale')
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(request, self.users)), ['150.00', '250.00'])

    def test_09_all_search_groups(self):
        for kind in (*policy.DOCUMENTS, *policy.MASTERS, 'serial'):
            self.assertEqual(self.get(q='SP', kind=kind).status_code, 200, kind)

    def test_10_voucher_aliases_metadata_and_numeric_queries(self):
        for text in ('1', '#1', 'sale #1', 'invoice1', 'sales 1'):
            self.assertTrue(any(row['kind']=='sale' and row['id']=='1' for row in self.rows(q=text)), text)
        for text in ('SP PHONE', 'PHONE SAME'):
            self.assertTrue(any(row['kind']=='item' for row in self.rows(q=text)), text)
        # References and kind prefixes follow the same document numbering as the screens.
        t = self.testers[0]
        t.exec('SELECT make_payment(%s::jsonb)', [json.dumps({'party_name':'SP SAME VENDOR',
            'amount':10, 'method':'Cash', 'payment_date':'2025-07-04', 'reference_no':'SP-VOUCHER',
            'created_by_id':self.users[0].pk})])
        self.assertTrue(any(row['kind']=='payment' for row in self.rows(q='PMT-1')))
        self.assertTrue(any(row['kind']=='payment' for row in self.rows(q='SP-VOUCHER')))

    def test_11_paging_and_representative_query_cost(self):
        t = self.testers[0]
        t.exec("INSERT INTO items(item_id,item_name,brand,category) SELECT 100000+n, 'SP PERF PHONE ' || n, 'SPBRAND', 'PHONES' FROM generate_series(1,10000) n")
        try:
            started = time.perf_counter()
            response = self.get(q='SPBRAND')
            elapsed = time.perf_counter()-started
            self.assertEqual(response.status_code, 200)
            group = next(g for g in response.json()['groups'] if g['key']=='item')
            self.assertEqual(len(group['results']), queries.LIMIT); self.assertEqual(group['next'], queries.LIMIT)
            second = self.get(q='SPBRAND', kind='item', offset=queries.LIMIT).json()['groups'][0]
            self.assertFalse(set(row['id'] for row in group['results']) & set(row['id'] for row in second['results']))
            self.assertLess(elapsed, 2.5)
            print(f'Spotlight 10000-item all-group search: {elapsed*1000:.1f} ms; bounded pages {queries.LIMIT}.')
        finally:
            t.exec('DELETE FROM items WHERE item_id BETWEEN 100001 AND 110000')

    def test_12_revoked_recents_and_no_membership(self):
        self.users[0].user_permissions.clear()
        groups = self.get(recent='sale:1,party:1,serial:1').json()['groups']
        self.assertFalse(any(g['key']=='recent' for g in groups))
        user = get_user_model().objects.create_user(username=self.tag+'_orphan')
        try:
            self.client.force_login(user)
            self.assertEqual(self.get().status_code, 403)
        finally: user.delete()

    def test_13_balance_and_stock_fact_permissions(self):
        user = self.users[0]
        def permissions(*codenames):
            user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
        permissions('view_party', 'view_item')
        rows = self.rows(q='SP SAME')
        self.assertFalse(any('balance' in row or 'in_stock' in row for row in rows))
        permissions('view_party', 'view_item', 'view_payment', 'view_stock_reports_page', 'view_stock_summary')
        rows = self.rows(q='SP SAME')
        self.assertTrue(any(row['kind']=='party' and 'balance' in row for row in rows))
        item = next(row for row in rows if row['kind']=='item')
        self.assertEqual(item['in_stock'], 1)
        self.assertNotIn('reserved_units', item)
        Company.objects.filter(pk=self.companies[0].pk).update(disabled_features=['payments','stock_reports'])
        rows = self.rows(q='SP SAME')
        self.assertFalse(any('balance' in row or 'in_stock' in row for row in rows))


if __name__ == '__main__': unittest.main(verbosity=2)
