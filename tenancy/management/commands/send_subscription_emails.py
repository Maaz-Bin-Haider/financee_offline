"""
Run one subscription-email scan by hand (the hourly background scheduler in
the web process does this automatically).

    python manage.py send_subscription_emails            # send what is due
    python manage.py send_subscription_emails --dry-run  # report only
"""
from django.core.management.base import BaseCommand

from tenancy.subscription_emails import process_subscription_emails


class Command(BaseCommand):
    help = "Send due subscription expiry/suspension emails to company billing addresses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be sent without sending anything.",
        )

    def handle(self, *args, **options):
        summary = process_subscription_emails(dry_run=options["dry_run"])
        self.stdout.write(f"sent: {summary['sent']}  failed: {summary['failed']}")
        for reason, count in sorted(summary["skipped"].items()):
            self.stdout.write(f"  skipped [{reason}]: {count}")
        if summary["failed"]:
            self.stderr.write("Some emails failed — see the Subscription emails log in the admin.")
