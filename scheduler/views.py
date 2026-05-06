from scheduler import job

from ingestion.views import *

# Create your views here.

@job('interval', seconds=10)
def my_job():
    print('Hello World!')