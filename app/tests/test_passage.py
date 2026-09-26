from datetime import date, timedelta
from unittest import mock

from django.utils import timezone
from post_office.models import EmailTemplate

from members.models import (
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


class PassageTestBase(TroopSettingsTestCase):
    """Shared setup for passage tests.

    ``run_passage`` writes the anti-replay marker back onto the troop settings
    row, so these are exactly the tests that must not leave it cached.
    """

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )

    def setUp(self):
        super().setUp()
        self.role_anime = Role.objects.get(short="e")
        self.role_animateur = Role.objects.get(short="a")
        self.role_parent = Role.objects.get(short="p")

        # Current school year (created by migration 0002)
        self.current_year = SchoolYear.current()
        # Next school year (may already exist from seed data)
        next_name = self.current_year.name + 1
        self.next_year, _ = SchoolYear.objects.get_or_create(
            name=next_name,
            defaults={
                "start_date": self.current_year.end_date + timedelta(days=1),
                "end_date": self.current_year.end_date.replace(
                    year=self.current_year.end_date.year + 1,
                ),
                "range": f"{next_name}-{next_name + 1}",
            },
        )

        # Branches: Baladins (6-9), Louveteaux (10-12), Pionniers (13-17), and
        # the ladder that links them — which the passage follows, rather than
        # working the order out from the ages.
        self.branch_young = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=9,
        )
        self.branch_mid = Branch.objects.create(
            name="Louveteaux", min_age_dec_31=10, max_age_dec_31=12,
        )
        self.branch_old = Branch.objects.create(
            name="Pionniers", min_age_dec_31=13, max_age_dec_31=17,
        )
        self.branch_young.promotes_to = self.branch_mid
        self.branch_mid.promotes_to = self.branch_old
        self.branch_old.is_top = True
        Branch.objects.bulk_update(
            [self.branch_young, self.branch_mid, self.branch_old],
            ["promotes_to", "is_top"],
        )

        # Sections (one per branch)
        self.section_young = Section.objects.create(
            name="Baladins", branch=self.branch_young,
        )
        self.section_mid = Section.objects.create(
            name="Louveteaux", branch=self.branch_mid,
        )
        self.section_old = Section.objects.create(
            name="Pionniers", branch=self.branch_old,
        )

        # Freeze "today" on the passage trigger date (May 1 of the target year)
        # so run_passage's date gate passes regardless of when the suite runs.
        self._today_patcher = mock.patch(
            "members.tasks._today", return_value=date(next_name, 5, 1),
        )
        self._today_patcher.start()
        self.addCleanup(self._today_patcher.stop)


class ChildMovesToNextBranchTest(PassageTestBase):
    """Child aging out of current branch moves to next branch."""

    def test_child_aging_out_moves_to_next_branch(self):
        """A 9-year-old (turns 10 before Dec 31 next year) should move to Louveteaux."""
        dec_31_next = self.next_year.name  # the Dec 31 inside that school year
        # Birthday: turns 10 before Dec 31 of next school year
        birthday = timezone.now().date().replace(year=dec_31_next - 10) + timedelta(days=1)
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            birthday=birthday,
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )

        run_passage()

        next_enrollment = Enrollment.objects.get(user=child, school_year=self.next_year)
        self.assertEqual(next_enrollment.section, self.section_mid)


class ChildStaysInBranchTest(PassageTestBase):
    """Child still within branch age range stays in same section."""

    def test_child_stays_in_branch(self):
        """An 8-year-old stays in Baladins."""
        dec_31_next = self.next_year.name  # the Dec 31 inside that school year
        birthday = timezone.now().date().replace(year=dec_31_next - 8)
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            birthday=birthday,
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )

        run_passage()

        next_enrollment = Enrollment.objects.get(user=child, school_year=self.next_year)
        self.assertEqual(next_enrollment.section, self.section_young)


