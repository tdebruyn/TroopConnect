from django.test import TestCase, Client

from members.models import Account, Branch, Section, Person, Role, SchoolYear, Enrollment, ParentChild
from post_office.models import EmailTemplate


class NavSectionsContextProcessorTest(TestCase):
    """Test that nav_sections context processor returns sections per user."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        cls.branch = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=8,
        )
        cls.section = Section.objects.create(name="Baladins 1", branch=cls.branch)

    def setUp(self):
        self.current_year = SchoolYear.current()
        self.role_parent = Role.objects.get(short="p")
        self.role_e = Role.objects.get(short="e")

    def test_staff_sees_all_sections(self):
        staff_person = Person.objects.create(
            first_name="Staff", last_name="User",
            primary_role=self.role_parent, status="a",
        )
        Account.objects.create_user(
            email="staff_nav@test.com", password="testpass",
            person=staff_person, is_staff=True,
        )

        self.client.login(email="staff_nav@test.com", password="testpass")
        response = self.client.get("/")
        nav_sections = response.context["nav_sections"]
        names = [s.name for s in nav_sections]
        self.assertIn("Baladins 1", names)

    def test_unauthenticated_sees_no_sections(self):
        response = self.client.get("/")
        nav_sections = response.context["nav_sections"]
        self.assertEqual(list(nav_sections), [])

    def test_parent_sees_children_sections(self):
        parent_person = Person.objects.create(
            first_name="Parent", last_name="Test",
            primary_role=self.role_parent, status="a",
        )
        child_person = Person.objects.create(
            first_name="Child", last_name="Test",
            primary_role=self.role_e, status="a",
        )
        ParentChild.objects.create(parent=parent_person, child=child_person, primary_contact=True)

        if self.current_year:
            Enrollment.objects.create(
                user=child_person, section=self.section,
                school_year=self.current_year,
            )

        Account.objects.create_user(
            email="parent_nav@test.com", password="testpass",
            person=parent_person,
        )

        self.client.login(email="parent_nav@test.com", password="testpass")
        response = self.client.get("/")
        nav_sections = response.context["nav_sections"]
        names = [s.name for s in nav_sections]
        self.assertIn("Baladins 1", names)
