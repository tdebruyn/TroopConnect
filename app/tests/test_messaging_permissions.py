from django.test import Client, TestCase
from django.urls import reverse

from members.models import Account, Enrollment, Person, Role, SchoolYear, Section


class MessagingPermissionTest(TestCase):
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

        # Animateur (primary role "a") — can send to section
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

        # Plain parent — cannot send messages
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

    def test_parent_cannot_access_compose(self):
        self.client.login(email="parent@test.com", password="testpass")
        response = self.client.get("/messaging/compose/")
        self.assertEqual(response.status_code, 404)

    def test_animateur_can_access_compose(self):
        self.client.login(email="anim@test.com", password="testpass")
        response = self.client.get("/messaging/compose/")
        self.assertEqual(response.status_code, 200)

    def test_staff_can_access_compose(self):
        self.client.login(email="staff@test.com", password="testpass")
        response = self.client.get("/messaging/compose/")
        self.assertEqual(response.status_code, 200)

    def test_animateur_can_view_history(self):
        self.client.login(email="anim@test.com", password="testpass")
        response = self.client.get("/messaging/history/")
        self.assertEqual(response.status_code, 200)

    def test_staff_can_view_history(self):
        self.client.login(email="staff@test.com", password="testpass")
        response = self.client.get("/messaging/history/")
        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_view_history(self):
        self.client.login(email="parent@test.com", password="testpass")
        response = self.client.get("/messaging/history/")
        self.assertEqual(response.status_code, 404)

    def test_animateur_history_shows_compose_button(self):
        """The history page itself offers a way to compose.

        Counted rather than asserted by label: base.html renders "Envoyer un
        message" in the nav dropdown for anyone who can compose, so asserting
        the label passed even with the page's own button deleted.
        """
        self.client.login(email="anim@test.com", password="testpass")
        response = self.client.get("/messaging/history/")
        html = response.content.decode()
        # one link from the nav dropdown, one from the page body
        self.assertEqual(html.count(reverse("messaging:compose")), 2)

    def test_staff_history_shows_compose_button(self):
        self.client.login(email="staff@test.com", password="testpass")
        response = self.client.get("/messaging/history/")
        html = response.content.decode()
        self.assertEqual(html.count(reverse("messaging:compose")), 2)
