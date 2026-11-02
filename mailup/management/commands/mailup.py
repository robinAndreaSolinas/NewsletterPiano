from datetime import datetime

from django.core.management import BaseCommand, CommandError

from mailup.models import MailingList
from mailup.tasks import get_client, ingest_analytics, ingest_lists, parse_day
from var.lib.mailup import MailUpException


class Command(BaseCommand):
    help = (
        "MailUp ingestion. 'check' verifica le credenziali ed elenca le liste visibili (con il loro ID), "
        "'lists' sincronizza le liste, 'analytics' importa le metriche (--start/--end YYYYMMDD, default "
        "dall'ultima data importata a ieri). Di default i task vanno su Celery, con --sync girano nel processo."
    )

    DATE_FORMAT = "%Y%m%d"

    def add_arguments(self, parser):
        parser.add_argument("type", choices=["check", "lists", "analytics"])
        parser.add_argument("--start", "-s", default=None, help="(solo 'analytics') data inizio YYYYMMDD")
        parser.add_argument("--end", "-e", default=None, help="(solo 'analytics') data fine YYYYMMDD, default ieri")
        parser.add_argument("--sync", action="store_true", help="esegue il task nel processo corrente")

    def handle(self, *args, **options):
        if options["type"] == "check":
            return self._check()

        if options["type"] == "lists":
            return self._run(ingest_lists, options["sync"])

        try:
            start = parse_day(options["start"])
            end = parse_day(options["end"])
        except ValueError as e:
            raise CommandError(str(e))
        if start and end and start > end:
            raise CommandError("start non può essere successiva a end")

        self._run(
            ingest_analytics,
            options["sync"],
            start.strftime(self.DATE_FORMAT) if start else None,
            end.strftime(self.DATE_FORMAT) if end else None,
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
        self.stdout.write("(* = già presente e attiva nel database)")

    def _run(self, task, sync, *args):
        name = task.name.rsplit(".", 1)[-1]
        if sync:
            self.stdout.write(self.style.NOTICE(f"Eseguo '{name}' nel processo corrente {args or ''}"))
            started = datetime.now()
            result = task(*args)
            self.stdout.write(self.style.SUCCESS(f"'{name}' completato in {datetime.now() - started}: {result}"))
            return

        result = task.delay(*args)
        self.stdout.write(self.style.SUCCESS(f"Task '{name}' schedulato su Celery (id={result.id})"))
