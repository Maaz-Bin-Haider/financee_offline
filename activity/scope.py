"""Validated scope for explicit activity maintenance; always restore the caller."""
from contextlib import contextmanager
import re
from django.db import connection
from tenancy.utils import set_search_path
from tenancy.schema_verification import verify_company_schema


@contextmanager
def tenant(company):
    if not re.fullmatch(r'tenant_company_[1-9][0-9]*',company.schema_name):raise ValueError('Invalid company schema.')
    with connection.cursor() as cur:cur.execute('SHOW search_path');previous=cur.fetchone()[0]
    try:
        set_search_path(company.schema_name)
        if not verify_company_schema(company,use_cache=False).ok:raise ValueError('Company schema unavailable.')
        yield
    finally:
        with connection.cursor() as cur:cur.execute("SELECT set_config('search_path',%s,false)",[previous])
