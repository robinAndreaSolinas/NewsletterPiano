from django.core.management import BaseCommand, CommandError
from django.utils import timezone

from mailup.cli import ensure_not_future, parse_iso_date
from mailup.models import MailingList
from mailup.tasks import default_close_day, ingest_analytics
from var.lib.mailup import MailUpException


class Command(BaseCommand):
    help = "Chiude un giorno MailUp: snapshot cumulativi e riga analytics (delta rispetto al giorno precedente)."
    epilog = (
        "Esempi:\n"
        "  ./manage.py mailup_sync\n"
        "  ./manage.py mailup_sync --date 2026-11-08\n"
        "  ./manage.py mailup_sync --dry-run --list-id 18\n"
        "Prima delle 07:00 Europe/Rome il giorno predefinito è ieri (l'invio delle 06:01 non è ancora partito)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Giorno da chiudere, YYYY-MM-DD. Default: giorno dell'invio già partito.")
        parser.add_argument("--list-id", type=int, help="Solo questa lista MailUp.")
        parser.add_argument("--dry-run", action="store_true", help="Legge MailUp e non scrive nel database.")

    def handle(self, *args, **options):
        today = timezone.localdate()
        day = parse_iso_date(options["date"], "--date") if options["date"] else default_close_day()
        ensure_not_future(day, today)
        if options["list_id"] is not None and not MailingList.objects.filter(list_id=options["list_id"]).exists():
            # The list may not be imported yet. A real run imports it first; dry-run cannot invent it.
            if options["dry_run"]:
                raise CommandError(f"list-id {options['list_id']} non è nel database")

        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(self.style.NOTICE(f"{prefix}Chiudo {day.isoformat()}"))
        try:
            result = ingest_analytics(
                end=day.strftime("%Y%m%d"),
                dry_run=options["dry_run"],
                list_id=options["list_id"],
            )
        except MailUpException as e:
            raise CommandError(str(e))

        for row in result["rows"]:
            self._print_row(prefix, row)
        if result["failed"]:
            raise CommandError(f"Fetch fallito per le liste {result['failed']}. Nessuno zero è stato scritto al posto dei dati mancanti.")
        self.stdout.write(self.style.SUCCESS(f"{prefix}Fatto."))

    def _print_row(self, prefix, row):
        status = row.get("status")
        excluded = row.get("excluded") or []
        if excluded:
            self.stdout.write(self.style.WARNING(f"{prefix}messaggi esclusi: {excluded}"))
        for warning in row.get("warnings") or []:
            self.stdout.write(self.style.WARNING(f"{prefix}{warning}"))
        fields = row.get("fields") or {}
        if status == "baseline":
            self.stdout.write(f"{prefix}lista {row.get('list_id')}: primo snapshot, nessuna riga del giorno (il cumulativo non è un giorno)")
            return
        if status == "unchanged":
            self.stdout.write(f"{prefix}lista {row.get('list_id')}: riga invariata")
        elif status == "dry-run":
            self.stdout.write(f"{prefix}lista {row.get('list_id')}: verrebbe scritta")
        elif status == "closed":
            self.stdout.write(self.style.SUCCESS(f"{prefix}lista {row.get('list_id')}: riga aggiornata"))
        elif status == "failed":
            self.stdout.write(self.style.ERROR(f"{prefix}lista {row.get('list_id')}: errore"))
            return
        if fields:
            self.stdout.write(
                f"{prefix}Sent={fields.get('sent')} Delivered={fields.get('delivered')} "
                f"Bounced={fields.get('bounced')} Opened={fields.get('opened')} "
                f"Clicked={fields.get('clicked')} Unsubscribed={fields.get('unsubscribed')}"
            )
