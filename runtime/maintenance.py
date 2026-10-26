#!/usr/bin/env python3
"""Device-owner development maintenance controller; packaged GUI is Phase 5.
Never drops a database or deletes a media generation. All Docker calls are scoped
only to the selected Financee Offline installation.
"""
import argparse,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
from location import selected,save
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['backup','inspect','restore','recover','open-folder','folder','set-folder'])
    p.add_argument('archive',nargs='?');p.add_argument('--stack',choices=['review','test'],default='review')
    p.add_argument('--confirm-sha',help='Exact inspected ZIP SHA-256; confirms replacement with this recovery point.')
    a=p.parse_args();customer=ROOT/'.runtime'/a.stack;env=customer/'Config/compose.env'
    if not env.is_file():p.error('Installation configuration is missing; do not initialize over existing data.')
    child_env=dict(os.environ,BACKUP_DIR=str(selected(customer,customer/'Backups')))
    base=['docker','compose','-p','financee_offline_'+a.stack,'--env-file',str(env),'-f',str(ROOT/'runtime/compose.yml')]
    def run(*parts,**kw):return subprocess.run(base+list(parts),cwd=ROOT,check=True,env=child_env,**kw)
    def tool(command,*parts,archive=None,capture=False):
        options=['run','--rm','--no-deps','--pull','never']
        if archive:options+=['-v',str(archive)+':/restore-input/archive.zip:ro']
        return run(*options,'backup','python','-m','local.backups.cli',command,*parts,stdout=subprocess.PIPE if capture else None,text=True)
    with (customer/'Config/controller.lock').open('a+') as lock:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write('0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        values=dict(line.split('=',1) for line in env.read_text().splitlines() if '=' in line)
        folder=selected(customer,os.environ.get('BACKUP_DIR',values.get('BACKUP_DIR',customer/'Backups')))
        child_env['BACKUP_DIR']=str(folder)
        if a.command=='set-folder':
            if not a.archive:p.error('Choose an existing local backup folder.')
            chosen=Path(a.archive).expanduser().resolve(strict=True)
            if not chosen.is_dir() or any(ord(c)<32 for c in str(chosen)):p.error('Choose an existing local folder with a normal directory name.')
            for forbidden in (customer/'Data',customer/'Config'):
                if chosen==forbidden or forbidden in chosen.parents:p.error('Keep backups outside active Data and Config folders.')
            run('stop','web','backup')
            previous=(customer/'Config/backup-location.json').read_bytes() if (customer/'Config/backup-location.json').exists() else None
            try:
                save(customer,chosen);child_env['BACKUP_DIR']=str(chosen)
                run('up','-d','--no-build','--pull','never','--no-deps','web','backup')
            except BaseException:
                if previous is None:(customer/'Config/backup-location.json').unlink(missing_ok=True)
                else:(customer/'Config/backup-location.json').write_bytes(previous)
                child_env['BACKUP_DIR']=str(folder)
                run('up','-d','--no-build','--pull','never','--no-deps','web','backup');raise
            finally:run('exec','-T','nginx','nginx','-s','reload')
            print('Backup folder selected. Existing ZIPs remain in their previous folder.');return
        if a.command=='folder':print(folder);return
        if a.command=='open-folder':
            if not folder.is_dir():raise SystemExit('Backup folder is missing. Reconnect it before opening.')
            if sys.platform=='darwin':subprocess.run(['open',str(folder)],check=True)
            elif os.name=='nt':os.startfile(folder)
            else:subprocess.run(['xdg-open',str(folder)],check=True)
            return
        if a.command=='backup':tool('backup');return
        path=None
        if a.command in ('inspect','restore'):
            if not a.archive:p.error('Choose a local ZIP file.')
            path=Path(a.archive).expanduser().resolve(strict=True)
            info=json.loads(tool('inspect','/restore-input/archive.zip',archive=path,capture=True).stdout)
            if a.command=='inspect':
                print(json.dumps(info,indent=2));print('Restore replaces the active company. Inspect company/date, then use restore with --confirm-sha '+info['archive_sha256']);return
            if a.confirm_sha!=info['archive_sha256']:p.error('Inspect this ZIP first, then explicitly confirm replacement using its full --confirm-sha value.')
            run('up','-d','--wait','db','redis')
            output=run('exec','-T','db','df','-Pk','/var/lib/postgresql/data',stdout=subprocess.PIPE,text=True).stdout
            if int(output.splitlines()[-1].split()[3])*1024<int(info['database_bytes'])*2+16*1024*1024:raise SystemExit('The database volume needs more free disk space for recovery.')
        if a.command=='recover':run('up','-d','--wait','db','redis')
        run('stop','backup','web')
        def health(expected):
            for _ in range(40):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:'+values['HTTP_PORT']+'/health/',timeout=2) as r:value=json.load(r)
                    if value.get('product')=='Financee_Offline' and value.get('generation')==expected and value.get('schema')==2 and value.get('setup_complete'):return
                except (OSError,ValueError):pass
                time.sleep(.5)
            raise RuntimeError('Application startup verification failed.')
        try:
            if a.command=='restore':journal=json.loads(tool('restore','/restore-input/archive.zip','--confirm-sha',a.confirm_sha,archive=path,capture=True).stdout)
            else:journal=json.loads(tool('recover',capture=True).stdout)
            run('up','-d','--no-build','--pull','never','--no-deps','web','nginx')
            run('exec','-T','nginx','nginx','-s','reload')
            expected=(journal.get('new') if a.command=='restore' else journal.get('old')) or json.loads((customer/'Config/active.json').read_text())
            health(expected['generation'])
            if a.command=='restore':tool('commit')
        except BaseException:
            run('stop','web');tool('recover')
            run('up','-d','--no-build','--pull','never','--no-deps','web','nginx');run('exec','-T','nginx','nginx','-s','reload')
            health(json.loads((customer/'Config/active.json').read_text())['generation'])
            print('Recovery was not completed; the previous generation is active.',file=sys.stderr);raise
        finally:run('up','-d','--no-build','--pull','never','--no-deps','backup')
        print('Recovery health checks passed. Previous database/media and rescue ZIP retained. Sign in again.')
if __name__=='__main__':main()
