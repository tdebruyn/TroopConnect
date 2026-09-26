"""Tests for what happens before the app serves its first request.

The container entrypoint generates the secrets, waits for the database and
migrates under an advisory lock. These cover the parts of that contract that
can be exercised without building a container.
"""

import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import psycopg
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase

from members.management.commands.migrate_locked import MIGRATE_LOCK_ID

APP_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = APP_ROOT / "entrypoint.sh"


class EntrypointSecretTest(SimpleTestCase):
    """`entrypoint.sh init-secrets` is what the init service runs."""

    def run_entrypoint(self, secrets_dir, **env_overrides):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "SECRETS_DIR": str(secrets_dir),
        }
        # The host environment must not leak in, or a SECRET_KEY exported for
        # another purpose would silently satisfy the test.
        env.pop("SECRET_KEY", None)
        env.pop("POSTGRES_PASSWORD", None)
        env.update(env_overrides)

        return subprocess.run(
            ["sh", str(ENTRYPOINT), "init-secrets"],
            env=env,
            capture_output=True,
            text=True,
        )

    def test_generates_both_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_entrypoint(tmp)
            self.assertEqual(result.returncode, 0, result.stderr)

            key = Path(tmp) / "secret_key"
            password = Path(tmp) / "postgres_password"

            self.assertTrue(key.is_file())
            self.assertTrue(password.is_file())
            # Long enough to be worth calling a secret.
            self.assertGreaterEqual(len(key.read_text()), 32)
            self.assertGreaterEqual(len(password.read_text()), 32)

    def test_secret_key_is_private_and_the_database_password_is_readable(self):
        """Postgres reads its own password as a different user, mid-flight."""
        with tempfile.TemporaryDirectory() as tmp:
            self.run_entrypoint(tmp)

            key_mode = (Path(tmp) / "secret_key").stat().st_mode & 0o777
            password_mode = (Path(tmp) / "postgres_password").stat().st_mode & 0o777

            self.assertEqual(oct(key_mode), oct(0o600))
            self.assertEqual(oct(password_mode), oct(0o644))

    def test_generated_values_are_safe_in_urls_and_shells(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_entrypoint(tmp)

            for name in ("secret_key", "postgres_password"):
                value = (Path(tmp) / name).read_text().strip()
                self.assertRegex(value, r"^[A-Za-z0-9_-]+$")

    def test_secrets_survive_a_second_start(self):
        """Regenerating either would log everyone out, or lock the app out of
        the database it already initialised."""
        with tempfile.TemporaryDirectory() as tmp:
            self.run_entrypoint(tmp)
            first = {
                name: (Path(tmp) / name).read_text()
                for name in ("secret_key", "postgres_password")
            }

            second_run = self.run_entrypoint(tmp)
            self.assertEqual(second_run.returncode, 0, second_run.stderr)

            for name, value in first.items():
                self.assertEqual((Path(tmp) / name).read_text(), value)

    def test_operator_supplied_values_are_used_instead(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_entrypoint(
                tmp, SECRET_KEY="chosen-key", POSTGRES_PASSWORD="chosen-password"
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            self.assertEqual((Path(tmp) / "secret_key").read_text(), "chosen-key")
            self.assertEqual(
                (Path(tmp) / "postgres_password").read_text(), "chosen-password"
            )

    def test_reports_a_clear_error_when_the_secrets_dir_cannot_be_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("not a directory")

            result = self.run_entrypoint(blocker / "secrets")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("app_data", result.stderr)


class WaitForDbTest(TransactionTestCase):
    def test_returns_once_the_database_answers(self):
        # Raises if it cannot connect, so simply completing is the assertion.
        call_command("wait_for_db", timeout=10)


class MigrateLockedTest(TransactionTestCase):
    @contextmanager
    def competing_lock(self):
        """Hold the migrate lock from a second database session.

        A real second process is the only way to exercise this: the lock is
        scoped to a session, and Django reuses one connection per thread.
        """
        settings_dict = connection.settings_dict
        holder = psycopg.connect(
            host=settings_dict["HOST"],
            port=settings_dict["PORT"],
            dbname=settings_dict["NAME"],
            user=settings_dict["USER"],
            password=settings_dict["PASSWORD"],
            autocommit=True,
        )
        try:
            holder.execute("SELECT pg_advisory_lock(%s)", [MIGRATE_LOCK_ID])
            yield
        finally:
            holder.close()

    def advisory_locks_held(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")
            return cursor.fetchone()[0]

    def test_migrates_and_releases_the_lock(self):
        call_command("migrate_locked", verbosity=0)

        self.assertEqual(self.advisory_locks_held(), 0)

    def test_gives_up_with_a_useful_message_when_another_process_holds_the_lock(self):
        with self.competing_lock():
            with self.assertRaises(CommandError) as ctx:
                call_command("migrate_locked", timeout=2, verbosity=0)

        self.assertIn("Another process has been migrating", str(ctx.exception))

    def test_proceeds_once_the_other_process_finishes(self):
        with self.competing_lock():
            pass

        # The holder has gone, so the lock is free again.
        call_command("migrate_locked", timeout=10, verbosity=0)

        self.assertEqual(self.advisory_locks_held(), 0)
