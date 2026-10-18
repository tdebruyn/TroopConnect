"""Add the section communications role.

"Responsable communication" is a secondary role on an Animateur. The role says
they speak for their section; the enrolment says which section. It is not a
unit-team role: it grants no administrative screens and does not put its holder
in ``STAFF_ROLES``.

The per-language columns are written explicitly, like migration ``0039``: the
migration must not depend on modeltranslation's runtime descriptors.
"""

from django.db import migrations

ROLE_TEXT = {
    "name": "Responsable communication de la section",
    "name_fr": "Responsable communication de la section",
    "name_en": "Section communications lead",
    "name_nl": "Communicatieverantwoordelijke van de sectie",
    "description": (
        "Fait le lien entre la section et les familles pour les communications."
    ),
    "description_fr": (
        "Fait le lien entre la section et les familles pour les communications."
    ),
    "description_en": (
        "Handles communication between the section and its families."
    ),
    "description_nl": (
        "Verzorgt de communicatie tussen de sectie en de gezinnen."
    ),
}


def forward(apps, schema_editor):
    Role = apps.get_model("members", "Role")
    Role.objects.update_or_create(
        short="rc",
        defaults={**ROLE_TEXT, "is_primary": False},
    )


def backward(apps, schema_editor):
    # Reversing deletes the role's assignments with it. They cannot be
    # reconstructed, but the role is part of the pre-migration state.
    Role = apps.get_model("members", "Role")
    Role.objects.filter(short="rc").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0044_passage_help_text"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
