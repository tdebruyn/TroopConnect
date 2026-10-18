"""Move the passage's beat entry from daily to monthly on the first.

``run_passage`` now runs once a month instead of every day: it skips members
who already have a section for the target year, so the repetition exists only
to catch up on whoever is left. A live instance's schedule lives in the
``django_celery_beat`` tables, and ``members.setup.ensure_periodic_tasks`` only
ever *adds* an entry — it does not rewrite the timing of one that already
exists — so without this migration an installed troop would keep the old daily
tick.

Only a daily entry is touched, and its hour and minute are kept: changing the
cadence is the product's decision, while the time of day is the troop's. An
entry already scheduled some other way is left alone.
"""

from django.db import migrations

NAME = "run-passage-daily"
NEW_NAME = "run-passage-monthly"
TASK = "run_passage"


def make_monthly(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")

    for row in PeriodicTask.objects.filter(task=TASK).select_related("crontab"):
        crontab = row.crontab
        if (
            crontab is None
            or crontab.day_of_month != "*"
            or crontab.month_of_year != "*"
        ):
            continue

        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=crontab.minute,
            hour=crontab.hour,
            day_of_month="1",
            month_of_year="*",
            day_of_week="*",
            timezone=crontab.timezone,
        )
        row.crontab = schedule
        # The default name says "daily"; a troop that renamed its copy keeps
        # the name it chose.
        if row.name == NAME and not PeriodicTask.objects.filter(name=NEW_NAME).exists():
            row.name = NEW_NAME
        row.save(update_fields=["crontab", "name"])


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0001_initial"),
        ("members", "0041_remove_troopsettings_age_reference_day_and_more"),
    ]

    operations = [
        migrations.RunPython(make_monthly, migrations.RunPython.noop),
    ]
