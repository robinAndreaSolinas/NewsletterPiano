from datetime import datetime, timedelta

from django.core.management import BaseCommand, CommandError

from mailup.aggregate import day_bounds, sum_sent_on
from mailup.models import Analytics, MailingList
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
        parser.add_argument("type", choices=["check", "lists", "analytics", "backfill"])
        parser.add_argument("--start", "-s", default=None, help="data inizio YYYYMMDD")
        parser.add_argument("--end", "-e", default=None, help="data fine YYYYMMDD, default ieri")
        parser.add_argument("--sync", action="store_true", help="esegue il task nel processo corrente")
        parser.add_argument("--apply", action="store_true", help="(solo backfill) scrive. Senza, è un dry-run")

    def handle(self, *args, **options):
        if options["type"] == "check":
            return self._check()

        if options["type"] == "backfill":
            return self._backfill(options)

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

    def _backfill(self, options):
        """Show per-day sent from send history. Writes only with --apply, and only `sent`/`delivered` on rows that already exist."""
        try:
            start = parse_day(options["start"])
            end = parse_day(options["end"])
        except ValueError as e:
            raise CommandError(str(e))
        if not start or not end:
            raise CommandError("backfill richiede --start e --end")
        if start > end:
            raise CommandError("start non può essere successiva a end")

        mode = "APPLY (solo sent sulle righe già presenti)" if options["apply"] else "DRY-RUN (nessuna scrittura)"
        self.stdout.write(self.style.NOTICE(mode))
        self.stdout.write("opened, clicked, subscribed, unsubscribed non sono ricostruibili per i giorni passati e non vengono toccati.")

        written = 0
        with get_client() as client:
            for ml in MailingList.objects.filter(active=True):
                window_start, _ = day_bounds(start)
                _, window_end = day_bounds(end)
                try:
                    sendings = client.get_send_history(ml.list_id, window_start, window_end)
                except MailUpException as e:
                    raise CommandError(f"MailUp lista {ml.list_id}: {e}")
                day = start
                while day <= end:
                    sent = sum_sent_on(sendings, day)
                    current = Analytics.objects.filter(mailing_list=ml, date=day).first()
                    self.stdout.write(
                        f"{ml.name} {day} sent_attuale={current.sent if current else 'assente'} "
                        f"sent_da_storico={sent if sent is not None else 'sconosciuto'}"
                    )
                    if options["apply"] and sent is not None and current is not None:
                        current.sent = sent
                        note = "backfill sent=SendHistory.Recipient; delivered/opened/clicked/subscribed lasciati com'erano"
                        current.provenance = f"{current.provenance} | {note}".strip(" |")
                        current.save(update_fields=["sent", "provenance"])
                        written += 1
                    day += timedelta(days=1)
        if not options["apply"]:
            self.stdout.write(self.style.SUCCESS("Dry-run finito, nessuna riga scritta."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Aggiornate {written} righe già presenti."))

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
