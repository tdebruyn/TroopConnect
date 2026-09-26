"""What an empty, freshly migrated database has to be able to do.

A troop installs TroopConnect by pointing it at an empty database, running
``migrate`` and creating a superuser. Nothing is seeded by hand, so anything the
first registration needs has to come from a migration: a ``django.contrib.sites``
row (there is none by default, and every email links back through it) and email
copy that speaks for whoever is hosting it.
"""

import importlib

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.sites.models import Site
from django.template import Context, Engine
from django.test import TestCase, override_settings
from post_office.models import Email, EmailTemplate
from post_office.utils import get_email_template
from post_office.validators import validate_template_syntax

from members import email_templates
from members.mail import absolute_url, resolve_language, send_templated
from members.models import SiteSettings

from .mail import MailTestCase

# The module name starts with a digit, so it cannot be imported normally.
SITE_MIGRATION = importlib.import_module(
    "members.migrations.0021_pristine_site_and_generic_templates"
)


class PristineDatabaseTest(TestCase):
    """The state a fresh install is in before anything is configured."""

    def test_the_database_starts_empty(self):
        self.assertEqual(SiteSettings.objects.count(), 0)

    def test_migrating_creates_the_site_row(self):
        """django.contrib.sites ships no data, so this has to come from us."""
        self.assertEqual(Site.objects.filter(pk=settings.SITE_ID).count(), 1)

    def test_the_data_migration_alone_is_enough(self):
        """Guards the migration, not just the startup hook that also syncs it."""
        Site.objects.all().delete()

        SITE_MIGRATION.create_site_row(django_apps, None)

        self.assertEqual(Site.objects.filter(pk=settings.SITE_ID).count(), 1)

    def test_the_current_site_resolves(self):
        self.assertTrue(Site.objects.get_current().domain)


class PristineEmailTest(MailTestCase):
    """Rendering an email that links back to the site, on an untouched database."""

    @override_settings(TROOP_NAME="Unit Test")
    def test_a_registration_email_renders_with_an_absolute_url(self):
        domain = Site.objects.get_current().domain

        send_templated(
            recipients=["staff@example.org"],
            template="new_child_staff",
            language="fr",
            context={
                "first_name": "Ana",
                "last_name": "Dupont",
                "url": absolute_url("/users/adminupdate/42"),
            },
        )

        email = Email.objects.latest("created")
        link = f"https://{domain}/users/adminupdate/42"

        # Without the scheme the link is not clickable in a mail client, which
        # is what a bare Site.domain produced.
        self.assertIn(link, email.message)
        self.assertIn(link, email.html_message)

    @override_settings(TROOP_NAME="Unit Test")
    def test_the_email_speaks_for_the_configured_troop(self):
        send_templated(
            recipients=["staff@example.org"],
            template="new_child_staff",
            language="fr",
            context={
                "first_name": "Ana",
                "last_name": "Dupont",
                "url": absolute_url("/users/adminupdate/42"),
            },
        )

        email = Email.objects.latest("created")

        # The name comes from the caller's context, not from the stored copy.
        self.assertIn("Unit Test", email.message)
        self.assertIn("Unit Test", email.html_message)

    def test_a_dutch_recipient_gets_a_dutch_email(self):
        """Only French used to be seeded, so this raised DoesNotExist."""
        send_templated(
            recipients=["ouder@example.org"],
            template="new_child_parent",
            language="nl",
            context={"parent": "Jan", "first_name": "Ana", "last_name": "Dupont"},
        )

        email = Email.objects.latest("created")
        self.assertIn("Bevestiging van inschrijving", email.subject)

    def test_an_english_recipient_gets_an_english_email(self):
        send_templated(
            recipients=["parent@example.org"],
            template="new_child_parent",
            language="en",
            context={"parent": "Jane", "first_name": "Ana", "last_name": "Dupont"},
        )

        email = Email.objects.latest("created")
        self.assertIn("Registration confirmation", email.subject)


class SeededTemplateTest(TestCase):
    """The copy that ends up in the database."""

    def seeded_rows(self):
        return EmailTemplate.objects.filter(name__in=email_templates.TEMPLATES)

    def test_every_template_is_seeded_in_every_language(self):
        for name, language, fields in email_templates.rows():
            row = EmailTemplate.objects.get(name=name, language=language)
            for field, value in fields.items():
                self.assertEqual(
                    getattr(row, field), value, f"{name}/{language}/{field}"
                )

    def test_no_seeded_row_names_a_troop(self):
        for row in self.seeded_rows():
            for field in ("subject", "content", "html_content"):
                text = getattr(row, field)
                for marker in email_templates.LEGACY_MARKERS:
                    self.assertNotIn(marker, text, f"{row.name}/{row.language}/{field}")

    def test_seeded_copy_is_valid_template_syntax(self):
        for row in self.seeded_rows():
            for field in ("subject", "content", "html_content"):
                validate_template_syntax(getattr(row, field))

    def test_seeded_copy_renders_and_uses_the_troop_name(self):
        context = {name: name for name in email_templates.variables_used()}
        context["troop_name"] = "Unit Test"
        context["url"] = "https://example.org/x"
        context["body"] = "First line\nSecond line"

        engine = Engine.get_default()

        for name, language, fields in email_templates.rows():
            rendered = "\n".join(
                engine.from_string(source).render(Context(context))
                for source in fields.values()
            )

            where = f"{name}/{language}"
            self.assertNotIn("{{", rendered, f"unrendered variable in {where}")
            # Every one of these emails speaks for the troop somewhere.
            self.assertIn("Unit Test", rendered, f"no troop name in {where}")


