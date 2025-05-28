from django.db import migrations
from datetime import date, datetime


def create_roles(apps, schema_editor):
    Role = apps.get_model("members", "Role")

    # Define the roles to create
    roles_to_create = [
        {
            "short": "n",
            "name": "Nouveau",
            "description": "Compte créé mais pas encore validé",
            "is_primary": True,
        },
        {
            "short": "a",
            "name": "Animateur",
            "description": "Animateur de staff",
            "is_primary": True,
        },
        {
            "short": "p",
            "name": "Parent",
            "description": "Parent d'un membre",
            "is_primary": True,
        },
        {
            "short": "e",
            "name": "Animé",
            "description": "Enfant animé",
            "is_primary": True,
        },
        {
            "short": "pa",
            "name": "Parent actif",
            "description": "Parent volontaire pour aider l'unité occasionellement",
            "is_primary": False,
        },
        {
            "short": "ar",
            "name": "Animateur responsable",
            "description": "Animateur responsable d'un staff",
            "is_primary": False,
        },
        {
            "short": "t",
            "name": "Trésorier",
            "description": "Trésorier de l'unité, donne accès aux cotisations",
            "is_primary": False,
        },
        {
            "short": "ri",
            "name": "Responsable inscriptions",
            "description": "Peut gérer les inscriptions",
            "is_primary": False,
        },
        {
            "short": "ad",
            "name": "Admin",
            "description": "Administrateur du site",
            "is_primary": False,
        },
    ]

    # Get existing role names to avoid duplicates
    existing_roles = set(Role.objects.values_list("name", flat=True))

    # Create only roles that don't exist yet
    roles_to_bulk_create = []
    for role_data in roles_to_create:
        if role_data["name"] not in existing_roles:
            roles_to_bulk_create.append(Role(**role_data))

    # Only bulk create if there are new roles to add
    if roles_to_bulk_create:
        Role.objects.bulk_create(roles_to_bulk_create)


def create_school_years(apps, schema_editor):
    SchoolYear = apps.get_model("members", "SchoolYear")

    # Get current year
    current_year = datetime.now().year

    # If we're past July 31st, the current school year starts this year
    # Otherwise, it started last year
    if datetime.now().date() > date(current_year, 7, 31):
        first_year = current_year
    else:
        first_year = current_year - 1

    # Check if current school year already exists
    if not SchoolYear.objects.filter(name=first_year).exists():
        SchoolYear.objects.create(
            name=first_year,
            start_date=date(first_year, 8, 1),
            end_date=date(first_year + 1, 7, 31),
            range=f"{first_year}-{first_year + 1}",
        )

    # Check if next school year already exists
    next_year = first_year + 1
    if not SchoolYear.objects.filter(name=next_year).exists():
        SchoolYear.objects.create(
            name=next_year,
            start_date=date(next_year, 8, 1),
            end_date=date(next_year + 1, 7, 31),
            range=f"{next_year}-{next_year + 1}",
        )


def create_new_child_staff_template(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    template_name = "new_child_staff_fr"  # Add '_fr' suffix to indicate French version

    # Filter only by name, since 'language' field doesn't exist
    if not EmailTemplate.objects.filter(name=template_name).exists():
        EmailTemplate.objects.create(
            name=template_name,
            subject="Nouvelle inscription d’un enfant à valider – {{ first_name }} {{ last_name }}",
            content=(
                "Bonjour,\n\n"
                "Un parent vient d’inscrire un nouvel enfant : {{ first_name }} {{ last_name }}.\n\n"
                "Merci de valider ou de compléter cette inscription en vous rendant sur le lien suivant :\n"
                "{{ url }}\n\n"
                "Cordialement,\n"
                "L’équipe d’administration du site Scouts Limal"
            ),
            html_content=(
                "<p>Bonjour,</p>"
                "<p>Un parent vient d’inscrire un nouvel enfant : <strong>{{ first_name }} {{ last_name }}</strong>.</p>"
                "<p>Merci de valider ou de compléter cette inscription en cliquant sur le lien suivant :</p>"
                '<p><a href="{{ url }}" style="background-color: #4CAF50; color: white; padding: 10px 15px; '
                'text-decoration: none; border-radius: 5px;">Gérer l’inscription</a></p>'
                "<p>Cordialement,<br>L’équipe d’administration du site <strong>Scouts Limal</strong></p>"
            ),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0001_initial"),
        ("post_office", "__first__"),
    ]

    operations = [
        migrations.RunPython(create_roles),
        migrations.RunPython(create_school_years),
        migrations.RunPython(create_new_child_staff_template),
    ]
