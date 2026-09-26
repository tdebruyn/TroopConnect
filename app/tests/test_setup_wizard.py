"""The first-run wizard: the gate, the steps, and when it stops existing.

Three things have to hold, and most of these tests are one of them:

* while an instance has no administrator and its deployment armed it for
  setup, the wizard is the whole site and everything else leads to it;
* once it has one, the wizard is gone — 404 — and the site is served;
* and neither is true of an instance that was never armed, which is every
  test run and every deployment that skipped the entrypoint.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_celery_beat.models import PeriodicTask
from post_office.models import EmailTemplate

from homepage.models import SiteContent
from members import email_templates, permissions, setup
from members.models import (
    Account,
    Branch,
    PersonRole,
    SchoolYear,
    Section,
    TroopSettings,
)
from members.wizard import (
    clear_attempts,
    ensure_setup_code,
    forget_setup_code,
    setup_complete,
    setup_required,
)
from members.wizard.steps import SESSION_KEY, StructureForm, default_structure

from .base import TroopSettingsTestCase

PASSWORD = "Vlinders-van-het-Woud-42"
ADMIN = {
    "email": "chef@example.org",
    "first_name": "Ada",
    "last_name": "Chef",
    "password": PASSWORD,
    "password_confirm": PASSWORD,
}


class WizardTestCase(TroopSettingsTestCase):
    """A fresh instance, armed for setup, with its code to hand."""

    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.code_file = Path(directory.name) / "setup_code"
        self.code = self.arm(self.code_file)
        # The rate limit is kept in the shared cache, which a rollback does not
        # clear; a test that spends it would throttle the next one.
        self.addCleanup(clear_attempts, "127.0.0.1")

    def arm(self, path):
        """Point the wizard at ``path`` and issue a code there."""
        override = override_settings(SETUP_CODE_FILE=str(path))
        override.enable()
        self.addCleanup(override.disable)
        return ensure_setup_code()


def post_structure(client, branches=None):
    """Post the structure editor's rows, the way the browser would."""
    branches = branches if branches is not None else default_structure(["fr"])
    data = {}
    for branch in branches:
        data.setdefault("branch-id", []).append(branch.id)
        data.setdefault("branch-key", []).append(branch.key)
        for field in branch.name_fields:
            data.setdefault(f"branch-name-{field['language']}", []).append(field["value"])
        data.setdefault("branch-min", []).append(
            "" if branch.min_age is None else branch.min_age
        )
        data.setdefault("branch-max", []).append(
            "" if branch.max_age is None else branch.max_age
        )
        for section in branch.sections:
            data.setdefault("section-id", []).append(section.id)
            data.setdefault("section-branch", []).append(section.branch)
            for field in section.name_fields:
                data.setdefault(
                    f"section-name-{field['language']}", []
                ).append(field["value"])
            data.setdefault("section-sex", []).append(section.sex)
    return client.post(reverse("setup:step", args=["structure"]), data)


