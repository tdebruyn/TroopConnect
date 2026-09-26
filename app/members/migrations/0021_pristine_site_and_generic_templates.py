"""Give a pristine database a Site row, and email copy that names no troop.

Two things a fresh database needs, and only a migration can guarantee:

* ``django.contrib.sites`` ships no data, so a new database has no Site row at
  all and ``Site.objects.get_current()`` raises ``DoesNotExist``. Every email
  that links back to the site calls it, so the first registration would fail.
  The row is created here; its *domain* is then kept in step with SITE_DOMAIN
  by ``troopconnect.siteconfig``, which runs on every ``migrate``. The split is
  deliberate: this migration guarantees the row exists, the startup hook keeps
  its value current.

* The email templates were seeded with one troop's name written into the text,
  and only in French -- so a parent whose language is Dutch or English got a
  template lookup failure instead of an email. They are rewritten from
  ``members.email_templates``, which speaks of ``{{ troop_name }}`` and exists
  in all three languages the site offers.

The seeding migrations that came before are left as they were: they have
already run on live databases, and rewriting an applied migration would make a
fresh install diverge from an upgraded one. Their copy is normalised here
instead, and only where it has not been rewritten by hand in the admin.
"""

from django.conf import settings
from django.db import migrations

from members import email_templates


def create_site_row(apps, schema_editor):
    Site = apps.get_model("sites", "Site")

    site_id = getattr(settings, "SITE_ID", 1)
    # A bare hostname is required by the model's validator; SITE_DOMAIN is
    # checked for shape by troopconnect.checks, and siteconfig rewrites this on
    # every migrate once the operator has set it.
    domain = getattr(settings, "SITE_DOMAIN", None) or "localhost"

    Site.objects.get_or_create(
        id=site_id,
        defaults={"domain": domain, "name": domain},
    )


def seed_email_templates(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    email_templates.seed(EmailTemplate)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0020_deregistration_admin"),
        ("sites", "0002_alter_domain_unique"),
        # email_templates.seed() writes the `language` column, which only
        # exists from post_office's i18n migration onward.
        ("post_office", "0002_add_i18n_and_backend_alias"),
    ]

    operations = [
        # Reversing would delete a row that live instances now depend on, so
        # going back leaves it in place.
        migrations.RunPython(create_site_row, migrations.RunPython.noop),
        migrations.RunPython(seed_email_templates, migrations.RunPython.noop),
    ]
