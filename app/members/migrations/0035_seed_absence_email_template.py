"""Give databases that already exist the absence-notice email copy.

``email_templates.seed()`` is what writes this copy, and migration ``0021``
already calls it — but that migration has run on every live database, and it
read the copy as it stood then. A template added afterwards therefore reaches a
fresh install (which runs ``0021`` against today's ``email_templates``) and no
one else, so the row has to be seeded again here for an upgraded one.

``seed()`` without ``force`` is what is wanted here: it creates the missing row
and leaves every existing one as it is, so a troop that has rewritten its own
wording keeps it.
"""

from django.db import migrations

from members import email_templates


def seed_email_templates(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    email_templates.seed(EmailTemplate)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0034_absence"),
        # seed() writes the `language` column, which only exists from
        # post_office's i18n migration onward.
        ("post_office", "0002_add_i18n_and_backend_alias"),
    ]

    operations = [
        # Reversing would delete copy a live instance now sends, so going back
        # leaves the row in place.
        migrations.RunPython(seed_email_templates, migrations.RunPython.noop),
    ]
