"""Introduce "Autre membre" and model the unit team explicitly.

The unit's secondary roles (ar/t/ri) now belong to Parents and Autres membres
only: an Animateur's responsibility is their section, and a Participant is a
child. The old "Admin" role is gone — the site's Django administrator already
reaches every screen, and a second role with a subset of those powers only
made the two easy to confuse.
"""
from django.db import migrations, models


# short -> field values. The original column and the per-language columns are
# all written: modeltranslation reads the language columns at runtime, while
# the migration must not depend on that runtime descriptor.
ROLE_TEXT = {
    "am": {
        "name": "Autre membre",
        "name_fr": "Autre membre",
        "name_en": "Other member",
        "name_nl": "Ander lid",
        "description": (
            "Membre adulte de l'unité qui n'est ni parent ni animateur."
        ),
        "description_fr": (
            "Membre adulte de l'unité qui n'est ni parent ni animateur."
        ),
        "description_en": (
            "Adult member of the unit who is neither a parent nor an animator."
        ),
        "description_nl": (
            "Volwassen lid van de eenheid dat geen ouder of animator is."
        ),
    },
    "ar": {
        "name": "Animateur responsable de l'équipe d'unité",
        "name_fr": "Animateur responsable de l'équipe d'unité",
        "name_en": "Unit team lead",
        "name_nl": "Verantwoordelijke animator van het eenheidsteam",
        "description": (
            "Responsable de l'équipe d'unité : administration des membres "
            "et des finances."
        ),
        "description_fr": (
            "Responsable de l'équipe d'unité : administration des membres "
            "et des finances."
        ),
        "description_en": (
            "Leads the unit team: administers members and finances."
        ),
        "description_nl": (
            "Leidt het eenheidsteam: beheert leden en financiën."
        ),
    },
    "t": {
        "name": "Trésorier de l'équipe d'unité",
        "name_fr": "Trésorier de l'équipe d'unité",
        "name_en": "Unit team treasurer",
        "name_nl": "Penningmeester van het eenheidsteam",
        "description": "Trésorier de l'équipe d'unité, accès aux cotisations.",
        "description_fr": (
            "Trésorier de l'équipe d'unité, accès aux cotisations."
        ),
        "description_en": (
            "Unit team treasurer, with access to membership fees."
        ),
        "description_nl": (
            "Penningmeester van het eenheidsteam, met toegang tot de "
            "lidgelden."
        ),
    },
    "ri": {
        "name": "Responsable inscriptions de l'équipe d'unité",
        "name_fr": "Responsable inscriptions de l'équipe d'unité",
        "name_en": "Unit team registration lead",
        "name_nl": "Inschrijvingsbeheerder van het eenheidsteam",
        "description": "Gère les inscriptions et les dossiers des membres.",
        "description_fr": "Gère les inscriptions et les dossiers des membres.",
        "description_en": "Manages registrations and member records.",
        "description_nl": "Beheert inschrijvingen en ledendossiers.",
    },
}


#: The names this migration replaces. Restored on reverse before the
#: AlterFields shrink the column back to 30 characters.
OLD_ROLE_TEXT = {
    "ar": {
        "name": "Animateur responsable",
        "name_fr": "Animateur responsable",
        "name_en": "Lead animator",
        "name_nl": "Verantwoordelijke animator",
    },
    "t": {
        "name": "Trésorier",
        "name_fr": "Trésorier",
        "name_en": "Treasurer",
        "name_nl": "Penningmeester",
    },
    "ri": {
        "name": "Responsable inscriptions",
        "name_fr": "Responsable inscriptions",
        "name_en": "Registration manager",
        "name_nl": "Inschrijvingsbeheerder",
    },
    "ad": {
        "name": "Admin",
        "name_fr": "Admin",
        "name_en": "Admin",
        "name_nl": "Beheerder",
    },
}


def backward(apps, schema_editor):
    Role = apps.get_model("members", "Role")
    for short, values in OLD_ROLE_TEXT.items():
        Role.objects.filter(short=short).update(**values)
    # The role's assignments cannot be recovered, but the role itself was
    # part of the pre-migration state.
    Role.objects.get_or_create(
        short="ad", defaults={**OLD_ROLE_TEXT["ad"], "is_primary": False}
    )


def forward(apps, schema_editor):
    Role = apps.get_model("members", "Role")
    PersonRole = apps.get_model("members", "PersonRole")

    for short, values in ROLE_TEXT.items():
        role, _created = Role.objects.get_or_create(
            short=short, defaults={**values, "is_primary": short == "am"}
        )
        Role.objects.filter(pk=role.pk).update(
            is_primary=short == "am", **values
        )

    # The Admin role has no remaining meaning: a site/Django administrator is
    # is_staff/is_superuser. Deleting the role cascades to its assignments.
    Role.objects.filter(short="ad").delete()

    # Enforce the new invariants on existing data. Animateurs, participants
    # and not-yet-validated accounts hold no secondary role, and "Parent
    # actif" only means anything beside Parent.
    PersonRole.objects.filter(role__is_primary=False).exclude(
        person__primary_role__short__in=["p", "am"]
    ).delete()
    PersonRole.objects.filter(role__short="pa").exclude(
        person__primary_role__short="p"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0038_clear_parent_actif_for_non_parents'),
    ]

    operations = [
        migrations.AlterField(
            model_name='role',
            name='name',
            field=models.CharField(max_length=60, unique=True),
        ),
        migrations.AlterField(
            model_name='role',
            name='name_en',
            field=models.CharField(max_length=60, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='role',
            name='name_fr',
            field=models.CharField(max_length=60, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='role',
            name='name_nl',
            field=models.CharField(max_length=60, null=True, unique=True),
        ),
        migrations.RunPython(forward, backward),
    ]
