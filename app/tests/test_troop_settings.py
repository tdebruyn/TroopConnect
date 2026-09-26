"""TroopSettings: the staff page, and the settings it feeds.

The model holds what a troop edits in the browser — its name, the languages it
offers, the dates its scout year runs on. These tests cover the page that edits
it, and the places the values have to actually reach: the language switcher, the
phone fields, the money display and the mail pipeline.
"""

from decimal import Decimal

from django.template import Context, Template
from django.urls import reverse
from django.utils.translation import gettext as _
from post_office.models import Email

from members.models import Account, Person, Role, TroopSettings
from members.money import format_money
from members.phone import troop_region

from .base import TroopSettingsTestCase
from .mail import MailTestCase


class StaffPageTestBase(TroopSettingsTestCase):
    """A staff account, for the page that is staff-only.

    ``is_staff`` is what the page gates on; the primary role is a real one
    because a Person's role has to be primary, not one of the "ad"/"t" codes
    (those are secondary roles, attached separately).
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff_person = Person.objects.create(
            first_name="Ada", last_name="Staff",
            primary_role=Role.objects.get(short="p"), status="a",
        )
        Account.objects.create_user(
            email="staff@test.com", password="testpass",
            person=cls.staff_person, is_staff=True,
        )

    def login_staff(self):
        self.client.login(email="staff@test.com", password="testpass")


class SettingsPageTest(StaffPageTestBase):
    """The staff-only settings page."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.parent_person = Person.objects.create(
            first_name="Paul", last_name="Parent",
            primary_role=Role.objects.get(short="p"), status="a",
        )
        Account.objects.create_user(
            email="parent@test.com", password="testpass",
            person=cls.parent_person,
        )

    def setUp(self):
        super().setUp()
        self.url = reverse("members:troop_settings")

    def test_anonymous_visitor_is_sent_to_the_login_page(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('account_login')}?next={self.url}"
        )

    def test_a_non_staff_member_is_refused(self):
        self.client.login(email="parent@test.com", password="testpass")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_staff_see_every_section(self):
        self.login_staff()
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        keys = [section["key"] for section in response.context["sections"]]
        self.assertEqual(keys, ["organisation", "locale", "calendar", "modules"])

    def test_saving_organisation_persists_and_redirects(self):
        self.login_staff()
        response = self.client.post(
            self.url,
            {
                "section": "organisation",
                "name": "Scouts de Limal",
                "short_name": "SDL",
                "federation": "Les Scouts ASBL",
                "contact_email": "hello@limal.be",
                "reply_to_email": "secretariat@limal.be",
                "contact_phone": "010 12 34 56",
                "footer_address": "Rue de l'Église 1, 1348 Louvain-la-Neuve",
                "privacy_policy": "https://limal.be/privacy",
            },
        )

        self.assertRedirects(response, self.url)
        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name, "Scouts de Limal")
        self.assertEqual(troop.reply_to_email, "secretariat@limal.be")
        self.assertEqual(troop.footer_address, "Rue de l'Église 1, 1348 Louvain-la-Neuve")
        self.assertEqual(troop.privacy_policy_url(), "https://limal.be/privacy")

    def test_htmx_save_returns_only_that_section(self):
        self.login_staff()
        response = self.client.post(
            self.url,
            {
                "section": "modules",
                "fees_enabled": "on",
                "agenda_enabled": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        # The section card, not a whole page: no <html>, and the confirmation.
        # The strings are asserted through gettext so the test reads the same
        # regardless of the language the suite happens to run in.
        self.assertNotContains(response, "<html")
        self.assertContains(response, _("Saved."))
        self.assertContains(response, 'id="settings-modules"')

        troop = TroopSettings.get_settings()
        self.assertTrue(troop.fees_enabled)
        self.assertFalse(troop.signing_enabled)

    def test_htmx_error_comes_back_inside_the_section(self):
        """A rejected save has to leave the section on screen, with the error."""
        self.login_staff()
        response = self.client.post(
            self.url,
            {
                "section": "locale",
                "enabled_languages": ["fr", "nl"],
                "default_language": "en",  # not among the enabled ones
                "phone_region": "BE",
                "currency": "EUR",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="settings-locale"')
        # The dropdown only offers the enabled languages, so a default outside
        # them is rejected as an invalid choice before clean() ever sees it.
        self.assertContains(response, 'aria-invalid="true"')
        self.assertEqual(TroopSettings.get_settings().default_language, "fr")

    def test_at_least_one_language_has_to_stay_enabled(self):
        self.login_staff()
        response = self.client.post(
            self.url,
            {
                "section": "locale",
                "enabled_languages": [],
                "default_language": "fr",
                "phone_region": "BE",
                "currency": "EUR",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, _("Select at least one available language."))
        self.assertEqual(TroopSettings.get_settings().enabled_languages, ["fr"])

    def test_an_unknown_section_is_a_bad_request(self):
        self.login_staff()
        response = self.client.post(self.url, {"section": "nonsense"})
        self.assertEqual(response.status_code, 400)

    def test_language_switcher_follows_the_enabled_languages(self):
        """The selector offers the languages the troop enabled, not the shipped set."""
        self.login_staff()
        self.client.post(
            self.url,
            {
                "section": "locale",
                "enabled_languages": ["fr", "nl"],
                "default_language": "fr",
                "phone_region": "BE",
                "currency": "EUR",
            },
        )

        response = self.client.get(reverse("homepage"))
        self.assertEqual(sorted(response.context["available_languages"]), ["fr", "nl"])
        self.assertTrue(response.context["show_language_selector"])


class MoneyDisplayTest(TroopSettingsTestCase):
    """Amounts are shown in the troop's currency."""

    def test_the_default_is_the_euro(self):
        self.assertEqual(format_money(Decimal("12.50")), "12.50€")

    def test_a_configured_currency_replaces_the_symbol(self):
        troop = TroopSettings.get_settings()
        troop.currency = "USD"
        troop.save()

        self.assertEqual(format_money(Decimal("12.50")), "12.50$")

    def test_a_currency_without_a_symbol_is_written_as_its_code(self):
        troop = TroopSettings.get_settings()
        troop.currency = "SEK"
        troop.save()

        self.assertEqual(format_money(Decimal("12.50")), "12.50 SEK")

    def test_a_code_is_normalised_to_upper_case(self):
        troop = TroopSettings.get_settings()
        troop.currency = "usd"
        troop.save()
        troop.refresh_from_db()

        self.assertEqual(troop.currency, "USD")

    def test_no_amount_renders_nothing(self):
        self.assertEqual(format_money(None), "")

    def test_the_template_filter_is_wired(self):
        rendered = Template("{% load money %}{{ amount|money }}").render(
            Context({"amount": Decimal("3.00")})
        )
        self.assertEqual(rendered, "3.00€")


class PhoneRegionTest(TroopSettingsTestCase):
    """Phone numbers are read in the troop's country."""

    def setUp(self):
        super().setUp()
        self.field = Person._meta.get_field("phone")

    def test_the_configured_region_is_used(self):
        self.assertEqual(troop_region(), "BE")
        self.assertEqual(self.field.region, "BE")

    def test_changing_the_setting_changes_the_region(self):
        troop = TroopSettings.get_settings()
        troop.phone_region = "nl"
        troop.save()

        self.assertEqual(troop_region(), "NL")

    def test_a_national_number_is_stored_in_international_form(self):
        """What the region is actually for: reading "0475 12 34 56" as Belgian."""
        person = Person(first_name="Ana", last_name="Dupont")
        person.phone = "0475123456"

        self.assertEqual(str(person.phone), "+32475123456")


class TroopSettingsMailTest(TroopSettingsTestCase, MailTestCase):
    """Outgoing mail speaks for the troop, in the recipient's language."""

    def name_the_troop(self, fr, nl, en):
        troop = TroopSettings.get_settings()
        troop.name_fr, troop.name_nl, troop.name_en = fr, nl, en
        troop.save()

    def test_the_name_follows_the_recipient_language(self):
        """Not the sender's: a Dutch family must not get the French name."""
        self.name_the_troop("Scouts de Limal", "Scouts van Limal", "Limal Scouts")

        from members.mail import send_templated

        send_templated(
            recipients=["ouder@example.org"],
            template="new_child_parent",
            language="nl",
            context={"parent": "Jan", "first_name": "Ana", "last_name": "Dupont"},
        )

        email = Email.objects.latest("created")
        self.assertIn("Scouts van Limal", email.message)
        self.assertNotIn("Scouts de Limal", email.message)

    def test_a_reply_to_address_becomes_a_header(self):
        from members.mail import send_templated

        troop = TroopSettings.get_settings()
        troop.reply_to_email = "secretariat@limal.be"
        troop.save()

        send_templated(
            recipients=["parent@example.org"],
            template="new_child_parent",
            language="fr",
            context={"parent": "Jan", "first_name": "Ana", "last_name": "Dupont"},
        )

        self.assertEqual(
            Email.objects.latest("created").headers["Reply-To"],
            "secretariat@limal.be",
        )

    def test_no_reply_to_header_without_a_reply_to_address(self):
        from members.mail import send_templated

        send_templated(
            recipients=["parent@example.org"],
            template="new_child_parent",
            language="fr",
            context={"parent": "Jan", "first_name": "Ana", "last_name": "Dupont"},
        )

        headers = Email.objects.latest("created").headers
        self.assertNotIn("Reply-To", headers or {})


class ModuleSwitchesTest(StaffPageTestBase):
    """Turning a module off takes it out of the navigation."""

    def test_the_agenda_entry_is_there_by_default(self):
        self.login_staff()
        self.assertContains(
            self.client.get(reverse("homepage")), reverse("members:agenda")
        )

    def test_the_agenda_entry_disappears_when_the_module_is_off(self):
        troop = TroopSettings.get_settings()
        troop.agenda_enabled = False
        troop.save()

        self.login_staff()
        response = self.client.get(reverse("homepage"))

        self.assertNotContains(response, reverse("members:agenda"))
        self.assertFalse(response.context["agenda_enabled"])

    def test_the_attestations_entry_disappears_when_the_module_is_off(self):
        troop = TroopSettings.get_settings()
        troop.signing_enabled = False
        troop.save()

        # The entry lives in the Administration dropdown, which staff can open.
        self.login_staff()
        response = self.client.get(reverse("homepage"))

        self.assertNotContains(response, reverse("attestations:index"))
