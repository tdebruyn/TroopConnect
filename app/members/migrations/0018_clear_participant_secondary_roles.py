from django.db import migrations


def clear_participant_secondary_roles(apps, schema_editor):
    """Rule 1: a Participant (primary role short "e") can never have
    secondary roles. Remove any that exist so the invariant holds."""
    PersonRole = apps.get_model("members", "PersonRole")
    PersonRole.objects.filter(
        person__primary_role__short="e",
        role__is_primary=False,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0017_sitesettings_default_language"),
    ]

    operations = [
        migrations.RunPython(
            clear_participant_secondary_roles, migrations.RunPython.noop
        ),
    ]
