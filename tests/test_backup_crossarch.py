"""Verify a real x64 re-dump on the ARM64 disposable PostgreSQL server."""
import contextlib,json,os
from pathlib import Path
from psycopg2 import sql
from local.backups import database
from local.backups.engine import Engine
assert os.environ['DB_NAME']=='financee_offline_test'
name='financee_offline_xarch_test';created=False
with contextlib.closing(database.connect('postgres',autocommit=True)) as admin:
    try:
        with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)));created=True
        Engine().pg('pg_restore',['--no-owner','--no-acl','--exit-on-error','--single-transaction','--dbname',name,'/customer/Cache/xarch/amd64.dump'])
        with contextlib.closing(database.connect(name)) as c:
            database.integrity(c,Path('/customer/Data/media'))
            assert database.fingerprints(c)==json.loads(Path('/customer/Cache/xarch/integrity.json').read_text())
            result={'roundtrip':'ARM64 -> emulated Linux AMD64 -> ARM64','source_sql_functions':190,'all_table_sequence_fingerprints_match':True,'attachments_and_journal_integrity':True,'postgres_major':c.server_version//10000}
        Path('/customer/Cache/xarch/results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    finally:
        if created:
            with admin.cursor() as c:c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
