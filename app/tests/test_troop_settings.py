"""TroopSettings: the staff page, and the settings it feeds.

The model holds what a troop edits in the browser — its name, the languages it
offers, the dates its scout year runs on. These tests cover the page that edits
it, and the places the values have to actually reach: the language switcher, the
phone fields, the money display and the mail pipeline.
"""

from datetime import date
from decimal import Decimal

from django.template import Context, Template
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext as _
from post_office.models import Email

from homepage.models import TimelineActivity
from members.models import Account, Person, Role, TroopSettings
from members.money import format_money
from members.phone import troop_region

from .base import TroopSettingsTestCase
from .mail import MailTestCase


class StaffPageTestBase(TroopSettingsTestCase):
    """A staff account, for the page that is staff-only.

    ``is_staff`` is what the page gates on; the primary role is a real one
    because a Person's role has to be primary, not one of the "ar"/"t" codes
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
        self.assertEqual(
            keys, ["organisation", "locale", "calendar", "public_page", "modules"]
        )

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
                "privacy_policy": "https://limal.be/privacy",
            },
        )

        self.assertRedirects(response, self.url)
        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name, "Scouts de Limal")
        self.assertEqual(troop.reply_to_email, "secretariat@limal.be")
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


class PublicPageSettingsTest(StaffPageTestBase):
    """The public page's blocks, and the year-line's dates, in one card.

    The card is where a superuser composes what a visitor sees, so the tests
    read its switches, its words and its list as one save.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse("members:troop_settings")
        self.login_staff()

    def public_page_data(self, **overrides):
        """The card's formset management, plus whatever the test is changing.

        Every save of this section has to carry the management form: the
        formset decides how many rows it was given from these counts, and a
        card posted without them silently looks empty.
        """
        data = {
            "section": "public_page",
            "site_description": "Bienvenue chez les Scouts.",
            "activities-TOTAL_FORMS": "0",
            "activities-INITIAL_FORMS": "0",
            "activities-MIN_NUM_FORMS": "0",
            "activities-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def test_the_card_saves_the_blocks_words_and_place(self):
        response = self.client.post(
            self.url,
            self.public_page_data(
                homepage_band_enabled="on",
                homepage_desk_enabled="on",
                homepage_place_enabled="on",
                homepage_about_enabled="on",
                homepage_about_text="Notre unité, en deux paragraphes.",
                homepage_faq_enabled="on",
                homepage_faq_text="Une question ?\nUne réponse.",
                footer_address="Rue de l'Église 1\n1348 Louvain-la-Neuve",
                meeting_place="La ferme",
            ),
        )

        self.assertRedirects(response, self.url)
        troop = TroopSettings.get_settings()
        self.assertTrue(troop.homepage_about_enabled)
        self.assertEqual(troop.homepage_about_text, "Notre unité, en deux paragraphes.")
        self.assertEqual(troop.homepage_faq_text, "Une question ?\nUne réponse.")
        self.assertEqual(
            troop.footer_address, "Rue de l'Église 1\n1348 Louvain-la-Neuve"
        )
        self.assertEqual(troop.meeting_place, "La ferme")

    def test_a_content_module_cannot_be_turned_on_without_its_text(self):
        response = self.client.post(
            self.url,
            self.public_page_data(
                homepage_about_enabled="on",
                homepage_about_text="   ",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            escape(
                _("Write the text before turning %(module)s on.")
                % {"module": _("About us")}
            ),
        )
        self.assertFalse(TroopSettings.get_settings().homepage_about_enabled)

    def test_the_year_line_adds_a_date(self):
        response = self.client.post(
            self.url,
            self.public_page_data(
                **{
                    "activities-TOTAL_FORMS": "1",
                    "activities-0-id": "",
                    "activities-0-name": "Camps",
                    "activities-0-start_date": "2027-07-18",
                    "activities-0-end_date": "2027-07-25",
                }
            ),
        )

        self.assertRedirects(response, self.url)
        activity = TimelineActivity.objects.get()
        self.assertEqual(activity.start_date, date(2027, 7, 18))
        self.assertEqual(activity.end_date, date(2027, 7, 25))

    def test_the_year_line_removes_a_date(self):
        activity = TimelineActivity.objects.create(
            name="Inscription", start_date=date(2026, 9, 4)
        )
        response = self.client.post(
            self.url,
            self.public_page_data(
                **{
                    "activities-TOTAL_FORMS": "1",
                    "activities-INITIAL_FORMS": "1",
                    "activities-0-id": activity.pk,
                    "activities-0-name": "Inscription",
                    "activities-0-start_date": "2026-09-04",
                    "activities-0-DELETE": "on",
                }
            ),
        )

        self.assertRedirects(response, self.url)
        self.assertFalse(TimelineActivity.objects.exists())

    def test_a_date_outside_the_year_line_is_refused(self):
        response = self.client.post(
            self.url,
            self.public_page_data(
                **{
                    "activities-TOTAL_FORMS": "1",
                    "activities-0-id": "",
                    "activities-0-name": "Trop tard",
                    "activities-0-start_date": "2027-08-15",
                }
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            escape(
                _(
                    "The year-line runs from 1 September to 31 July. "
                    "Enter a date inside that window."
                )
            ),
        )
        self.assertFalse(TimelineActivity.objects.exists())

    def test_htmx_returns_the_composed_card(self):
        response = self.client.post(
            self.url,
            self.public_page_data(homepage_band_enabled="on"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, 'id="settings-public_page"')
        self.assertContains(response, "id_activities-TOTAL_FORMS")
        self.assertContains(response, _("Saved."))


class MoneyDisplayTest(TroopSettingsTestCase):
    """Amounts are shown in the troop's currency."""

    def test_the_default_is_the_euro(self):
        self.assertEqual(format_money(Decimal("12.50")), "12,50\u00a0€")

    def test_a_configured_currency_replaces_the_symbol(self):
        troop = TroopSettings.get_settings()
        troop.currency = "USD"
        troop.save()

        self.assertEqual(format_money(Decimal("12.50")), "12,50\u00a0$")

    def test_a_currency_without_a_symbol_is_written_as_its_code(self):
        troop = TroopSettings.get_settings()
        troop.currency = "SEK"
        troop.save()

        self.assertEqual(format_money(Decimal("12.50")), "12,50\u00a0SEK")

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
        self.assertEqual(rendered, "3,00\u00a0€")


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


class SiteFooterTest(TroopSettingsTestCase):
    """Where four settings that had no home finally reach a page.

    The address, the phone, the legal line and the social accounts were all
    editable — and all rendered by nothing — until the footer existed. This
    asserts the values arrive, not the sentences around them: the source
    strings are English while a French instance renders the catalogue.
    """

    def _troop(self, **fields):
        troop = TroopSettings.get_settings()
        for name, value in fields.items():
            setattr(troop, name, value)
        troop.save()
        return troop

    def test_it_carries_what_the_troop_stored(self):
        self._troop(
            name="Les Scouts de Limal",
            federation="Les Scouts Baden Powel de Belgique",
            footer_address="Rue Achille Bauduin 89\n1300 Limal",
            contact_email="contact@example.org",
            contact_phone="010 41 12 34",
        )

        response = self.client.get(reverse("homepage"))

        self.assertContains(response, "site-footer")
        self.assertContains(response, "Les Scouts de Limal")
        self.assertContains(response, "Les Scouts Baden Powel de Belgique")
        self.assertContains(response, "Rue Achille Bauduin 89")
        self.assertContains(response, "1300 Limal")
        self.assertContains(response, "contact@example.org")
        # Linked, and the number is bare inside the URI.
        self.assertContains(response, "tel:010411234")

    def test_the_legal_line_is_a_link_when_the_troop_stored_a_url(self):
        self._troop(privacy_policy="https://example.org/privacy")

        response = self.client.get(reverse("homepage"))

        self.assertContains(response, 'href="https://example.org/privacy"')
        self.assertNotContains(response, "footer-legal")

    def test_the_legal_line_is_the_words_when_the_troop_wrote_them(self):
        """The field holds a URL or a policy, and the footer shows whichever
        it was given rather than a link to nothing."""
        self._troop(privacy_policy="Nous ne gardons que ce qu'il faut.")

        response = self.client.get(reverse("homepage"))

        self.assertContains(response, "footer-legal")
        self.assertContains(response, "Nous ne gardons")
        self.assertNotContains(response, "Privacy policy")

    def test_social_accounts_appear_only_when_the_troop_has_them(self):
        self._troop(facebook_url="", instagram_url="")

        response = self.client.get(reverse("homepage"))

        self.assertNotContains(response, "facebook.com")
        self.assertNotContains(response, "Instagram")

    def test_it_is_on_pages_other_than_the_homepage(self):
        """A footer is the site's steady strip, so it is not per-page."""
        self._troop(contact_email="contact@example.org")

        response = self.client.get(reverse("unit_page"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "site-footer")
        self.assertContains(response, "contact@example.org")
