import json
import os
import subprocess
import sys
from pathlib import Path

from django.template.loader import get_template
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from members.adapters import SocialAccountAdapter
from members.models import Account, Person, Role

APP_ROOT = Path(__file__).resolve().parent.parent

# Prints the social providers a given environment registers, as JSON.
SETTINGS_PROBE = """
import json

from django.conf import settings

print(json.dumps({
    "providers": sorted(settings.SOCIALACCOUNT_PROVIDERS),
    "installed": sorted(
        app for app in settings.INSTALLED_APPS
        if "socialaccount.providers" in app
    ),
}))
"""

PROVIDER_ENV_VARS = (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "FACEBOOK_APP_ID",
    "FACEBOOK_SECRET",
)


class SocialProviderGatingTest(SimpleTestCase):
    """A provider is only registered when both of its keys are set.

    The settings module decides this at import time (it appends to
    INSTALLED_APPS), so each case runs in a fresh interpreter with a different
    environment rather than trying to reload settings in-process.
    """

    def _probe(self, **env_overrides):
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "troopconnect.settings",
            "SECRET_KEY": "test-key-not-used-for-anything-real",
        }
        for name in PROVIDER_ENV_VARS:
            env.pop(name, None)
        env.update(env_overrides)

        result = subprocess.run(
            [sys.executable, "-c", SETTINGS_PROBE],
            cwd=APP_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_no_keys_registers_no_providers(self):
        probed = self._probe()
        self.assertEqual(probed["providers"], [])
        self.assertEqual(probed["installed"], [])

    def test_google_registered_when_both_keys_are_set(self):
        probed = self._probe(GOOGLE_CLIENT_ID="id", GOOGLE_CLIENT_SECRET="secret")
        self.assertEqual(probed["providers"], ["google"])
        self.assertIn("allauth.socialaccount.providers.google", probed["installed"])

    def test_google_not_registered_with_only_one_key(self):
        probed = self._probe(GOOGLE_CLIENT_ID="id")
        self.assertEqual(probed["providers"], [])

    def test_facebook_registered_when_both_keys_are_set(self):
        probed = self._probe(FACEBOOK_APP_ID="id", FACEBOOK_SECRET="secret")
        self.assertEqual(probed["providers"], ["facebook"])
        self.assertIn("allauth.socialaccount.providers.facebook", probed["installed"])

    def test_facebook_not_registered_with_only_one_key(self):
        probed = self._probe(FACEBOOK_APP_ID="id")
        self.assertEqual(probed["providers"], [])


class SocialButtonTemplateTest(TestCase):
    """Login and signup build their provider buttons from the configured set.

    There is deliberately no facebook- or google-specific template test: the
    templates no longer name a provider, so asserting one is present would
    re-assert the hardcoding this replaced.
    """

    TEMPLATES = ("account/login.html", "account/signup.html")

    def test_templates_do_not_contain_dead_links(self):
        for name in self.TEMPLATES:
            source = get_template(name).template.source
            self.assertNotIn('href="#!"', source)

    def test_templates_do_not_name_a_provider(self):
        """Naming one would show a broken button on a troop that has no keys."""
        for name in self.TEMPLATES:
            source = get_template(name).template.source
            self.assertNotIn("provider_login_url 'facebook'", source)
            self.assertNotIn("provider_login_url 'google'", source)

    def test_templates_loop_over_the_configured_providers(self):
        for name in self.TEMPLATES:
            source = get_template(name).template.source
            self.assertIn("{% get_providers as socialaccount_providers %}", source)
            self.assertIn("provider_login_url provider.id", source)

    def test_login_page_offers_no_social_provider_when_none_configured(self):
        # The test settings configure no provider keys, so the whole block --
        # heading included -- must be absent from the rendered page.
        response = self.client.get(reverse("account_login"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("/accounts/google/login", content)
        self.assertNotIn("/accounts/facebook/login", content)
        self.assertNotIn("Or log in with", content)


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
        # /accounts/social/signup/ should not redirect to onboarding. Asserted
        # unconditionally: the previous `if response.status_code == 302:` guard
        # meant any other status — including a 500 — asserted nothing at all.
        response = self.client.get(reverse("socialaccount_signup"), follow=False)
        self.assertIn(response.status_code, (200, 302))
        self.assertNotEqual(
            response.headers.get("Location", ""), reverse("members:onboarding"),
        )

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
        # Should not redirect to onboarding (asserted unconditionally, see above).
        self.assertIn(response.status_code, (200, 302))
        self.assertNotEqual(
            response.headers.get("Location", ""), reverse("members:onboarding"),
        )


class SocialAccountSignupTemplateTest(TestCase):
    """Tests for the styled social signup template."""

    def test_social_signup_template_has_bootstrap_styling(self):
        template = get_template("socialaccount/signup.html")
        source = template.template.source
        self.assertIn("form-control", source)
        self.assertNotIn("form.as_p", source)

    def test_social_signup_template_has_submit_button(self):
        """Assert the element, not the word: "Continue" appearing anywhere —
        a paragraph, a comment — used to satisfy this."""
        template = get_template("socialaccount/signup.html")
        source = template.template.source
        self.assertRegex(source, r'<button[^>]*type="submit"')
