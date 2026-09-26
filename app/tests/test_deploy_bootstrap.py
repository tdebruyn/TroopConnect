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

    # Mirrors the two volumes compose mounts: the key the application signs
    # sessions with, and the database password, which lives on its own so the
    # database container can see one but not the other.
    KEY_DIR = "secrets"
    PASSWORD_DIR = "db-secrets"

    def paths(self, root):
        root = Path(root)
        return {
            "secret_key": root / self.KEY_DIR / "secret_key",
            "postgres_password": root / self.PASSWORD_DIR / "postgres_password",
        }

    def run_entrypoint(self, root, **env_overrides):
        paths = self.paths(root)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "SECRET_KEY_FILE": str(paths["secret_key"]),
            "POSTGRES_PASSWORD_FILE": str(paths["postgres_password"]),
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

            for name, path in self.paths(tmp).items():
                self.assertTrue(path.is_file(), name)
                # Long enough to be worth calling a secret.
                self.assertGreaterEqual(len(path.read_text()), 32)

    def test_the_secrets_are_written_to_separate_directories(self):
        """So that the database volume can hold one without the other."""
        with tempfile.TemporaryDirectory() as tmp:
            self.run_entrypoint(tmp)

            self.assertNotEqual(
                self.paths(tmp)["secret_key"].parent,
                self.paths(tmp)["postgres_password"].parent,
            )

    def test_secret_key_is_private_and_the_database_password_is_readable(self):
        """Postgres reads its own password as a different user, mid-flight."""
        with tempfile.TemporaryDirectory() as tmp:
            self.run_entrypoint(tmp)
            paths = self.paths(tmp)

            key_mode = paths["secret_key"].stat().st_mode & 0o777
            password_mode = paths["postgres_password"].stat().st_mode & 0o777

            self.assertEqual(oct(key_mode), oct(0o600))
            self.assertEqual(oct(password_mode), oct(0o644))

    def test_generated_values_are_safe_in_urls_and_shells(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_entrypoint(tmp)

            for path in self.paths(tmp).values():
                self.assertRegex(path.read_text().strip(), r"^[A-Za-z0-9_-]+$")

    def test_secrets_survive_a_second_start(self):
        """Regenerating either would log everyone out, or lock the app out of
        the database it already initialised."""
        with tempfile.TemporaryDirectory() as tmp:
            self.run_entrypoint(tmp)
            first = {name: path.read_text() for name, path in self.paths(tmp).items()}

            second_run = self.run_entrypoint(tmp)
            self.assertEqual(second_run.returncode, 0, second_run.stderr)

            for name, path in self.paths(tmp).items():
                self.assertEqual(path.read_text(), first[name], name)

    def test_operator_supplied_values_are_used_instead(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_entrypoint(
                tmp, SECRET_KEY="chosen-key", POSTGRES_PASSWORD="chosen-password"
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            paths = self.paths(tmp)
            self.assertEqual(paths["secret_key"].read_text(), "chosen-key")
            self.assertEqual(paths["postgres_password"].read_text(), "chosen-password")

    def test_reports_a_clear_error_when_a_secrets_dir_cannot_be_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("not a directory")

            result = self.run_entrypoint(blocker)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Cannot create", result.stderr)
            self.assertIn("volume", result.stderr)


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
