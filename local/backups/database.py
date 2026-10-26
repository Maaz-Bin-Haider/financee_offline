"""Bounded, read-only integrity checks using destination credentials."""
import hashlib,json,os,time,uuid
from pathlib import Path
import psycopg2
from psycopg2 import sql

def connect(database,autocommit=False):
    c=psycopg2.connect(dbname=database,user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],host=os.environ.get('DB_HOST','db'),port=os.environ.get('DB_PORT','5432'),connect_timeout=5,options='-c search_path=public -c timezone=UTC')
    c.autocommit=autocommit;return c

def scalar(c,query,args=None):
    with c.cursor() as cur:cur.execute(query,args);return cur.fetchone()[0]

def tables(c):
    with c.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        return [r[0] for r in cur.fetchall()]

def budget(c,deadline):
    if deadline is None:return
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('The bounded backup pause expired. No ZIP was published.')
    with c.cursor() as cur:cur.execute('SET LOCAL statement_timeout=%s',[str(max(1,int(remaining*1000)))+'ms'])

def fingerprints(c,deadline=None):
    result={}
    for name in tables(c):
        budget(c,deadline)
        digest=hashlib.sha256();count=0
        with c.cursor(name='backup_'+uuid.uuid4().hex) as cur:
            cur.itersize=500
            cur.execute(sql.SQL('SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text').format(sql.Identifier('public',name)))
            for row in cur:
                if deadline and time.monotonic()>deadline:raise TimeoutError('The backup pause exceeded its time limit. No ZIP was published.')
                digest.update(row[0].encode());digest.update(b'\n');count+=1
        result[name]={'count':count,'sha256':digest.hexdigest()}
    sequences={}
    with c.cursor() as cur:
        cur.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename")
        names=[r[0] for r in cur.fetchall()]
        for name in names:
            budget(c,deadline)
            cur.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sql.Identifier('public',name)))
            sequences[name]=list(cur.fetchone())
    return {'tables':result,'sequences':sequences}

def integrity(c,media,deadline=None):
    def q(query,args=None):
        budget(c,deadline);return scalar(c,query,args)
    if not (q('SELECT version FROM offline_schema_version WHERE id=true')==2):raise ValueError('Unsupported database schema.')
    if not (q('SELECT count(*) FROM local_generalsettings')==1):raise ValueError('A single local company is required.')
    if not (q('SELECT count(*) FROM auth_user WHERE is_superuser AND is_active')>0):raise ValueError('No active owner account.')
    if not (q("SELECT count(*) FROM information_schema.schemata WHERE schema_name NOT IN ('public','information_schema') AND schema_name NOT LIKE 'pg_%'")==0):raise ValueError('Unexpected business schema.')
    if not (q('SELECT count(*) FROM (SELECT journal_id FROM journallines GROUP BY journal_id HAVING sum(debit)<>sum(credit)) q')==0):raise ValueError('Unbalanced journal entries.')
    if not (q("SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace AND NOT convalidated")==0):raise ValueError('Unvalidated database constraints.')
    # Source-derived function contract remains independent of the backup itself.
    contract=json.loads((Path(__file__).resolve().parents[2]/'tests/sql_source_contract.json').read_text())
    budget(c,deadline)
    with c.cursor() as cur:
        cur.execute("SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',p.prosrc,pg_get_function_result(p.oid),p.provolatile,p.proisstrict,p.prosecdef FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'")
        actual={r[0]:r[1:] for r in cur.fetchall()}
    # Contract hashes and attributes use the original verifier's serialization.
    from local.backups.provenance import verify
    verify(actual,contract)
    budget(c,deadline)
    with c.cursor() as cur:
        cur.execute('SELECT storage_path,file_size FROM document_attachments')
        root=(Path(media)/'private/document_attachments').resolve()
        for relative,size in cur:
            file=(root/relative).resolve()
            if not (root in file.parents and file.is_file() and not file.is_symlink()):raise ValueError('An attachment is missing or has an unsafe path.')
            if not (file.stat().st_size==size):raise ValueError('Attachment size mismatch.')
    return True
