"""Give the troop a logo and a favicon of its own, and put the logo in the mail.

The design stays the federation's — everything under
``app/static/vendor/template-unite/`` is Les Scouts' and is never edited. What
this adds is the one thing that is the *troop's*: its own mark, uploaded in the
settings page, shown in the site header and at the top of the emails the troop
sends. Both fields are optional; an empty logo falls back to the mark shipped
with the application, so an instance that configures nothing looks exactly as
it did before.

``members.email_templates`` prefixes every HTML body with the logo, so the rows
already in the database need updating. That is done here rather than through
``email_templates.seed(force=True)``, because force replaces *everything*: it
would overwrite the wording of a troop that had rewritten one of these emails
in the admin. A row is only touched when it still reads exactly as this project
wrote it — the new canonical body with the logo taken back off — which is a
match no hand-edited row can produce.
"""

from django.db import migrations, models
from post_office import cache as template_cache

from members import email_templates
from troopconnect.postoffice import cache_token


def _rewrite(row, html_content):
    """Store a new body and drop the copy post_office is holding.

    The cache fix in ``troopconnect.postoffice`` hangs off ``EmailTemplate``'s
    post_save signal, which the historical model does not send. Without this
    the old body keeps being sent — post_office's cache entry has an expiry,
    so it would correct itself eventually, which is worse: the change would
    look like it had not worked for an afternoon.
    """
    row.html_content = html_content
    row.save(update_fields=["html_content"])
    template_cache.delete(cache_token(row))


def add_logo_to_bodies(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    for name, language, fields in email_templates.rows():
        row = EmailTemplate.objects.filter(name=name, language=language).first()
        if row is None:
            continue

        before = email_templates.without_logo(fields["html_content"])
        if row.html_content != before:
            # Rewritten by hand, or seeded from different copy. Leave it.
            continue

        _rewrite(row, fields["html_content"])


def remove_logo_from_bodies(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    for name, language, fields in email_templates.rows():
        row = EmailTemplate.objects.filter(name=name, language=language).first()
        if row is None or row.html_content != fields["html_content"]:
            continue

        _rewrite(row, email_templates.without_logo(fields["html_content"]))


class Migration(migrations.Migration):

    # No explicit post_office dependency: members/0021 already pins the
    # post_office migration that introduced `language`, and this chain reaches
    # it, so `html_content` is there by the time this runs.
    dependencies = [
        ("members", "0027_derive_branch_ladder"),
    ]

    operations = [
        migrations.AddField(
            model_name="troopsettings",
            name="logo",
            field=models.ImageField(
                blank=True,
                help_text=(
                    "Shown in the site header and in outgoing email. Leave empty "
                    "to use the default Les Scouts mark."
                ),
                upload_to="troop/",
            ),
        ),
        migrations.AddField(
            model_name="troopsettings",
            name="favicon",
            field=models.ImageField(
                blank=True,
                help_text=(
                    "The small icon browsers show for the site. Leave empty for "
                    "no icon."
                ),
                upload_to="troop/",
            ),
        ),
        migrations.RunPython(add_logo_to_bodies, remove_logo_from_bodies),
    ]
