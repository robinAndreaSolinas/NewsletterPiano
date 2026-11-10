"""Recompute daily rows from snapshots already stored. It cannot invent a past cumulative."""
from datetime import timedelta

from django.core.management import BaseCommand, CommandError
from django.utils import timezone

from mailup import aggregate
from mailup.cli import confirm, ensure_not_future, parse_iso_date, write_backup
from mailup.models import Analytics, MailingList, MetricSnapshot
from mailup import tasks as mailup_tasks
from var.lib.mailup import MailUpException


class Command(BaseCommand):
    help = (
        "Ricalcola le righe giornaliere dagli snapshot già salvati. "
        "Non ricostruisce un giorno di cui non esiste lo snapshot."
    )
    epilog = (
        "Esempi:\n"
        "  ./manage.py mailup_backfill --from 2026-11-01 --to 2026-11-08 --dry-run\n"
        "  ./manage.py mailup_backfill --from 2026-11-01 --to 2026-11-08 --yes\n"
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", required=True, help="Inizio YYYY-MM-DD")
        parser.add_argument("--to", dest="end", required=True, help="Fine YYYY-MM-DD")
        parser.add_argument("--list-id", type=int)
        parser.add_argument("--message-id", type=int)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--yes", action="store_true", help="Salta la conferma. Obbligatorio senza terminale.")
        parser.add_argument("--no-backup", action="store_true")

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.yes = options["yes"]
        start = parse_iso_date(options["start"], "--from")
        end = parse_iso_date(options["end"], "--to")
        today = timezone.localdate()
        ensure_not_future(start, today)
        ensure_not_future(end, today)
        if start > end:
            raise CommandError("--from è successivo a --to")

        lists = MailingList.objects.filter(active=True)
        if options["list_id"] is not None:
            lists = lists.filter(list_id=options["list_id"])
            if not lists.exists():
                raise CommandError(f"list-id {options['list_id']} non è nel database")
        excluded = mailup_tasks.excluded_message_ids()
        prefix = "[DRY RUN] " if self.dry_run else ""
        plans = []
        try:
            with mailup_tasks.get_client() as client:
                for ml in lists:
                    day = start
                    while day <= end:
                        plans.append(self._plan(client, ml, day, excluded, options["message_id"]))
                        day += timedelta(days=1)
        except MailUpException as e:
            raise CommandError(str(e))

        for plan in plans:
            self.stdout.write(f"{prefix}{plan['line']}")
        writable = [plan for plan in plans if plan["fields"] is not None]
        if not writable:
            self.stdout.write(self.style.WARNING(f"{prefix}Niente da scrivere: servono due snapshot della stessa metrica."))
            return
        if self.dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY RUN] Nessuna riga scritta."))
            return
        summary = f"Verrebbero aggiornate {len(writable)} righe. Le altre colonne già presenti, se non ricalcolabili, restano."
        if not confirm(self, summary):
            return
        if not options["no_backup"]:
            path = write_backup({"plans": plans})
            self.stdout.write(f"Backup: {path}")
        for plan in writable:
            Analytics.objects.update_or_create(
                mailing_list_id=plan["mailing_list_id"],
                date=plan["date"],
                defaults={**plan["fields"], "provenance": plan["provenance"]},
            )
        self.stdout.write(self.style.SUCCESS(f"Aggiornate {len(writable)} righe."))

    def _plan(self, client, ml, day, excluded, only_message):
        snaps = MetricSnapshot.objects.filter(mailing_list=ml, captured_on=day).exclude(message_id__in=excluded)
        if only_message is not None:
            snaps = snaps.filter(message_id=only_message)
        if not snaps.exists():
            return {"line": f"{ml.name} {day} non calcolabile: nessuno snapshot", "fields": None}
        currents = {}
        for snap in snaps:
            currents[snap.message_id] = {key: getattr(snap, key) for key in aggregate.METRIC_KEYS}
        summed = mailup_tasks._day_values(ml, day, currents)
        if summed is None:
            return {"line": f"{ml.name} {day} non calcolabile: manca lo snapshot precedente", "fields": None}
        start, end = mailup_tasks.day_bounds(day)
        subscribed = client.count_optins(ml.list_id, start, end)
        unsubscribed = client.count_optins(ml.list_id, start, end, field="Optout_Date")
        fields = {key: summed[key] for key in aggregate.METRIC_KEYS}
        fields["subscribed"] = subscribed
        fields["unsubscribed"] = unsubscribed
        current = Analytics.objects.filter(mailing_list=ml, date=day).first()
        line = (
            f"{ml.name} {day} sent {getattr(current, 'sent', 'assente')} -> {fields['sent']} "
            f"delivered={fields['delivered']} bounced={fields['bounced']} opened={fields['opened']}"
        )
        return {
            "line": line,
            "fields": fields,
            "mailing_list_id": ml.id,
            "date": day.isoformat(),
            "provenance": "backfill from stored snapshots; subscribed/unsubscribed=EmailOptins of that Rome day",
        }
