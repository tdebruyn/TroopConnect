import os
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "troopconnect.settings")
app = Celery("troopconnect")
app.conf.enable_utc = False
app.config_from_object(settings, namespace="CELERY")
app.autodiscover_tasks()

# @app.task(bind=True)
# def debug_task(self):
#     print(f"Request: {self.request!r}")
