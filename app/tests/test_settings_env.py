"""Tests for the environment-driven settings, checks and env parsing.

Two levels are covered:

* pure helpers (``troopconnect.env``) called directly, and
* the settings module itself, which decides things like ALLOWED_HOSTS and which
  mail backend to use *at import time*. Those are probed in a fresh interpreter
  with a controlled environment rather than by reloading settings in-process.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.sites.models import Site
from django.core.checks import Error, Warning
from django.test import SimpleTestCase, TestCase, override_settings

from troopconnect import checks, env
from troopconnect.env import (
    ConfigProblem,
    env_bool,
    env_int,
    parse_database_url,
    parse_email_url,
)
from troopconnect.siteconfig import sync_site_domain

APP_ROOT = Path(__file__).resolve().parent.parent

SETTINGS_PROBE = """
import json

from django.conf import settings

print(json.dumps({
    "DEBUG": settings.DEBUG,
    "ALLOWED_HOSTS": settings.ALLOWED_HOSTS,
    "CSRF_TRUSTED_ORIGINS": settings.CSRF_TRUSTED_ORIGINS,
    "SITE_ID": settings.SITE_ID,
    "EMAIL_BACKEND": settings.EMAIL_BACKEND,
    "EMAIL_HOST": settings.EMAIL_HOST,
    "EMAIL_PORT": settings.EMAIL_PORT,
    "EMAIL_USE_TLS": settings.EMAIL_USE_TLS,
    "EMAIL_USE_SSL": settings.EMAIL_USE_SSL,
    "POST_OFFICE_BACKEND": settings.POST_OFFICE["BACKENDS"]["default"],
    "MAIL_SEND_MODE": settings.MAIL_SEND_MODE,
    "DATABASE_NAME": settings.DATABASES["default"]["NAME"],
    "DATABASE_HOST": settings.DATABASES["default"]["HOST"],
    "STATICFILES_DIRS": [str(d) for d in settings.STATICFILES_DIRS],
    "STATIC_ROOT": str(settings.STATIC_ROOT),
    "SERVE_MEDIA_LOCALLY": settings.SERVE_MEDIA_LOCALLY,
}))
"""

# A valid baseline; individual tests override one variable at a time.
VALID_ENV = {
    "SITE_DOMAIN": "troop.example.org",
    "EMAIL_URL": "smtp+tls://user:secret@mail.example.org:587",
    "DEFAULT_FROM_EMAIL": "inscriptions@example.org",
    "ACME_EMAIL": "admin@example.org",
    "SECRET_KEY": "test-key-not-used-for-anything-real",
}

class ParseEmailUrlTest(SimpleTestCase):
    """EMAIL_URL is the only thing an operator configures to get mail working."""

    def test_console_scheme_selects_the_console_backend(self):
        parsed = parse_email_url("console://")
        self.assertEqual(
            parsed["EMAIL_BACKEND"], "django.core.mail.backends.console.EmailBackend"
        )
        self.assertNotIn("EMAIL_HOST", parsed)

    def test_smtp_scheme_uses_port_25_without_tls(self):
        parsed = parse_email_url("smtp://mail.example.org")
        self.assertEqual(parsed["EMAIL_HOST"], "mail.example.org")
        self.assertEqual(parsed["EMAIL_PORT"], 25)
        self.assertFalse(parsed["EMAIL_USE_TLS"])
        self.assertFalse(parsed["EMAIL_USE_SSL"])

    def test_smtp_tls_scheme_uses_port_587_with_starttls(self):
        parsed = parse_email_url("smtp+tls://mail.example.org")
        self.assertEqual(parsed["EMAIL_PORT"], 587)
        self.assertTrue(parsed["EMAIL_USE_TLS"])
        self.assertFalse(parsed["EMAIL_USE_SSL"])

    def test_smtp_ssl_scheme_uses_port_465_with_implicit_tls(self):
        parsed = parse_email_url("smtp+ssl://mail.example.org")
        self.assertEqual(parsed["EMAIL_PORT"], 465)
        self.assertTrue(parsed["EMAIL_USE_SSL"])
        self.assertFalse(parsed["EMAIL_USE_TLS"])

    def test_explicit_port_and_credentials_are_used(self):
        parsed = parse_email_url("smtp://alice:s3cret@mail.example.org:2525")
        self.assertEqual(parsed["EMAIL_PORT"], 2525)
        self.assertEqual(parsed["EMAIL_HOST_USER"], "alice")
        self.assertEqual(parsed["EMAIL_HOST_PASSWORD"], "s3cret")

    def test_percent_encoded_credentials_are_decoded(self):
        # A password containing "@" or ":" has to be encoded to stay parseable.
        parsed = parse_email_url("smtp+tls://user:p%40ss%3Aword@mail.example.org")
        self.assertEqual(parsed["EMAIL_HOST_PASSWORD"], "p@ss:word")

    def test_timeout_query_parameter_is_read(self):
        parsed = parse_email_url("smtp://mail.example.org?timeout=10")
        self.assertEqual(parsed["EMAIL_TIMEOUT"], 10)

    def test_non_numeric_timeout_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            parse_email_url("smtp://mail.example.org?timeout=soon")
        self.assertIn("timeout", str(ctx.exception))

    def test_unsupported_scheme_lists_the_supported_ones(self):
        with self.assertRaises(ValueError) as ctx:
            parse_email_url("ftp://mail.example.org")
        message = str(ctx.exception)
        self.assertIn("ftp://", message)
        for scheme in ("console://", "smtp://", "smtp+tls://", "smtp+ssl://"):
            self.assertIn(scheme, message)

    def test_missing_scheme_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_email_url("mail.example.org")

    def test_missing_host_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            parse_email_url("smtp+tls://")
        self.assertIn("host", str(ctx.exception).lower())


class ParseDatabaseUrlTest(SimpleTestCase):
    def test_full_url_is_parsed(self):
        parsed = parse_database_url(
            "postgres://alice:s3cret@db.example.org:5433/troop"
        )
        self.assertEqual(parsed["NAME"], "troop")
        self.assertEqual(parsed["USER"], "alice")
        self.assertEqual(parsed["PASSWORD"], "s3cret")
        self.assertEqual(parsed["HOST"], "db.example.org")
        self.assertEqual(parsed["PORT"], "5433")

    def test_postgresql_alias_is_accepted(self):
        parsed = parse_database_url("postgresql://db.example.org/troop")
        self.assertEqual(parsed["NAME"], "troop")

    def test_port_and_database_default(self):
        parsed = parse_database_url("postgres://db.example.org")
        self.assertEqual(parsed["PORT"], "5432")
        self.assertEqual(parsed["NAME"], "troopconnect")

    def test_non_postgres_scheme_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            parse_database_url("mysql://db.example.org/troop")
        self.assertIn("PostgreSQL", str(ctx.exception))


class EnvHelperTest(SimpleTestCase):
    def setUp(self):
        env.reset_problems()
        self.addCleanup(env.reset_problems)

    def test_blank_is_treated_as_unset(self):
        os.environ["TROOPCONNECT_TEST_BLANK"] = "   "
        self.addCleanup(os.environ.pop, "TROOPCONNECT_TEST_BLANK", None)
        self.assertEqual(env.env("TROOPCONNECT_TEST_BLANK", "fallback"), "fallback")

    def test_env_bool_accepts_the_usual_spellings(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            os.environ["TROOPCONNECT_TEST_BOOL"] = value
            self.assertTrue(env_bool("TROOPCONNECT_TEST_BOOL"))
        self.addCleanup(os.environ.pop, "TROOPCONNECT_TEST_BOOL", None)

        for value in ("0", "false", "no", "off"):
            os.environ["TROOPCONNECT_TEST_BOOL"] = value
            self.assertFalse(env_bool("TROOPCONNECT_TEST_BOOL"))

    def test_env_bool_falls_back_and_records_a_problem(self):
        os.environ["TROOPCONNECT_TEST_BOOL"] = "maybe"
        self.addCleanup(os.environ.pop, "TROOPCONNECT_TEST_BOOL", None)

        self.assertTrue(env_bool("TROOPCONNECT_TEST_BOOL", default=True))
        problems = env.get_problems()
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].variable, "TROOPCONNECT_TEST_BOOL")
        self.assertIn("boolean", problems[0].message)

    def test_env_int_falls_back_and_records_a_problem(self):
        os.environ["TROOPCONNECT_TEST_INT"] = "not-a-number"
        self.addCleanup(os.environ.pop, "TROOPCONNECT_TEST_INT", None)

        self.assertEqual(env_int("TROOPCONNECT_TEST_INT", 7), 7)
        self.assertEqual(len(env.get_problems()), 1)


class LoadSecretKeyTest(SimpleTestCase):
    def test_existing_key_file_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secret_key"
            path.write_text("stored-key\n")

            key, problem = env.load_secret_key(path)

        self.assertEqual(key, "stored-key")
        self.assertIsNone(problem)

    def test_key_is_generated_persisted_and_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "secret_key"

            generated, problem = env.load_secret_key(path)
            self.assertIsNone(problem)
            self.assertTrue(generated)

            # A second boot must find the same key, or every session is lost.
            again, _ = env.load_secret_key(path)

        self.assertEqual(generated, again)

    def test_unreadable_path_reports_a_problem_but_still_returns_a_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("I am a file, not a directory")
            path = blocker / "secret_key"

            key, problem = env.load_secret_key(path)

        self.assertTrue(key)
        self.assertIsNotNone(problem)
        self.assertIn(str(path), problem)

    def test_unwritable_path_warns_that_the_key_is_only_in_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secret_key"

            with mock.patch.object(
                Path, "write_text", side_effect=PermissionError(13, "Permission denied")
            ):
                key, problem = env.load_secret_key(path)

        self.assertTrue(key)
        self.assertIsNotNone(problem)
        self.assertIn("throwaway", problem)
        # The operator needs to know the consequence, not just the cause.
        self.assertIn("logged out", problem)


class CheckTest(SimpleTestCase):
    """The system check an operator sees at startup."""

    def run_checks(self):
        return checks.troopconnect_settings_checks(None)

    def ids(self, messages):
        return {message.id for message in messages}

    @override_settings(DEBUG=False)
    def test_missing_required_variables_are_errors_in_production(self):
        with override_settings(
            SITE_DOMAIN="", EMAIL_URL="", DEFAULT_FROM_EMAIL="", ACME_EMAIL=""
        ):
            messages = self.run_checks()

        for message in messages:
            self.assertIsInstance(message, Error)

        self.assertEqual(
            self.ids(messages),
            {"troopconnect.E001", "troopconnect.E002", "troopconnect.E003",
             "troopconnect.E004"},
        )

    @override_settings(DEBUG=False)
    def test_missing_required_variables_report_one_line_each(self):
        with override_settings(
            SITE_DOMAIN="", EMAIL_URL="", DEFAULT_FROM_EMAIL="", ACME_EMAIL=""
        ):
            messages = self.run_checks()

        # One plain-language line per variable, naming it and saying what to do.
        by_id = {message.id: message for message in messages}
        for check_id, variable in (
            ("troopconnect.E001", "SITE_DOMAIN"),
            ("troopconnect.E002", "EMAIL_URL"),
            ("troopconnect.E003", "DEFAULT_FROM_EMAIL"),
            ("troopconnect.E004", "ACME_EMAIL"),
        ):
            message = by_id[check_id]
            self.assertIn(variable, message.msg)
            self.assertIn("Set it", message.msg)
            self.assertNotIn("\n", message.msg)

    @override_settings(DEBUG=True)
    def test_missing_required_variables_only_warn_in_debug(self):
        with override_settings(
            SITE_DOMAIN="", EMAIL_URL="", DEFAULT_FROM_EMAIL="", ACME_EMAIL=""
        ):
            messages = self.run_checks()

        self.assertTrue(messages)
        for message in messages:
            self.assertIsInstance(message, Warning)

    @override_settings(DEBUG=False)
    def test_site_domain_with_a_scheme_is_rejected(self):
        with override_settings(SITE_DOMAIN="https://troop.example.org"):
            messages = self.run_checks()

        self.assertIn("troopconnect.E001", self.ids(messages))
        self.assertIn("bare hostname", messages[0].msg)

    @override_settings(DEBUG=False)
    def test_site_domain_with_a_path_is_rejected(self):
        with override_settings(SITE_DOMAIN="troop.example.org/scouts"):
            messages = self.run_checks()

        self.assertIn("troopconnect.E001", self.ids(messages))

    @override_settings(DEBUG=False)
    def test_malformed_default_from_email_is_rejected(self):
        with override_settings(DEFAULT_FROM_EMAIL="not-an-address"):
            messages = self.run_checks()

        self.assertIn("troopconnect.E003", self.ids(messages))

    @override_settings(DEBUG=True, SITE_DOMAIN="troop.example.org")
    def test_debug_on_a_public_domain_warns(self):
        messages = self.run_checks()

        self.assertIn("troopconnect.W001", self.ids(messages))
        warning = next(m for m in messages if m.id == "troopconnect.W001")
        self.assertIn("source code", warning.msg)

    @override_settings(DEBUG=True, SITE_DOMAIN="localhost")
    def test_debug_on_a_local_domain_does_not_warn(self):
        messages = self.run_checks()

        self.assertNotIn("troopconnect.W001", self.ids(messages))

    @override_settings(DEBUG=False)
    def test_recorded_parse_problems_are_replayed(self):
        env.reset_problems()
        self.addCleanup(env.reset_problems)
        env.record_problem("EMAIL_URL", "EMAIL_URL uses the unsupported scheme.")

        try:
            messages = self.run_checks()
        finally:
            env.reset_problems()

        self.assertIn("troopconnect.E002", self.ids(messages))


class SiteDomainSyncTest(TestCase):
    """Links in outgoing email have to point at the instance's own domain."""

    @override_settings(SITE_DOMAIN="troop.example.org", SITE_ID=1)
    def test_sync_creates_the_configured_site_row(self):
        Site.objects.filter(pk=1).delete()

        sync_site_domain()

        self.assertEqual(Site.objects.get(pk=1).domain, "troop.example.org")

    @override_settings(SITE_DOMAIN="troop.example.org", SITE_ID=1)
    def test_sync_overwrites_a_stale_domain(self):
        Site.objects.update_or_create(
            pk=1, defaults={"domain": "example.com", "name": "example.com"}
        )

        sync_site_domain()

        self.assertEqual(Site.objects.get(pk=1).domain, "troop.example.org")

    @override_settings(SITE_DOMAIN="", SITE_ID=1)
    def test_sync_does_nothing_without_a_domain(self):
        Site.objects.update_or_create(
            pk=1, defaults={"domain": "example.com", "name": "example.com"}
        )

        sync_site_domain()

        self.assertEqual(Site.objects.get(pk=1).domain, "example.com")


