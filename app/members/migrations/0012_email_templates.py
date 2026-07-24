from django.db import migrations


# Recommended default copy (fr-be) for the registration templates.
# Kept in sync with migration 0002 so both fresh installs and already-migrated
# databases end up with the same wording.

NEW_CHILD_STAFF = {
    "subject": "Nouvelle inscription à valider – {{ first_name }} {{ last_name }}",
    "content": (
        "Bonjour,\n\n"
        "Une nouvelle inscription vient d'être enregistrée sur le site des "
        "Scouts de Limal :\n"
        "{{ first_name }} {{ last_name }}\n\n"
        "Merci de la valider ou de la compléter en cliquant sur le lien suivant :\n"
        "{{ url }}\n\n"
        "Cordialement,\n"
        "L'équipe d'administration du site Scouts de Limal"
    ),
    "html_content": (
        "<p>Bonjour,</p>"
        "<p>Une nouvelle inscription vient d'être enregistrée sur le site des "
        "<strong>Scouts de Limal</strong> :</p>"
        "<p><strong>{{ first_name }} {{ last_name }}</strong></p>"
        "<p>Merci de la valider ou de la compléter via le lien suivant :</p>"
        '<p><a href="{{ url }}" style="background-color: #0d6efd; color: #ffffff; '
        'padding: 10px 15px; text-decoration: none; border-radius: 5px;">'
        "Valider l'inscription</a></p>"
        "<p>Cordialement,<br>L'équipe d'administration du site Scouts de Limal</p>"
    ),
}

NEW_CHILD_PARENT = {
    "subject": "Confirmation d'inscription – Scouts de Limal",
    "content": (
        "Bonjour {{ parent }},\n\n"
        "Nous confirmons la bonne réception de l'inscription de votre enfant "
        "{{ first_name }} {{ last_name }} au sein de notre unité.\n\n"
        "Un membre du staff va examiner l'inscription et prendra contact avec "
        "vous si nécessaire. Vous pouvez consulter et compléter le dossier "
        "depuis votre espace personnel sur le site.\n\n"
        "Cordialement,\n"
        "L'équipe des Scouts de Limal"
    ),
    "html_content": (
        "<p>Bonjour {{ parent }},</p>"
        "<p>Nous confirmons la bonne réception de l'inscription de votre enfant "
        "<strong>{{ first_name }} {{ last_name }}</strong> au sein de notre unité.</p>"
        "<p>Un membre du staff va examiner l'inscription et prendra contact avec "
        "vous si nécessaire. Vous pouvez consulter et compléter le dossier "
        "depuis votre espace personnel sur le site.</p>"
        "<p>Cordialement,<br>L'équipe des Scouts de Limal</p>"
    ),
}


def create_and_fix_templates(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    # The code resolves "new_child_staff" with the model's default language
    # (""), but the template was historically seeded under the wrong name
    # ("new_child_staff_fr") or with the wrong language, so post_office could
    # never find it and the registration flow crashed. Remove every variant and
    # seed a single template with the correct name and recommended copy. We
    # filter/create by name only, so this stays valid regardless of the
    # post_office schema state at migration time.
    EmailTemplate.objects.filter(name__in=["new_child_staff", "new_child_staff_fr"]).delete()
    EmailTemplate.objects.create(name="new_child_staff", **NEW_CHILD_STAFF)

    # Parent confirmation email, sent by add_new_child_view.
    if not EmailTemplate.objects.filter(name="new_child_parent").exists():
        EmailTemplate.objects.create(name="new_child_parent", **NEW_CHILD_PARENT)


def remove_templates(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.filter(name="new_child_parent").delete()
    # Reversing the rename is intentionally a no-op: the misnamed
    # "new_child_staff_fr" row is not resurrected.


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0011_sitesettings_new_fields"),
        ("post_office", "__first__"),
    ]

    operations = [
        migrations.RunPython(create_and_fix_templates, remove_templates),
    ]
