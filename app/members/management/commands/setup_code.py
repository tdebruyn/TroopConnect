"""Print (or issue) the first-run wizard's one-time setup code.

Run by the container entrypoint on the web service, right after ``migrate``,
so a fresh install prints its code into the web container's logs without
anybody having to ask for it:

    docker compose logs web | grep -i "setup code"

It can also be run by hand, which is what an operator does when the code is
no longer in the scrolling buffer:

    docker compose exec web python manage.py setup_code

Once an instance has an administrator there is nothing to set up and the code
is not printed; ``--reset`` issues a new one (for a deployment whose code file
was lost, or whose instance was wiped and re-migrated).
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.utils import ProgrammingError

from members.wizard import ensure_setup_code, forget_setup_code, setup_complete


class Command(BaseCommand):
    help = (
        "Print the first-run wizard's one-time setup code, generating it if "
        "this instance does not have one yet."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Discard the current code and issue a new one. Use it when the "
                "code is known to somebody who should not have it."
            ),
        )

    def handle(self, *args, **options):
        try:
            complete = setup_complete()
        except ProgrammingError:
            raise CommandError(
                "the database is not migrated yet — run `manage.py migrate` first"
            ) from None

        if complete:
            self.stdout.write(
                "This instance already has an administrator, so there is no "
                "setup code. Remove the account if you really mean to set this "
                "instance up again."
            )
            return

        if options["reset"]:
            forget_setup_code()

        code = ensure_setup_code()
        # Both lines are written to be found in a container's log: the first
        # says what the code is, the second what to do with it.
        self.stdout.write(f"Setup code: {code}")
        self.stdout.write(self._where())

    def _where(self):
        """Where the wizard is, for whoever is reading the log."""
        site = getattr(settings, "SITE_DOMAIN", "")
        if not site:
            return "Open the wizard at /setup once the site is serving."
        return f"Open https://{site}/setup and enter it."
