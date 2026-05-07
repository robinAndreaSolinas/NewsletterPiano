"""
URL configuration for app project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from scheduler.apps import SchedulerConfig

"""
WARNING: The scheduler is intentionally started here in urls.py to prevent:
         1. Circular import issues when importing scheduler components in other modules
         2. Database connection errors that occur when the scheduler starts too early
            in the Django initialization process (e.g., in apps.py ready() method)
         
         This placement ensures Django's app registry and database connections are
         fully initialized before the scheduler attempts to access the database
         for job persistence via DjangoJobStore.

NOTE: You can change the hash algorithm used for job ID generation before starting
      the scheduler by calling SchedulerConfig.set_hash_algo('algorithm_name').
      *This must be done before SchedulerConfig.start_scheduler() is called.*
         
"""
SchedulerConfig.start_scheduler()

urlpatterns = [
    path('__administration/', admin.site.urls)
]