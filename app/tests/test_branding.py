"""The troop's own mark: the logo and the favicon, on the site and in the mail.

The design belongs to Les Scouts and is vendored untouched (see
``app/static/vendor/template-unite/``). What a troop owns is its own mark: an
upload in the media storage, shown in the site header and at the top of the
emails it sends. Both fields are optional, and what an instance that has
uploaded nothing shows is the point of most of these tests — the fallback has
to exist, be served, and be what the header already showed before the fields
were introduced.
"""

import importlib
import tempfile

from django.apps import apps as django_apps
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.signals import post_delete, post_save
from django.test import override_settings
from django.urls import reverse
from post_office import cache as template_cache
from post_office.models import Email, EmailTemplate
from post_office.utils import get_email_template

from members import email_templates
from members.constants import DEFAULT_LOGO
from members.mail import absolute_url, send_templated
from members.models import (
    Account,
    Person,
    Role,
    TroopSettings,
    _invalidate_troop_settings_cache,
)
from troopconnect.postoffice import TEMPLATE_CACHE_UID, cache_token, forget_template

from .base import TroopSettingsTestCase
from .mail import MailTestCase

# The module name starts with a digit, so it cannot be imported normally.
LOGO_MIGRATION = importlib.import_module(
    "members.migrations.0029_seed_troop_logo"
)
BODY_MIGRATION = importlib.import_module(
    "members.migrations.0028_troopsettings_logo_favicon"
)


def an_image(name="mine.png"):
    """A real image file, taken from the mark the application ships.

    Using the shipped asset rather than a hand-written PNG keeps this honest
    without depending on Pillow to build one: ``ImageField`` validates the file
    it is given.
    """
    with open(finders.find(DEFAULT_LOGO), "rb") as fh:
        return SimpleUploadedFile(name, fh.read(), content_type="image/png")


class MediaRootTestCase(TroopSettingsTestCase):
    """Anything that writes an upload needs somewhere to write it."""

    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.override = override_settings(MEDIA_ROOT=media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)


class LogoResolutionTest(MediaRootTestCase):
    """``logo_url`` / ``favicon_url``, which is the only thing templates read."""

    def test_the_bundled_mark_is_actually_shipped(self):
        """The fallback is a path into the static files, so it has to resolve.

        Without this the header would render a broken image on every instance
        that never uploaded a logo, and only a browser would notice.
        """
        self.assertIsNotNone(finders.find(DEFAULT_LOGO))

    def test_no_upload_falls_back_to_the_bundled_mark(self):
        troop = TroopSettings.get_settings()

        self.assertEqual(troop.logo_url(), f"/static/{DEFAULT_LOGO}")

    def test_an_uploaded_logo_is_served_from_the_media_storage(self):
        troop = TroopSettings.get_settings()
        troop.logo = an_image()
        troop.save()

        url = troop.logo_url()

        self.assertTrue(url.startswith("/media/troop/"), url)
        self.assertNotIn(DEFAULT_LOGO, url)
        self.assertTrue(url.endswith(".png"))
        self.assertTrue(troop.logo.storage.exists(troop.logo.name))

    def test_a_logo_replacing_another_does_not_fall_back(self):
        troop = TroopSettings.get_settings()
        troop.logo = an_image("first.png")
        troop.save()
        first = troop.logo_url()

        troop.logo = an_image("second.png")
        troop.save()

        self.assertNotEqual(troop.logo_url(), first)

    def test_favicon_is_empty_until_one_is_uploaded(self):
        """Empty is the honest answer: there is no default icon to fall back to."""
        self.assertEqual(TroopSettings.get_settings().favicon_url(), "")

    def test_an_uploaded_favicon_is_served_from_the_media_storage(self):
        troop = TroopSettings.get_settings()
        troop.favicon = an_image("icon.png")
        troop.save()

        self.assertTrue(troop.favicon_url().startswith("/media/troop/"))

    def test_a_favicon_is_not_the_logo(self):
        """Two independent fields: uploading one must not stand in for the other."""
        troop = TroopSettings.get_settings()
        troop.logo = an_image()
        troop.save()

        self.assertEqual(troop.favicon_url(), "")


