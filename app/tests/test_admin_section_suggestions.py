"""The section dropdowns on the member page lead with the age-fit sections.

A child enrolling has no section yet, and the admin has to pick one from a
list that mixes every branch. The form groups the sections whose branch age
range contains the child's age (on the troop's reference day, for that
school year) above a divider, and leaves every other section below it.
"""

from datetime import date

from django.urls import reverse
from django.utils import translation

from members.forms import AdminUserUpdateForm
from members.models import (
    Account,
    Branch,
    Enrollment,
    Person,
    Role,
    SchoolYear,
    Section,
)

from .base import TroopSettingsTestCase


def resolved_choices(person, field_name="current_section"):
    """The field's choices with their labels rendered in English.

    Lazy ``gettext`` labels resolve in the active language, so render them
    inside the override rather than comparing proxies after it ends.
    """
    with translation.override("en"):
        field = AdminUserUpdateForm(instance=person).fields[field_name]
        choices = []
        for first, second in field.choices:
            if isinstance(second, list):
                choices.append(
                    (str(first), [(pk, str(name)) for pk, name in second])
                )
            else:
                choices.append((str(first), str(second)))
        return choices


def groups(choices):
    """The optgroups of a choice list, as (label, [section names])."""
    return [
        (label, [name for _pk, name in options])
        for label, options in choices[1:]
        if isinstance(options, list)
    ]


class AdminSectionSuggestionTest(TroopSettingsTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year = SchoolYear.current()
        cls.role_child = Role.objects.get(short=Person.CHILD_ROLE_SHORT)
        cls.role_parent = Role.objects.get(short="p")

        cls.baladins = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=9
        )
        cls.louveteaux = Branch.objects.create(
            name="Louveteaux", min_age_dec_31=10, max_age_dec_31=12
        )
        cls.baladins_mixed = Section.objects.create(
            name="Baladins A", branch=cls.baladins, sex=Section.Sex.BOTH
        )
        Section.objects.create(
            name="Baladins boys", branch=cls.baladins, sex=Section.Sex.MALE
        )
        Section.objects.create(
            name="Baladins girls", branch=cls.baladins, sex=Section.Sex.FEMALE
        )
        Section.objects.create(
            name="Louveteaux A", branch=cls.louveteaux, sex=Section.Sex.BOTH
        )

    def child(self, birthday, sex=Section.Sex.MALE, role=None):
        return Person.objects.create(
            first_name="Enfant",
            last_name="Test",
            primary_role=role or self.role_child,
            birthday=birthday,
            sex=sex,
        )

    def test_an_unassigned_child_leads_with_the_sections_for_their_age(self):
        choices = resolved_choices(self.child(date(self.year.name - 8, 6, 15)))

        self.assertEqual(
            groups(choices),
            [
                ("Suitable for their age", ["Baladins A", "Baladins boys"]),
                ("Other sections", ["Baladins girls", "Louveteaux A"]),
            ],
        )

    def test_the_empty_choice_stays_above_both_groups(self):
        choices = resolved_choices(self.child(date(self.year.name - 8, 6, 15)))

        self.assertEqual(choices[0][0], "")

    def test_a_section_for_the_other_sex_is_never_suggested(self):
        choices = resolved_choices(
            self.child(date(self.year.name - 8, 6, 15), sex=Section.Sex.FEMALE)
        )

        suggested = groups(choices)[0][1]
        self.assertIn("Baladins A", suggested)
        self.assertIn("Baladins girls", suggested)
        self.assertNotIn("Baladins boys", suggested)

    def test_an_enrolled_child_keeps_the_flat_list(self):
        person = self.child(date(self.year.name - 9, 6, 15))
        Enrollment.objects.create(
            user=person, section=self.baladins_mixed, school_year=self.year
        )

        self.assertEqual(groups(resolved_choices(person)), [])

    def test_the_next_year_field_uses_that_years_age(self):
        if not SchoolYear.objects.filter(name=self.year.name + 1).exists():
            SchoolYear.objects.create_year(self.year.name + 1)
        person = self.child(date(self.year.name - 9, 6, 15))

        current = groups(resolved_choices(person, "current_section"))
        upcoming = groups(resolved_choices(person, "next_section"))

        self.assertEqual(
            current[0], ("Suitable for their age", ["Baladins A", "Baladins boys"])
        )
        self.assertEqual(
            upcoming[0], ("Suitable for their age", ["Louveteaux A"])
        )
        self.assertIn("Baladins A", upcoming[1][1])

    def test_a_new_member_is_suggested_by_age_before_their_role_is_set(self):
        person = self.child(
            date(self.year.name - 8, 6, 15),
            role=Role.objects.get(short="n"),
        )

        self.assertEqual(
            groups(resolved_choices(person)),
            [
                ("Suitable for their age", ["Baladins A", "Baladins boys"]),
                ("Other sections", ["Baladins girls", "Louveteaux A"]),
            ],
        )

    def test_a_member_without_a_birthday_keeps_the_flat_list(self):
        self.assertEqual(groups(resolved_choices(self.child(None))), [])

    def test_an_adult_is_not_suggested_a_child_section(self):
        person = self.child(
            date(self.year.name - 40, 6, 15), role=self.role_parent
        )

        self.assertEqual(groups(resolved_choices(person)), [])

    def test_the_page_renders_the_two_group_headings(self):
        staff = Account.objects.create_user(
            email="staff@test.be",
            password="pass",
            is_staff=True,
            person=Person.objects.create(
                first_name="Admin",
                last_name="Staff",
                primary_role=self.role_parent,
                status="a",
            ),
        )
        self.client.force_login(staff)
        person = self.child(date(self.year.name - 8, 6, 15))

        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": person.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Correspondant à son âge")
        self.assertContains(response, "Autres sections")
