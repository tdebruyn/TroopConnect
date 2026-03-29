from django.test import TestCase, Client
from django.template import Template, Context
from django.template.loader import get_template
from django.urls import reverse
from members.models import Account, Person, Role
from members.adapters import SocialAccountAdapter


class FacebookButtonTemplateTest(TestCase):
    """Tests that Facebook login buttons are correctly wired in templates."""

    def test_login_template_does_not_contain_dead_link(self):
        template = get_template("account/login.html")
        source = template.template.source
        self.assertNotIn('href="#!"', source)

    def test_login_template_has_facebook_provider_url(self):
        template = get_template("account/login.html")
        source = template.template.source
        self.assertIn("provider_login_url 'facebook'", source)

    def test_signup_template_does_not_contain_dead_link(self):
        template = get_template("account/signup.html")
        source = template.template.source
        self.assertNotIn('href="#!"', source)

    def test_signup_template_has_facebook_provider_url(self):
        template = get_template("account/signup.html")
        source = template.template.source
        self.assertIn("provider_login_url 'facebook'", source)


class GoogleButtonTemplateTest(TestCase):
    """Tests that Google login buttons are correctly wired in templates."""

    def test_login_template_has_google_provider_url(self):
        template = get_template("account/login.html")
        source = template.template.source
        self.assertIn("provider_login_url 'google'", source)

    def test_signup_template_has_google_provider_url(self):
        template = get_template("account/signup.html")
        source = template.template.source
        self.assertIn("provider_login_url 'google'", source)


class SocialAccountAdapterTest(TestCase):
    """Tests for the custom SocialAccountAdapter."""

    def setUp(self):
        self.role_parent, _ = Role.objects.get_or_create(
            short="p",
            defaults={"name": "Parent", "description": "", "is_primary": True},
        )
        self.person = Person.objects.create(
            first_name="Existing",
            last_name="User",
            primary_role=self.role_parent,
            status="a",
        )
        self.account = Account.objects.create_user(
            email="existing@test.be",
            password="Test1234!",
            person=self.person,
        )

    def test_adapter_class_exists(self):
        adapter = SocialAccountAdapter()
        self.assertTrue(hasattr(adapter, "pre_social_login"))
        self.assertTrue(hasattr(adapter, "get_connect_redirect_url"))

    def test_connect_redirect_url_is_homepage(self):
        adapter = SocialAccountAdapter()
        url = adapter.get_connect_redirect_url(request=None, socialaccount=None)
        self.assertEqual(url, "/")


class SocialLoginMiddlewareExemptTest(TestCase):
    """Tests that middleware doesn't block social login URLs."""

    def setUp(self):
        self.client = Client()
        self.role_nouveau, _ = Role.objects.get_or_create(
            short="n",
            defaults={"name": "Nouveau", "description": "", "is_primary": True},
        )

    def test_accounts_path_exempt_from_middleware(self):
        """An unprofiled user should be able to reach /accounts/ paths."""
        person = Person.objects.create(
            first_name="",
            last_name="",
            primary_role=self.role_nouveau,
            status="r",
        )
        account = Account.objects.create_user(
            email="social@test.be",
            password="Test1234!",
            person=person,
        )
        self.client.force_login(account)
        # /accounts/social/signup/ should not redirect to onboarding
        response = self.client.get(reverse("socialaccount_signup"), follow=False)
        if response.status_code == 302:
            self.assertNotEqual(response.url, reverse("members:onboarding"))

    def test_logout_exempt_from_middleware(self):
        """Logout should work even for unprofiled users."""
        person = Person.objects.create(
            first_name="",
            last_name="",
            primary_role=self.role_nouveau,
            status="r",
        )
        account = Account.objects.create_user(
            email="logout@test.be",
            password="Test1234!",
            person=person,
        )
        self.client.force_login(account)
        response = self.client.post(reverse("account_logout"), follow=False)
        # Should not redirect to onboarding
        if response.status_code == 302:
            self.assertNotEqual(response.url, reverse("members:onboarding"))


class SocialAccountSignupTemplateTest(TestCase):
    """Tests for the styled social signup template."""

    def test_social_signup_template_has_bootstrap_styling(self):
        template = get_template("socialaccount/signup.html")
        source = template.template.source
        self.assertIn("form-control", source)
        self.assertNotIn("form.as_p", source)

    def test_social_signup_template_has_submit_button(self):
        template = get_template("socialaccount/signup.html")
        source = template.template.source
        self.assertIn("Continuer", source)