class ChildAgesOutTest(PassageTestBase):
    """Child exceeding oldest branch becomes Animateur."""

    def test_child_exceeding_oldest_branch_becomes_animateur(self):
        """A 17-year-old (turns 18 before Dec 31) ages out → Animateur."""
        dec_31_next = self.next_year.name  # the Dec 31 inside that school year
        birthday = timezone.now().date().replace(year=dec_31_next - 18)
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            birthday=birthday,
        )
        Enrollment.objects.create(
            user=child, section=self.section_old, school_year=self.current_year,
        )

        run_passage()

        child.refresh_from_db()
        self.assertEqual(child.primary_role, self.role_animateur)

    def test_aged_out_child_removed_from_household(self):
        """Aged-out child's ParentChild links are deleted."""
        dec_31_next = self.next_year.name  # the Dec 31 inside that school year
        birthday = timezone.now().date().replace(year=dec_31_next - 18)
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            birthday=birthday,
        )
        parent = Person.objects.create(
            first_name="Parent", last_name="Test",
            primary_role=self.role_parent, status="a",
        )
        ParentChild.objects.create(parent=parent, child=child)
        Enrollment.objects.create(
            user=child, section=self.section_old, school_year=self.current_year,
        )

        run_passage()

        self.assertFalse(ParentChild.objects.filter(child=child).exists())


class NextSectionOverrideTest(PassageTestBase):
    """Manual next_section override is respected."""

    def test_manual_override_assigns_correct_section(self):
        """next_section takes priority over the age calculation.

        The birthday is pinned so the age path alone keeps the child in
        ``section_young`` (age 8 → Baladins, max 9). The override is therefore
        the only reason they end up in ``section_mid``, so deleting the override
        branch fails here — with a "now - 8 years" birthday the age path landed
        in ``section_mid`` by itself and the test proved nothing.
        """
        birthday = date(self.next_year.name - 8, 6, 1)
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            next_section=self.section_mid,
            birthday=birthday,
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )

        run_passage()

        next_enrollment = Enrollment.objects.get(user=child, school_year=self.next_year)
        self.assertEqual(next_enrollment.section, self.section_mid)


class AlphabeticalSectionTest(PassageTestBase):
    """When multiple sections exist in a branch, alphabetically first is chosen."""

    def test_alphabetically_first_section_chosen(self):
        """Two sections in mid branch → 'Aigles' is chosen before 'Louveteaux'."""
        section_aigles = Section.objects.create(
            name="Aigles", branch=self.branch_mid,
        )
        dec_31_next = self.next_year.name  # the Dec 31 inside that school year
        birthday = timezone.now().date().replace(year=dec_31_next - 10)
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            birthday=birthday,
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )

        run_passage()

        next_enrollment = Enrollment.objects.get(user=child, school_year=self.next_year)
        self.assertEqual(next_enrollment.section, section_aigles)


class SkipInactiveChildrenTest(PassageTestBase):
    """Inactive children and those without birthday are skipped."""

    def test_archived_child_skipped(self):
        archived = Person.objects.create(
            first_name="Archived", last_name="Child",
            primary_role=self.role_anime, status="ar",
            birthday=timezone.now().date() - timedelta(days=365 * 8),
        )
        Enrollment.objects.create(
            user=archived, section=self.section_young, school_year=self.current_year,
        )

        run_passage()

        self.assertFalse(
            Enrollment.objects.filter(user=archived, school_year=self.next_year).exists()
        )

    def test_child_without_birthday_skipped(self):
        no_bday = Person.objects.create(
            first_name="NoBday", last_name="Child",
            primary_role=self.role_anime, status="a",
        )
        Enrollment.objects.create(
            user=no_bday, section=self.section_young, school_year=self.current_year,
        )

        run_passage()

        self.assertFalse(
            Enrollment.objects.filter(user=no_bday, school_year=self.next_year).exists()
        )


