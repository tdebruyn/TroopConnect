from datetime import date
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from members.models import Branch, Person, Role, SchoolYear


class PersonChildValidationTest(TestCase):
    """Person.clean() requires a birthday and a sex for children (Animé),
    since passage/promotion relies on birthday and section enrollment on sex.
    Other roles are unaffected."""

    def _child(self, **overrides):
        defaults = dict(
            first_name="Test",
            last_name="Child",
            primary_role=Role.objects.get(short=Person.CHILD_ROLE_SHORT),
            birthday=date(2017, 6, 15),
            sex=Person.Sex.MALE,
        )
        defaults.update(overrides)
        return Person(**defaults)

    def test_child_with_birthday_and_sex_is_valid(self):
        self._child().full_clean()  # must not raise

    def test_child_without_birthday_is_invalid(self):
        with self.assertRaises(ValidationError) as cm:
            self._child(birthday=None).full_clean()
        self.assertIn("birthday", cm.exception.message_dict)

    def test_child_without_sex_is_invalid(self):
        with self.assertRaises(ValidationError) as cm:
            self._child(sex=None).full_clean()
        self.assertIn("sex", cm.exception.message_dict)

    def test_non_child_does_not_require_birthday_or_sex(self):
        parent = Person(
            first_name="Parent",
            last_name="One",
            primary_role=Role.objects.get(short="p"),
        )
        parent.full_clean()  # must not raise


class PersonBranchAgeTest(TestCase):
    """age_on_dec_31 / age_fits_branch (rule 2 helpers).

    Branches: 6-9 (Baladins), 10-12 (Louveteaux). Boundaries are inclusive on
    both ends. Ages are computed as (dec_31 - birthday).days // 365, mirroring
    run_passage."""

    def setUp(self):
        self.year = SchoolYear.current()
        Branch.objects.create(name="Baladins", min_age_dec_31=6, max_age_dec_31=9)
        Branch.objects.create(name="Louveteaux", min_age_dec_31=10, max_age_dec_31=12)

    def _person(self, birthday):
        return Person.objects.create(
            first_name="Age",
            last_name="Test",
            primary_role=Role.objects.get(short="p"),
            birthday=birthday,
        )

    def test_age_on_dec_31_simple(self):
        # 10th birthday in June of the school year's end year (year.name + 1)
        person = self._person(date(self.year.name - 10, 6, 15))
        self.assertEqual(person.age_on_dec_31(), 10)

    def test_age_on_dec_31_boundary_birthday_on_dec_31(self):
        # Birthday exactly on Dec 31: (dec_31 - birthday).days // 365
        person = self._person(date(self.year.name - 9, 12, 31))
        self.assertEqual(person.age_on_dec_31(), 9)

    def test_age_on_dec_31_boundary_birthday_on_jan_1(self):
        # Calendar age on Dec 31 is 8, but the days//365 formula (which
        # mirrors run_passage) counts the accumulated leap days: an 8-year
        # span always contains 1-2 of them, so the result is 9.
        person = self._person(date(self.year.name - 8, 1, 1))
        self.assertEqual(person.age_on_dec_31(), 9)

    def test_age_on_dec_31_none_without_birthday(self):
        person = self._person(None)
        self.assertIsNone(person.age_on_dec_31())

    def test_age_on_dec_31_none_without_school_year(self):
        person = self._person(date(self.year.name - 8, 6, 15))
        with mock.patch.object(
            SchoolYear, "current", staticmethod(lambda: None)
        ):
            self.assertIsNone(person.age_on_dec_31())

    def test_age_on_dec_31_explicit_school_year(self):
        person = self._person(date(self.year.name - 8, 6, 15))
        explicit = SchoolYear.objects.create(
            name=self.year.name + 5,
            start_date=date(self.year.name + 5, 8, 1),
            end_date=date(self.year.name + 6, 7, 31),
        )
        self.assertEqual(person.age_on_dec_31(explicit), 13)

    def test_age_fits_branch_inside_range(self):
        person = self._person(date(self.year.name - 7, 3, 1))
        self.assertTrue(person.age_fits_branch())

    def test_age_fits_branch_at_min_boundary(self):
        person = self._person(date(self.year.name - 6, 12, 31))
        self.assertTrue(person.age_fits_branch())

    def test_age_fits_branch_at_max_boundary(self):
        # Turns 12 exactly on Dec 31 → computed age 12 = max of Louveteaux.
        person = self._person(date(self.year.name - 12, 12, 31))
        self.assertTrue(person.age_fits_branch())

    def test_age_fits_branch_younger_than_all_branches(self):
        person = self._person(date(self.year.name - 3, 6, 15))
        self.assertFalse(person.age_fits_branch())

    def test_age_fits_branch_older_than_all_branches(self):
        person = self._person(date(self.year.name - 40, 6, 15))
        self.assertFalse(person.age_fits_branch())

    def test_age_fits_branch_false_without_birthday(self):
        person = self._person(None)
        self.assertFalse(person.age_fits_branch())

    def test_age_fits_branch_ignores_branch_missing_ages(self):
        # A Branch with a null age bound must not match anything.
        Branch.objects.create(name="NoBounds", min_age_dec_31=None, max_age_dec_31=None)
        person = self._person(date(self.year.name - 20, 6, 15))
        self.assertFalse(person.age_fits_branch())

    def test_age_fits_branch_false_without_branches(self):
        Branch.objects.all().delete()
        person = self._person(date(self.year.name - 8, 6, 15))
        self.assertFalse(person.age_fits_branch())
