from typing import Iterable, Self
from django.apps import AppConfig

from .job_registry import JobRegistry
from django.utils.module_loading import autodiscover_modules


class SchedulerConfig(AppConfig):
    """Django app configuration for the scheduler application."""

    name = 'scheduler'
    _scheduler = None

    def ready(self):
        import sys
        self.load_jobs()
        if not sys.argv[0].endswith('manage.py') or 'runserver' in sys.argv or 'test' in sys.argv:
            # * Run the scheduler only if the command is `runserver`, `test` or other commands (Gunicorn)
            self.start_scheduler()

    @classmethod
    def start_scheduler(cls):
        """
        Start the background scheduler and register jobs from specified modules.

        Returns:
            The scheduler instance (started).
        """
        from apscheduler.schedulers.background import BackgroundScheduler
        from django_apscheduler.jobstores import DjangoJobStore

        if cls._scheduler is not None:
            if cls._scheduler.running:
                cls._scheduler.resume()
            else:
                cls._scheduler.start()
            return cls._scheduler
        else:
            scheduler = BackgroundScheduler()
            scheduler.add_jobstore(DjangoJobStore(), "default")

            if scheduler.running:
                scheduler.resume()
            else:
                scheduler.start(paused=True)

            cls._scheduler = scheduler

            for job in JobRegistry.get():
                if not cls._scheduler.get_job(job.id, "default"):
                    scheduler.add_job(
                        job.function,
                        job.trigger,
                        id=job.id,
                        name=job.name,
                        **job.kwargs
                    )

            cls._scheduler.resume()
            return cls._scheduler

    @classmethod
    def load_jobs(cls,
                  include_module: Iterable[str] = None,
                  exclude_module: Iterable[str] = None,
                  include_default=True):
        """
        Load jobs from specified modules.

        Args:
            include_module: Iterable of module names to include for job discovery.
            exclude_module: Iterable of module names to exclude from job discovery.
            include_default: If True, includes 'views' and 'jobs' modules by default.

        Note:
            This method automatically discovers and registers jobs from the specified modules.
            The scheduler starts in a paused state and is resumed after all jobs are added.
        """
        modules = set(include_module or []) - set(exclude_module or [])
        modules |= {"views", "jobs"} if include_default else set()

        for mod in modules: autodiscover_modules(mod)