"""No database or delivery required; exercise the actual Financee mapping."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','financee.settings')
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest
from reportmailer import reports


class Rendering(unittest.TestCase):
    def setUp(self):
        self.company = SimpleNamespace(name='<Company & A>', base_currency_id='PKR',
            base_currency=SimpleNamespace(minor_units=2))
        self.report = {'rows':[{'customer_name':'<script>alert(1)</script>', 'item_name':'=HYPERLINK("x")',
            'sale_price':Decimal('120.50'),'purchase_price':Decimal('100.00'),
            'profit_loss':Decimal('20.50'),'profit_loss_percent':Decimal('20.50')}],
            'totals':{'units':1,'revenue':Decimal('120.50'),'cost':Decimal('100'),
                      'profit':Decimal('20.50'),'margin_pct':Decimal('17.01')}}

    def test_sql_totals_and_distinct_markup_margin(self):
        text=reports.build_text(self.report,date(2026,10,23),self.company)
        self.assertIn('Profit: PKR 20.50',text)
        self.assertIn('Margin on revenue: 17.01%',text)
        html=reports.build_html(self.report,date(2026,10,23),self.company,'Asia/Karachi')
        self.assertIn('20.50%',html)
        self.assertIn('17.01%',html)
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;Company &amp; A&gt;',html)

    def test_csv_formula_escape_and_numeric_precision(self):
        csv=reports.build_csv(self.report,date(2026,10,23),self.company)
        self.assertIn("'=HYPERLINK",csv)
        self.assertIn('120.50,100.00,20.50,20.50',csv)
        self.assertIn('Margin on revenue,17.01',csv)

    def test_source_cents_are_not_hidden_by_zero_decimal_currency(self):
        self.company.base_currency_id='JPY'
        self.company.base_currency.minor_units=0
        self.assertEqual(reports.money(Decimal('12.50'),self.company),'JPY 12.50')

    def test_company_currency_and_no_sales(self):
        self.company.base_currency_id='AED'
        empty={'rows':[], 'totals':{'units':0,'revenue':0,'cost':0,'profit':0,'margin_pct':0}}
        self.assertIn('no sales',reports.subject(empty,date(2026,10,23),self.company))
        self.assertIn('AED 0.00',reports.build_text(empty,date(2026,10,23),self.company))
        self.assertNotIn('GST Cost',reports.build_csv(empty,date(2026,10,23),self.company))


if __name__=='__main__': unittest.main()
