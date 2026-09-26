"""The passage on a ladder the code knows nothing about.

``run_passage`` used to pick the next branch by scanning ``min_age_dec_31`` in
order — an implicit assumption that a troop's branches form one age ladder, in
age order, with our names. It now follows ``Branch.promotes_to``, and these
tests pin the consequences: the shape of the ladder is data, sections have to
suit the member, and anything the task cannot decide is flagged for a human
rather than guessed at.
"""

from datetime import date
from unittest import mock

from django.urls import reverse
from post_office.models import EmailTemplate

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
from members.tasks import run_passage

from .base import TroopSettingsTestCase


class LadderTestBase(TroopSettingsTestCase):
    @classmethod
    def setUpTestData(cls):
        # Same reason as the passage tests next door: creating a member can
        # reach for this template.
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test"
        )

    def setUp(self):
        super().setUp()
        self.role_child = Role.objects.get(short="e")
        self.role_leader = Role.objects.get(short="a")
        self.role_parent = Role.objects.get(short="p")
        self.current_year = SchoolYear.current()
        self.next_year = SchoolYear.next_school_year()
        # Stand on the passage day, so an unforced run is due.
        self._today = mock.patch(
            "members.tasks._today",
            return_value=TroopSettings.get_settings()
            .passage_datetime(self.next_year)
            .date(),
        )
        self._today.start()
        self.addCleanup(self._today.stop)

    def branch(self, name, min_age=None, max_age=None, promotes_to=None, is_top=False):
        return Branch.objects.create(
            name=name,
            min_age_dec_31=min_age,
            max_age_dec_31=max_age,
            promotes_to=promotes_to,
            is_top=is_top,
        )

    def section(self, name, branch, sex=Section.Sex.BOTH):
        return Section.objects.create(name=name, branch=branch, sex=sex)

    def child(self, age, sex=Person.Sex.MALE, section=None, **kwargs):
        """A participant who turns ``age`` on the target year's reference day."""
        reference = TroopSettings.get_settings().age_reference_date(self.next_year)
        birthday = reference.replace(year=reference.year - age)
        fields = {
            "first_name": "Test",
            "last_name": "Child",
            "primary_role": self.role_child,
            "status": "a",
            "sex": sex,
            "birthday": birthday,
        }
        fields.update(kwargs)
        child = Person.objects.create(**fields)
        if section is not None:
            Enrollment.objects.create(
                user=child, section=section, school_year=self.current_year
            )
        return child

    def next_section_of(self, child):
        enrollment = Enrollment.objects.filter(
            user=child, school_year=self.next_year
        ).first()
        return enrollment.section if enrollment else None


class NonLinearLadderTest(LadderTestBase):
    """The ladder may be any shape: it is followed, not recomputed."""

    def setUp(self):
        super().setUp()
        # Names and ages deliberately disagree with the order the branches
        # promote in: "Zed" is the youngest and points at the *oldest* branch,
        # skipping "Mid" entirely.
        self.young = self.branch("Zed", min_age=6, max_age=8)
        self.old = self.branch("Alpha", min_age=14, max_age=16)
        self.mid = self.branch("Mid", min_age=9, max_age=13)
        self.young.promotes_to = self.old
        self.young.save(update_fields=["promotes_to"])
        self.old.promotes_to = self.mid
        self.old.save(update_fields=["promotes_to"])
        self.mid.is_top = True
        self.mid.save(update_fields=["is_top"])

        self.section_young = self.section("Zed A", self.young)
        self.section_old = self.section("Alpha A", self.old)
        self.section_mid = self.section("Mid A", self.mid)

    def test_follows_promotes_to_and_not_the_age_order(self):
        child = self.child(9, section=self.section_young)

        run_passage()

        # 9 is "Mid"'s age band, but Zed promotes to Alpha and that is the link
        # that counts.
        self.assertEqual(self.next_section_of(child), self.section_old)

    def test_a_second_hop_follows_the_next_link(self):
        child = self.child(17, section=self.section_old)

        run_passage()

        self.assertEqual(self.next_section_of(child), self.section_mid)

    def test_the_last_branch_graduates_its_members(self):
        parent = Person.objects.create(
            first_name="Parent", last_name="Test", primary_role=self.role_parent
        )
        child = self.child(17, section=self.section_mid)
        ParentChild.objects.create(parent=parent, child=child)

        result = run_passage()

        child.refresh_from_db()
        self.assertEqual(child.primary_role, self.role_leader)
        self.assertEqual(result["aged_out"], 1)
        self.assertFalse(ParentChild.objects.filter(child=child).exists())

    def test_a_branch_with_no_next_branch_is_flagged(self):
        loose = self.branch("Loose", min_age=6, max_age=8)
        section = self.section("Loose A", loose)
        child = self.child(9, section=section)

        result = run_passage()

        child.refresh_from_db()
        self.assertEqual(child.passage_review, Person.PassageReview.NO_NEXT_BRANCH)
        self.assertEqual(result["flagged"], 1)
        self.assertIsNone(self.next_section_of(child))
        # Still a participant: flagging never changes who someone is.
        self.assertEqual(child.primary_role, self.role_child)


