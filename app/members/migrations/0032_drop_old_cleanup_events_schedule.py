"""Drop the beat entry for the agenda's old cleanup task.

``cleanup_old_events`` deleted ``homepage.Event`` rows older than 30 days. The
task and the model are both gone, but a live instance's schedule lives in the
``django_celery_beat`` tables, and ``members.setup.ensure_periodic_tasks`` only
ever *adds* an entry — it never removes one that has fallen out of
``CELERY_BEAT_SCHEDULE``. Left behind, beat would fire a task that no longer
exists once a day and the worker would log ``Received unregistered task`` every
time, which is the trap ``send_queued_mail`` fell into before it was registered.

An entry is matched by task as well as by the name this project gives it, so an
instance that renamed its copy still gets it removed. Nothing is restored on a
reverse: the task no longer exists to run.
"""

from django.db import migrations
from django.db.models import Q

TASK = "cleanup_old_events"
NAME = "cleanup-old-events-daily"


def drop_old_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # The row's own crontab is left behind: an unreferenced CrontabSchedule is
    # inert, `from_schedule` reuses a matching one if the schedule ever comes
    # back, and deleting it would mean deciding what else might point at it.
    PeriodicTask.objects.filter(Q(name=NAME) | Q(task=TASK)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0001_initial"),
        (
            "members",
            "0031_rename_public_agenda_enabled_troopsettings_agenda_enabled_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(drop_old_schedule, migrations.RunPython.noop),
    ]
