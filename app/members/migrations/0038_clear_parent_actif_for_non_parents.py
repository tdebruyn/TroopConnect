from django.db import migrations


def clear_parent_actif_for_non_parents(apps, schema_editor):
    """A "Parent actif" is a Parent who helps out, so the role only makes
    sense alongside the Parent primary role. Remove assignments left on
    anyone else by earlier forms."""
    PersonRole = apps.get_model("members", "PersonRole")
    PersonRole.objects.filter(role__short="pa").exclude(
        person__primary_role__short="p"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0037_troopsettings_map_image_troopsettings_meeting_place"),
    ]

    operations = [
        migrations.RunPython(
            clear_parent_actif_for_non_parents, migrations.RunPython.noop
        ),
    ]
