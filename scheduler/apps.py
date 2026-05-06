from django.apps import AppConfig

from .job_registry import JobRegistry
from django.utils.module_loading import autodiscover_modules


class SchedulerConfig(AppConfig):
    name = 'scheduler'

    def ready(self):
        import os
        if os.environ.get("RUN_MAIN") != "true":
            return

        autodiscover_modules("views") ## import all installed apps views
        autodiscover_modules("jobs") ## import all installed apps jobs

        scheduler = self._get_scheduler()


    def _get_scheduler(self):

        from apscheduler.schedulers.background import BackgroundScheduler
        from django_apscheduler.jobstores import DjangoJobStore

        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        for job in JobRegistry.get():
            if not scheduler.get_job(job.name):
                scheduler.add_job(
                    job.function,
                    job.trigger,
                    id=job.name,
                    name=job.name,
                    **job.kwargs
                )

        if scheduler.running:
            scheduler.resume()
        else:
            scheduler.start()

        return scheduler