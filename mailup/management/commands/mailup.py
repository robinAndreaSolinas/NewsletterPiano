"""Deprecated name. The Celery tasks mailup.tasks.ingest_lists and ingest_analytics are unchanged."""
from django.core.management import BaseCommand, CommandError, call_command

from mailup.models import MailingList
from mailup.tasks import get_client, ingest_analytics, ingest_lists, parse_day
from var.lib.mailup import MailUpException


class Command(BaseCommand):
    help = "Deprecato. Usa mailup_sync, mailup_backfill, mailup_cleanup. Gli argomenti vecchi funzionano ancora."
    epilog = (
        "Esempi ancora validi:\n"
        "  ./manage.py mailup check\n"
        "  ./manage.py mailup analytics --end 20261108 --sync\n"
        "  ./manage.py mailup backfill --start 20261101 --end 20261108 --dry-run\n"
    )

    def add_arguments(self, parser):
        parser.add_argument("type", choices=["check", "lists", "analytics", "backfill"])
        parser.add_argument("--start", "-s", default=None)
        parser.add_argument("--end", "-e", default=None)
        parser.add_argument("--sync", action="store_true", help="Ignorato: il comando gira nel processo.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--yes", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            "Deprecato: preferisci mailup_sync, mailup_backfill o mailup_cleanup. "
            "mailup.tasks.ingest_analytics resta il nome della periodic task."
        ))
        kind = options["type"]
        if kind == "check":
            return self._check()
        if kind == "lists":
            if options["dry_run"]:
                self.stdout.write("[DRY RUN] lists leggerebbe le liste e non scriverebbe. Usa mailup_sync --dry-run.")
                return
            ingest_lists()
            self.stdout.write(self.style.SUCCESS("Liste allineate."))
            return
        if kind == "analytics":
            try:
                if options["start"]:
                    parse_day(options["start"])
                end = parse_day(options["end"]) if options["end"] else None
            except ValueError as e:
                raise CommandError(str(e))
            result = ingest_analytics(
                start=options["start"],
                end=end.strftime("%Y%m%d") if end else None,
                dry_run=options["dry_run"],
            )
            prefix = "[DRY RUN] " if options["dry_run"] else ""
            self.stdout.write(f"{prefix}{result['date']} failed={result['failed']}")
            if result["failed"]:
                raise CommandError(f"Fetch fallito per {result['failed']}")
            self.stdout.write(self.style.SUCCESS(f"{prefix}Fatto."))
            return
        start = _compact_to_iso(options["start"], "--start")
        end = _compact_to_iso(options["end"], "--end")
        if not start or not end:
            raise CommandError("backfill richiede --start e --end")
        call_command(
            "mailup_backfill",
            start=start,
            end=end,
            dry_run=options["dry_run"],
            yes=options["yes"],
            stdout=self.stdout,
        )

    def _check(self):
        active = set(MailingList.objects.filter(active=True).values_list("list_id", flat=True))
        try:
            with get_client() as client:
                client.authenticate()
                lists = client.get_lists()
        except MailUpException as e:
            raise CommandError(f"MailUp: {e}")
        self.stdout.write(self.style.SUCCESS(f"Autenticazione OK, {len(lists)} liste visibili (tutte importate):"))
        for item in lists:
            lowered = {k.lower(): v for k, v in item.items()}
            flag = "*" if lowered.get("idlist") in active else " "
            self.stdout.write(f" {flag} {lowered.get('idlist'):>6}  {lowered.get('name')}")


def _compact_to_iso(value, label):
    if not value:
        return None
    try:
        day = parse_day(value)
    except ValueError as e:
        raise CommandError(f"{label} non valida: '{value}'. Formato atteso: YYYYMMDD") from e
    return day.isoformat()
