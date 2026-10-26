"""Integration race test in an explicitly owned, disposable database only."""
import os,subprocess,sys,threading,time
import psycopg2
assert os.environ['DB_NAME']=='financee_offline_test','Requires disposable offline test stack'
params=dict(dbname=os.environ['DB_NAME'],user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],host=os.environ['DB_HOST'],port=os.environ['DB_PORT'])
name='financee_offline_currency_race_test'
control=psycopg2.connect(**params);control.autocommit=True
connections=[];threads=[];created=False
def connect():
 conn=psycopg2.connect(**dict(params,dbname=name));connections.append(conn);return conn
try:
 with control.cursor() as cur:cur.execute('CREATE DATABASE '+name)
 created=True
 env=dict(os.environ,DB_NAME=name)
 subprocess.run([sys.executable,'manage.py','migrate','--noinput'],env=env,check=True,stdout=subprocess.DEVNULL)
 main=connect();main.autocommit=True
 with main.cursor() as cur:cur.execute("INSERT INTO local_generalsettings(id,name,base_currency_id,symbol_override,timezone,contact_email,phone,address,disabled_features) VALUES(1,'Race test','AED','','UTC','','','','[]')")
 def race(first_sql,second_sql,commit=True,expected_error=False):
  first=connect();second=connect();ready=threading.Event();answer={}
  with first.cursor() as cur:cur.execute(first_sql)
  def worker():
   try:
    with second.cursor() as cur:
     cur.execute('SELECT pg_backend_pid()');answer['pid']=cur.fetchone()[0];ready.set();cur.execute(second_sql)
    second.commit();answer['ok']=True
   except Exception as exc:second.rollback();answer['error']=str(exc)
  thread=threading.Thread(target=worker,daemon=True);threads.append(thread);thread.start();assert ready.wait(3)
  deadline=time.monotonic()+3;waiting=False
  while time.monotonic()<deadline:
   with main.cursor() as cur:
    cur.execute('SELECT wait_event FROM pg_stat_activity WHERE pid=%s',[answer['pid']]);row=cur.fetchone()
   if row and row[0]=='advisory':waiting=True;break
   if not thread.is_alive():break
   time.sleep(.02)
  assert waiting,'Concurrent transaction did not wait on the currency/posting barrier'
  first.commit() if commit else first.rollback()
  thread.join(5);assert not thread.is_alive(),'Race did not complete'
  if expected_error:assert 'Base currency is locked' in answer.get('error',''),answer
  else:assert answer.get('ok'),answer
  first.close();second.close()
 race("INSERT INTO journalentries(description) VALUES('first posting')","UPDATE local_generalsettings SET base_currency_id='USD' WHERE id=1",expected_error=True)
 with main.cursor() as cur:
  cur.execute('SELECT base_currency_id FROM local_generalsettings');assert cur.fetchone()[0]=='AED'
  cur.execute("DELETE FROM journalentries WHERE description='first posting'")
 print('PASS: committed first posting blocks a racing currency change')
 race("INSERT INTO journalentries(description) VALUES('rolled back posting')","UPDATE local_generalsettings SET base_currency_id='EUR' WHERE id=1",commit=False)
 with main.cursor() as cur:
  cur.execute('SELECT base_currency_id FROM local_generalsettings');assert cur.fetchone()[0]=='EUR'
 print('PASS: rolled-back posting permits the waiting currency change')
 race("UPDATE local_generalsettings SET base_currency_id='USD' WHERE id=1","INSERT INTO journalentries(description) VALUES('posting after currency')")
 with main.cursor() as cur:
  cur.execute('SELECT base_currency_id FROM local_generalsettings');assert cur.fetchone()[0]=='USD'
  cur.execute('SELECT count(*) FROM journalentries');assert cur.fetchone()[0]==1
 print('PASS: racing first posting waits for the selected currency to commit')
finally:
 for conn in connections:
  if not conn.closed:
   try:conn.cancel()
   except Exception:pass
   conn.close()
 for thread in threads:thread.join(2)
 if created:
  with control.cursor() as cur:cur.execute('DROP DATABASE '+name)
 control.close()
