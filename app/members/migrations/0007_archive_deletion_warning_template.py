from django.db import migrations


def create_archive_deletion_warning_template(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    if not EmailTemplate.objects.filter(name="archive_deletion_warning").exists():
        EmailTemplate.objects.create(
            name="archive_deletion_warning",
            subject="Suppression imminente de votre compte – Scouts de Limal",
            content=(
                "Bonjour,\n\n"
                "Le compte de {{ person_name }} est archivé depuis plus de 4 ans et 11 mois.\n\n"
                "Conformément à notre politique de conservation des données, ce compte sera "
                "définitivement supprimé le {{ deletion_date }}.\n\n"
                "Si vous souhaitez conserver ce compte, veuillez contacter l'unité avant cette date.\n\n"
                "Cordialement,\n"
                "Les Scouts de Limal"
            ),
            html_content=(
                "<p>Bonjour,</p>"
                "<p>Le compte de <strong>{{ person_name }}</strong> est archivé depuis plus de 4 ans et 11 mois.</p>"
                "<p>Conformément à notre politique de conservation des données, ce compte sera "
                "<strong>définitivement supprimé le {{ deletion_date }}</strong>.</p>"
                "<p>Si vous souhaitez conserver ce compte, veuillez contacter l'unité avant cette date.</p>"
                "<p>Cordialement,<br>Les Scouts de Limal</p>"
            ),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0006_add_archived_date_to_person"),
        ("post_office", "__first__"),
    ]

    operations = [
        migrations.RunPython(create_archive_deletion_warning_template),
    ]