class BrandingInThePageTest(MediaRootTestCase):
    """What the header actually renders, through a real request."""

    def setUp(self):
        super().setUp()
        self.url = reverse("homepage")

    def test_the_header_shows_the_bundled_mark_by_default(self):
        response = self.client.get(self.url)

        self.assertContains(response, f"/static/{DEFAULT_LOGO}")

    def test_the_header_shows_an_uploaded_logo(self):
        troop = TroopSettings.get_settings()
        troop.logo = an_image()
        troop.save()

        response = self.client.get(self.url)

        self.assertContains(response, troop.logo_url())
        self.assertNotContains(response, f"/static/{DEFAULT_LOGO}")

    def test_there_is_no_icon_link_without_a_favicon(self):
        """A site with no favicon gets the browser's own behaviour, as before."""
        response = self.client.get(self.url)

        self.assertNotContains(response, 'rel="icon"')

    def test_an_uploaded_favicon_becomes_the_icon_link(self):
        troop = TroopSettings.get_settings()
        troop.favicon = an_image("icon.png")
        troop.save()

        response = self.client.get(self.url)

        self.assertContains(response, f'rel="icon" href="{troop.favicon_url()}"')


class SettingsPageUploadTest(MediaRootTestCase):
    """The staff page has to accept a file, not just remember a string."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_person = Person.objects.create(
            first_name="Ada",
            last_name="Staff",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        Account.objects.create_user(
            email="staff-branding@test.com",
            password="testpass",
            person=cls.staff_person,
            is_staff=True,
        )

    def setUp(self):
        super().setUp()
        self.url = reverse("members:troop_settings")
        self.client.login(email="staff-branding@test.com", password="testpass")

    def test_the_form_is_multipart_and_htmx_is_told_so(self):
        """The attributes a file upload needs, on the section form itself.

        Nothing else asserts these, and dropping either one does not raise: the
        file fields simply come back empty and the image is silently not saved.
        ``hx-encoding`` is the one HTMX needs; ``enctype`` is what a
        non-JavaScript post uses.
        """
        response = self.client.get(self.url)

        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'hx-encoding="multipart/form-data"')

    def test_uploading_a_logo_stores_it_on_the_settings_row(self):
        response = self.client.post(
            self.url,
            {
                "section": "organisation",
                "name": "Scouts de Test",
                "logo": an_image(),
                "favicon": an_image("icon.png"),
            },
        )

        self.assertEqual(response.status_code, 302)
        troop = TroopSettings.get_settings()
        self.assertTrue(troop.logo)
        self.assertTrue(troop.favicon)
        self.assertTrue(troop.logo.storage.exists(troop.logo.name))

    def test_saving_the_section_without_a_file_keeps_the_logo(self):
        """The upload must survive an unrelated edit of the same section.

        A bound ModelForm that is not handed the files treats an unchanged
        upload as cleared, so this is the regression the view's request.FILES
        guards.
        """
        troop = TroopSettings.get_settings()
        troop.logo = an_image()
        troop.save()
        stored = troop.logo.name

        self.client.post(
            self.url,
            {"section": "organisation", "name": "Renamed", "logo": "", "favicon": ""},
        )

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name, "Renamed")
        self.assertTrue(troop.logo, "the logo was dropped by an unrelated save")
        self.assertEqual(troop.logo.name, stored)


class EmailLogoTest(TroopSettingsTestCase, MailTestCase):
    """The logo reaches the HTML bodies, at an absolute URL."""

    def test_every_canonical_body_opens_with_the_logo(self):
        for name, language, fields in email_templates.rows():
            self.assertTrue(
                fields["html_content"].startswith(email_templates.LOGO_HTML),
                f"{name}/{language}",
            )

    def test_the_canonical_body_still_renders_with_the_troop_name(self):
        """The logo must not quietly displace the name these emails speak for."""
        rendered = (
            email_templates.with_logo("<p>{{ troop_name }}</p>")
            .replace("{{ logo_url }}", "/static/x.png")
            .replace("{{ troop_name }}", "Unit Test")
        )

        self.assertNotIn("{{", rendered)
        self.assertIn("Unit Test", rendered)

    def test_a_sent_email_carries_an_absolute_logo_url(self):
        send_templated(
            recipients=["staff@example.org"],
            template="new_child_staff",
            language="fr",
            context={"first_name": "Ana", "last_name": "Dupont", "url": "/x"},
        )

        email = Email.objects.latest("created")

        self.assertIn(f"/static/{DEFAULT_LOGO}", email.html_message)
        # Absolute, because a mail client has no page to resolve it against.
        self.assertIn(absolute_url(f"/static/{DEFAULT_LOGO}"), email.html_message)

    def test_the_logo_is_the_troops_own_once_it_has_one(self):
        troop = TroopSettings.get_settings()
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                troop.logo = an_image()
                troop.save()
                troop_url = troop.logo_url()

                send_templated(
                    recipients=["staff@example.org"],
                    template="new_child_staff",
                    language="fr",
                    context={"first_name": "Ana", "last_name": "Dupont", "url": "/x"},
                )

        self.assertIn(troop_url, Email.objects.latest("created").html_message)


class HistoricalModelMixin:
    """Exercise a migration the way ``migrate`` actually calls it.

    A migration never sees the model the application imported. It gets one
    rebuilt from the recorded migration state, and ``save()`` on that class
    sends ``post_save`` with a *different* sender — so every receiver the app
    connected is skipped. Calling a migration function with ``django.apps.apps``
    hands it the real model instead, which fires those receivers and does the
    invalidation the migration is supposed to do itself. A test written that way
    passes whether or not the migration does anything.

    Disconnecting the receivers is what puts the condition back.
    """

    def without_settings_cache_receiver(self):
        post_save.disconnect(_invalidate_troop_settings_cache, sender=TroopSettings)
        post_delete.disconnect(_invalidate_troop_settings_cache, sender=TroopSettings)
        self.addCleanup(
            post_save.connect,
            _invalidate_troop_settings_cache,
            sender=TroopSettings,
        )
        self.addCleanup(
            post_delete.connect,
            _invalidate_troop_settings_cache,
            sender=TroopSettings,
        )

    def without_template_cache_receiver(self):
        post_save.disconnect(
            forget_template,
            sender=EmailTemplate,
            dispatch_uid=TEMPLATE_CACHE_UID,
        )
        self.addCleanup(
            post_save.connect,
            forget_template,
            sender=EmailTemplate,
            dispatch_uid=TEMPLATE_CACHE_UID,
        )


class EmailLogoMigrationTest(HistoricalModelMixin, TroopSettingsTestCase):
    """The migration that adds the logo to bodies already in the database.

    It may only touch a body that still reads exactly as this project wrote it.
    Sending ``seed(force=True)`` would have been simpler and would have thrown
    away the wording of a troop that had rewritten one of these emails.
    """

    def body(self, name="new_child_staff", language="fr"):
        return EmailTemplate.objects.get(name=name, language=language).html_content

    def an_older_database(self, name="new_child_staff", language="fr"):
        """Put the row back the way it was before the logo existed.

        A database migrated from scratch already has the logo — 0021 seeds the
        current copy — so the only way to reach the state this migration is for
        is to take it off again first.
        """
        EmailTemplate.objects.filter(name=name, language=language).update(
            html_content=email_templates.without_logo(self.body(name, language))
        )

    def test_an_untouched_body_gains_the_logo(self):
        self.an_older_database()
        before = self.body()
        self.assertFalse(before.startswith(email_templates.LOGO_HTML))

        BODY_MIGRATION.add_logo_to_bodies(django_apps, None)

        self.assertEqual(self.body(), email_templates.with_logo(before))

    def test_the_body_the_next_send_uses_is_the_new_one(self):
        """The migration writes behind a cache, and so has to drop it.

        post_office caches each body under ``name:language``, and the fix in
        ``troopconnect.postoffice`` hangs off ``EmailTemplate``'s post_save
        signal — which a migration's historical model does not send. Reading
        through the same cached lookup a send uses is the only way to see it.
        """
        self.without_template_cache_receiver()
        self.an_older_database()
        row = EmailTemplate.objects.get(name="new_child_staff", language="fr")
        get_email_template("new_child_staff", language="fr")  # fill the cache

        cached = template_cache.get(cache_token(row))
        self.assertIsNotNone(cached, "the template cache is off; this proves nothing")
        self.assertFalse(cached.html_content.startswith(email_templates.LOGO_HTML))

        BODY_MIGRATION.add_logo_to_bodies(django_apps, None)

        rendered = get_email_template("new_child_staff", language="fr").html_content
        self.assertTrue(rendered.startswith(email_templates.LOGO_HTML))

    def test_a_rewritten_body_is_left_alone(self):
        EmailTemplate.objects.filter(name="new_child_staff", language="fr").update(
            html_content="<p>Notre propre texte.</p>"
        )

        BODY_MIGRATION.add_logo_to_bodies(django_apps, None)

        self.assertEqual(self.body(), "<p>Notre propre texte.</p>")

    def test_a_body_that_keeps_the_copy_but_edits_it_is_left_alone(self):
        """An edit that leaves the rest of the body alone is still an edit."""
        self.an_older_database()
        EmailTemplate.objects.filter(name="new_child_staff", language="fr").update(
            html_content=self.body().replace("Bonjour", "Bonjour à tous")
        )

        BODY_MIGRATION.add_logo_to_bodies(django_apps, None)

        self.assertNotIn(email_templates.LOGO_HTML, self.body())

    def test_it_can_be_undone(self):
        self.an_older_database()
        before = self.body()

        BODY_MIGRATION.add_logo_to_bodies(django_apps, None)
        self.assertTrue(self.body().startswith(email_templates.LOGO_HTML))

        BODY_MIGRATION.remove_logo_from_bodies(django_apps, None)

        self.assertEqual(self.body(), before)


class SeedTroopLogoMigrationTest(HistoricalModelMixin, MediaRootTestCase):
    """The migration that gives an instance already in use the logo it showed.

    "Already in use" is what the migration keys on: a database holding no
    member yet is a fresh install, and has no logo to preserve.
    """

    def an_existing_deployment(self):
        """One member is all it takes for the database to have been in use."""
        Person.objects.create(
            first_name="Ada",
            last_name="Member",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )

    def test_an_instance_in_use_takes_its_logo_from_the_bundled_mark(self):
        self.an_existing_deployment()
        self.assertFalse(TroopSettings.get_settings().logo)

        LOGO_MIGRATION.seed_logo(django_apps, None)

        troop = TroopSettings.get_settings()
        self.assertTrue(troop.logo, "the existing instance lost its logo")
        self.assertTrue(troop.logo.storage.exists(troop.logo.name))
        # Same image, served from the troop's own storage rather than the app's.
        self.assertTrue(troop.logo_url().startswith("/media/troop/"))

    def test_the_next_read_sees_the_logo_it_stored(self):
        """The migration writes behind a cache, and so has to drop it.

        ``get_settings`` serves a cached row with **no expiry**, kept in Redis,
        which outlives the deploy. Without an explicit invalidation the instance
        goes on serving the row it cached before the migration: the header keeps
        showing the static fallback and the settings page offers an empty logo
        field over a row that has one.
        """
        self.without_settings_cache_receiver()
        self.an_existing_deployment()
        self.assertFalse(TroopSettings.get_settings().logo)  # fills the cache

        LOGO_MIGRATION.seed_logo(django_apps, None)

        self.assertTrue(TroopSettings.get_settings().logo)

    def test_undoing_it_is_visible_on_the_next_read_too(self):
        self.without_settings_cache_receiver()
        self.an_existing_deployment()
        LOGO_MIGRATION.seed_logo(django_apps, None)
        self.assertTrue(TroopSettings.get_settings().logo)

        LOGO_MIGRATION.clear_logo(django_apps, None)

        self.assertFalse(TroopSettings.get_settings().logo)

    def test_a_fresh_install_is_left_on_the_fallback(self):
        """No member means nothing was showing a logo worth keeping."""
        LOGO_MIGRATION.seed_logo(django_apps, None)

        self.assertFalse(TroopSettings.get_settings().logo)

    def test_it_leaves_a_logo_the_troop_chose_alone(self):
        self.an_existing_deployment()
        troop = TroopSettings.get_settings()
        troop.logo = an_image("chosen.png")
        troop.save()
        chosen = troop.logo.name

        LOGO_MIGRATION.seed_logo(django_apps, None)

        self.assertEqual(TroopSettings.get_settings().logo.name, chosen)

    def test_it_is_reversible(self):
        self.an_existing_deployment()
        LOGO_MIGRATION.seed_logo(django_apps, None)
        troop = TroopSettings.get_settings()
        name, storage = troop.logo.name, troop.logo.storage

        LOGO_MIGRATION.clear_logo(django_apps, None)

        self.assertFalse(TroopSettings.get_settings().logo)
        self.assertFalse(storage.exists(name))

    def test_undo_leaves_a_logo_the_troop_uploaded_alone(self):
        self.an_existing_deployment()
        troop = TroopSettings.get_settings()
        troop.logo = an_image("chosen.png")
        troop.save()
        chosen = troop.logo.name

        LOGO_MIGRATION.clear_logo(django_apps, None)

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.logo.name, chosen)
        self.assertTrue(troop.logo.storage.exists(chosen))
