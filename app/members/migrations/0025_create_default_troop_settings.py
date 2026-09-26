"""Create the troop settings row, so a fresh install has one to edit.

``TroopSettings.get_settings()`` can create the row on demand, but a fresh
install has to be able to *reach* the settings page and send coherent mail
before anyone has saved anything, so the row is created here with the generic
defaults instead. An install that already has a row keeps it untouched.
"""

from django.db import migrations


def create_troop_settings(apps, schema_editor):
    TroopSettings = apps.get_model("members", "TroopSettings")
    TroopSettings.objects.get_or_create(pk=1)


def delete_troop_settings(apps, schema_editor):
    """Reverse: drop the row, so the migration can be replayed.

    Only the row this migration would have created is of interest, and there is
    exactly one, so removing it is the inverse of creating it.
    """
    TroopSettings = apps.get_model("members", "TroopSettings")
    TroopSettings.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0024_widen_troop_settings"),
    ]

    operations = [
        migrations.RunPython(create_troop_settings, delete_troop_settings),
    ]
