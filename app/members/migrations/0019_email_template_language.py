from django.db import migrations


# post_office looks templates up by exact (name, language); the registration
# notifications are sent with `language=settings.LANGUAGE_CODE` ("fr"), but the
# templates were historically seeded with post_office's default language (""),
# so every lookup raised DoesNotExist and the child registration flow crashed.
# Pin both templates to the language the code actually sends.
TEMPLATES = ("new_child_parent", "new_child_staff")


def pin_template_language(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.filter(name__in=TEMPLATES).update(language="fr")


def unpin_template_language(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.filter(name__in=TEMPLATES).update(language="")


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0018_clear_participant_secondary_roles"),
        # The `language` field only exists from post_office's i18n migration
        # onward; depending on __first__ would give a model without it.
        ("post_office", "0002_add_i18n_and_backend_alias"),
    ]

    operations = [
        migrations.RunPython(pin_template_language, unpin_template_language),
    ]
