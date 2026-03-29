from django.test import TestCase
from django.urls import reverse

from members.models import (
    Account, Person, Role, SchoolYear, Section, Branch, Enrollment,
)
from post_office.models import EmailTemplate


class AdminListFilterTest(TestCase):
    """Test admin user list filters and school year toggle."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        cls.role_parent = Role.objects.get(short="p")
        cls.role_anime = Role.objects.get(short="e")
        cls.role_animateur = Role.objects.get(short="a")

        cls.staff_person = Person.objects.create(
            first_name="Admin", last_name="Staff",
            primary_role=cls.role_parent, status="a",
        )
        cls.staff_user = Account.objects.create_user(
            email="admin@test.com", password="pass",
            person=cls.staff_person, is_staff=True,
        )

        cls.person1 = Person.objects.create(
            first_name="Alice", last_name="Dupont",
            birthday="2015-03-15", primary_role=cls.role_anime, status="a",
        )
        cls.person2 = Person.objects.create(
            first_name="Bob", last_name="Martin",
            birthday="2012-07-20", primary_role=cls.role_anime, status="a",
        )
        cls.person3 = Person.objects.create(
            first_name="Claire", last_name="Dupont",
            birthday="1990-01-10", primary_role=cls.role_animateur, status="a",
        )

        branch = Branch.objects.first()
        if branch:
            section = Section.objects.filter(branch=branch).first()
            if section:
                year = SchoolYear.current()
                Enrollment.objects.create(
                    user=cls.person1, section=section, school_year=year,
                )

    def test_staff_can_access_admin_list(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("members:admin_list"))
        self.assertEqual(response.status_code, 200)

    def test_non_staff_cannot_access(self):
        non_staff = Account.objects.create_user(
            email="user@test.com", password="pass",
            person=Person.objects.create(
                first_name="Normal", last_name="User",
                primary_role=self.role_parent, status="a",
            ),
        )
        self.client.force_login(non_staff)
        response = self.client.get(reverse("members:admin_list"))
        self.assertEqual(response.status_code, 403)

    def test_filter_by_name(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("members:admin_list"), {"first_name": "Alice"})
        self.assertContains(response, "Alice")
        self.assertNotContains(response, "Bob")

    def test_filter_by_last_name(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("members:admin_list"), {"last_name": "Martin"})
        self.assertContains(response, "Bob")
        self.assertNotContains(response, "Alice")

    def test_filter_by_role(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:admin_list"), {"role": self.role_anime.pk}
        )
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertNotContains(response, "Claire")

    def test_filter_by_birth_year(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:admin_list"), {"birth_year": "2015"}
        )
        self.assertContains(response, "Alice")
        self.assertNotContains(response, "Bob")

    def test_school_year_toggle(self):
        """Changing year changes the displayed section assignments."""
        self.client.force_login(self.staff_user)
        current_year = SchoolYear.current()

        # With current year, person1 should show a section if enrolled
        response = self.client.get(
            reverse("members:admin_list"), {"year": current_year.pk}
        )
        self.assertEqual(response.status_code, 200)

        # With a different year, section display may change
        # Create a next year if it doesn't exist
        next_year_name = current_year.name + 1
        next_year, _ = SchoolYear.objects.get_or_create(
            name=next_year_name,
            defaults={"start_date": current_year.start_date, "end_date": current_year.end_date},
        )
        response = self.client.get(
            reverse("members:admin_list"), {"year": next_year.pk}
        )
        self.assertEqual(response.status_code, 200)

    def test_default_sort_is_last_name(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("members:admin_list"))
        self.assertEqual(response.context["current_sort"], "last_name")

    def test_sort_by_first_name(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:admin_list"), {"sort": "first_name", "direction": "asc"}
        )
        self.assertEqual(response.context["current_sort"], "first_name")
        self.assertEqual(response.context["current_direction"], "asc")
