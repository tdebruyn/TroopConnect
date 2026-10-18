"""The two surfaces at ``/``: the public enrolment desk and the member page.

The assertions are on structure and on the troop's own data, never on
translated copy — the source strings are English while a French instance
renders the catalogue, so a test that matched a sentence would pass in one
language and fail in the others. The one exception pins the French catalogue
on purpose: the answer sentence carries markup, and that markup must not keep
the sentence out of the catalogue.
"""

from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.html import escape
from django.utils.translation import gettext as _

from finance.models import FeeRule
from homepage.models import TimelineActivity
from homepage.templatetags.homepage_content import faq_entries
from homepage.timeline import axis_for, timeline_for
from homepage.views import (
    _desk_groups,
    _desk_rows,
    _household_dues,
    _siblings_are_discounted,
)
from members.forms import PublicPageSettingsForm
from members.models import (
    Account,
    Branch,
    Enrollment,
    ImportantDocument,
    ParentChild,
    Person,
    Role,
    SchoolYear,
    Section,
    SectionEvent,
    TroopSettings,
)
from members.permissions import (
    ANIMATEUR_ROLES,
    ANIME,
    can_manage_unit,
    has_primary_role,
    visible_sections,
)
from tests.base import TroopSettingsTestCase
from tests.test_branding import MediaRootTestCase, an_image
from tests.test_finance import FinanceTestBase


class DeskTestBase(TroopSettingsTestCase):
    """Two branches with a gap between them, so a year can land in neither."""

    @classmethod
    def setUpTestData(cls):
        cls.school_year = SchoolYear.current()
        cls.reference_year = TroopSettings.get_settings().age_reference_date(
            cls.school_year
        ).year
        cls.baladins = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=8
        )
        cls.louveteaux = Branch.objects.create(
            name="Louveteaux", min_age_dec_31=9, max_age_dec_31=11
        )
        cls.section = Section.objects.create(name="Baladins 1", branch=cls.baladins)

    def year_in(self, branch):
        """A birth year that lands in ``branch`` for the current school year."""
        for year, candidate in _desk_rows(self.school_year):
            if candidate.pk == branch.pk:
                return year
        raise AssertionError("no birth year lands in that branch")


class DeskRowsTest(DeskTestBase):
    """The age range read backwards, which is the whole rule behind the desk."""

    def test_both_ages_a_branch_declares_are_ages_it_takes(self):
        """The bounds are inclusive, which is what `Person.age_fits_branch`
        and the passage task read them as — the desk cannot disagree with the
        enrolment logic about where a child belongs."""
        years = {year for year, branch in _desk_rows(self.school_year)
                 if branch.pk == self.baladins.pk}
        self.assertEqual(
            years,
            set(range(self.reference_year - 8, self.reference_year - 6 + 1)),
        )

    def test_the_rows_run_oldest_child_first(self):
        """``_desk_rows`` sorts ascending, which is the order the grouping
        below consumes and un-sorts again for the rail."""
        years = [year for year, _branch in _desk_rows(self.school_year)]
        self.assertEqual(years, sorted(years))
        self.assertEqual(
            years[0], self.reference_year - self.louveteaux.max_age_dec_31
        )
        self.assertEqual(years[-1], self.reference_year - self.baladins.min_age_dec_31)

    def test_each_branch_runs_its_youngest_year_to_its_oldest(self):
        """The rail draws a branch's years the way it draws the branches, so
        the line reads as one journey rather than restarting at every
        segment."""
        groups = _desk_groups(_desk_rows(self.school_year))
        for group in groups:
            years = group["years"]
            self.assertEqual(years, sorted(years, reverse=True), group["branch"].name)
        # Read across the segments it is then one descending run, which is the
        # point: each branch carries on where the one before it left off.
        line = [year for group in groups for year in group["years"]]
        self.assertEqual(line, sorted(line, reverse=True))

    def test_a_branch_without_ages_is_skipped(self):
        Branch.objects.create(name="Sans âges")
        self.assertNotIn(
            "Sans âges", {branch.name for _year, branch in _desk_rows(self.school_year)}
        )