class GraduationToggleTest(LadderTestBase):
    def setUp(self):
        super().setUp()
        self.top = self.branch("Top", min_age=13, max_age=15, is_top=True)
        self.section_top = self.section("Top A", self.top)
        self.parent = Person.objects.create(
            first_name="Parent", last_name="Test", primary_role=self.role_parent
        )

    def _graduate(self):
        child = self.child(16, section=self.section_top)
        ParentChild.objects.create(parent=self.parent, child=child)
        return child

    def test_on_they_become_leaders(self):
        child = self._graduate()

        run_passage()

        child.refresh_from_db()
        self.assertEqual(child.primary_role, self.role_leader)
        self.assertEqual(child.passage_review, "")

    def test_off_they_are_flagged_instead(self):
        troop = TroopSettings.get_settings()
        troop.top_branch_graduates_become_leaders = False
        troop.save(update_fields=["top_branch_graduates_become_leaders"])

        child = self._graduate()
        result = run_passage()

        child.refresh_from_db()
        self.assertEqual(child.passage_review, Person.PassageReview.GRADUATION)
        self.assertEqual(child.primary_role, self.role_child)
        self.assertEqual(result["flagged"], 1)
        # Nothing was taken away, so the troop can still decide either way.
        self.assertTrue(ParentChild.objects.filter(child=child).exists())
        self.assertIsNone(self.next_section_of(child))


class SectionSexTest(LadderTestBase):
    """A section only takes the members it is meant for."""

    def setUp(self):
        super().setUp()
        self.young = self.branch("Young", min_age=6, max_age=8)
        self.older = self.branch("Older", min_age=9, max_age=12)
        self.young.promotes_to = self.older
        self.young.save(update_fields=["promotes_to"])
        self.section_young = self.section("Young A", self.young)

    def test_mixed_branch_avoids_the_wrong_single_sex_section(self):
        # "Aigles" sorts first, but it is the boys' section: a girl belongs in
        # the mixed one even though the alphabetical rule picked the other.
        self.section("Aigles", self.older, sex=Section.Sex.MALE)
        biches = self.section("Biches", self.older, sex=Section.Sex.BOTH)
        girl = self.child(9, sex=Person.Sex.FEMALE, section=self.section_young)

        run_passage()

        self.assertEqual(self.next_section_of(girl), biches)

    def test_single_sex_branch_places_by_sex(self):
        filles = self.section("Filles", self.older, sex=Section.Sex.FEMALE)
        garcons = self.section("Garcons", self.older, sex=Section.Sex.MALE)
        girl = self.child(9, sex=Person.Sex.FEMALE, section=self.section_young)
        boy = self.child(9, sex=Person.Sex.MALE, section=self.section_young)

        run_passage()

        self.assertEqual(self.next_section_of(girl), filles)
        self.assertEqual(self.next_section_of(boy), garcons)

    def test_single_sex_branch_with_no_place_for_them_is_flagged(self):
        self.section("Garcons", self.older, sex=Section.Sex.MALE)
        girl = self.child(9, sex=Person.Sex.FEMALE, section=self.section_young)

        result = run_passage()

        girl.refresh_from_db()
        self.assertEqual(girl.passage_review, Person.PassageReview.NO_SECTION)
        self.assertEqual(result["flagged"], 1)
        self.assertIsNone(self.next_section_of(girl))

    def test_an_unknown_sex_only_goes_to_a_mixed_section(self):
        self.section("Filles", self.older, sex=Section.Sex.FEMALE)
        child = self.child(9, sex=None, section=self.section_young)

        run_passage()

        child.refresh_from_db()
        self.assertEqual(child.passage_review, Person.PassageReview.NO_SECTION)

    def test_a_section_declaring_no_sex_takes_anyone(self):
        undeclared = self.section("Open", self.older, sex=None)
        child = self.child(9, sex=Person.Sex.FEMALE, section=self.section_young)

        run_passage()

        self.assertEqual(self.next_section_of(child), undeclared)


