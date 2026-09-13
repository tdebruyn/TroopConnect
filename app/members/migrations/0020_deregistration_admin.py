from django.db import migrations


# A current-year deregistration cannot be unwound automatically (the fee and
# attestation sides are already built on that enrolment), so deregister_confirm
# archives the child and tells the registration admins to follow the internal
# procedure. Seeded with the same fr-be copy and language as the other
# registration notifications (see 0012 / 0019).
DEREGISTRATION_ADMIN = {
    "subject": "Désinscription à traiter – {{ first_name }} {{ last_name }}",
    "content": (
        "Bonjour,\n\n"
        "{{ parent }} a demandé la désinscription de "
        "{{ first_name }} {{ last_name }} pour l'année scolaire en cours.\n\n"
        "Une désinscription en cours d'année ne peut pas être traitée "
        "automatiquement : le suivi de la cotisation et des attestations doit "
        "être clôturé manuellement. Merci de suivre la procédure décrite dans "
        "le règlement interne.\n\n"
        "Fiche du membre : {{ url }}\n\n"
        "Cordialement,\n"
        "L'équipe d'administration du site Scouts de Limal"
    ),
    "html_content": (
        "<p>Bonjour,</p>"
        "<p><strong>{{ parent }}</strong> a demandé la désinscription de "
        "<strong>{{ first_name }} {{ last_name }}</strong> pour l'année "
        "scolaire en cours.</p>"
        "<p>Une désinscription en cours d'année ne peut pas être traitée "
        "automatiquement : le suivi de la cotisation et des attestations doit "
        "être clôturé manuellement. Merci de suivre la procédure décrite dans "
        "le règlement interne.</p>"
        '<p><a href="{{ url }}" style="background-color: #0d6efd; color: #ffffff; '
        'padding: 10px 15px; text-decoration: none; border-radius: 5px;">'
        "Ouvrir la fiche du membre</a></p>"
        "<p>Cordialement,<br>L'équipe d'administration du site Scouts de Limal</p>"
    ),
    "language": "fr",
}


def create_template(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.filter(name="deregistration_admin").delete()
    EmailTemplate.objects.create(name="deregistration_admin", **DEREGISTRATION_ADMIN)


def remove_template(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.filter(name="deregistration_admin").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0019_email_template_language"),
        # The `language` field only exists from post_office's i18n migration on.
        ("post_office", "0002_add_i18n_and_backend_alias"),
    ]

    operations = [
        migrations.RunPython(create_template, remove_template),
    ]
