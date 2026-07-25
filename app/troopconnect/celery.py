import os

from celery import Celery
from celery.signals import worker_ready
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "troopconnect.settings")
app = Celery("troopconnect")
app.conf.enable_utc = False
app.config_from_object(settings, namespace="CELERY")
app.autodiscover_tasks()


@worker_ready.connect
def run_create_year_on_startup(sender=None, **kwargs):
    """Backfill current/next school years as soon as the worker boots.

    The daily 03:00 beat tick fires only once a day, so a worker restart
    outside that window would otherwise leave a missing school year until the
    next 03:00. create_year_task is idempotent (guarded creates, never
    deletes), so enqueueing it on startup is safe. It runs via .delay() so it
    executes in a worker child where the ORM is fully ready. worker_ready only
    fires for the worker — not beat or the web process — so it triggers exactly
    on worker (re)start.
    """
    from members.tasks import create_year_task

    create_year_task.delay()


# @app.task(bind=True)
# def debug_task(self):
#     print(f"Request: {self.request!r}")
