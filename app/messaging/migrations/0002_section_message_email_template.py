from django.db import migrations


def create_section_message_template(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    if not EmailTemplate.objects.filter(name="section_message").exists():
        EmailTemplate.objects.create(
            name="section_message",
            subject="{{ subject }}",
            content=(
                "Message de {{ sender_name }} (Section {{ section_name }})\n\n"
                "{{ body }}\n\n"
                "---\n"
                "Ce message a été envoyé via le site TroopConnect."
            ),
            html_content=(
                "<p><strong>Message de {{ sender_name }}</strong> "
                "(Section {{ section_name }})</p>"
                "<p>{{ body|linebreaksbr }}</p>"
                "<hr>"
                "<p><small>Ce message a été envoyé via le site TroopConnect.</small></p>"
            ),
        )


def remove_section_message_template(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.filter(name="section_message").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("messaging", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_section_message_template,
            remove_section_message_template,
        ),
    ]
