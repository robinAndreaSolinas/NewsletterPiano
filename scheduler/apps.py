from typing import Iterable, Self
from django.apps import AppConfig
from .job_registry import JobRegistry
from django.utils.module_loading import autodiscover_modules


class SchedulerConfig(AppConfig):
    """Django app configuration for the scheduler application."""

    name = 'scheduler'
    _instance = None

    @classmethod
    def start_scheduler(cls,
                        include_module: Iterable[str] = None,
                        exclude_module: Iterable[str] = None,
                        include_default=True):
        """
        Start the background scheduler and register jobs from specified modules.
        
        Args:
            include_module: Iterable of module names to include for job discovery.
            exclude_module: Iterable of module names to exclude from job discovery.
            include_default: If True, includes 'views' and 'jobs' modules by default.
        
        Returns:
            The scheduler instance (started).
        
        Note:
            This method automatically discovers and registers jobs from the specified modules.
            The scheduler starts in a paused state and is resumed after all jobs are added.
        """
        from apscheduler.schedulers.background import BackgroundScheduler
        from django_apscheduler.jobstores import DjangoJobStore

        modules = set(include_module or []) & set(exclude_module or [])
        modules |= {"views", "jobs"} if include_default else set()

        for mod in modules: autodiscover_modules(mod)

        if cls._instance is not None:
            if cls._instance.running:
                cls._instance.resume()
            else:
                cls._instance.start()
            return cls._instance
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
    def set_hash_algo(cls, algo) -> type[Self]:
        """
        Set the hash algorithm used for generating job IDs.
        
        Args:
            algo: The name of the hash algorithm to use.
        
        Returns:
            The class itself for method chaining.
        """
        JobRegistry.set_algo(algo)
        return cls