class FederationMappingTest(TroopSettingsTestCase):
    """The birth years the shipped preset's branches cover, for 2026-2027.

    Pinned to the numbers the user gave: the Pionniers are born in 2009 and
    2010, the Baladins in 2019 and 2020.

    The ranges below are the *effective* ones the corrected database holds —
    6-7, 8-11, 12-15, 16-17 — not the ages the branches are advertised as. A
    branch whose maximum is an age it does not take hands that child to the
    next branch as well.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school_year = SchoolYear.current()
        cls.reference_year = TroopSettings.get_settings().age_reference_date(
            cls.school_year
        ).year
        for name, low, high in (
            ("Baladins", 6, 7),
            ("Louveteaux", 8, 11),
            ("Éclaireurs", 12, 15),
            ("Pionniers", 16, 17),
        ):
            Branch.objects.create(
                name=name,
                key=name.lower(),
                min_age_dec_31=low,
                max_age_dec_31=high,
            )

    def years_of(self, name):
        return sorted(
            year for year, branch in _desk_rows(self.school_year)
            if branch.name == name
        )

    def test_the_baladins_are_the_two_youngest_years(self):
        self.assertEqual(self.years_of("Baladins"), [self.reference_year - 7,
                                                     self.reference_year - 6])

    def test_the_pionniers_are_the_two_oldest_years(self):
        self.assertEqual(self.years_of("Pionniers"), [self.reference_year - 17,
                                                      self.reference_year - 16])

    def answer_for(self, year):
        from homepage.views import _desk_answer

        return _desk_answer(_desk_rows(self.school_year), str(year), self.school_year)

    def test_a_child_in_their_last_year_is_told_so(self):
        """Born 2015, they are 11 in 2026-2027 — the last Louveteaux year.

        This is the example the user gave when asking for the scout years.
        """
        answer = self.answer_for(2015)
        self.assertEqual(answer["branch"].name, "Louveteaux")
        self.assertEqual(answer["first_year"], "2026-2027")
        self.assertEqual(answer["last_year"], "2026-2027")
        self.assertTrue(answer["is_final_year"])

    def test_a_child_with_the_branch_ahead_of_them_gets_the_span(self):
        """Born 2020, the Baladins hold ages 6 and 7, so two scout years."""
        answer = self.answer_for(2020)
        self.assertEqual(answer["branch"].name, "Baladins")
        self.assertEqual(answer["first_year"], "2026-2027")
        self.assertEqual(answer["last_year"], "2027-2028")
        self.assertFalse(answer["is_final_year"])

    def test_years_already_behind_the_child_are_not_shown(self):
        """A parent is asking where to register, not where they would have been."""
        answer = self.answer_for(2018)
        self.assertEqual(answer["branch"].name, "Louveteaux")
        self.assertEqual(answer["first_year"], "2026-2027", "not 2023-2024")

    def test_the_desk_agrees_with_the_apps_own_branch_check(self):
        """Every year the desk gives a branch must be an age that branch takes.

        The desk and `Person.age_fits_branch` read the same two columns, and
        they disagreed only while a branch's maximum was an age it did not
        take. Checked at three birthdays a year, because the age is measured on
        the troop's reference day and a January child is not a December one.
        """
        role = Role.objects.get(short="e")
        settings = TroopSettings.get_settings()
        for year, branch in _desk_rows(self.school_year):
            for month, day in ((1, 15), (6, 15), (12, 15)):
                age = settings.age_at_reference(
                    Person(
                        first_name="x", last_name="y", primary_role=role,
                        status="a", birthday=date(year, month, day),
                    ),
                    self.school_year,
                )
                with self.subTest(year=year, birthday=f"{month:02d}-{day:02d}"):
                    self.assertTrue(
                        branch.min_age_dec_31 <= age <= branch.max_age_dec_31,
                        f"{year} -> {branch.name}, but the child is {age} and "
                        f"that branch takes {branch.min_age_dec_31} to "
                        f"{branch.max_age_dec_31}",
                    )

    def test_every_year_lands_in_exactly_one_branch(self):
        """No gaps and no overlaps, which is the whole point of the rule."""
        rows = _desk_rows(self.school_year)
        self.assertEqual(
            [year for year, _ in rows],
            list(range(self.reference_year - 17, self.reference_year - 6 + 1)),
        )


class PublicPageModulesTest(TroopSettingsTestCase):
    """The blocks a troop composes on the public page card.

    Each switch is read by the page rather than by a template tag of its own,
    so the tests assert the rendered page, not the stored flag.
    """

    def set_troop(self, **fields):
        troop = TroopSettings.get_settings()
        for name, value in fields.items():
            setattr(troop, name, value)
        troop.save()
        return troop

    def test_the_band_can_be_turned_off(self):
        self.set_troop(homepage_band_enabled=False)

        response = self.client.get("/")

        self.assertNotContains(response, 'class="masthead"')
        # The page still names itself for a screen reader: the band is its h1.
        self.assertContains(response, "visually-hidden")

    def test_the_desk_and_the_place_can_be_turned_off(self):
        self.set_troop(
            homepage_desk_enabled=False,
            homepage_place_enabled=False,
            meeting_place="La ferme",
            footer_address="Rue Achille Bauduin 89\n1300 Limal",
        )

        response = self.client.get("/")

        self.assertNotContains(response, "desk-question")
        self.assertNotContains(response, "place-eyebrow")

    def test_the_place_can_be_turned_off_on_its_own(self):
        self.set_troop(
            meeting_place="La ferme",
            footer_address="Rue Achille Bauduin 89\n1300 Limal",
        )
        self.assertContains(self.client.get("/"), "place-eyebrow")

        self.set_troop(homepage_place_enabled=False)
        self.assertNotContains(self.client.get("/"), "place-eyebrow")

    def test_about_and_faq_render_their_plain_text(self):
        self.set_troop(
            homepage_about_enabled=True,
            homepage_about_text="Un paragraphe.\n\nUn deuxième.",
            homepage_faq_enabled=True,
            homepage_faq_text="Comment ?\nComme ceci.\n\nQuand ?\nLe samedi.",
        )

        response = self.client.get("/")

        self.assertContains(response, "note-sheet")
        self.assertContains(response, "Un paragraphe.")
        self.assertContains(response, "Un deuxième.")
        self.assertContains(response, "Comment ?")
        self.assertContains(response, "Comme ceci.")
        self.assertContains(response, _("Frequently asked questions"))

    def test_a_content_module_with_no_text_is_left_out(self):
        self.set_troop(homepage_about_enabled=True, homepage_about_text="")

        response = self.client.get("/")

        self.assertNotContains(response, "note-sheet")
        self.assertNotContains(response, _("About us"))

    def test_closed_modules_make_no_notes_band(self):
        response = self.client.get("/")

        self.assertNotContains(response, 'class="notes"')

    def test_the_units_own_page_carries_the_content_blocks(self):
        self.set_troop(
            homepage_about_enabled=True,
            homepage_about_text="Notre unité.",
        )

        response = self.client.get(reverse("unit_page"))

        self.assertContains(response, "note-sheet")
        self.assertContains(response, "Notre unité.")

    def test_faq_blocks_split_into_a_question_and_its_answer(self):
        self.assertEqual(
            faq_entries("Question ?\nRéponse.\nSuite.\n\nSeule ?"),
            [
                {"question": "Question ?", "answer": "Réponse.\nSuite."},
                {"question": "Seule ?", "answer": ""},
            ],
        )

    def test_faq_text_with_windows_newlines_still_splits(self):
        self.assertEqual(
            [entry["question"] for entry in faq_entries("Une ?\r\nOui.\r\n\r\nDeux ?")],
            ["Une ?", "Deux ?"],
        )


class PublicHomepageTest(DeskTestBase):
    def test_a_visitor_gets_the_desk_and_the_troops_own_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "desk-question")
        self.assertContains(response, "desk-year")

    def test_picking_a_year_names_that_branch(self):
        year = self.year_in(self.louveteaux)
        response = self.client.get("/", {"annee": year})
        self.assertContains(response, "desk-answer-title")
        self.assertContains(response, "Louveteaux")

    def test_the_answer_sentence_comes_from_the_catalogue(self):
        """The branch name rides inside the translated sentence.

        Markup in a `blocktranslate` changes its msgid, so a span around the
        branch silently took the sentence out of the catalogue; the name was
        also missing from the `with` clause and rendered as a gap.
        """
        year = self.year_in(self.louveteaux)
        with translation.override("fr"):
            response = self.client.get("/", {"annee": year})
        self.assertContains(
            response,
            'Votre enfant rejoindrait la branche <span class="desk-answer-name">'
            "Louveteaux</span>",
        )

    def test_the_answer_reads_with_a_renamed_branch(self):
        """The sentence must not assume the preset's plural branch names.

        A troop can rename a branch to anything, and "les Meute" is the kind
        of grammar a preset cannot promise; the construction names the branch
        without giving it an article of its own.
        """
        Branch.objects.create(
            name="Meute", key="louveteaux", min_age_dec_31=8, max_age_dec_31=12
        )
        with translation.override("fr"):
            response = self.client.get("/", {"annee": self.reference_year - 12})
        self.assertContains(
            response,
            'la branche <span class="desk-answer-name">Meute</span>',
        )

    def test_the_answer_carries_the_branch_topping(self):
        """The coloured tile, keyed by the preset slug like the colour is."""
        Branch.objects.create(
            name="Meute", key="louveteaux", min_age_dec_31=8, max_age_dec_31=12
        )
        response = self.client.get("/", {"annee": self.reference_year - 12})
        self.assertContains(response, "topping_Louveteaux_vert_100.png")


    def test_the_chosen_year_is_marked(self):
        year = self.year_in(self.baladins)
        response = self.client.get("/", {"annee": year})
        self.assertContains(response, "desk-year-on")

    def test_the_answer_carries_the_branch_colour(self):
        """The page's one spend of colour, keyed on the preset slug.

        A troop renames its branches, so the colour follows the slug the
        preset wrote rather than the name the troop chose.
        """
        Branch.objects.create(
            name="Meute", key="louveteaux", min_age_dec_31=8, max_age_dec_31=12
        )
        # Age 12 is only this branch's: the fixture's Baladins stops at 8 and
        # its Louveteaux start at 9, so no overlap can decide the answer.
        response = self.client.get("/", {"annee": self.reference_year - 12})
        self.assertContains(response, "Meute")
        self.assertContains(response, "--branch: #296f52")

    def test_a_branch_no_preset_made_carries_no_colour_rule(self):
        """Rather than a fallback in the page's own ink, which would look like
        a branch colour and mean nothing. The fixture's branches have no key."""
        response = self.client.get("/", {"annee": self.year_in(self.baladins)})
        self.assertNotContains(response, "--branch")
        self.assertNotContains(response, "desk-answer-branch")

    def test_an_unknown_slug_is_also_no_colour(self):
        Branch.objects.create(
            name="Maison", key="maison", min_age_dec_31=8, max_age_dec_31=12
        )
        response = self.client.get("/", {"annee": self.reference_year - 12})
        self.assertContains(response, "Maison")
        self.assertNotContains(response, "--branch")

    def test_a_year_in_no_branch_says_so_instead_of_guessing(self):
        """Told, not silently re-asked with the year still in the URL.

        The unanswered desk and a year that fits nowhere are different states
        and say different things; the page used to render the first for both.
        """
        response = self.client.get("/", {"annee": 1900})
        self.assertContains(response, "desk-answer-quiet")
        self.assertContains(response, "1900")
        self.assertNotContains(response, "desk-answer-branch")

    def test_nonsense_in_the_query_string_is_not_a_crash(self):
        for value in ("abc", "-1", "", "2018.5"):
            with self.subTest(value=value):
                self.assertEqual(self.client.get("/", {"annee": value}).status_code, 200)

    def test_htmx_gets_the_answer_alone(self):
        """The swap replaces one element, so the fragment must not carry a page."""
        year = self.year_in(self.baladins)
        response = self.client.get(
            "/", {"annee": year}, headers={"HX-Request": "true"}
        )
        self.assertContains(response, "desk-answer")
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "desk-question")

    def test_closed_registrations_hide_the_action_and_say_why(self):
        settings_row = TroopSettings.get_settings()
        settings_row.registration_open = False
        settings_row.registration_message = "Les inscriptions rouvrent en août."
        settings_row.save()

        response = self.client.get("/", {"annee": self.year_in(self.baladins)})
        self.assertNotContains(response, "desk-cta")
        self.assertContains(response, "Les inscriptions rouvrent en août.")

    def test_each_branch_gets_its_own_card_of_years(self):
        """The grouping that replaced the flat year row: the branch names the
        card and its age range is the way in."""
        response = self.client.get("/")
        self.assertEqual(response.content.count(b'class="desk-years"'), 2)

    def test_the_way_in_is_there_before_anything_is_picked(self):
        """The page's one action does not wait on the desk's question.

        A parent who arrived to register should not have to answer it first —
        and the region that carries the answer carries the action on both of
        its states.
        """
        response = self.client.get("/")
        self.assertContains(response, "desk-answer-quiet")
        self.assertContains(response, "desk-cta")

    def test_the_action_carries_the_year_it_was_given(self):
        """So the branch a parent has just found is not asked for again on the
        other side of the sign-up."""
        year = self.year_in(self.louveteaux)
        response = self.client.get("/", {"annee": year})
        self.assertContains(response, f"{reverse('account_signup')}?annee={year}")

    def test_the_units_own_page_is_public_and_carries_the_desk(self):
        """`/unite/` is the public page for everyone, a signed-in reader
        included, so it carries the same visitor's half as an anonymous `/`."""
        response = self.client.get("/unite/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "desk-question")

    def test_the_unit_page_swaps_the_desk_answer_like_the_homepage(self):
        """The desk's year links are relative, so without the partial the
        whole page would be swapped into the answer region."""
        year = self.year_in(self.louveteaux)

        response = self.client.get(
            reverse("unit_page"), {"annee": year}, HTTP_HX_REQUEST="true"
        )

        self.assertNotContains(response, "<html")
        self.assertContains(response, f"{reverse('account_signup')}?annee={year}")


class TimelineTest(TroopSettingsTestCase):
    """The year-line is drawn from dates, not from markup someone typed.

    The current school year is whatever the test run's date makes it; the
    assertions derive their expected fractions from that axis so the tests do
    not rot when the calendar moves.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school_year = SchoolYear.current()
        year = cls.school_year.name
        cls.inscription = TimelineActivity.objects.create(
            name="Inscription", name_fr="Inscription",
            start_date=date(year, 9, 5),
        )
        cls.passage = TimelineActivity.objects.create(
            name="Passage", name_fr="Passage",
            start_date=date(year, 9, 19),
        )
        cls.veillee = TimelineActivity.objects.create(
            name="Veillée de Noël", name_fr="Veillée de Noël",
            start_date=date(year, 12, 12),
        )
        cls.fete = TimelineActivity.objects.create(
            name="Fête d'unité", name_fr="Fête d'unité",
            start_date=date(year + 1, 4, 3),
        )
        cls.camps = TimelineActivity.objects.create(
            name="Camps", name_fr="Camps",
            start_date=date(year + 1, 7, 18),
            end_date=date(year + 1, 7, 25),
        )

    def timeline(self):
        with translation.override("fr"):
            return timeline_for(self.school_year)

    def events_by_name(self):
        return {event["name"]: event for event in self.timeline()["events"]}

    def test_a_date_is_placed_by_its_day_fraction(self):
        axis_start, axis_end = axis_for(self.inscription.start_date)
        total = (axis_end - axis_start).days
        expected = (self.inscription.start_date - axis_start).days / total * 100
        self.assertAlmostEqual(
            self.events_by_name()["Inscription"]["at"], expected, places=2
        )

    def test_a_multiday_activity_is_an_inclusive_span(self):
        axis_start, axis_end = axis_for(self.camps.start_date)
        total = (axis_end - axis_start).days
        camps = self.events_by_name()["Camps"]
        self.assertTrue(camps["is_range"])
        self.assertAlmostEqual(
            camps["width"], 8 / total * 100, places=2
        )  # the 18th through the 25th

    def test_month_ticks_sit_on_the_first_of_the_month(self):
        months = self.timeline()["months"]
        axis_start, axis_end = axis_for(self.inscription.start_date)
        total = (axis_end - axis_start).days
        year = self.school_year.name
        self.assertEqual([month["label"] for month in months], [
            "sept", "oct", "nov", "déc", "janv", "févr",
            "mars", "avr", "mai", "juin", "juil",
        ])
        self.assertEqual(months[0]["at"], 0)
        self.assertAlmostEqual(
            months[5]["at"],
            (date(year + 1, 2, 1) - axis_start).days / total * 100,
            places=2,
        )

    def test_the_september_pair_splits_across_the_line(self):
        events = self.events_by_name()
        self.assertEqual(events["Inscription"]["side"], "above")
        self.assertEqual(events["Passage"]["side"], "below")

    def test_another_school_years_activities_are_not_drawn(self):
        year = self.school_year.name
        TimelineActivity.objects.create(
            name="Trop tôt", name_fr="Trop tôt",
            start_date=date(year + 1, 9, 5),
        )
        self.assertNotIn("Trop tôt", self.events_by_name())

    def test_a_long_name_asks_for_the_tall_chart(self):
        TimelineActivity.objects.create(
            name="Un nom vraiment trop long", name_fr="Un nom vraiment trop long",
            start_date=date(self.school_year.name, 10, 3),
        )
        self.assertTrue(self.timeline()["tall"])

    def test_an_activity_cannot_end_before_it_starts(self):
        activity = TimelineActivity(
            name="X", name_fr="X",
            start_date=date(self.school_year.name, 9, 5),
            end_date=date(self.school_year.name, 9, 4),
        )
        with self.assertRaises(ValidationError) as caught:
            activity.full_clean()
        self.assertIn("end_date", caught.exception.message_dict)

    def test_a_date_outside_september_to_july_is_rejected(self):
        activity = TimelineActivity(
            name="X", name_fr="X", start_date=date(self.school_year.name, 8, 15)
        )
        with self.assertRaises(ValidationError) as caught:
            activity.full_clean()
        self.assertIn("start_date", caught.exception.message_dict)

    def test_the_page_draws_the_configured_line(self):
        response = self.client.get("/")
        self.assertNotContains(response, "data-home-timeline")
        for name in ("Inscription", "Passage", "Veillée de Noël",
                     "Fête d'unité", "Camps"):
            # The template autoescapes the apostrophe in "Fête d'unité".
            self.assertContains(response, escape(name))
        camps = self.events_by_name()["Camps"]
        self.assertContains(response, "hero-timeline__event--range")
        # The style values stay machine-readable: a localized decimal comma
        # would make the browser drop the whole declaration.
        self.assertContains(response, f'--at: {camps["at"]}%')
        self.assertContains(response, f'--w: {camps["width"]}%')
        self.assertNotContains(
            response, f'--at: {str(camps["at"]).replace(".", ",")}%'
        )

    def test_an_empty_year_removes_the_slot(self):
        TimelineActivity.objects.all().delete()
        response = self.client.get("/")
        self.assertNotContains(response, "data-home-timeline")
        self.assertNotContains(response, "hero-timeline__chart")


class MemberHomepageTest(DeskTestBase):
    def setUp(self):
        super().setUp()
        self.parent_role = Role.objects.get(short="p")
        self.child_role = Role.objects.get(short="e")
        self.leader_role = Role.objects.get(short="a")

    def make_parent(self, email, *children):
        person = Person.objects.create(
            first_name="Parent", last_name="Test",
            primary_role=self.parent_role, status="a",
        )
        account = Account.objects.create_user(
            email=email, password="testpass", person=person,
        )
        for child in children:
            ParentChild.objects.create(parent=person, child=child)
        return account

    def make_child(self, name, branch=None):
        child = Person.objects.create(
            first_name=name, last_name="Enfant",
            primary_role=self.child_role, status="a",
        )
        if branch is not None:
            Enrollment.objects.create(
                user=child,
                section=Section.objects.create(name=name, branch=branch),
                school_year=self.school_year,
            )
        return child

    def make_child_account(self, email, name="Ana", branch=None):
        child = self.make_child(name, branch)
        account = Account.objects.create_user(
            email=email, password="testpass", person=child,
        )
        return account, child

    def test_a_childs_page_names_their_section_not_their_children(self):
        """A participant answers for themselves, not for a family.

        The heading used to read "Your children" and the empty state asked
        them to link children to an account that will never have any.
        """
        account, child = self.make_child_account(
            "participant@test.com", branch=self.baladins
        )
        self.client.force_login(account)

        response = self.client.get("/")

        self.assertTrue(response.context["member_is_child"])
        self.assertEqual(
            str(response.context["member_heading"]),
            str(translation.pgettext("informal", "Your section")),
        )
        self.assertFalse(response.context["member_show_empty"])
        self.assertNotContains(response, "member-empty")

    def test_a_child_with_no_section_is_told_so_without_mentioning_children(self):
        account, _child = self.make_child_account("no-section@test.com")
        self.client.force_login(account)

        response = self.client.get("/")

        self.assertTrue(response.context["member_is_child"])
        self.assertEqual(
            str(response.context["member_heading"]),
            str(translation.pgettext("informal", "Your unit")),
        )
        self.assertTrue(response.context["member_show_empty"])

    def test_a_plain_parents_board_reads_vous(self):
        """French keeps the formal register for the family the unit serves."""
        account = self.make_parent(
            "vous@test.com", self.make_child("Ana", self.baladins)
        )
        self.client.force_login(account)

        response = self.client.get("/")
        body = response.content.decode()

        self.assertTrue(response.context["member_formal_address"])
        self.assertIn("Vos enfants", body)
        self.assertIn("Vos outils", body)
        self.assertNotIn("Tes outils", body)

    def test_a_childs_board_reads_tu(self):
        account, _child = self.make_child_account(
            "tu@test.com", branch=self.baladins
        )
        self.client.force_login(account)

        response = self.client.get("/")
        body = response.content.decode()

        self.assertFalse(response.context["member_formal_address"])
        self.assertEqual(
            str(response.context["member_heading"]),
            str(translation.pgettext("informal", "Your section")),
        )
        self.assertIn("Tes outils", body)
        self.assertIn("Ton compte", body)
        self.assertNotIn("Vos outils", body)

    def test_staff_with_a_parent_role_reads_tu(self):
        """Staff accounts keep the Parent primary role in a real troop; the
        register follows the board they answer for, not the role alone."""
        person = Person.objects.create(
            first_name="Staff", last_name="One",
            primary_role=self.parent_role, status="a",
        )
        account = Account.objects.create_user(
            email="staff@test.com",
            password="testpass",
            person=person,
            is_staff=True,
        )
        self.client.force_login(account)

        response = self.client.get("/")
        body = response.content.decode()

        self.assertFalse(response.context["member_formal_address"])
        self.assertIn("Ton unité", body)
        self.assertIn("Tes outils", body)
        self.assertNotIn("Vos outils", body)

    def test_an_informal_readers_child_count_uses_tu(self):
        person = Person.objects.create(
            first_name="Leader", last_name="Parent",
            primary_role=self.leader_role, status="a",
        )
        account = Account.objects.create_user(
            email="leader-parent@test.com",
            password="testpass",
            person=person,
        )
        ParentChild.objects.create(
            parent=person, child=self.make_child("Ana", self.baladins)
        )
        self.client.force_login(account)

        body = self.client.get("/").content.decode()

        self.assertIn("enfant rattaché à ton compte", body)
        self.assertNotIn("rattaché à votre compte", body)

    def test_a_childs_agenda_tile_names_the_next_activities(self):
        """The agenda is the child's own work, so it belongs in their account
        group — and its detail lines save a click just to learn when they meet.

        It is the group's third tile and takes the wide row: activity lines
        are longer than a document's name, so the room goes to them.
        """
        from homepage.views import _member_tools

        account, child = self.make_child_account(
            "next-event@test.com", branch=self.baladins
        )
        section = child.get_section()
        first = SectionEvent.objects.create(
            section=section,
            title="Grand jeu",
            start_date=timezone.localdate() + timedelta(days=3),
        )
        second = SectionEvent.objects.create(
            section=section,
            title="Week-end",
            start_date=timezone.localdate() + timedelta(days=10),
        )

        groups = _member_tools(
            account, account.person, [], [], False, section, [first, second]
        )
        account_group = next(
            group for group in groups if group["kind"] == "account"
        )

        self.assertEqual(
            account_group["items"][0].url,
            reverse("members:profile", kwargs={"pk": account.pk}),
        )
        self.assertEqual(
            account_group["items"][1].url,
            reverse("members:documents"),
        )
        agenda = account_group["items"][2]
        self.assertEqual(
            agenda.url,
            f"{reverse('members:agenda')}?section={section.pk}",
        )
        self.assertEqual(len(agenda.details), 2)
        self.assertIn(first.title, str(agenda.details[0]))
        self.assertIn(second.title, str(agenda.details[1]))

    def test_the_documents_tile_names_the_newest_documents(self):
        ImportantDocument.objects.create(title="Reglement de unite")
        ImportantDocument.objects.create(title="Liste de camp")
        account = self.make_parent("docs-tile@test.com")
        self.client.force_login(account)

        body = self.client.get("/").content.decode()

        self.assertIn("Reglement de unite", body)
        self.assertIn("Liste de camp", body)

    def test_a_child_sees_the_next_activity_on_the_page(self):
        account, child = self.make_child_account(
            "next-on-page@test.com", branch=self.baladins
        )
        SectionEvent.objects.create(
            section=child.get_section(),
            title="Grand jeu",
            start_date=timezone.localdate() + timedelta(days=3),
        )
        self.client.force_login(account)

        response = self.client.get("/")

        self.assertContains(response, "Grand jeu")
        self.assertContains(response, reverse("members:agenda"))
        # Profile and documents share the first row; the agenda spans the
        # wide row under them.
        self.assertContains(response, 'data-pair-first="true"')

    def test_a_childs_agenda_tile_follows_the_module_switch(self):
        account, _child = self.make_child_account(
            "child-agenda-off@test.com", branch=self.baladins
        )
        self.client.force_login(account)
        self.assertContains(self.client.get("/"), reverse("members:agenda"))

        settings_row = TroopSettings.get_settings()
        settings_row.agenda_enabled = False
        settings_row.save()

        self.assertNotContains(self.client.get("/"), reverse("members:agenda"))

    def test_a_member_gets_the_tool_and_not_the_troops_page(self):
        account = self.make_parent("member@test.com", self.make_child("Ana"))
        self.client.force_login(account)

        response = self.client.get("/")
        self.assertContains(response, "member-page")
        self.assertNotContains(response, "desk-question")

    def test_the_troops_page_is_one_click_away_for_a_member(self):
        """The decision was "tool owns /, the troop's content one click away"."""
        account = self.make_parent("reach@test.com", self.make_child("Ana"))
        self.client.force_login(account)
        self.assertContains(self.client.get("/"), reverse("unit_page"))

        # A visitor is already on that page, so the entry would be a no-op.
        self.client.logout()
        self.assertNotContains(self.client.get("/"), reverse("unit_page"))

    def test_a_parent_sees_one_panel_per_child(self):
        account = self.make_parent(
            "two@test.com",
            self.make_child("Ana", self.baladins),
            self.make_child("Bo", self.baladins),
        )
        self.client.force_login(account)

        response = self.client.get("/")
        self.assertEqual(response.content.decode().count('class="member-panel"'), 2)

    def test_siblings_share_an_equal_children_row(self):
        """Siblings are peers: the balance takes the first row and the children
        stand under it in equal columns, instead of the asymmetric weights
        that make one child share the balance's line and the next stretch alone
        beneath it."""
        account = self.make_parent(
            "siblings@test.com",
            self.make_child("Ana", self.baladins),
            self.make_child("Bo", self.baladins),
        )
        self.client.force_login(account)

        response = self.client.get("/")
        self.assertContains(response, 'data-many-children="true"')
        self.assertContains(response, 'data-child-count="2"')

    def test_a_single_child_keeps_the_asymmetric_board(self):
        account = self.make_parent("only@test.com", self.make_child("Ana"))
        self.client.force_login(account)

        self.assertNotContains(self.client.get("/"), "data-many-children")

    def test_a_parent_does_not_see_another_familys_child(self):
        self.make_parent("other@test.com", self.make_child("Zoe", self.baladins))
        account = self.make_parent("mine@test.com", self.make_child("Ana", self.baladins))
        self.client.force_login(account)

        self.assertNotContains(self.client.get("/"), "Zoe")

    def test_an_animateur_gets_one_section_panel(self):
        """An animateur leads exactly one section.

        A second enrolment is data a real troop cannot have; it must not grow
        a second panel and turn the page into a list of sections.
        """
        person = Person.objects.create(
            first_name="One", last_name="Section",
            primary_role=self.leader_role, status="a",
        )
        account = Account.objects.create_user(
            email="one-section@test.com", password="testpass", person=person,
        )
        other = Section.objects.create(name="Zone", branch=self.louveteaux)
        for section in (self.section, other):
            Enrollment.objects.create(
                user=person, section=section, school_year=self.school_year,
            )
        self.client.force_login(account)

        body = self.client.get("/").content.decode()
        self.assertEqual(body.count('class="member-panel"'), 1)
        self.assertIn(self.section.name, body)
        self.assertNotIn(other.name, body)

    def test_a_leader_gets_section_panels(self):
        person = Person.objects.create(
            first_name="Lea", last_name="Animatrice",
            primary_role=self.leader_role, status="a",
        )
        account = Account.objects.create_user(
            email="leader@test.com", password="testpass", person=person,
        )
        Enrollment.objects.create(
            user=person, section=self.section, school_year=self.school_year,
        )
        self.client.force_login(account)

        response = self.client.get("/")
        body = response.content.decode()
        self.assertContains(response, self.section.name)
        self.assertEqual(body.count('class="member-panel"'), 1)
        # The tile states the section; acting on it belongs to the tools, so
        # the panel carries neither a foot nor the duplicate doors.
        self.assertNotIn("member-panel-foot", body)
        self.assertNotIn(reverse("members:agenda_event_create"), body)
        self.assertNotIn("member-avatar", body)

    def test_the_panels_follow_the_agenda_module(self):
        """A module switched off removes its UI, not only its URLs."""
        account = self.make_parent("agenda@test.com", self.make_child("Ana", self.baladins))
        self.client.force_login(account)
        self.assertContains(self.client.get("/"), reverse("members:agenda"))

        settings_row = TroopSettings.get_settings()
        settings_row.agenda_enabled = False
        settings_row.save()

        self.assertNotContains(self.client.get("/"), reverse("members:agenda"))

    def test_the_units_band_becomes_the_pages_h1(self):
        """A heading above the desk would otherwise start the page at level 2."""
        body = self.client.get("/").content.decode()
        self.assertIn('h1 class="h2"', body, "the band's heading was not promoted")
        self.assertIn('h2 class="desk-question"', body, "the desk is not a subheading")

    def test_a_unit_admin_gets_no_section_panels(self):
        """Their page is their tools, not a wall of sections.

        `can_edit_section_agenda` is read-only for unit admins: they read every
        agenda and lead none, so a panel per section said nothing about their
        work and the write link on each answered 404.
        """
        person = Person.objects.create(
            first_name="Ad", last_name="Min",
            primary_role=self.parent_role, status="a",
        )
        person.roles.add(Role.objects.get(short="ar"))
        account = Account.objects.create_user(
            email="admin@test.com", password="testpass", person=person,
        )
        self.client.force_login(account)

        body = self.client.get("/").content.decode()
        self.assertNotIn("member-panel", body)
        self.assertNotIn(reverse("members:agenda_event_create"), body)
        self.assertIn("member-tool", body, "the tools are what carries the page")
        self.assertNotIn("member-empty", body, "an admin is not missing anything")

    def test_a_sections_own_leader_gets_its_panel(self):
        account = self.make_leader("leads@test.com", self.section)
        self.client.force_login(account)
        body = self.client.get("/").content.decode()
        self.assertIn("member-panel", body)
        self.assertIn(self.section.name, body)

    def test_a_sections_own_leader_writes_from_the_agenda(self):
        """The board no longer repeats the agenda's own actions on the tile:
        the leader reaches the agenda from the tools, and adds an activity
        there, where the button belongs."""
        person = Person.objects.create(
            first_name="Lea", last_name="Leader",
            primary_role=self.leader_role, status="a",
        )
        account = Account.objects.create_user(
            email="lea@test.com", password="testpass", person=person,
        )
        Enrollment.objects.create(
            user=person, section=self.section, school_year=self.school_year,
        )
        self.client.force_login(account)

        self.assertNotIn(
            reverse("members:agenda_event_create"),
            self.client.get("/").content.decode(),
        )
        self.assertIn(
            reverse("members:agenda_event_create"),
            self.client.get(reverse("members:agenda")).content.decode(),
        )

    def test_a_unit_admin_gets_the_section_tools_under_the_unit(self):
        """A unit admin's section tools reach every section, not their own."""
        account = self.make_staff("admin-tools@test.com")
        self.client.force_login(account)

        groups = self.client.get("/").context["member_tools"]
        self.assertNotIn("sections", [group["kind"] for group in groups])
        unit = next(group for group in groups if group["kind"] == "unit")
        urls = [item.url for item in unit["items"]]
        self.assertIn(reverse("messaging:compose"), urls)
        self.assertIn(reverse("messaging:animateur_history"), urls)
        self.assertIn(reverse("members:agenda"), urls)

    def test_a_sections_own_leader_keeps_the_section_group(self):
        account = self.make_leader("own-tools@test.com", self.section)
        self.client.force_login(account)

        groups = self.client.get("/").context["member_tools"]
        section_group = next(
            group for group in groups if group["kind"] == "sections"
        )
        urls = [item.url for item in section_group["items"]]
        self.assertIn(reverse("messaging:compose"), urls)
        self.assertIn(reverse("members:agenda"), urls)

    def test_the_admin_door_is_quiet_and_named_for_advanced_settings(self):
        account = self.make_staff("advanced@test.com")
        account.is_superuser = True
        account.save()
        self.client.force_login(account)

        response = self.client.get("/")
        unit = next(
            group
            for group in response.context["member_tools"]
            if group["kind"] == "unit"
        )
        advanced = next(
            item for item in unit["items"] if item.url == reverse("admin:index")
        )
        self.assertEqual(
            str(advanced.label), str(translation.gettext("Advanced settings"))
        )
        self.assertTrue(advanced.quiet)
        self.assertEqual(
            [str(detail) for detail in advanced.details],
            [str(translation.gettext("Technical settings, rarely needed"))],
        )
        self.assertContains(response, "member-tool-quiet")

        # The advanced door closes the unit group and the queue is last of
        # all: a queue is read when something failed, not a destination.
        urls = [item.url for item in unit["items"]]
        self.assertEqual(urls[-1], reverse("members:mail_queue"))
        self.assertEqual(urls[-2], reverse("admin:index"))

    def make_leader(self, email, *sections):
        person = Person.objects.create(
            first_name="Lea", last_name="Leader",
            primary_role=self.leader_role, status="a",
        )
        account = Account.objects.create_user(
            email=email, password="testpass", person=person,
        )
        for section in sections:
            Enrollment.objects.create(
                user=person, section=section, school_year=self.school_year,
            )
        return account

    def make_staff(self, email):
        person = Person.objects.create(
            first_name="Sta", last_name="Ff",
            primary_role=self.parent_role, status="a",
        )
        account = Account.objects.create_user(
            email=email, password="testpass", person=person, is_staff=True,
        )
        return account

    def test_the_header_carries_no_menu_for_a_member(self):
        """Their tools are on the page; a link in both is two things to keep."""
        account = self.make_parent("nomenu@test.com", self.make_child("Ana"))
        self.client.force_login(account)
        self.assertNotContains(self.client.get("/"), "navbar-nav")

    def test_a_visitor_still_gets_the_public_navigation(self):
        self.assertContains(self.client.get("/"), "navbar-nav")

    def test_a_parent_is_offered_their_own_tools_and_not_the_units(self):
        account = self.make_parent("tools@test.com", self.make_child("Ana", self.baladins))
        self.client.force_login(account)
        body = self.client.get("/").content.decode()
        self.assertIn(reverse("members:add_new_child"), body)
        self.assertNotIn(reverse("members:admin_list"), body)
        self.assertNotIn(reverse("members:troop_settings"), body)

    def child_tools(self, account, children):
        from homepage.views import _member_tools

        groups = _member_tools(account, account.person, [], children, False)
        return next(group for group in groups if group["kind"] == "children")

    def test_a_parent_with_no_child_is_offered_creation_before_the_calendar(self):
        """The calendar has nobody on it yet; the ways to add a child lead.

        The order is asserted on the URLs, not the labels: the catalogues are
        translated, so the words are not this test's business.
        """
        account = self.make_parent("firstchild@test.com")
        group = self.child_tools(account, [])
        self.assertEqual(
            [item[1] for item in group["items"]],
            [
                reverse("members:add_new_child"),
                reverse("members:add_key_child"),
                reverse("members:agenda"),
                reverse("members:contact_leaders"),
            ],
        )
        self.assertTrue(group["no_children"])

        self.client.force_login(account)
        self.assertContains(self.client.get("/"), 'data-no-children="true"')

    def test_a_parent_with_a_child_keeps_the_calendar_first(self):
        """The creation tools stay below it once there is somebody to see."""
        account = self.make_parent("haschild@test.com", self.make_child("Ana"))
        children = list(Person.objects.filter(as_child__parent=account.person))
        group = self.child_tools(account, children)
        self.assertEqual(
            [item[1] for item in group["items"]],
            [
                reverse("members:agenda"),
                reverse("members:add_new_child"),
                reverse("members:add_key_child"),
                reverse("members:contact_leaders"),
            ],
        )
        self.assertFalse(group["no_children"])

    def test_a_leader_is_offered_the_section_tools(self):
        account = self.make_leader("leadertools@test.com", self.section)
        self.client.force_login(account)
        body = self.client.get("/").content.decode()
        self.assertIn(reverse("messaging:compose"), body)
        self.assertIn(reverse("messaging:animateur_history"), body)
        self.assertNotIn(reverse("members:troop_settings"), body)

    def test_a_unit_admin_is_offered_the_administration_tools(self):
        account = self.make_staff("stafftools@test.com")
        self.client.force_login(account)
        body = self.client.get("/").content.decode()
        for name in ("members:admin_list", "members:passage",
                     "members:member_import", "members:troop_settings",
                     "members:mail_queue"):
            self.assertIn(reverse(name), body, name)

    def test_a_unit_teams_tools_are_ranked_by_how_often_it_reaches_for_them(self):
        """The daily three, then the regular three, then the rest.

        The rank is data, not only order: the template draws the tier, so a
        tool that moves without its tier loses its ground and label size. The
        unit's page rides in this group too rather than duplicating a group.
        """
        account = self.make_staff("ranked@test.com")
        account.is_superuser = True
        account.save()
        self.client.force_login(account)
        response = self.client.get("/")
        unit = self.unit_tools(response)

        self.assertEqual(
            [(item.url, item.tier) for item in unit["items"] if item.tier < 3],
            [
                (reverse("members:admin_list"), 1),
                (reverse("messaging:compose"), 1),
                (reverse("finance:billing"), 1),
                (reverse("attestations:index"), 2),
                (reverse("members:agenda"), 2),
                (reverse("members:troop_settings"), 2),
            ],
        )
        self.assertIn(reverse("unit_page"), [item.url for item in unit["items"]])
        self.assertNotIn(
            "site",
            [group["kind"] for group in response.context["member_tools"]],
        )

    def make_nouveau(self, first_name="Nou", last_name="Veau"):
        """A member created without a role, as the parent's child form leaves it."""
        return Person.objects.create(
            first_name=first_name, last_name=last_name, status="r",
        )

    def nouveau_url(self):
        return (
            f"{reverse('members:admin_list')}"
            f"?role={Role.objects.get(short='n').pk}"
        )

    def unit_tools(self, response):
        return next(
            group
            for group in response.context["member_tools"]
            if group["kind"] == "unit"
        )

    def test_a_nouveau_member_is_a_highlighted_tile_for_member_managers(self):
        self.make_nouveau()
        account = self.make_staff("nouveau-staff@test.com")
        self.client.force_login(account)

        response = self.client.get("/")
        body = response.content.decode()

        self.assertIn(self.nouveau_url(), body)
        self.assertIn("member-tool-alert", body)

        tile = next(
            item
            for item in self.unit_tools(response)["items"]
            if item.url == self.nouveau_url()
        )
        self.assertTrue(tile.alert)
        self.assertIn("1", tile.details[0])

        # The tile's promise: the filtered list answers for a member manager.
        self.assertEqual(self.client.get(self.nouveau_url()).status_code, 200)

    def test_the_nouveau_tile_counts_them_all_in_one_tile(self):
        self.make_nouveau("Un", "Nouveau")
        self.make_nouveau("Deux", "Nouveau")
        account = self.make_staff("nouveau-count@test.com")
        self.client.force_login(account)

        response = self.client.get("/")
        tiles = [
            item
            for item in self.unit_tools(response)["items"]
            if item.url == self.nouveau_url()
        ]

        self.assertEqual(len(tiles), 1)
        self.assertIn("2", tiles[0].details[0])
        self.assertEqual(response.content.decode().count(self.nouveau_url()), 1)

    def test_the_nouveau_tile_disappears_when_nobody_is_left(self):
        self.make_nouveau()
        account = self.make_staff("nouveau-gone@test.com")
        self.client.force_login(account)
        self.assertIn(self.nouveau_url(), self.client.get("/").content.decode())

        Person.objects.filter(primary_role__short="n").update(
            primary_role=Role.objects.get(short="p")
        )

        self.assertNotIn(self.nouveau_url(), self.client.get("/").content.decode())

    def make_registration_manager(self, email, role_short):
        person = Person.objects.create(
            first_name="Reg", last_name=role_short,
            primary_role=self.parent_role, status="a",
        )
        person.roles.add(Role.objects.get(short=role_short))
        return Account.objects.create_user(
            email=email, password="testpass", person=person,
        )

    def test_registration_manager_and_unit_lead_see_the_nouveau_tile(self):
        self.make_nouveau()
        for role_short in ("ri", "ar"):
            with self.subTest(role=role_short):
                account = self.make_registration_manager(
                    f"{role_short}-nouveau@test.com", role_short
                )
                self.client.force_login(account)
                self.assertIn(
                    self.nouveau_url(),
                    self.client.get("/").content.decode(),
                )

    def test_a_parent_without_a_member_role_does_not_see_the_nouveau_tile(self):
        self.make_nouveau()
        account = self.make_parent("plain-nouveau@test.com")
        self.client.force_login(account)

        body = self.client.get("/").content.decode()

        self.assertNotIn(self.nouveau_url(), body)
        self.assertNotIn("member-tool-alert", body)

    def test_every_tool_link_answers_for_every_role(self):
        """The hub promises each destination, and three dead ones have shipped.

        Checked for every reader, because a link can answer for one role and
        404 for another — which is exactly how the Pay button and "Add an
        activity" went wrong.
        """
        from homepage.views import _member_tools

        child = self.make_child("Ana", self.baladins)
        child_account = Account.objects.create_user(
            email="ans-child@test.com", password="testpass", person=child,
        )
        readers = {
            "parent": (self.make_parent("ans-parent@test.com", child), child.parents.first()),
            "child": (child_account, child),
            "leader": (self.make_leader("ans-leader@test.com", self.section), None),
            "staff": (self.make_staff("ans-staff@test.com"), None),
        }
        for role, (account, person) in readers.items():
            person = person or account.person
            children = list(Person.objects.filter(as_child__parent=person))
            sections = list(visible_sections(account))
            leads = can_manage_unit(account) or has_primary_role(account, ANIMATEUR_ROLES)
            own_section = (
                sections[0]
                if has_primary_role(account, (ANIME,)) and sections
                else None
            )
            for group in _member_tools(
                account, person, sections, children, leads, own_section
            ):
                for tool in group["items"]:
                    label, url = tool.label, tool.url
                    with self.subTest(role=role, tool=label):
                        self.client.force_login(account)
                        self.assertEqual(
                            self.client.get(url).status_code, 200,
                            f"{role}: {label} -> {url} did not answer",
                        )

    def test_a_member_with_nothing_attached_gets_an_explanation(self):
        person = Person.objects.create(
            first_name="Nou", last_name="Veau",
            primary_role=self.parent_role, status="a",
        )
        account = Account.objects.create_user(
            email="empty@test.com", password="testpass", person=person,
        )
        self.client.force_login(account)

        response = self.client.get("/")
        self.assertContains(response, "member-empty")
        self.assertEqual(response.content.decode().count('class="member-panel"'), 0)


class MemberDuesTest(FinanceTestBase):
    """The balance is the household's, because that is what a troop bills."""

    def setUp(self):
        super().setUp()
        # This base mutates TroopSettings for one test below, and the settings
        # row is cached: clear it in and out, as tests.base does.
        TroopSettings.clear_cache()
        self.addCleanup(TroopSettings.clear_cache)

    def test_dues_are_the_household_total_not_the_one_child(self):
        """Charlie is billed 80.00 and Diana 60.00 at the same address.

        Asking about Charlie alone must still report 140.00: the household pays
        as a household, and a parent is never asked for one child's share.
        """
        dues = _household_dues([self.child_eldest], self.current_year)
        self.assertEqual(dues["owed"], Decimal("140.00"))

    def test_a_child_at_another_address_is_a_separate_household(self):
        dues = _household_dues([self.child_other], self.current_year)
        self.assertEqual(dues["owed"], Decimal("80.00"))

    def test_nothing_owed_is_not_a_band(self):
        for child in (self.child_eldest, self.child_youngest, self.child_other):
            Enrollment.objects.filter(user=child).delete()
        self.assertIsNone(_household_dues([self.child_eldest], self.current_year))

    def test_the_band_appears_for_a_parent_who_owes(self):
        self.client.force_login(self.parent1_account)
        self.assertContains(self.client.get("/"), "member-house-amount")

    def test_a_parent_is_not_handed_the_treasurers_ledger(self):
        """`finance:billing` raises Http404 for anyone without can_access_finance.

        A Pay button a parent cannot follow is worse than no button: it is the
        page's most prominent action pointing at a 404.
        """
        self.client.force_login(self.parent1_account)
        response = self.client.get("/")
        self.assertContains(response, "member-house-amount")
        self.assertNotContains(response, reverse("finance:billing"))

    def test_a_parent_who_is_the_treasurer_does_get_it(self):
        self.parent1.roles.add(Role.objects.get(short="t"))
        self.client.force_login(self.parent1_account)
        self.assertContains(self.client.get("/"), reverse("finance:billing"))

    def test_a_parent_can_message_the_treasurer_from_the_balance(self):
        treasurer = Person.objects.create(
            first_name="Tess", last_name="Treasurer",
            primary_role=self.role_parent, status="a",
        )
        treasurer.roles.add(Role.objects.get(short="t"))
        Account.objects.create_user(
            email="tres@test.com", password="testpass", person=treasurer,
        )

        self.client.force_login(self.parent1_account)
        response = self.client.get("/")
        url = f"{reverse('members:contact_leaders')}?to=treasurer"
        self.assertContains(response, url)
        # The door opens the dialog; the plain href remains the fallback.
        self.assertContains(response, f'hx-get="{url}"')

    def test_the_band_is_gone_when_the_troop_runs_without_fees(self):
        settings_row = TroopSettings.get_settings()
        settings_row.fees_enabled = False
        settings_row.save()

        self.client.force_login(self.parent1_account)
        response = self.client.get("/")
        self.assertContains(response, "member-page")
        self.assertNotContains(response, "member-house-amount")

    def test_the_sibling_discount_is_reported_because_this_troop_has_one(self):
        """The fixture prices rank 1 at 80.00 and rank 2 at 60.00."""
        self.assertTrue(_siblings_are_discounted(self.current_year))

    def test_no_discount_is_claimed_when_every_rank_costs_the_same(self):
        """The rule is read off the fee table, never assumed from the model."""
        FeeRule.objects.filter(
            school_year=self.current_year, member_type=FeeRule.MemberType.CHILD
        ).update(amount=Decimal("80.00"))
        self.assertFalse(_siblings_are_discounted(self.current_year))

    def test_the_deadline_is_stated_when_the_band_is_shown(self):
        self.config.late_deadline = date.today() + timedelta(days=14)
        self.config.save()

        self.client.force_login(self.parent1_account)
        self.assertContains(self.client.get("/"), "member-house")

    def test_the_overdue_state_is_marked_when_the_deadline_has_passed(self):
        self.config.late_deadline = date.today() - timedelta(days=1)
        self.config.save()

        self.client.force_login(self.parent1_account)
        self.assertContains(self.client.get("/"), "member-house-late")


class PublicPageOrderTest(TroopSettingsTestCase):
    """The troop chooses the order of the blocks under the introduction."""

    def setUp(self):
        super().setUp()
        row = TroopSettings.get_settings()
        row.homepage_about_enabled = True
        row.homepage_about_text = "About the unit."
        row.homepage_faq_enabled = True
        row.homepage_faq_text = "A question?\n\nAn answer."
        row.footer_address = "Rue Test 1, 1000 Bruxelles"
        row.homepage_block_order = "faq,place,desk,about"
        row.save()

    def positions(self, content, keys):
        return [content.find(f'data-public-block="{key}"') for key in keys]

    def test_the_blocks_follow_the_stored_order(self):
        content = self.client.get("/").content.decode()
        positions = self.positions(content, ("faq", "place", "desk", "about"))
        self.assertTrue(all(position >= 0 for position in positions))
        self.assertEqual(positions, sorted(positions))

    def test_the_unit_page_carries_every_enabled_block_in_order(self):
        """`/unite/` is the same page an anonymous visitor gets at `/`: the
        desk and the place included, in the stored order."""
        content = self.client.get(reverse("unit_page")).content.decode()
        positions = self.positions(content, ("faq", "place", "desk", "about"))
        self.assertTrue(all(position >= 0 for position in positions))
        self.assertEqual(positions, sorted(positions))

    def test_each_block_needs_its_own_position(self):
        form = PublicPageSettingsForm(
            instance=TroopSettings.get_settings(),
            data={
                "position_desk": 1,
                "position_place": 1,
                "position_about": 3,
                "position_faq": 4,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(
            any(
                "position" in str(error).lower()
                for error in form.non_field_errors()
            )
        )

    def test_the_form_stores_the_positions(self):
        row = TroopSettings.get_settings()
        form = PublicPageSettingsForm(instance=row)
        data = {}
        for name, field in form.fields.items():
            if name.startswith("position_"):
                continue
            if isinstance(
                field.widget, (forms.FileInput, forms.ClearableFileInput)
            ):
                continue
            value = getattr(row, name, "")
            if isinstance(field, forms.BooleanField):
                data[name] = "on" if value else ""
            else:
                data[name] = "" if value is None else value
        data.update(
            {
                "position_desk": 3,
                "position_place": 1,
                "position_about": 2,
                "position_faq": 4,
            }
        )

        form = PublicPageSettingsForm(instance=row, data=data)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        row.refresh_from_db()
        self.assertEqual(row.homepage_block_order, "place,about,desk,faq")


class PlaceBandTest(MediaRootTestCase):
    """Where the unit meets, under the desk.

    This band is the only place the unit's address reaches a page at all: it
    was stored on the settings row and rendered by no template before it.
    """

    def test_absent_until_the_unit_says_where_it_meets(self):
        """No empty frame where a map should be."""
        troop = TroopSettings.get_settings()
        troop.footer_address = ""
        troop.meeting_place = ""
        troop.save()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "place-title")

    def test_names_the_place_and_the_address(self):
        troop = TroopSettings.get_settings()
        troop.meeting_place = "Par delà l'eau"
        troop.footer_address = "Rue Achille Bauduin 89\n1300 Limal"
        troop.save()

        response = self.client.get("/")

        self.assertContains(response, "place-title")
        # The apostrophe is escaped in the response, so the assertion stops
        # short of it rather than pinning the escaping.
        self.assertContains(response, "Par delà l")
        self.assertContains(response, "Rue Achille Bauduin 89")
        self.assertContains(response, "1300 Limal")

    def test_directions_are_a_link_the_reader_chooses_to_follow(self):
        """The page must not call a map service on its own: the address goes
        into a query, and the request happens when a reader clicks it."""
        troop = TroopSettings.get_settings()
        troop.footer_address = "Rue Achille Bauduin 89\n1300 Limal"
        troop.save()

        response = self.client.get("/")

        self.assertContains(response, "openstreetmap.org/search?query=")
        # Collapsed onto one line, which is what a query wants.
        self.assertContains(
            response, "query=Rue%20Achille%20Bauduin%2089%201300%20Limal"
        )

    def test_a_troop_with_words_alone_still_gets_a_directions_link(self):
        """The fallback for the troop whose address is all it has: with no
        picture to point at, the words are the only way to ask for the route."""
        troop = TroopSettings.get_settings()
        troop.footer_address = "Rue Achille Bauduin 89"
        troop.save()

        response = self.client.get("/")

        self.assertContains(response, "place-directions")
        self.assertContains(response, "openstreetmap.org/search?query=")

    def test_the_map_carries_the_directions_link(self):
        """Where the troop did upload a picture, the picture is the link: the
        reader points at the place rather than at a word beside it."""
        troop = TroopSettings.get_settings()
        troop.footer_address = "Rue Achille Bauduin 89\n1300 Limal"
        troop.map_image = an_image("hall.png")
        troop.save()

        response = self.client.get("/")
        content = response.content.decode()
        map_url = troop.map_url()

        # The map is the only thing inside the anchor, so the picture's own URL
        # standing after the anchor's opening tag is what says so.
        anchor = content.index(f'href="{troop.address_search_url()}"')
        self.assertGreater(content.index(f'src="{map_url}"'), anchor)
        # And the row of words it used to sit beside is gone: one offer, not
        # two copies of the same one.
        self.assertNotContains(response, "place-directions")

    def test_no_map_image_until_one_is_uploaded(self):
        troop = TroopSettings.get_settings()
        troop.footer_address = "Rue Achille Bauduin 89"
        troop.save()

        response = self.client.get("/")

        self.assertContains(response, "place-address")
        self.assertNotContains(response, "place-map")

    def test_the_unit_page_carries_the_place_band(self):
        """The public page is one page at two URLs, so the place band sits
        under the desk at `/unite/` exactly as it does for an anonymous `/`."""
        troop = TroopSettings.get_settings()
        troop.footer_address = "Rue Achille Bauduin 89"
        troop.save()

        response = self.client.get("/unite/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-public-block="place"')
        self.assertContains(response, "place-address")
