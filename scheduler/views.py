from scheduler import job

# @job('cron', hour=10, minute=30)
# @job('date', run_date='2026-06-01 10:00:00')
# @job('interval', hours=2, minutes=30)

# Create your views here.

@job('interval', minutes=1)
def my_job():
    print('Hello World!')

@job('interval', minutes=1, args=(1,2))
def my_jxob(a, b):
    print(a+b)