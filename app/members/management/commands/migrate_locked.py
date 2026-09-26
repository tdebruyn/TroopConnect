"""Run migrations while holding a Postgres advisory lock.

Only one process should ever migrate a database. The web service does it at
startup; a second replica, a rolling deploy, or somebody running
``manage.py migrate`` by hand would otherwise race it, which shows up as
duplicate-applied migrations or "tuple concurrently updated" errors.

The lock is session-scoped, so PostgreSQL releases it automatically if the
process dies mid-migration -- there is no stale lock to clean up.

Lives in ``members`` because Django only discovers management commands inside
an installed app, and that is the project's core app.
"""

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

# Arbitrary but fixed. PostgreSQL keeps advisory locks in their own namespace,
# so the value only has to avoid colliding with other users of advisory locks
# in this database. 0x54524F4F spells "TROO".
MIGRATE_LOCK_ID = 0x54524F4F

DEFAULT_TIMEOUT = 300
RETRY_INTERVAL = 1


class Command(BaseCommand):
    help = (
        "Run migrate while holding a Postgres advisory lock, so that only one "
        "process migrates at a time."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=int,
            default=DEFAULT_TIMEOUT,
            help=(
                "Seconds to wait for another process to finish migrating "
                f"before giving up (default: {DEFAULT_TIMEOUT})."
            ),
        )

    def handle(self, *args, **options):
        self._wait_for_lock(options["timeout"])
        try:
            call_command(
                "migrate", interactive=False, verbosity=options["verbosity"]
            )
        finally:
            # If the connection is gone the lock went with it, and opening a
            # new one to "release" a lock we no longer hold would be wrong.
            if connection.connection is not None:
                self._release_lock()

    def _wait_for_lock(self, timeout):
        """Take the lock, or give up after ``timeout`` seconds."""
        deadline = time.monotonic() + timeout

        while True:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [MIGRATE_LOCK_ID])
                acquired = cursor.fetchone()[0]

            if acquired:
                return

            if time.monotonic() >= deadline:
                raise CommandError(
                    f"Another process has been migrating for more than {timeout}s. "
                    "Wait for it to finish, or retry with a longer --timeout."
                )

            time.sleep(RETRY_INTERVAL)

    def _release_lock(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [MIGRATE_LOCK_ID])