class GateTest(WizardTestCase):
    """What the instance shows before it has an administrator."""

    def test_every_page_but_the_wizard_leads_to_it(self):
        for url in ("/", "/faq/", reverse("members:admin_list"), "/accounts/login/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302, url)
                self.assertEqual(response["Location"], reverse("setup:index"))

    def test_even_an_authenticated_visitor_is_sent_to_the_wizard(self):
        """Nothing on the site is worth using before the site is set up."""
        person = setup.ensure_admin_account(
            email="someone@example.org",
            password=PASSWORD,
            first_name="Some",
            last_name="One",
            superuser=False,
        )
        self.assertTrue(person.created)
        self.client.force_login(Account.objects.get(email="someone@example.org"))

        response = self.client.get(reverse("members:admin_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("setup:index"))

    def test_health_and_static_files_are_let_through(self):
        """The container's own healthcheck must not be redirected.

        A fresh instance that answers 302 to /healthz is one Docker never
        calls healthy, which is precisely when Caddy refuses to start and the
        wizard becomes unreachable.
        """
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertNotEqual(self.client.get("/static/css/troopconnect.css").status_code, 302)

    def test_an_unarmed_instance_is_left_completely_alone(self):
        """No code issued means no wizard, and no redirects either.

        This is what keeps the wizard from being something every other part of
        the application has to know about: a test run, or a deployment started
        without the entrypoint, is not a first run.
        """
        forget_setup_code()

        self.assertFalse(setup_required())
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get(reverse("setup:index")).status_code, 404)

    def test_the_wizard_is_gone_once_an_administrator_exists(self):
        self.create_superuser()

        self.assertFalse(setup_required())
        self.assertEqual(self.client.get(reverse("setup:index")).status_code, 404)
        for step in ("code", "admin", "structure", "done"):
            with self.subTest(step=step):
                response = self.client.get(reverse("setup:step", args=[step]))
                self.assertEqual(response.status_code, 404)

    def test_the_site_is_served_once_an_administrator_exists(self):
        self.create_superuser()

        self.assertEqual(self.client.get("/").status_code, 200)

    def test_the_code_is_read_per_request_not_held_in_the_process(self):
        """An instance whose code comes and goes follows it either way."""
        forget_setup_code()
        self.assertFalse(setup_required())

        ensure_setup_code()

        self.assertTrue(setup_required())

    def create_superuser(self):
        account = setup.ensure_admin_account(
            email="chef@example.org",
            password=PASSWORD,
            first_name="Ada",
            last_name="Chef",
            superuser=True,
        )
        return account


class CodeStepTest(WizardTestCase):
    """The one-time code, and what it costs to guess."""

    def test_the_wizard_opens_on_the_code_step(self):
        response = self.client.get(reverse("setup:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("setup:step", args=["code"]))
        # What the page shows is asserted by its fields rather than its words:
        # the wizard is translated, and a test that reads the French is a test
        # that breaks the moment somebody rewords a sentence.
        self.assertContains(response, 'name="code"')

    def test_the_right_code_opens_the_next_step(self):
        response = self.post_code(self.code)

        self.assertContains(response, 'name="password_confirm"')
        self.assertEqual(self.client.session[SESSION_KEY]["code_ok"], True)

    def test_a_wrong_code_is_refused_and_says_so(self):
        response = self.post_code("AAAA-BBBB-CCCC-DDDD")

        self.assertContains(response, "alert-danger")
        self.assertContains(response, 'name="code"')  # still the code step
        self.assertNotIn("code_ok", self.client.session.get(SESSION_KEY, {}))

    def test_a_wrong_code_is_counted_against_the_address(self):
        from members.wizard import attempts_left

        self.post_code("AAAA-BBBB-CCCC-DDDD")

        allowed, _wait = attempts_left("127.0.0.1")
        self.assertTrue(allowed)  # one guess is not a lockout

    def test_guessing_is_rate_limited(self):
        from members.wizard import MAX_ATTEMPTS

        for _ in range(MAX_ATTEMPTS):
            self.post_code("AAAA-BBBB-CCCC-DDDD")

        response = self.post_code(self.code)

        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "alert-danger", status_code=429)

    def test_a_later_step_cannot_be_reached_without_the_code(self):
        for step in ("admin", "identity", "email"):
            with self.subTest(step=step):
                response = self.client.get(reverse("setup:step", args=[step]))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    response["Location"], reverse("setup:step", args=["code"])
                )
                response = self.client.post(reverse("setup:step", args=[step]), ADMIN)
                self.assertEqual(response.status_code, 302)

    def test_the_code_is_forgotten_once_it_has_been_used(self):
        """A right answer clears the count, so a typo costs nothing later."""
        from members.wizard import attempts_left

        self.post_code("AAAA-BBBB-CCCC-DDDD")
        self.post_code(self.code)

        self.assertTrue(attempts_left("127.0.0.1")[0])

    def post_code(self, code):
        return self.client.post(reverse("setup:step", args=["code"]), {"code": code})


class HappyPathTest(WizardTestCase):
    """The whole walk, from a bare database to a site that serves."""

    def walk(self):
        """Walk every step, and return the response of each."""
        responses = {}
        responses["code"] = self.client.post(
            reverse("setup:step", args=["code"]), {"code": self.code}
        )
        responses["admin"] = self.client.post(
            reverse("setup:step", args=["admin"]), ADMIN
        )
        responses["identity"] = self.client.post(
            reverse("setup:step", args=["identity"]),
            {
                "name": "Les Scouts de Limal",
                "short_name": "SV021",
                "contact_email": "info@example.org",
            },
        )
        responses["locale"] = self.client.post(
            reverse("setup:step", args=["locale"]),
            {
                "enabled_languages": ["fr", "nl"],
                "default_language": "fr",
                "phone_region": "BE",
                "currency": "EUR",
            },
        )
        responses["structure"] = self.post_structure()
        responses["calendar"] = self.client.post(
            reverse("setup:step", args=["calendar"]),
            {
                "year_start_month": 8,
                "year_start_day": 1,
                "age_reference_month": 12,
                "age_reference_day": 31,
                "passage_month": 5,
                "passage_day": 1,
                "passage_mode": "auto",
                "top_branch_graduates_become_leaders": "on",
                "archive_retention_years": 5,
            },
        )
        responses["modules"] = self.client.post(
            reverse("setup:step", args=["modules"]),
            {"fees_enabled": "on", "signing_enabled": "on", "agenda_enabled": "on"},
        )
        responses["email"] = self.post_email()
        return responses

    def post_structure(self, branches=None):
        self.advance_past_the_admin()
        return post_structure(self.client, branches)

    def advance_past_the_admin(self):
        """Get the session as far as the structure step, once."""
        if self.client.session.get(SESSION_KEY, {}).get("code_ok"):
            return
        self.client.post(reverse("setup:step", args=["code"]), {"code": self.code})
        self.client.post(reverse("setup:step", args=["admin"]), ADMIN)

    def post_email(self):
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            return self.client.post(reverse("setup:step", args=["email"]), {})

    def test_the_walk_creates_a_working_instance(self):
        responses = self.walk()

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name_fr, "Les Scouts de Limal")
        self.assertEqual(troop.short_name, "SV021")
        self.assertEqual(troop.enabled_languages, ["fr", "nl"])
        self.assertEqual(Branch.objects.count(), 4)
        self.assertEqual(Section.objects.count(), 4)
        self.assertEqual(SchoolYear.objects.count(), 2)
        self.assertEqual(responses["email"].status_code, 200)

    def test_the_wizard_provisions_what_it_never_asks_about(self):
        """A browser-set-up instance ends up as complete as a shell one.

        The school years, the templates, the starter pages and the beat
        schedule have no questions worth asking, so they happen when the last
        step lands rather than as pages of their own.
        """
        self.walk()

        self.assertEqual(EmailTemplate.objects.count(), len(list(email_templates.rows())))
        self.assertEqual(SiteContent.objects.count(), 2)
        self.assertEqual(PeriodicTask.objects.count(), len(settings.CELERY_BEAT_SCHEDULE))

    def test_the_wizard_ends_with_the_site_serving(self):
        self.walk()

        self.assertTrue(setup_complete())
        self.assertFalse(setup_required())
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_the_administrator_can_log_in_at_the_end(self):
        self.walk()

        account = Account.objects.get(email="chef@example.org")
        self.assertTrue(account.is_superuser)
        self.assertTrue(account.is_staff)
        self.assertTrue(check_password(PASSWORD, account.password))
        self.assertEqual(account.person.primary_role.short, permissions.ANIMATEUR)
        self.assertTrue(
            PersonRole.objects.filter(
                person=account.person, role__short=permissions.ADMIN
            ).exists()
        )
        self.assertTrue(
            Client().login(email="chef@example.org", password=PASSWORD)
        )

    def test_the_last_page_stays_readable_for_the_session_that_finished(self):
        """The browser lands on it; a refresh should not 404."""
        self.walk()

        response = self.client.get(reverse("setup:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "setup-next")

    def test_every_step_is_reachable_again_while_the_wizard_is_open(self):
        """Back, and a reload, both land on something that renders."""
        self.advance_past_the_admin()

        for step in ("admin", "identity", "locale", "structure"):
            with self.subTest(step=step):
                response = self.client.get(reverse("setup:step", args=[step]))
                self.assertEqual(response.status_code, 200)

    def test_the_wizard_may_be_left_and_resumed(self):
        """Landing on /setup again picks up where the last save left off."""
        self.advance_past_the_admin()

        response = self.client.get(reverse("setup:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="short_name"')  # the unit step

    def test_an_htmx_request_gets_the_pane_alone(self):
        """What the browser swaps in, and where the address bar follows it to."""
        self.advance_past_the_admin()

        response = self.client.post(
            reverse("setup:step", args=["locale"]),
            {
                "enabled_languages": ["fr"],
                "default_language": "fr",
                "phone_region": "BE",
                "currency": "EUR",
            },
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, 'id="wizard-pane"')
        self.assertEqual(
            response.headers["HX-Push-Url"], reverse("setup:step", args=["structure"])
        )


class AdminStepTest(WizardTestCase):
    """The first administrator, before and after the last step."""

    def setUp(self):
        super().setUp()
        self.client.post(reverse("setup:step", args=["code"]), {"code": self.code})

    def post(self, **overrides):
        data = {**ADMIN, **overrides}
        return self.client.post(reverse("setup:step", args=["admin"]), data)

    def test_the_account_is_created_before_it_is_a_superuser(self):
        """Otherwise the wizard would close the instance behind itself.

        "An instance with an administrator" is what says setup is over, so the
        account that administers it is only completed on the last step.
        """
        self.post()

        account = Account.objects.get(email="chef@example.org")
        self.assertTrue(account.is_staff)
        self.assertFalse(account.is_superuser)
        self.assertTrue(setup_required())

    def test_a_mismatched_confirmation_is_refused(self):
        response = self.post(password_confirm="Something-else-9")

        self.assertContains(response, "alert-danger")
        self.assertFalse(Account.objects.exists())

    def test_a_weak_password_is_refused(self):
        response = self.post(password="password", password_confirm="password")

        # The message is Django's own, and so translated; what matters is that
        # the step refuses rather than storing it.
        self.assertContains(response, "alert-danger")
        self.assertFalse(Account.objects.exists())

    def test_the_address_is_marked_verified(self):
        self.post()

        account = Account.objects.get(email="chef@example.org")
        self.assertTrue(account.emailaddress_set.get().verified)

    def test_the_step_says_which_step_comes_next(self):
        response = self.post()

        self.assertContains(response, reverse("setup:step", args=["identity"]))
        self.assertEqual(self.client.session[SESSION_KEY]["step"], "identity")


class StructureStepTest(WizardTestCase):
    """The branch and section editor."""

    def setUp(self):
        super().setUp()
        self.client.post(reverse("setup:step", args=["code"]), {"code": self.code})
        self.client.post(reverse("setup:step", args=["admin"]), ADMIN)

    def rows(self):
        return default_structure(["fr"])

    def test_it_opens_on_the_federation_s_own_layout(self):
        response = self.client.get(reverse("setup:step", args=["structure"]))

        self.assertContains(response, "Baladins")
        self.assertContains(response, "Louveteaux")
        self.assertContains(response, "Éclaireurs")
        self.assertContains(response, "Pionniers")

    def test_saving_creates_the_branches_and_their_sections(self):
        response = post_structure(self.client)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(Branch.objects.order_by("min_age_dec_31").values_list("key", flat=True)),
            ["baladins", "louveteaux", "eclaireurs", "pionniers"],
        )
        self.assertEqual(Section.objects.count(), 4)
        self.assertEqual(Branch.objects.get(key="baladins").min_age_dec_31, 6)
        self.assertEqual(Branch.objects.get(key="baladins").promotes_to.key, "louveteaux")
        self.assertTrue(Branch.objects.get(key="pionniers").is_top)

    def test_a_renamed_branch_keeps_its_place_in_the_ladder(self):
        rows = self.rows()
        rows[1].names["fr"] = "Meute Seeonee"
        for section in rows[1].sections:
            section.names["fr"] = "Meute Seeonee"

        post_structure(self.client, rows)

        self.assertEqual(Branch.objects.get(key="louveteaux").name_fr, "Meute Seeonee")
        self.assertEqual(Branch.objects.count(), 4)

    def test_saving_twice_does_not_add_a_second_set(self):
        post_structure(self.client)
        rows = StructureForm(
            None, ["fr"]
        ).branch_entries  # what the editor now shows: the database
        post_structure(self.client, rows)

        self.assertEqual(Branch.objects.count(), 4)
        self.assertEqual(Section.objects.count(), 4)

    def test_a_branch_left_with_no_section_is_refused(self):
        rows = self.rows()
        rows[0].sections = []

        response = post_structure(self.client, rows)

        self.assertContains(response, "alert-danger")
        self.assertEqual(Branch.objects.count(), 0)

    def test_a_branch_removed_from_the_list_is_deleted(self):
        post_structure(self.client)

        rows = StructureForm(None, ["fr"]).branch_entries
        post_structure(self.client, rows[:3])

        self.assertEqual(Branch.objects.count(), 3)
        self.assertFalse(Branch.objects.filter(key="pionniers").exists())

    def test_ages_the_wrong_way_round_are_refused(self):
        rows = self.rows()
        rows[0].min_age, rows[0].max_age = 12, 6

        response = post_structure(self.client, rows)

        self.assertContains(response, "alert-danger")
        self.assertEqual(Branch.objects.count(), 0)

    def test_the_editor_can_add_and_remove_rows_without_javascript(self):
        """The buttons are round trips: one row of markup, served once."""
        add_section = self.client.post(
            reverse("setup:structure_row", args=["add-section"]), {"branch-id": "baladins"}
        )
        self.assertEqual(add_section.status_code, 200)
        self.assertContains(add_section, 'name="section-branch" value="baladins"')

        add_branch = self.client.post(reverse("setup:structure_row", args=["add-branch"]))
        self.assertContains(add_branch, 'name="branch-id" value="new-')
        self.assertContains(add_branch, 'name="section-branch"')

        remove = self.client.post(reverse("setup:structure_row", args=["remove"]))
        self.assertEqual(remove.status_code, 200)
        self.assertEqual(remove.content, b"")


class EmailStepTest(WizardTestCase):
    """The test message, which is the one step that cannot be skipped."""

    def setUp(self):
        super().setUp()
        self.client.post(reverse("setup:step", args=["code"]), {"code": self.code})
        self.client.post(reverse("setup:step", args=["admin"]), ADMIN)

    def test_it_sends_through_the_configured_backend(self):
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            response = self.client.post(reverse("setup:step", args=["email"]), {})

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["chef@example.org"])
        self.assertContains(response, "setup-next")

    def test_a_refused_message_is_shown_plainly_and_can_be_retried(self):
        error = OSError(111, "Connection refused")
        with mock.patch("django.core.mail.send_mail", side_effect=error):
            response = self.client.post(reverse("setup:step", args=["email"]), {})

        self.assertContains(response, "alert-danger")
        # The server's own words, not a category this code invented.
        self.assertContains(response, "Connection refused")
        self.assertFalse(setup_complete())

    def test_a_failed_message_leaves_the_wizard_open(self):
        with mock.patch("django.core.mail.send_mail", side_effect=OSError("boom")):
            self.client.post(reverse("setup:step", args=["email"]), {})

        self.assertTrue(setup_required())
        self.assertEqual(
            self.client.get(reverse("setup:index")).status_code, 200
        )

    def test_a_retry_after_a_failure_can_still_finish(self):
        with mock.patch("django.core.mail.send_mail", side_effect=OSError("boom")):
            self.client.post(reverse("setup:step", args=["email"]), {})
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            self.client.post(reverse("setup:step", args=["email"]), {})

        self.assertTrue(setup_complete())


class SetupCodeCommandTest(WizardTestCase):
    """The command the entrypoint runs, and an operator can run again."""

    def test_it_prints_the_code_of_an_instance_that_needs_setting_up(self):
        out = StringIO()
        call_command("setup_code", stdout=out)

        self.assertIn(self.code, out.getvalue())
        self.assertIn("/setup", out.getvalue())

    def test_it_says_nothing_to_do_once_an_administrator_exists(self):
        setup.ensure_admin_account(
            email="chef@example.org",
            password=PASSWORD,
            first_name="Ada",
            last_name="Chef",
            superuser=True,
        )
        out = StringIO()
        call_command("setup_code", stdout=out)

        self.assertNotIn(self.code, out.getvalue())
        self.assertIn("already has an administrator", out.getvalue())

    def test_it_generates_a_code_the_first_time_it_is_run(self):
        forget_setup_code()

        out = StringIO()
        call_command("setup_code", stdout=out)

        self.assertIn("Setup code:", out.getvalue())
        self.assertEqual(self.code_file.read_text().strip(), out.getvalue().split()[2])

    def test_reset_issues_a_different_code(self):
        out = StringIO()
        call_command("setup_code", "--reset", stdout=out)

        new_code = out.getvalue().split()[2]
        self.assertNotEqual(new_code, self.code)
        self.assertEqual(self.code_file.read_text().strip(), new_code)


class StandaloneWizardTest(TestCase):
    """The gate, asked directly, on an instance set up by the command line."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(SETUP_CODE_FILE=str(Path(directory.name) / "c"))
        override.enable()
        self.addCleanup(override.disable)

    def test_an_instance_with_no_code_row_and_no_admin_is_not_a_first_run(self):
        self.assertFalse(setup_required())

    def test_the_code_the_command_prints_is_the_one_the_wizard_wants(self):
        out = StringIO()
        call_command("setup_code", stdout=out)
        code = out.getvalue().split()[2]

        response = self.client.post(reverse("setup:step", args=["code"]), {"code": code})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "not this instance&#x27;s setup code")