class StayingTest(LadderTestBase):
    def test_within_the_age_range_they_stay_put(self):
        young = self.branch("Young", min_age=6, max_age=8)
        young.promotes_to = self.branch("Older", min_age=9, max_age=12)
        young.save(update_fields=["promotes_to"])
        section = self.section("Young A", young)
        child = self.child(8, section=section)

        run_passage()

        self.assertEqual(self.next_section_of(child), section)

    def test_a_branch_with_no_max_age_keeps_them(self):
        # Nothing has said they outgrew it, so a link is not followed on a
        # guess.
        open_branch = self.branch("Open", min_age=6)
        open_branch.promotes_to = self.branch("Older", min_age=9, max_age=12)
        open_branch.save(update_fields=["promotes_to"])
        section = self.section("Open A", open_branch)
        child = self.child(17, section=section)

        run_passage()

        child.refresh_from_db()
        self.assertEqual(self.next_section_of(child), section)
        self.assertEqual(child.passage_review, "")


class FlagLifecycleTest(LadderTestBase):
    """A flag is a question, and the next run asks it again."""

    def setUp(self):
        super().setUp()
        self.young = self.branch("Young", min_age=6, max_age=8)
        self.older = self.branch("Older", min_age=9, max_age=12)
        self.young.promotes_to = self.older
        self.young.save(update_fields=["promotes_to"])
        self.section_young = self.section("Young A", self.young)
        self.section_boys = self.section("Garcons", self.older, sex=Section.Sex.MALE)

    def test_the_flag_clears_once_a_section_exists(self):
        girl = self.child(9, sex=Person.Sex.FEMALE, section=self.section_young)
        run_passage()
        girl.refresh_from_db()
        self.assertEqual(girl.passage_review, Person.PassageReview.NO_SECTION)

        section_filles = self.section("Filles", self.older, sex=Section.Sex.FEMALE)
        run_passage(force=True)

        girl.refresh_from_db()
        self.assertEqual(girl.passage_review, "")
        self.assertEqual(self.next_section_of(girl), section_filles)

    def test_an_override_wins_and_answers_the_question(self):
        girl = self.child(9, sex=Person.Sex.FEMALE, section=self.section_young)
        run_passage()

        # The troop decides by hand, despite the section being the boys' one.
        girl.refresh_from_db()
        girl.next_section = self.section_boys
        girl.save(update_fields=["next_section"])
        run_passage(force=True)

        girl.refresh_from_db()
        self.assertEqual(girl.passage_review, "")
        self.assertIsNone(girl.next_section)
        self.assertEqual(self.next_section_of(girl), self.section_boys)


class IdempotencyTest(LadderTestBase):
    def test_running_again_changes_nothing(self):
        young = self.branch("Young", min_age=6, max_age=8)
        older = self.branch("Older", min_age=9, max_age=12, is_top=True)
        young.promotes_to = older
        young.save(update_fields=["promotes_to"])
        section_young = self.section("Young A", young)
        section_older = self.section("Older A", older)
        placed = self.child(9, section=section_young)
        flagged = self.child(9, section=section_young)
        flagged.sex = Person.Sex.FEMALE
        flagged.save(update_fields=["sex"])
        Section.objects.filter(pk=section_older.pk).update(sex=Section.Sex.MALE)

        run_passage()
        self.assertEqual(self.next_section_of(placed), section_older)
        flagged.refresh_from_db()
        self.assertEqual(flagged.passage_review, Person.PassageReview.NO_SECTION)

        result = run_passage(force=True)

        # Same placements, same flag, and no second enrollment anywhere.
        self.assertEqual(self.next_section_of(placed), section_older)
        flagged.refresh_from_db()
        self.assertEqual(flagged.passage_review, Person.PassageReview.NO_SECTION)
        self.assertEqual(
            Enrollment.objects.filter(school_year=self.next_year).count(), 1
        )
        self.assertEqual(result["flagged"], 1)


class OneHopLadderTestBase(LadderTestBase):
    """Two branches that promote into each other, for the run-timing tests."""

    def setUp(self):
        super().setUp()
        self.young = self.branch("Young", min_age=6, max_age=8)
        self.older = self.branch("Older", min_age=9, max_age=12, is_top=True)
        self.young.promotes_to = self.older
        self.young.save(update_fields=["promotes_to"])
        self.section_young = self.section("Young A", self.young)
        self.section_older = self.section("Older A", self.older)

    def set_mode(self, mode):
        troop = TroopSettings.get_settings()
        troop.passage_mode = mode
        troop.save(update_fields=["passage_mode"])