class SeedingTest(TestCase):
    """Re-seeding has to fix the copy without trampling on an admin's own."""

    def test_it_replaces_seeded_copy(self):
        EmailTemplate.objects.filter(name="new_child_staff", language="fr").update(
            subject="Nouvelle inscription – Scouts de Limal",
            content="Une inscription sur le site des Scouts de Limal",
            html_content="<p>Scouts de Limal</p>",
        )

        email_templates.seed(EmailTemplate)

        row = EmailTemplate.objects.get(name="new_child_staff", language="fr")
        self.assertIn("{{ troop_name }}", row.content)
        self.assertNotIn("Scouts de Limal", row.content)

    def test_it_keeps_copy_that_was_rewritten_by_hand(self):
        EmailTemplate.objects.filter(name="new_child_staff", language="fr").update(
            subject="Notre sujet",
            content="Notre propre texte.",
            html_content="<p>Notre propre texte.</p>",
        )

        email_templates.seed(EmailTemplate)

        row = EmailTemplate.objects.get(name="new_child_staff", language="fr")
        self.assertEqual(row.subject, "Notre sujet")
        self.assertEqual(row.content, "Notre propre texte.")

    def test_force_replaces_copy_that_no_longer_looks_seeded(self):
        """What a migration changing the canonical copy has to pass.

        After the first seed a row holds this module's copy, which the
        conservative check cannot recognise, so without force=True the new
        wording would never reach an already-seeded database.
        """
        EmailTemplate.objects.filter(name="new_child_staff", language="fr").update(
            subject="Previous canonical subject",
            content="Previous canonical copy.",
            html_content="<p>Previous canonical copy.</p>",
        )

        email_templates.seed(EmailTemplate)
        unchanged = EmailTemplate.objects.get(name="new_child_staff", language="fr")
        self.assertEqual(unchanged.subject, "Previous canonical subject")

        email_templates.seed(EmailTemplate, force=True)
        replaced = EmailTemplate.objects.get(name="new_child_staff", language="fr")
        self.assertEqual(
            replaced.subject, email_templates.TEMPLATES["new_child_staff"]["fr"]["subject"]
        )

    def test_it_creates_a_language_that_was_never_seeded(self):
        EmailTemplate.objects.filter(name="new_child_staff").delete()

        email_templates.seed(EmailTemplate)

        self.assertTrue(
            EmailTemplate.objects.filter(
                name="new_child_staff", language="en"
            ).exists()
        )

    def test_it_removes_a_seeded_row_in_a_language_we_no_longer_use(self):
        # post_office's default language is "", which is what these were once
        # seeded under; nothing looks them up now.
        EmailTemplate.objects.create(
            name="section_message",
            language="",
            subject="{{ subject }}",
            content="Message envoyé via le site TroopConnect.",
            html_content="<p>TroopConnect</p>",
        )

        email_templates.seed(EmailTemplate)

        self.assertFalse(
            EmailTemplate.objects.filter(name="section_message", language="").exists()
        )


class TemplateCacheInvalidationTest(TestCase):
    """post_office caches under "{name}:{language}" but only clears "{name}".

    Without the correction in troopconnect.postoffice, re-seeding the templates
    -- or editing one in the admin -- leaves the previous copy being sent until
    the cache entry expires.
    """

    def setUp(self):
        self.template = EmailTemplate.objects.create(
            name="cache_probe",
            language="fr",
            subject="First",
            content="first",
        )
        # Prime the cache the way a send would.
        self.assertEqual(get_email_template("cache_probe", "fr").subject, "First")

    def test_saving_a_template_forgets_the_cached_copy(self):
        changed = EmailTemplate.objects.get(pk=self.template.pk)
        changed.subject = "Second"
        changed.save()

        self.assertEqual(get_email_template("cache_probe", "fr").subject, "Second")

    def test_deleting_a_template_forgets_the_cached_copy(self):
        self.template.delete()

        with self.assertRaises(EmailTemplate.DoesNotExist):
            get_email_template("cache_probe", "fr")


class AbsoluteUrlTest(TestCase):
    def test_it_adds_the_scheme_and_the_current_domain(self):
        domain = Site.objects.get_current().domain

        self.assertEqual(absolute_url("/users/x"), f"https://{domain}/users/x")

    def test_it_tolerates_a_missing_leading_slash(self):
        domain = Site.objects.get_current().domain

        self.assertEqual(absolute_url("users/x"), f"https://{domain}/users/x")

    def test_it_leaves_an_absolute_url_alone(self):
        self.assertEqual(
            absolute_url("https://elsewhere.example/x"), "https://elsewhere.example/x"
        )


class ResolveLanguageTest(TestCase):
    def test_it_keeps_a_language_we_have_templates_for(self):
        self.assertEqual(resolve_language("nl"), "nl")

    def test_it_falls_back_to_the_site_language(self):
        self.assertEqual(resolve_language("de"), settings.LANGUAGE_CODE)

    def test_it_falls_back_to_french_when_the_site_language_is_unknown(self):
        with override_settings(LANGUAGE_CODE="de"):
            self.assertEqual(resolve_language(None), email_templates.DEFAULT_LANGUAGE)
