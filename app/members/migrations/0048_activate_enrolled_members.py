"""A member with a section has been confirmed.

``Enrollment.save`` now turns a Requested member Active, because assigning a
section is what the registration team does to accept the request. This
backfills the rows that predate the rule, so already-enrolled members stop
being hidden from billing (``household_groups`` only bills active members).
"""

from django.db import migrations


def forward(apps, schema_editor):
    Person = apps.get_model("members", "Person")
    Enrollment = apps.get_model("members", "Enrollment")
    Person.objects.filter(
        status="r", pk__in=Enrollment.objects.values("user_id")
    ).update(status="a")


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0047_alter_troopsettings_homepage_about_enabled"),
    ]

    operations = [
        # Reversing cannot know which members were requested rather than
        # active before this ran, so it deliberately does nothing.
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