class NoNextYearTest(TroopSettingsTestCase):
    """Passage handles missing next school year gracefully."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )

    def test_no_next_year_returns_early(self):
        # Delete any future school years
        current = SchoolYear.current()
        SchoolYear.objects.filter(start_date__gt=current.start_date).delete()
        result = run_passage()
        self.assertIsNone(result)


class PassageGuardTest(PassageTestBase):
    """Date gate + idempotency marker: the daily task must (a) not promote
    before the trigger date, (b) catch up if the trigger day was missed because
    Celery was down, and (c) never process the same target year twice."""

    def _make_child(self, next_section=None):
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            next_section=next_section,
            birthday=timezone.now().date() - timedelta(days=365 * 8),
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )
        return child

    def test_skips_before_trigger_date(self):
        """Before May 1 of the target year the date gate skips; nothing happens."""
        child = self._make_child()
        with mock.patch(
            "members.tasks._today",
            return_value=date(self.next_year.name, 4, 30),
        ):
            run_passage()

        self.assertFalse(
            Enrollment.objects.filter(user=child, school_year=self.next_year).exists()
        )
        # Marker must NOT be set, otherwise catch-up would be blocked.
        self.assertIsNone(TroopSettings.get_settings().last_passage_school_year)

    def test_catchup_after_missed_trigger_day(self):
        """Celery down on/around May 1: an April tick does nothing, the next
        start (mid-June) performs the passage."""
        child = self._make_child()

        with mock.patch(
            "members.tasks._today",
            return_value=date(self.next_year.name, 4, 30),
        ):
            run_passage()
        self.assertFalse(
            Enrollment.objects.filter(user=child, school_year=self.next_year).exists()
        )

        # Next start after the outage → passage runs and marks the year done.
        with mock.patch(
            "members.tasks._today",
            return_value=date(self.next_year.name, 6, 15),
        ):
            run_passage()
        self.assertTrue(
            Enrollment.objects.filter(user=child, school_year=self.next_year).exists()
        )
        self.assertEqual(
            TroopSettings.get_settings().last_passage_school_year, self.next_year.name
        )

    def test_second_run_is_a_noop(self):
        """Once the marker is set, a later daily tick must not reprocess —
        notably it must not re-derive sections by age after the manual override
        has already been applied and cleared."""
        child = self._make_child(next_section=self.section_mid)

        # First run (setUp patches _today to the trigger date): override applied.
        run_passage()
        self.assertEqual(
            Enrollment.objects.get(user=child, school_year=self.next_year).section,
            self.section_mid,
        )
        child.refresh_from_db()
        self.assertIsNone(child.next_section)

        # A later tick → marker set → no-op. Enrollment unchanged.
        with mock.patch(
            "members.tasks._today",
            return_value=date(self.next_year.name, 6, 15),
        ):
            run_passage()
        self.assertEqual(
            Enrollment.objects.get(user=child, school_year=self.next_year).section,
            self.section_mid,
        )


class PassageCustomDayTest(PassageTestBase):
    """The date gate follows the troop's passage day, not a hardcoded 1 May.

    ``PassageTestBase`` freezes today on 1 May of the target year, so moving
    the passage day around that date decides whether the daily task acts.
    """

    def _child(self):
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            next_section=self.section_mid,
            birthday=timezone.now().date() - timedelta(days=365 * 8),
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )
        return child

    def _set_passage_day(self, month, day):
        troop = TroopSettings.get_settings()
        troop.passage_month, troop.passage_day = month, day
        troop.save(update_fields=["passage_month", "passage_day"])

    def test_a_later_passage_day_blocks_the_run(self):
        self._set_passage_day(6, 1)
        child = self._child()

        run_passage()

        self.assertFalse(
            Enrollment.objects.filter(user=child, school_year=self.next_year).exists()
        )
        # Marker must stay unset, or the catch-up would never happen.
        self.assertIsNone(TroopSettings.get_settings().last_passage_school_year)

    def test_an_earlier_passage_day_lets_it_run(self):
        self._set_passage_day(4, 1)
        child = self._child()

        run_passage()

        self.assertEqual(
            Enrollment.objects.get(user=child, school_year=self.next_year).section,
            self.section_mid,
        )


class AgeReferenceConsistencyTest(PassageTestBase):
    """``run_passage`` and ``Person.age_on_dec_31`` must measure the same day.

    Regression: the task used to take the age on 31 December of the calendar
    year *after* the target school year — a day outside that school year, and a
    full year later than the age every other call site reckons with.
    """

    def test_the_age_is_the_one_inside_the_target_school_year(self):
        # 9 on 31 Dec of the target school year → Baladins (6-9): the child
        # stays.
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            birthday=date(self.next_year.name - 9, 6, 1),
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )
        self.assertEqual(child.age_on_dec_31(self.next_year), 9)

        run_passage()

        next_enrollment = Enrollment.objects.get(user=child, school_year=self.next_year)
        self.assertEqual(next_enrollment.section, self.section_young)
