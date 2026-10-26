"""Compare SQL definitions with an independently loaded confirmed source snapshot.
Only Financee_Offline test databases are accepted. The reference is disposable.
"""
import hashlib, json, os, sys
from pathlib import Path
import psycopg2

assert os.environ['DB_NAME']=='financee_offline_test', 'Disposable offline test DB required'
params=dict(dbname=os.environ['DB_NAME'],user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],host=os.environ['DB_HOST'],port=os.environ['DB_PORT'])
query="""SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',
 p.prosrc, pg_get_function_result(p.oid), p.provolatile, p.proisstrict, p.prosecdef
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' ORDER BY 1"""
def definitions(conn):
    with conn.cursor() as cur:
        cur.execute(query)
        return {name:dict(body_sha256=hashlib.sha256(body.encode()).hexdigest(),result=result,volatility=volatility,strict=strict,security_definer=security) for name,body,result,volatility,strict,security in cur.fetchall()}

conn=psycopg2.connect(**params);conn.autocommit=True
actual=definitions(conn)
root=Path(__file__).resolve().parents[1]
contract_path=root/'tests/sql_source_contract.json'
if len(sys.argv)>1:
    template=Path(sys.argv[1]).read_bytes()
    expected_hash=json.loads((root/'SOURCE_FILES_SHA256.json').read_text())['tenancy/sql/tenant_template.sql']
    assert hashlib.sha256(template).hexdigest()==expected_hash, 'Reference must be the exact confirmed source snapshot'
    with conn.cursor() as cur: cur.execute('CREATE DATABASE financee_offline_reference_test')
    reference=None
    try:
        refparams=dict(params,dbname='financee_offline_reference_test')
        reference=psycopg2.connect(**refparams);reference.autocommit=True
        with reference.cursor() as cur:
            cur.execute('CREATE TABLE public.auth_user(id integer PRIMARY KEY)')
            cur.execute(template.decode())
        expected=definitions(reference)
        # These functions belong exclusively to the removed report email feature.
        removed={name:value for name,value in expected.items() if 'report_email' in name or any(name.startswith(prefix+'(') for prefix in ('get_report_email_settings','save_report_email_settings','report_email_settings_get','report_email_settings_save','add_report_recipient_from_json','update_report_recipient_from_json','delete_report_recipient','report_email_recipients_list'))}
        retained={name:value for name,value in expected.items() if name not in removed}
        contract={'source_sha':'96fd8b9dc4105870bc76cbb2b443bf5c36da2d66','template_sha256':expected_hash,'functions':retained,'removed_email_functions':sorted(removed)}
    finally:
        if reference: reference.close()
        with conn.cursor() as cur:cur.execute('DROP DATABASE financee_offline_reference_test')
else:
    contract=json.loads(contract_path.read_text())
expected=contract['functions']
missing=sorted(set(expected)-set(actual))
changed=sorted(name for name in set(expected)&set(actual) if expected[name]!=actual[name])
extra=sorted(set(actual)-set(expected))
allowed_extra=['local_currency_posting_lock()','local_profile_guard()','local_profile_no_truncate()']
assert not missing, ('Missing functions',missing)
assert not changed, ('Changed financial definitions',changed)
assert extra==allowed_extra, ('Unexpected function additions',extra)
if len(sys.argv)>1:contract_path.write_text(json.dumps(contract,indent=2)+'\n')
print(f'SQL provenance PASS: {len(expected)} retained definitions match confirmed source; {len(contract["removed_email_functions"])} email functions intentionally removed; 3 local integrity guards added.')
conn.close()
