from django.test import TestCase, Client, override_settings
from django.urls import reverse
from members.models import Account, Person, Role


class OnboardingMiddlewareTest(TestCase):
    """Tests for the OnboardingMiddleware redirect behavior."""

    def setUp(self):
        self.client = Client()
        # Get or create roles (they may already exist from migrations)
        self.role_nouveau, _ = Role.objects.get_or_create(
            short="n",
            defaults={"name": "Nouveau", "description": "", "is_primary": True},
        )
        self.role_parent, _ = Role.objects.get_or_create(
            short="p",
            defaults={"name": "Parent", "description": "", "is_primary": True},
        )

    def _create_unprofiled_user(self):
        """Create a user whose Person still has status='r' (not onboarded)."""
        person = Person.objects.create(
            first_name="",
            last_name="",
            primary_role=self.role_nouveau,
            status="r",
        )
        account = Account.objects.create_user(
            email="newuser@test.be",
            password="Test1234!",
            person=person,
        )
        return account

    def _create_profiled_user(self):
        """Create a user who has completed onboarding (status='a')."""
        person = Person.objects.create(
            first_name="Done",
            last_name="User",
            primary_role=self.role_parent,
            status="a",
        )
        account = Account.objects.create_user(
            email="doneuser@test.be",
            password="Test1234!",
            person=person,
        )
        return account

    def test_unprofiled_user_redirected_to_onboarding(self):
        account = self._create_unprofiled_user()
        self.client.force_login(account)
        response = self.client.get(reverse("homepage"))
        self.assertRedirects(response, reverse("members:onboarding"))

    def test_profiled_user_not_redirected(self):
        account = self._create_profiled_user()
        self.client.force_login(account)
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)

    def test_onboarding_page_accessible_for_unprofiled(self):
        account = self._create_unprofiled_user()
        self.client.force_login(account)
        response = self.client.get(reverse("members:onboarding"))
        self.assertEqual(response.status_code, 200)

    def test_staff_not_redirected(self):
        """Staff users should never be forced to onboarding."""
        person = Person.objects.create(
            first_name="Staff",
            last_name="User",
            primary_role=self.role_nouveau,
            status="r",
        )
        account = Account.objects.create_user(
            email="staff@test.be",
            password="Test1234!",
            person=person,
        )
        account.is_staff = True
        account.save()
        self.client.force_login(account)
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_user_not_redirected(self):
        """Anonymous users should see the homepage normally."""
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)


class OnboardingViewTest(TestCase):
    """Tests for the OnboardingView form submission."""

    def setUp(self):
        self.client = Client()
        self.role_nouveau, _ = Role.objects.get_or_create(
            short="n",
            defaults={"name": "Nouveau", "description": "", "is_primary": True},
        )
        self.role_parent, _ = Role.objects.get_or_create(
            short="p",
            defaults={"name": "Parent", "description": "", "is_primary": True},
        )
        self.role_animateur, _ = Role.objects.get_or_create(
            short="a",
            defaults={"name": "Animateur", "description": "", "is_primary": True},
        )
        self.role_anime, _ = Role.objects.get_or_create(
            short="e",
            defaults={"name": "Animé", "description": "", "is_primary": True},
        )
        person = Person.objects.create(
            first_name="",
            last_name="",
            primary_role=self.role_nouveau,
            status="r",
        )
        self.account = Account.objects.create_user(
            email="onboard@test.be",
            password="Test1234!",
            person=person,
        )
        self.client.force_login(self.account)

    def test_get_renders_form(self):
        response = self.client.get(reverse("members:onboarding"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Type de compte")
        self.assertContains(response, "Prénom")
        self.assertContains(response, "Nom")

    def test_get_prefills_existing_data(self):
        self.account.person.first_name = "Jean"
        self.account.person.last_name = "Dupont"
        self.account.person.save()
        response = self.client.get(reverse("members:onboarding"))
        self.assertContains(response, 'value="Jean"')
        self.assertContains(response, 'value="Dupont"')

    def test_submit_valid_form_completes_profile(self):
        response = self.client.post(
            reverse("members:onboarding"),
            {
                "first_name": "Marie",
                "last_name": "Martin",
                "address": "Rue de Limal 1, 1300 Limal",
                "phone": "+32470123456",
                "primary_role": "p",
                "photo_consent": "on",
            },
        )
        self.assertRedirects(response, reverse("homepage"))
        self.account.person.refresh_from_db()
        self.assertEqual(self.account.person.first_name, "Marie")
        self.assertEqual(self.account.person.last_name, "Martin")
        self.assertEqual(self.account.person.primary_role.short, "p")
        self.assertEqual(self.account.person.status, "a")
        self.assertTrue(self.account.person.photo_consent)

    def test_submit_sets_status_to_active(self):
        self.client.post(
            reverse("members:onboarding"),
            {
                "first_name": "Test",
                "last_name": "User",
                "primary_role": "a",
            },
        )
        self.account.person.refresh_from_db()
        self.assertEqual(self.account.person.status, "a")

    def test_submit_missing_required_fields_shows_errors(self):
        response = self.client.post(
            reverse("members:onboarding"),
            {
                "first_name": "",
                "last_name": "",
                "primary_role": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ce champ est obligatoire")

    def test_already_completed_profile_redirects_away(self):
        """If a user with status='a' hits onboarding, redirect to homepage."""
        self.account.person.status = "a"
        self.account.person.save()
        response = self.client.get(reverse("members:onboarding"))
        self.assertRedirects(response, reverse("homepage"))

    def test_onboarding_allows_animateur_role(self):
        response = self.client.post(
            reverse("members:onboarding"),
            {
                "first_name": "Anim",
                "last_name": "Leader",
                "primary_role": "a",
            },
        )
        self.assertRedirects(response, reverse("homepage"))
        self.account.person.refresh_from_db()
        self.assertEqual(self.account.person.primary_role.short, "a")

    def test_onboarding_allows_anime_role(self):
        response = self.client.post(
            reverse("members:onboarding"),
            {
                "first_name": "Young",
                "last_name": "Scout",
                "primary_role": "e",
            },
        )
        self.assertRedirects(response, reverse("homepage"))
        self.account.person.refresh_from_db()
        self.assertEqual(self.account.person.primary_role.short, "e")
