from django.contrib import admin
from django_apscheduler.admin import DjangoJobExecutionAdmin
from django_apscheduler.models import DjangoJobExecution

admin.site.unregister(DjangoJobExecution)

@admin.register(DjangoJobExecution)
class ReadOnlyDjangoJobExecutionAdmin(DjangoJobExecutionAdmin):

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False