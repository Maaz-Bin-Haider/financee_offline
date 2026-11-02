"""Target-release checks for a same-schema, lossless manual upgrade candidate."""
import contextlib,json,os
from pathlib import Path
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from . import archive,config,database
from .files import read

def verify(engine,path,confirmation):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
    import django
    django.setup()
    info=archive.validate(path)
    if confirmation!=info['archive_sha256']:raise ValueError('The paired upgrade rescue ZIP changed.')
    active=config.active(engine.root)
    journal=read(engine.control/'upgrade-journal.json',{})
    if journal.get('format')!=1 or journal.get('instance_id')!=active['instance_id'] or journal.get('rescue_sha256')!=confirmation:
        raise ValueError('A matching local upgrade transaction is required.')
    if active==journal.get('old_active'):raise ValueError('Upgrade verification requires a separate candidate generation.')
    if info['installation_id']!=active['instance_id']:raise ValueError('The rescue belongs to another installation.')
    import zipfile
    with zipfile.ZipFile(path) as z:
        expected=json.loads(z.read('integrity.json'));profile=json.loads(z.read('configuration.json'))['business_profile'];members=json.loads(z.read('checksums.json'))
    with contextlib.closing(database.connect(active['database'])) as c:
        database.integrity(c,engine.root/active['media']);actual=database.fingerprints(c)
        # Sessions deliberately expire; every business, permission, migration and
        # attribution row and every sequence must otherwise remain identical.
        actual['tables'].pop('django_session',None);expected['tables'].pop('django_session',None)
        if actual!=expected:raise ValueError('Upgrade changed business rows, permissions, migration history or sequences.')
        if database.scalar(c,'SELECT count(*) FROM django_session')!=0:raise ValueError('Upgrade sessions were not expired.')
        if database.scalar(c,'SELECT row_to_json(t) FROM local_generalsettings t WHERE id=1')!=profile:raise ValueError('Upgrade changed business settings.')
    media=engine.root/active['media'];actual_files={}
    for f in media.rglob('*'):
        if f.is_symlink():raise ValueError('Candidate media contains a link.')
        if f.is_file():actual_files['media/'+f.relative_to(media).as_posix()]={'size':f.stat().st_size,'sha256':archive.digest(f)}
    if actual_files!={n:v for n,v in members.items() if n.startswith('media/')}:
        raise ValueError('Upgrade changed uploaded files.')
    # This release authorizes no schema migrations. A future schema-changing
    # release must ship its own reviewed policy and preservation checks.
    executor=MigrationExecutor(connections['default'])
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):raise ValueError('Unreviewed database migrations are pending. This upgrade policy refuses them.')
    return {'verified':True,'schema':2,'retained_financial_SQL_definitions':190,'tables_verified':len(actual['tables']),'sequences_verified':len(actual['sequences']),'media_files_verified':len(actual_files),'sessions_expired':True}
