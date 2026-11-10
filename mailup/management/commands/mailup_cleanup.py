"""Show, and only with --yes delete, rows of excluded test messages. Analytics rows are listed and left in place."""
from django.core.management import BaseCommand
from django.db.models import F

from mailup.cli import confirm, write_backup
from mailup.models import Analytics, Message, MetricSnapshot
from mailup.tasks import excluded_message_ids


class Command(BaseCommand):
    help = "Mostra i messaggi esclusi già salvati. Li cancella solo con --yes, dopo un backup. Non ricalcola le analytics."
    epilog = (
        "Esempi:\n"
        "  ./manage.py mailup_cleanup --dry-run\n"
        "  ./manage.py mailup_cleanup --yes\n"
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--yes", action="store_true")
        parser.add_argument("--no-backup", action="store_true")
        parser.add_argument("--list-id", type=int)

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.yes = options["yes"]
        excluded = excluded_message_ids()
        messages = Message.objects.filter(message_id__in=excluded)
        snaps = MetricSnapshot.objects.filter(message_id__in=excluded)
        if options["list_id"] is not None:
            messages = messages.filter(mailing_list__list_id=options["list_id"])
            snaps = snaps.filter(mailing_list__list_id=options["list_id"])
        suspect = Analytics.objects.filter(sent=F("delivered"), bounced__gt=0)
        prefix = "[DRY RUN] " if self.dry_run else ""
        self.stdout.write(f"{prefix}Messaggi esclusi configurati: {sorted(excluded)}")
        self.stdout.write(f"{prefix}Righe Message da rimuovere: {messages.count()}")
        for message in messages.order_by("message_id"):
            self.stdout.write(f"{prefix}  message {message.message_id} {message.subject!r} sent={message.sent}")
        self.stdout.write(f"{prefix}Snapshot da rimuovere: {snaps.count()}")
        self.stdout.write(
            f"{prefix}Analytics con Sent=Delivered e Bounced>0 (non toccate, non ricalcolabili senza gli snapshot di quel giorno): "
            f"{suspect.count()}"
        )
        for row in suspect.order_by("date"):
            self.stdout.write(
                f"{prefix}  {row.date} sent={row.sent} delivered={row.delivered} bounced={row.bounced} "
                f"subscribed={row.subscribed} unsubscribed={row.unsubscribed}"
            )
        if self.dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY RUN] Nessuna riga cancellata."))
            return
        if not messages.exists() and not snaps.exists():
            self.stdout.write(self.style.SUCCESS("Niente da cancellare."))
            return
        if not confirm(self, f"Cancello {messages.count()} messaggi e {snaps.count()} snapshot. Le analytics restano."):
            return
        if not options["no_backup"]:
            payload = {
                "messages": list(messages.values()),
                "snapshots": list(snaps.values()),
            }
            path = write_backup(payload)
            self.stdout.write(f"Backup: {path}")
        message_count = messages.count()
        snap_count = snaps.count()
        snaps.delete()
        messages.delete()
        self.stdout.write(self.style.SUCCESS(f"Rimossi {message_count} messaggi e {snap_count} snapshot."))
