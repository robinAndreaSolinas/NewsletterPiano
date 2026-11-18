"""Verifica che ogni task pianificato in Celery beat esista davvero nel codice.

Il 13/11/2026 un decoratore spostato ha reso `mailup.tasks.ingest_analytics` non registrato: beat lo
lanciava ogni notte e il worker lo scartava ("Received unregistered task") senza che nessuno se ne accorgesse.
Usato come healthcheck del worker: se un task manca il container risulta "unhealthy".
"""
from django.core.management import BaseCommand, CommandError

from conf.celery import app


class Command(BaseCommand):
    help = "Esce con errore se un task pianificato (django_celery_beat) non è registrato in Celery."

    def handle(self, *args, **options):
        from django_celery_beat.models import PeriodicTask

        app.loader.import_default_modules()
        registered = set(app.tasks.keys())
        missing = [
            f"{p.name} → {p.task}"
            for p in PeriodicTask.objects.filter(enabled=True)
            if p.task not in registered
        ]
        if missing:
            raise CommandError("Task pianificati non registrati: " + "; ".join(missing))
        self.stdout.write("ok")