class ManualModeTest(OneHopLadderTestBase):
    """A troop that would rather press the button itself."""

    def setUp(self):
        super().setUp()
        self.set_mode("manual")

    def test_the_daily_run_leaves_a_manual_troop_alone(self):
        child = self.child(9, section=self.section_young)

        result = run_passage()

        self.assertIsNone(result)
        self.assertIsNone(self.next_section_of(child))
        self.assertIsNone(TroopSettings.get_settings().last_passage_school_year)

    def test_a_forced_run_does_the_work(self):
        child = self.child(9, section=self.section_young)

        run_passage(force=True)

        self.assertEqual(self.next_section_of(child), self.section_older)
        self.assertEqual(
            TroopSettings.get_settings().last_passage_school_year, self.next_year.name
        )

    def test_forcing_ignores_the_date_gate(self):
        child = self.child(9, section=self.section_young)
        before = date(self.next_year.name, 1, 1)

        with mock.patch("members.tasks._today", return_value=before):
            self.assertIsNone(run_passage())
            run_passage(force=True)

        self.assertEqual(self.next_section_of(child), self.section_older)


class ForcedRunTest(OneHopLadderTestBase):
    """The button is not a second implementation: it is the same code, unguarded."""

    def test_forcing_after_the_marker_still_runs(self):
        latecomer = self.child(9, section=self.section_young)
        run_passage()
        self.assertEqual(self.next_section_of(latecomer), self.section_older)

        # A member the first run could not see (added afterwards, or fixed by
        # hand) is picked up by pressing the button again.
        second = self.child(9, section=self.section_young, first_name="Second")
        run_passage(force=True)

        self.assertEqual(self.next_section_of(second), self.section_older)
        # The first member is reprocessed rather than moved on again, so a
        # forced run leaves one enrollment each, not two.
        self.assertEqual(self.next_section_of(latecomer), self.section_older)
        self.assertEqual(
            Enrollment.objects.filter(school_year=self.next_year).count(), 2
        )


class PassagePageTest(LadderTestBase):
    def setUp(self):
        super().setUp()
        self.young = self.branch("Young", min_age=6, max_age=8)
        self.older = self.branch("Older", min_age=9, max_age=12, is_top=True)
        self.young.promotes_to = self.older
        self.young.save(update_fields=["promotes_to"])
        self.section_young = self.section("Young A", self.young)
        self.section_older = self.section("Older A", self.older)

        self.staff_person = Person.objects.create(
            first_name="Staff", last_name="Member", primary_role=self.role_parent
        )
        Account.objects.create_user(
            email="staff@test.be", password="testpass", person=self.staff_person,
            is_staff=True,
        )
        self.url = reverse("members:passage")

    def login_staff(self):
        self.assertTrue(self.client.login(email="staff@test.be", password="testpass"))

    def test_staff_see_the_page(self):
        self.login_staff()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        # The coming school year, so staff can see which run they are forcing.
        self.assertContains(response, self.next_year.range)

    def test_the_button_runs_the_passage(self):
        self.login_staff()
        child = self.child(9, section=self.section_young)

        response = self.client.post(self.url)

        self.assertRedirects(response, self.url)
        self.assertEqual(self.next_section_of(child), self.section_older)

    def test_the_page_lists_who_is_waiting_for_a_decision(self):
        self.login_staff()
        child = self.child(9, section=self.section_young)
        child.passage_review = Person.PassageReview.NO_SECTION
        child.save(update_fields=["passage_review"])

        response = self.client.get(self.url)

        self.assertContains(response, child.last_name)

    def test_the_flag_is_shown_where_the_member_is_edited(self):
        """The passage page says who needs a decision; the member's own page
        says what the decision is about, which is where it gets made."""
        self.login_staff()
        child = self.child(9, section=self.section_young)
        child.passage_review = Person.PassageReview.NO_NEXT_BRANCH
        child.save(update_fields=["passage_review"])

        response = self.client.get(reverse("members:admin_update", args=[child.pk]))

        self.assertEqual(response.status_code, 200)
        # The page renders in the site language, so this is the French wording
        # of the reason's own label.
        self.assertContains(response, "Le passage de section attend une décision")

    def test_a_member_of_the_troop_cannot_reach_it(self):
        person = Person.objects.create(
            first_name="Plain",
            last_name="Member",
            primary_role=self.role_parent,
            status="a",
        )
        Account.objects.create_user(
            email="plain@test.be", password="testpass", person=person
        )
        self.assertTrue(
            self.client.login(email="plain@test.be", password="testpass")
        )

        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url).status_code, 403)
