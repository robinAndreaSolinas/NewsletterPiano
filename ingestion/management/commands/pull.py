from datetime import datetime, timedelta

from django.core.management import BaseCommand, CommandError
from ingestion.models import Campaign, Analytics
from ingestion.tasks import ingest_campaigns, ingest_analytics


class Command(BaseCommand):
    help = (
        "Lancia (via Celery) e attende il completamento dell'ingestion di 'campaign' "
        "(senza parametri) o 'analytics' (con --start e --end opzionale, default ieri)."
    )

    DATE_FORMAT = "%Y%m%d"

    def add_arguments(self, parser):
        parser.add_argument(
            "type",
            choices=["campaign", "analytics"],
            help="Tipo di ingestion da lanciare: 'campaign' o 'analytics'",
        )
        parser.add_argument(
            "--start", "-s",
            required=False,
            type=str,
            default=None,
            help="(solo per 'analytics') Data di inizio nel formato YYYYMMDD",
        )
        parser.add_argument(
            "--end", "-e",
            required=False,
            type=str,
            default=None,
            help="(solo per 'analytics') Data di fine nel formato YYYYMMDD (default: ieri)",
        )

    def handle(self, *args, **options):
        ingestion_type = options["type"]

        if ingestion_type == "campaign":
            self._handle_campaign(options)
        else:
            self._handle_analytics(options)

    def _handle_campaign(self, options):
        if options["start"] or options["end"]:
            self.stdout.write(
                self.style.WARNING(
                    "'--start'/'--end' sono ignorati per il tipo 'campaign'"
                )
            )

        self.stdout.write(self.style.NOTICE("Lancio task celery 'ingest_campaigns'"))

        task = ingest_campaigns.delay()
        self.stdout.write(self.style.NOTICE(f"Task schedulato (id={task.id}), attendo il completamento..."))

        result = self._wait_for_task(task)

        self.stdout.write(
            self.style.SUCCESS(f"Task 'ingest_campaigns' completato. Risultato: {result}")
        )

    def _handle_analytics(self, options):
        start_str = options["start"]
        end_str = options["end"]

        if not start_str:
            raise CommandError("--start è obbligatorio per il tipo 'analytics'")

        try:
            start = datetime.strptime(start_str, self.DATE_FORMAT).date()
        except ValueError:
            raise CommandError(f"start non valida: '{start_str}'. Formato atteso: YYYYMMDD")

        if end_str:
            try:
                end = datetime.strptime(end_str, self.DATE_FORMAT).date()
            except ValueError:
                raise CommandError(f"end non valida: '{end_str}'. Formato atteso: YYYYMMDD")
        else:
            end = datetime.now().date() - timedelta(days=1)

        if start > end:
            raise CommandError("start non può essere successiva a end")

        self.stdout.write(
            self.style.NOTICE(
                f"Lancio task celery 'ingest_analytics' per il periodo {start} -> {end}"
            )
        )

        task = ingest_analytics.delay(
            start.strftime(self.DATE_FORMAT), end.strftime(self.DATE_FORMAT)
        )
        self.stdout.write(self.style.NOTICE(f"Task schedulato (id={task.id}), attendo il completamento..."))

        self.stdout.write(
            self.style.SUCCESS(f"Task 'ingest_analytics' Scheduleator in Background.")
        )