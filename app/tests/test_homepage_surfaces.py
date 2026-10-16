"""The two surfaces at ``/``: the public enrolment desk and the member page.

The assertions are on structure and on the troop's own data, never on
translated copy — the source strings are English while a French instance
renders the catalogue, so a test that matched a sentence would pass in one
language and fail in the others.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse

from finance.models import FeeRule
from homepage.views import _desk_rows, _household_dues, _siblings_are_discounted
from members.models import (
    Account,
    Branch,
    Enrollment,
    ParentChild,
    Person,
    Role,
    SchoolYear,
    Section,
    TroopSettings,
)
from tests.base import TroopSettingsTestCase
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

    def test_a_branch_holds_its_ages_up_to_but_not_including_its_maximum(self):
        """A child joins at `min` and leaves when they reach `max`.

        Inclusive at the top instead would give an eight-year-old to both
        Baladins and Louveteaux, which is exactly the ambiguity the troop's own
        ranges have to be read without.
        """
        years = {year for year, branch in _desk_rows(self.school_year)
                 if branch.pk == self.baladins.pk}
        self.assertEqual(
            years,
            set(range(self.reference_year - 7, self.reference_year - 6 + 1)),
        )

    def test_the_years_run_oldest_child_to_youngest(self):
        """The desk reads left to right as the ages do."""
        years = [year for year, _branch in _desk_rows(self.school_year)]
        self.assertEqual(years, sorted(years))
        self.assertEqual(
            years[0], self.reference_year - self.louveteaux.max_age_dec_31 + 1
        )
        self.assertEqual(years[-1], self.reference_year - self.baladins.min_age_dec_31)

    def test_a_branch_without_ages_is_skipped(self):
        Branch.objects.create(name="Sans âges")
        self.assertNotIn(
            "Sans âges", {branch.name for _year, branch in _desk_rows(self.school_year)}
        )


class FederationMappingTest(TroopSettingsTestCase):
    """The birth years the shipped preset's branches cover, for 2026-2027.

    Pinned to the numbers the user gave when they reported the desk's mapping
    as wrong: the Pionniers are born in 2009 and 2010, the Baladins in 2019 and
    2020. Read with an inclusive maximum instead, every branch gains the year
    below it and one child fits two branches.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school_year = SchoolYear.current()
        cls.reference_year = TroopSettings.get_settings().age_reference_date(
            cls.school_year
        ).year
        for name, low, high in (
            ("Baladins", 6, 8),
            ("Louveteaux", 8, 12),
            ("Éclaireurs", 12, 16),
            ("Pionniers", 16, 18),
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

    def test_every_year_lands_in_exactly_one_branch(self):
        """No gaps and no overlaps, which is the whole point of the rule."""
        rows = _desk_rows(self.school_year)
        self.assertEqual(
            [year for year, _ in rows],
            list(range(self.reference_year - 17, self.reference_year - 6 + 1)),
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
        # Age 8 is only this branch's — Baladins stops at 7 and the fixture's
        # Louveteaux starts at 9 — so no overlap can decide the answer.
        response = self.client.get("/", {"annee": self.reference_year - 8})
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
        response = self.client.get("/", {"annee": self.reference_year - 8})
        self.assertContains(response, "Maison")
        self.assertNotContains(response, "--branch")

    def test_a_year_in_no_branch_asks_again_instead_of_guessing(self):
        response = self.client.get("/", {"annee": 1900})
        self.assertContains(response, "desk-prompt")
        self.assertNotContains(response, "desk-answer-title")

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

    def test_the_units_own_page_is_public_and_carries_no_desk(self):
        response = self.client.get("/unite/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "desk-question")


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

    def test_a_parent_does_not_see_another_familys_child(self):
        self.make_parent("other@test.com", self.make_child("Zoe", self.baladins))
        account = self.make_parent("mine@test.com", self.make_child("Ana", self.baladins))
        self.client.force_login(account)

        self.assertNotContains(self.client.get("/"), "Zoe")

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
        # A section panel carries a leader's own action and no child's avatar.
        self.assertIn(reverse("members:agenda_event_create"), body)
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
