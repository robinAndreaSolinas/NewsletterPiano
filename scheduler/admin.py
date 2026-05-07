from django.contrib import admin
from django_apscheduler.admin import DjangoJobExecutionAdmin,DjangoJobAdmin
from django_apscheduler.models import DjangoJobExecution, DjangoJob
from sqlparse import split

from .apps import SchedulerConfig
import re

admin.site.unregister(DjangoJobExecution)
admin.site.unregister(DjangoJob)

def get_scheduled_job(id):
    return SchedulerConfig._scheduler.get_job(id)

@admin.register(DjangoJobExecution)
class ReadOnlyDjangoJobExecutionAdmin(DjangoJobExecutionAdmin):

    @admin.display(description='Name')
    def job_name(self, obj):
        job = get_scheduled_job(obj.job.id)
        name = job.name if job else '-'
        return name

    @admin.display(description='Job ID')
    def job_id(self, obj):
        job = get_scheduled_job(obj.job.id)
        return job.id[:8] if job else obj.job.id[:8]

    def get_list_display(self, request):
        original = list(super().get_list_display(request))
        original.remove('id')
        original.remove('job')
        original.insert(0, 'job_id')
        original.insert(1, 'job_name')
        return original

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(DjangoJob)
class ReadOnlyDjangoJobAdmin(DjangoJobAdmin):

    @admin.display(description='Job ID')
    def job_id(self, obj):
        job = get_scheduled_job(obj.id)
        return job.id[:8] if job else obj.id[:8]

    @admin.display(description='Name')
    def job_name(self, obj):
        job = get_scheduled_job(obj.id)
        name = job.name if job else '-'
        return name

    @admin.display(description='Next Run')
    def next_run_time(self, obj):
        job = get_scheduled_job(obj.id)
        return job.next_run_time if job else '-'

    def get_list_display(self, request):
        original = list(super().get_list_display(request))
        original.append('next_run_time')
        original.remove('id')
        original.remove('local_run_time')
        original.insert(0, 'job_id')
        original.insert(1, 'job_name')
        return original

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return False
