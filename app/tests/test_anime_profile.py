from django.test import TestCase
from django.urls import reverse

from members.models import Account, Person, Role
from members.forms import AnimeProfileForm
from post_office.models import EmailTemplate


class AnimeProfileEditTest(TestCase):
    """Test Animé self-service profile editing (restricted fields)."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        role_anime = Role.objects.get(short="e")
        role_parent = Role.objects.get(short="p")

        cls.anime_person = Person.objects.create(
            first_name="Jean", last_name="Dupont",
            totem="Loup", address="Rue de Limal 1, 1300 Limal",
            phone="0470123456", primary_role=role_anime, status="a",
        )
        cls.anime_user = Account.objects.create_user(
            email="jean@test.com", password="pass", person=cls.anime_person,
        )

        cls.parent_person = Person.objects.create(
            first_name="Marie", last_name="Dupont",
            address="Rue de Limal 1, 1300 Limal",
            phone="0470654321", primary_role=role_parent, status="a",
        )
        cls.parent_user = Account.objects.create_user(
            email="marie@test.com", password="pass", person=cls.parent_person,
        )

    def test_anime_profile_uses_anime_form(self):
        """Animé user should get AnimeProfileForm, not ProfileEditForm."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], AnimeProfileForm)

    def test_anime_profile_shows_totem_email_phone(self):
        """Animé profile page should show editable totem, email, phone."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.get(url)
        self.assertContains(response, "id_totem")
        self.assertContains(response, "id_email")
        self.assertContains(response, "id_phone")

    def test_anime_profile_shows_address_readonly(self):
        """Animé profile should show address as disabled (read-only)."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.get(url)
        self.assertContains(response, "disabled")
        self.assertContains(response, "L'adresse est gérée par le parent responsable")

    def test_anime_profile_no_address_edit_field(self):
        """Animé profile should NOT have an editable address input."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.get(url)
        self.assertNotContains(response, 'name="address"')

    def test_anime_can_update_totem(self):
        """Animé user can update their totem."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.post(url, {
            "totem": "Loup Agile",
            "phone": "0470123456",
            "email": "jean@test.com",
        })
        self.assertEqual(response.status_code, 302)
        self.anime_person.refresh_from_db()
        self.assertEqual(self.anime_person.totem, "Loup Agile")

    def test_anime_can_update_phone(self):
        """Animé user can update their phone."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.post(url, {
            "totem": "Loup",
            "phone": "0499999999",
            "email": "jean@test.com",
        })
        self.assertEqual(response.status_code, 302)
        self.anime_person.refresh_from_db()
        self.assertIn("499999999", str(self.anime_person.phone))

    def test_anime_can_update_email(self):
        """Animé user can update their email."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.post(url, {
            "totem": "Loup",
            "phone": "0470123456",
            "email": "jean.new@test.com",
        })
        self.assertEqual(response.status_code, 302)
        self.anime_user.refresh_from_db()
        self.assertEqual(self.anime_user.email, "jean.new@test.com")

    def test_anime_address_not_changed_by_post(self):
        """Posting to anime profile should NOT change address."""
        self.client.force_login(self.anime_user)
        original_address = self.anime_person.address
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        self.client.post(url, {
            "totem": "Loup",
            "phone": "0470123456",
            "email": "jean@test.com",
        })
        self.anime_person.refresh_from_db()
        self.assertEqual(self.anime_person.address, original_address)

    def test_anime_profile_no_child_section(self):
        """Animé profile should NOT show the child management section."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.get(url)
        self.assertNotContains(response, "child-add")

    def test_anime_profile_no_role_radios(self):
        """Animé profile should NOT show primary role radio buttons."""
        self.client.force_login(self.anime_user)
        url = reverse("members:profile", kwargs={"pk": self.anime_user.pk})
        response = self.client.get(url)
        self.assertNotContains(response, "primary_role")

    def test_parent_profile_still_has_full_form(self):
        """Parent user should still get the full ProfileEditForm."""
        from members.forms import ProfileEditForm
        self.client.force_login(self.parent_user)
        url = reverse("members:profile", kwargs={"pk": self.parent_user.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], ProfileEditForm)
