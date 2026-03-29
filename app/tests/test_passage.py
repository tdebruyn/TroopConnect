from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from members.models import (
    Person, Role, SchoolYear, Section, Branch, Enrollment, ParentChild, Account,
)
from members.tasks import run_passage
from post_office.models import EmailTemplate


class PassageTestBase(TestCase):
    """Shared setup for passage tests."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )

    def setUp(self):
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

        # Branches: Baladins (6-9), Louveteaux (10-12), Pionniers (13-17)
        self.branch_young = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=9,
        )
        self.branch_mid = Branch.objects.create(
            name="Louveteaux", min_age_dec_31=10, max_age_dec_31=12,
        )
        self.branch_old = Branch.objects.create(
            name="Pionniers", min_age_dec_31=13, max_age_dec_31=17,
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


class ChildMovesToNextBranchTest(PassageTestBase):
    """Child aging out of current branch moves to next branch."""

    def test_child_aging_out_moves_to_next_branch(self):
        """A 9-year-old (turns 10 before Dec 31 next year) should move to Louveteaux."""
        dec_31_next = self.next_year.name + 1  # calendar year of Dec 31
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
        dec_31_next = self.next_year.name + 1
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
        dec_31_next = self.next_year.name + 1
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
        dec_31_next = self.next_year.name + 1
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
        """When next_section is set, it takes priority over age calculation."""
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            next_section=self.section_mid,
            birthday=timezone.now().date() - timedelta(days=365 * 8),
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )

        run_passage()

        next_enrollment = Enrollment.objects.get(user=child, school_year=self.next_year)
        self.assertEqual(next_enrollment.section, self.section_mid)

    def test_manual_override_cleared_after_use(self):
        """next_section is reset to None after passage."""
        child = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
            next_section=self.section_mid,
            birthday=timezone.now().date() - timedelta(days=365 * 8),
        )
        Enrollment.objects.create(
            user=child, section=self.section_young, school_year=self.current_year,
        )

        run_passage()

        child.refresh_from_db()
        self.assertIsNone(child.next_section)


class AlphabeticalSectionTest(PassageTestBase):
    """When multiple sections exist in a branch, alphabetically first is chosen."""

    def test_alphabetically_first_section_chosen(self):
        """Two sections in mid branch → 'Aigles' is chosen before 'Louveteaux'."""
        section_aigles = Section.objects.create(
            name="Aigles", branch=self.branch_mid,
        )
        dec_31_next = self.next_year.name + 1
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


class NoNextYearTest(TestCase):
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
