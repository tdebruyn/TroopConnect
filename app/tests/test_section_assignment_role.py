"""Assigning a section also settles the primary role.

A new member is listed as "Nouveau" until something makes them a participant
or a leader. That something is the section: below 18 on the school year's
reference day the member becomes Animé, at 18 or over Animateur. The current
year's section decides; a section prepared for next year only counts when
there is none this year.
"""

from datetime import date

from members.forms import AdminUserUpdateForm
from members.models import (
    Branch,
    Enrollment,
    Person,
    Role,
    SchoolYear,
    Section,
)

from .base import TroopSettingsTestCase


class SectionAssignmentRoleTest(TroopSettingsTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year = SchoolYear.current()
        if not SchoolYear.objects.filter(name=cls.year.name + 1).exists():
            SchoolYear.objects.create_year(cls.year.name + 1)
        cls.next_year = SchoolYear.objects.get(name=cls.year.name + 1)

        cls.role_nouveau = Role.objects.get(short="n")
        cls.role_anime = Role.objects.get(short="e")
        cls.role_animateur = Role.objects.get(short="a")

        branch = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=17
        )
        cls.section = Section.objects.create(
            name="Baladins A", branch=branch, sex=Section.Sex.BOTH
        )

    def person(self, birthday):
        return Person.objects.create(
            first_name="Enfant",
            last_name="Test",
            primary_role=self.role_nouveau,
            status="a",
            sex="M",
            birthday=birthday,
        )

    def form_data(self, person, **overrides):
        data = {
            "first_name": person.first_name,
            "last_name": person.last_name,
            "primary_role": person.primary_role.pk,
            "birthday": person.birthday.isoformat() if person.birthday else "",
            "sex": "M",
            "email": "",
            "current_section": "",
            "next_section": "",
        }
        data.update(overrides)
        return data

    def assign(self, person, **overrides):
        form = AdminUserUpdateForm(
            instance=person, data=self.form_data(person, **overrides)
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        person.refresh_from_db()
        return person

    def test_assigning_a_section_confirms_a_requested_member(self):
        person = self.person(date(self.year.name - 10, 6, 15))
        person.status = "r"
        person.save(update_fields=["status"])

        self.assign(person, current_section=self.section.pk)

        self.assertEqual(person.status, "a")

    def test_the_enrolment_itself_confirms_a_requested_member(self):
        person = self.person(date(self.year.name - 10, 6, 15))
        person.status = "r"
        person.save(update_fields=["status"])

        Enrollment.objects.create(
            user=person, section=self.section, school_year=self.year
        )

        person.refresh_from_db()
        self.assertEqual(person.status, "a")

    def test_an_archived_member_is_not_revived(self):
        person = self.person(date(self.year.name - 10, 6, 15))
        person.status = "ar"
        person.save(update_fields=["status"])

        Enrollment.objects.create(
            user=person, section=self.section, school_year=self.year
        )

        person.refresh_from_db()
        self.assertEqual(person.status, "ar")

    def test_a_child_assigned_a_section_becomes_anime(self):
        person = self.person(date(self.year.name - 10, 6, 15))

        self.assign(person, current_section=self.section.pk)

        self.assertEqual(person.primary_role, self.role_anime)

    def test_an_adult_assigned_a_section_becomes_animateur(self):
        person = self.person(date(self.year.name - 30, 6, 15))

        self.assign(person, current_section=self.section.pk)

        self.assertEqual(person.primary_role, self.role_animateur)

    def test_a_member_without_a_birthday_reads_as_an_adult(self):
        person = self.person(None)

        self.assign(person, current_section=self.section.pk)

        self.assertEqual(person.primary_role, self.role_animateur)

    def test_adult_status_is_read_on_thirty_first_december(self):
        # Eighteen on the reference day itself: a birthday late in December of
        # the year eighteen before.
        person = self.person(date(self.year.name - 18, 12, 30))
        self.assertEqual(person.age_on_dec_31(self.year), 18)

        self.assign(person, current_section=self.section.pk)

        self.assertEqual(person.primary_role, self.role_animateur)

    def test_seventeen_on_the_reference_day_stays_anime(self):
        person = self.person(date(self.year.name - 17, 12, 30))
        self.assertEqual(person.age_on_dec_31(self.year), 17)

        self.assign(person, current_section=self.section.pk)

        self.assertEqual(person.primary_role, self.role_anime)

    def test_a_next_years_section_uses_next_years_age(self):
        person = self.person(date(self.year.name - 17, 12, 30))

        self.assign(person, next_section=self.section.pk)

        self.assertEqual(person.primary_role, self.role_animateur)

    def test_the_current_years_section_wins_when_both_are_set(self):
        person = self.person(date(self.year.name - 17, 12, 30))

        self.assign(
            person,
            current_section=self.section.pk,
            next_section=self.section.pk,
        )

        self.assertEqual(person.primary_role, self.role_anime)

    def test_the_submitted_birthday_decides_the_role(self):
        person = self.person(None)

        self.assign(
            person,
            birthday=date(self.year.name - 10, 6, 15).isoformat(),
            current_section=self.section.pk,
        )

        self.assertEqual(person.primary_role, self.role_anime)

    def test_a_corrected_birthday_is_used_for_the_role(self):
        person = self.person(date(self.year.name - 40, 6, 15))

        self.assign(
            person,
            birthday=date(self.year.name - 10, 6, 15).isoformat(),
            current_section=self.section.pk,
        )

        self.assertEqual(person.primary_role, self.role_anime)
        self.assertEqual(person.birthday, date(self.year.name - 10, 6, 15))

    def test_no_section_leaves_the_role_alone(self):
        person = self.person(date(self.year.name - 10, 6, 15))

        self.assign(person)

        self.assertEqual(person.primary_role, self.role_nouveau)

    def test_an_existing_enrolment_keeps_its_role(self):
        person = self.person(date(self.year.name - 17, 12, 30))
        person.primary_role = self.role_anime
        person.save(update_fields=["primary_role"])
        Enrollment.objects.create(
            user=person, section=self.section, school_year=self.year
        )

        self.assign(
            person,
            current_section=self.section.pk,
            next_section=self.section.pk,
        )

        self.assertEqual(person.primary_role, self.role_anime)
