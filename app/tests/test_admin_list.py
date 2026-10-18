from django.test import TestCase
from django.urls import reverse
from post_office.models import EmailTemplate

from members.models import (
    Account,
    Branch,
    Enrollment,
    Person,
    Role,
    SchoolYear,
    Section,
)


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

        # The suite starts with roles and school years but no branch preset,
        # so the section filter needs one created for it.
        branch = Branch.objects.first() or Branch.objects.create(name="Test branch")
        cls.section = Section.objects.exclude(branch=None).first()
        if cls.section is None:
            cls.section = Section.objects.create(name="Test section", branch=branch)
        cls.current_year = SchoolYear.current()
        Enrollment.objects.create(
            user=cls.person1, section=cls.section, school_year=cls.current_year,
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

    def test_school_year_defaults_to_current(self):
        """The year selector always names a year; it is never blank."""
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("members:admin_list"))
        self.assertEqual(
            str(response.context["filter"].form["year"].value()),
            str(self.current_year.pk),
        )
        self.assertContains(
            response, f'<option value="{self.current_year.pk}"', status_code=200
        )

    def test_section_filter_uses_current_year_without_explicit_year(self):
        """Filtering by section without ?year= uses the current school year.

        With no year the enrollment lookup matched nothing, so choosing a
        section returned an empty list.
        """
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:admin_list"), {"section": self.section.pk}
        )
        self.assertContains(response, "Alice")
        self.assertNotContains(response, "Bob")

    def test_htmx_request_returns_only_the_results(self):
        """A live filter swaps the table, not the form above it."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:admin_list"),
            {"year": self.current_year.pk, "first_name": "Alice"},
            headers={"HX-Request": "true"},
        )
        self.assertTemplateUsed(response, "members/_admin_list_results.html")
        self.assertNotContains(response, "<form")
        self.assertContains(response, "Alice")

    def test_full_page_keeps_the_filter_form(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("members:admin_list"))
        self.assertTemplateUsed(response, "members/admin_list.html")
        self.assertContains(response, 'id="admin-filter-form"')

    def test_section_column_carries_the_year_selector(self):
        """The section column is that year's enrollment, and chooses it."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:admin_list"), {"year": self.current_year.pk}
        )
        self.assertContains(response, f'<option value="{self.current_year.pk}"')
        self.assertContains(response, self.current_year.range)

    def test_unknown_school_year_falls_back_instead_of_erroring(self):
        """A stale or malformed ?year= must still render the list.

        The year is round-tripped through the session filter, so a value that
        no longer resolves is reachable from an ordinary navigation.
        """
        self.client.force_login(self.staff_user)
        for bad_year in ("999999", "not-a-number"):
            response = self.client.get(
                reverse("members:admin_list"), {"year": bad_year}
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

    def test_filter_persists_across_navigation(self):
        """A filter survives navigating away (edit page) and back."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:admin_list"), {"first_name": "Alice"}
        )
        self.assertContains(response, "Alice")

        # Coming back with no filter params restores the saved filter.
        response = self.client.get(reverse("members:admin_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("first_name=Alice", response.url)

    def test_reset_clears_saved_filter(self):
        """The Reset action clears the saved filter."""
        self.client.force_login(self.staff_user)
        self.client.get(reverse("members:admin_list"), {"first_name": "Alice"})

        response = self.client.get(reverse("members:admin_list"), {"reset": "1"})
        self.assertEqual(response.status_code, 302)

        # After reset, a fresh visit shows the unfiltered list again.
        response = self.client.get(reverse("members:admin_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bob")

    def test_an_animateur_is_not_flagged_for_the_branch_age(self):
        """An animateur is enrolled in the section they lead; their age has
        nothing to do with its branch."""
        branch = Branch.objects.create(
            name="Age branch", min_age_dec_31=8, max_age_dec_31=12
        )
        section = Section.objects.create(name="Age section", branch=branch)
        Enrollment.objects.create(
            user=self.person3,
            section=section,
            school_year=self.current_year,
        )

        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("members:admin_list"))
        people = {person.pk: person for person in response.context["object_list"]}
        self.assertFalse(people[self.person3.pk].age_mismatch)

    def test_a_participant_is_still_flagged_for_the_branch_age(self):
        branch = Branch.objects.create(
            name="Young branch", min_age_dec_31=8, max_age_dec_31=9
        )
        section = Section.objects.create(name="Young section", branch=branch)
        Enrollment.objects.create(
            user=self.person2,
            section=section,
            school_year=self.current_year,
        )

        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("members:admin_list"))
        people = {person.pk: person for person in response.context["object_list"]}
        self.assertTrue(people[self.person2.pk].age_mismatch)
