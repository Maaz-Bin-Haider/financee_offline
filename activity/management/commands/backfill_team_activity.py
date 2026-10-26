"""No startup import. One explicit company, cutoff and confirmation per execution."""
from datetime import datetime
from zoneinfo import ZoneInfo
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from tenancy.models import Company, PROVISIONING_READY
from activity.scope import tenant
from activity.backfill import SOURCES, select_sql


class Command(BaseCommand):
    help='Preview or explicitly import approximate legacy Entry By activity for one company.'
    def add_arguments(self,parser):
        parser.add_argument('--company',type=int,required=True)
        parser.add_argument('--cutoff',required=True,help='Timezone-aware ISO timestamp; no future cutoff.')
        parser.add_argument('--execute',action='store_true')
        parser.add_argument('--confirm',help='Exact tenant schema required with --execute.')
    def handle(self,*args,**options):
        try:
            cutoff=datetime.fromisoformat(options['cutoff'])
            if cutoff.tzinfo is None or cutoff>timezone.now():raise ValueError()
            ZoneInfo(settings.ACTIVITY_TIMEZONE)
            company=Company.objects.get(pk=options['company'],provisioning_state=PROVISIONING_READY,is_active=True)
        except (ValueError,Company.DoesNotExist):raise CommandError('Choose an active company and a valid past aware cutoff.') from None
        if options['execute'] and options['confirm']!=company.schema_name:
            raise CommandError('Execution requires --confirm with the exact company schema.')
        # The shared report context validates schemas and restores the prior path.
        with tenant(company),transaction.atomic(),connection.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='15000ms'")
            cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',[company.schema_name+':activity-backfill'])
            candidates=0;inserted=0
            params={'tz':settings.ACTIVITY_TIMEZONE,'company':company.pk,'cutoff':cutoff}
            for spec in SOURCES:
                sql=select_sql(spec)
                cur.execute('SELECT count(*) FROM ('+sql+") b WHERE NOT EXISTS(SELECT 1 FROM activity_events e WHERE e.source='backfill' AND e.dedupe_key=b.dedupe_key)",params)
                candidates+=cur.fetchone()[0]
                if options['execute']:
                    cur.execute('''INSERT INTO activity_events(user_id,username,action,kind,record_id,label,source,at,dedupe_key,document_date)
                      SELECT b.user_id,left(b.username,150),'create',b.kind,b.record_id,
                        left('Legacy Entry By · ' || replace(b.kind,'_',' ') || ' #' || b.record_id::text,200),'backfill',b.at,b.dedupe_key,b.document_date
                      FROM ('''+sql+''') b ON CONFLICT(dedupe_key) WHERE source='backfill' DO NOTHING''',params)
                    inserted+=cur.rowcount
        self.stdout.write(f'COMPANY={company.pk} MODE={"execute" if options["execute"] else "preview"} CANDIDATES={candidates} INSERTED={inserted}')
        self.stdout.write('Approximate local-noon history only; unknown/nonmember attribution is skipped. Business records were not changed.')
