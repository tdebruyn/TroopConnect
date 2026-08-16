from django.test import TestCase
from django.urls import reverse

from members.models import Account, Person, Role


class AdminLinkTest(TestCase):
    """The profile dropdown links to the Django admin for superusers only."""

    def setUp(self):
        self.admin_url = reverse("admin:index")
        self.role_parent = Role.objects.get(short="p")

        self.superuser = Account.objects.create_user(
            email="super@test.be",
            password="pass",
            is_staff=True,
            is_superuser=True,
            person=Person.objects.create(
                first_name="Super", last_name="User",
                primary_role=self.role_parent, status="a",
            ),
        )
        self.staff_user = Account.objects.create_user(
            email="staff@test.be",
            password="pass",
            is_staff=True,
            person=Person.objects.create(
                first_name="Staff", last_name="Only",
                primary_role=self.role_parent, status="a",
            ),
        )
        self.regular_user = Account.objects.create_user(
            email="parent@test.be",
            password="pass",
            person=Person.objects.create(
                first_name="Regular", last_name="Parent",
                primary_role=self.role_parent, status="a",
            ),
        )

    def test_superuser_sees_admin_link(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.admin_url)

    def test_staff_non_superuser_does_not_see_admin_link(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.admin_url)

    def test_regular_user_does_not_see_admin_link(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.admin_url)

    def test_anonymous_user_does_not_see_admin_link(self):
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.admin_url)
