import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myshop.settings")

app = Celery("myshop") 
# directory at the project level, add it here:
app.config_from_object("django.conf:settings", namespace="CELERY")
# During production, collectstatic will gather static files here.
app.autodiscover_tasks()
