from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from members.models import Person, Role


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