class DerivedSettingsTest(SimpleTestCase):
    """Settings computed at import time, probed in a fresh interpreter."""

    def probe(self, **overrides):
        env_vars = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "DJANGO_SETTINGS_MODULE": "troopconnect.settings",
        }
        env_vars.update(VALID_ENV)
        env_vars.update(overrides)

        result = subprocess.run(
            [sys.executable, "-c", SETTINGS_PROBE],
            cwd=APP_ROOT,
            env=env_vars,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_allowed_hosts_and_csrf_origins_follow_the_domain(self):
        probed = self.probe()

        self.assertIn("troop.example.org", probed["ALLOWED_HOSTS"])
        self.assertIn("www.troop.example.org", probed["ALLOWED_HOSTS"])
        self.assertIn(
            "https://troop.example.org", probed["CSRF_TRUSTED_ORIGINS"]
        )

    def test_debug_is_off_unless_asked_for(self):
        self.assertFalse(self.probe()["DEBUG"])
        self.assertFalse(self.probe(DJANGO_DEBUG="0")["DEBUG"])
        self.assertTrue(self.probe(DJANGO_DEBUG="1")["DEBUG"])

    def test_localhost_is_allowed_only_in_debug(self):
        self.assertNotIn("localhost", self.probe()["ALLOWED_HOSTS"])
        self.assertIn("localhost", self.probe(DJANGO_DEBUG="1")["ALLOWED_HOSTS"])

    def test_smtp_tls_url_selects_the_smtp_backend(self):
        probed = self.probe()

        self.assertEqual(
            probed["EMAIL_BACKEND"], "django.core.mail.backends.smtp.EmailBackend"
        )
        self.assertEqual(probed["EMAIL_HOST"], "mail.example.org")
        self.assertEqual(probed["EMAIL_PORT"], 587)
        self.assertTrue(probed["EMAIL_USE_TLS"])

    def test_console_url_selects_the_console_backend(self):
        probed = self.probe(EMAIL_URL="console://")

        self.assertEqual(
            probed["EMAIL_BACKEND"], "django.core.mail.backends.console.EmailBackend"
        )
        self.assertEqual(
            probed["POST_OFFICE_BACKEND"],
            "django.core.mail.backends.console.EmailBackend",
        )

    def test_mailersend_key_switches_the_backend(self):
        probed = self.probe(MAILERSEND_API_KEY="mlsn.key")

        self.assertEqual(probed["MAIL_SEND_MODE"], "mailersend")
        self.assertEqual(
            probed["POST_OFFICE_BACKEND"],
            "troopconnect.mailersend_backend.MailerSendBackend",
        )

    def test_unknown_email_url_scheme_does_not_stop_the_app_booting(self):
        # The scheme problem is reported by the check instead, so the process
        # still starts far enough to print it.
        probed = self.probe(EMAIL_URL="ftp://mail.example.org")

        self.assertEqual(
            probed["EMAIL_BACKEND"], "django.core.mail.backends.smtp.EmailBackend"
        )

    def test_database_url_overrides_the_individual_variables(self):
        probed = self.probe(
            DATABASE_URL="postgres://alice:pw@db.internal:5433/troop",
            POSTGRES_DB="ignored",
            POSTGRES_HOST="ignored",
        )

        self.assertEqual(probed["DATABASE_NAME"], "troop")
        self.assertEqual(probed["DATABASE_HOST"], "db.internal")

    def test_postgres_variables_are_used_without_a_database_url(self):
        probed = self.probe(POSTGRES_DB="mytroop", POSTGRES_HOST="db")

        self.assertEqual(probed["DATABASE_NAME"], "mytroop")
        self.assertEqual(probed["DATABASE_HOST"], "db")

    def test_site_id_defaults_to_one(self):
        self.assertEqual(self.probe()["SITE_ID"], 1)
        self.assertEqual(self.probe(SITE_ID="2")["SITE_ID"], 2)

    def test_project_static_dir_is_collected_in_and_out_of_debug(self):
        """The site's own CSS/JS lives there, so collectstatic needs it always."""
        expected = str(APP_ROOT / "static")

        self.assertIn(expected, self.probe()["STATICFILES_DIRS"])
        self.assertIn(expected, self.probe(DJANGO_DEBUG="1")["STATICFILES_DIRS"])

    def test_media_is_served_by_django_only_in_debug_by_default(self):
        self.assertFalse(self.probe()["SERVE_MEDIA_LOCALLY"])
        self.assertTrue(self.probe(DJANGO_DEBUG="1")["SERVE_MEDIA_LOCALLY"])


class ReadFileSecretTest(SimpleTestCase):
    """The VAR / VAR_FILE convention the Postgres image also uses."""

    def setUp(self):
        env.reset_problems()
        self.addCleanup(env.reset_problems)
        self.addCleanup(os.environ.pop, "TROOPCONNECT_TEST_SECRET", None)
        self.addCleanup(os.environ.pop, "TROOPCONNECT_TEST_SECRET_FILE", None)

    def test_the_variable_wins_over_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secret"
            path.write_text("from-file\n")
            os.environ["TROOPCONNECT_TEST_SECRET"] = "from-env"
            os.environ["TROOPCONNECT_TEST_SECRET_FILE"] = str(path)

            self.assertEqual(
                env.read_file_secret("TROOPCONNECT_TEST_SECRET"), "from-env"
            )

    def test_the_file_is_used_when_the_variable_is_unset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secret"
            path.write_text("from-file\n")
            os.environ["TROOPCONNECT_TEST_SECRET_FILE"] = str(path)

            self.assertEqual(
                env.read_file_secret("TROOPCONNECT_TEST_SECRET"), "from-file"
            )

    def test_neither_set_returns_the_default(self):
        self.assertEqual(
            env.read_file_secret("TROOPCONNECT_TEST_SECRET", "fallback"), "fallback"
        )

    def test_an_unreadable_file_is_reported_rather_than_silently_empty(self):
        os.environ["TROOPCONNECT_TEST_SECRET_FILE"] = "/nonexistent/secret"

        self.assertEqual(env.read_file_secret("TROOPCONNECT_TEST_SECRET"), "")

        problems = env.get_problems()
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].variable, "TROOPCONNECT_TEST_SECRET_FILE")
        self.assertIn("/nonexistent/secret", problems[0].message)


class ConfigProblemTest(SimpleTestCase):
    def test_problem_keeps_the_variable_and_message(self):
        problem = ConfigProblem("SITE_DOMAIN", "SITE_DOMAIN is not set.")

        self.assertEqual(problem.variable, "SITE_DOMAIN")
        self.assertIn("SITE_DOMAIN", repr(problem))
