from django.test import TestCase, Client

from members.models import Account, Person, Role, SchoolYear, Section, Enrollment
from post_office.models import EmailTemplate


class MessagingPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create the email template the signal needs
        EmailTemplate.objects.create(
            name="new_child_staff",
            subject="New profile",
            content="Test",
        )

    def setUp(self):
        self.client = Client()
        self.current_year = SchoolYear.current()

        # Create roles
        self.role_animateur = Role.objects.get(short="a")
        self.role_parent = Role.objects.get(short="p")
        self.role_ar = Role.objects.get(short="ar")
        self.role_admin = Role.objects.get(short="ad")

        # Create section
        self.section = Section.objects.create(name="Louveteaux")

        # Animateur (primary role "a") — can send to section, NOT to all
        self.anim_person = Person.objects.create(
            first_name="Jean", last_name="Anim",
            primary_role=self.role_animateur, status="a",
        )
        self.anim_account = Account.objects.create_user(
            email="anim@test.com", password="testpass",
            person=self.anim_person,
        )

        # Staff d'unité: Parent with secondary "ar" — can send to all
        self.staff_person = Person.objects.create(
            first_name="Marie", last_name="Staff",
            primary_role=self.role_parent, status="a",
        )
        self.staff_person.roles.add(self.role_ar)
        self.staff_account = Account.objects.create_user(
            email="staff@test.com", password="testpass",
            person=self.staff_person,
        )

        # Plain parent — cannot send to section or all
        self.parent_person = Person.objects.create(
            first_name="Paul", last_name="Parent",
            primary_role=self.role_parent, status="a",
        )
        self.parent_account = Account.objects.create_user(
            email="parent@test.com", password="testpass",
            person=self.parent_person,
        )

        # Enroll animateur in section
        Enrollment.objects.create(
            user=self.anim_person, section=self.section,
            school_year=self.current_year,
        )

    def test_animateur_cannot_access_compose_all(self):
        self.client.login(email="anim@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/compose-all/")
        self.assertEqual(response.status_code, 404)

    def test_staff_can_access_compose_all(self):
        self.client.login(email="staff@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/compose-all/")
        self.assertEqual(response.status_code, 200)

    def test_animateur_can_access_section_compose(self):
        self.client.login(email="anim@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/compose/")
        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_access_section_compose(self):
        self.client.login(email="parent@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/compose/")
        self.assertEqual(response.status_code, 404)

    def test_animateur_can_view_history(self):
        self.client.login(email="anim@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/history/")
        self.assertEqual(response.status_code, 200)

    def test_staff_can_view_history(self):
        self.client.login(email="staff@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/history/")
        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_view_history(self):
        self.client.login(email="parent@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/history/")
        self.assertEqual(response.status_code, 404)

    def test_animateur_history_hides_send_all_button(self):
        self.client.login(email="anim@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/history/")
        self.assertNotContains(response, "Message à tous les membres")

    def test_staff_history_shows_send_all_button(self):
        self.client.login(email="staff@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/history/")
        self.assertContains(response, "Message à tous les membres")

    def test_animateur_history_shows_section_compose_button(self):
        self.client.login(email="anim@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/history/")
        self.assertContains(response, "Message à ma section")

    def test_staff_without_animateur_primary_no_section_compose_button(self):
        """Staff (primary role parent) should not see 'Message à ma section'."""
        self.client.login(email="staff@test.com", password="testpass")
        response = self.client.get("/messaging/animateurs/history/")
        self.assertNotContains(response, "Message à ma section")
