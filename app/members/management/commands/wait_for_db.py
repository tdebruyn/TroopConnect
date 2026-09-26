"""Block until the database accepts connections.

Compose already waits for the database's healthcheck before starting the
application, but the container entrypoint checks for itself as well: that also
covers running the image outside compose, and a database that is restarting
when the app happens to come up.

Lives in ``members`` because Django only discovers management commands inside
an installed app, and that is the project's core app.
"""

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.utils import OperationalError

DEFAULT_TIMEOUT = 60
RETRY_INTERVAL = 2


class Command(BaseCommand):
    help = "Wait until the database is reachable, then exit."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=int,
            default=DEFAULT_TIMEOUT,
            help=(
                "Seconds to keep retrying before giving up "
                f"(default: {DEFAULT_TIMEOUT})."
            ),
        )

    def handle(self, *args, **options):
        timeout = options["timeout"]
        deadline = time.monotonic() + timeout
        last_error = None

        while True:
            try:
                connection.ensure_connection()
            except OperationalError as exc:
                last_error = exc
                if time.monotonic() >= deadline:
                    break
                time.sleep(RETRY_INTERVAL)
                continue

            self.stdout.write("Database is reachable.")
            return

        raise CommandError(
            f"Could not reach the database within {timeout}s. Check "
            f"POSTGRES_HOST, POSTGRES_USER and POSTGRES_PASSWORD. "
            f"Last error: {last_error}"
        )
