import os, celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conf.settings')

app = celery.Celery('conf')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()
