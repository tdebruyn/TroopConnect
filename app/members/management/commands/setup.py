"""Bring an empty database to a usable state.

A freshly migrated instance can take a registration but is not yet a troop: no
branches, no administrator, nothing scheduled. This command does that part, so
that a self-hosted install is ``migrate`` and one more command rather than a
tour of the Django admin.

It is meant to be run more than once. Every step fills in only what is
missing, so running it again on an instance that has been in use for a year
reports what it kept and writes nothing. See ``members.setup`` for the steps
themselves — the same functions the first-run web wizard calls.

    manage.py setup                              # prompts for what it needs
    manage.py setup --answers answers.json       # everything from a file
    manage.py setup --unit-name "Les Scouts" --languages fr,nl
    manage.py setup --dry-run                    # report, write nothing

Values given as flags win over the answers file, which wins over a prompt.
"""

import getpass
import json
import sys
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db.utils import ProgrammingError

from members.models import (
    AVAILABLE_LANGUAGE_CHOICES,
    DAY_VALIDATORS,
    MONTH_VALIDATORS,
    TroopSettings,
)
from members.presets import DEFAULT_PRESET
from members.setup import SetupError, normalise_answers, run_setup

#: The steps that answer to a ``--no-<step>`` flag, and what they do.
STEP_FLAGS = {
    "preset": "create the branches and sections of a preset",
    "school_years": "create the current and next school year",
    "email_templates": "write the shipped email templates",
    "site_pages": "give the homepage and FAQ somewhere to start",
    "periodic_tasks": "schedule the recurring tasks Celery beat runs",
    "admin": "create the first administrator account",
}

#: Troop settings a flag can fill, as ``flag -> field name``.
SETTINGS_FLAGS = {
    "--unit-name": "name",
    "--short-name": "short_name",
    "--federation": "federation",
    "--contact-email": "contact_email",
    "--reply-to-email": "reply_to_email",
    "--contact-phone": "contact_phone",
    "--footer-address": "footer_address",
    "--privacy-policy": "privacy_policy",
    "--phone-region": "phone_region",
    "--currency": "currency",
    "--passage-mode": "passage_mode",
    "--archive-retention-years": "archive_retention_years",
}

#: Month/day settings a ``MM-DD`` flag fills.
DATE_FLAGS = {
    "--year-start": ("year_start_month", "year_start_day"),
    "--age-reference": ("age_reference_month", "age_reference_day"),
    "--passage-date": ("passage_month", "passage_day"),
}

LANGUAGE_CODES = [code for code, _label in AVAILABLE_LANGUAGE_CHOICES]


class Command(BaseCommand):
    help = (
        "Bring an empty database to a usable state: troop settings, branches "
        "and sections from a preset, school years, email templates, starter "
        "pages, the Celery beat schedule and the first administrator. Safe to "
        "run again: it fills in only what is missing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--answers",
            metavar="FILE",
            help=(
                "JSON file holding the answers (see docs/dev/CONTRACT.md). "
                "Flags override it."
            ),
        )
        parser.add_argument(
            "--preset",
            metavar="NAME_OR_FILE",
            help=(
                f"Branch/section layout to create, as a shipped name or a path "
                f"to a file in the same shape (default: {DEFAULT_PRESET})."
            ),
        )
        parser.add_argument(
            "--languages",
            metavar="FR,NL",
            help="Languages the site offers, comma-separated.",
        )
        parser.add_argument(
            "--default-language",
            metavar="FR",
            help="Language shown to a visitor whose own is not one of them.",
        )
        parser.add_argument(
            "--top-branch-graduates-become-leaders",
            action="store_true",
            default=None,
            help="Members who outgrow the last branch become animators.",
        )

        for flag, field in SETTINGS_FLAGS.items():
            parser.add_argument(flag, metavar="VALUE", help=f"Troop setting: {field}.")
        for flag in DATE_FLAGS:
            parser.add_argument(
                flag, metavar="MM-DD", help="Troop setting, as a month and day."
            )

        admin = parser.add_argument_group("first administrator")
        admin.add_argument("--admin-email", metavar="EMAIL")
        admin.add_argument("--admin-first-name", metavar="NAME")
        admin.add_argument("--admin-last-name", metavar="NAME")
        admin.add_argument(
            "--admin-password",
            metavar="PASSWORD",
            help=(
                "Password for the first administrator. Prefer the prompt: a "
                "password on a command line is kept in the shell's history."
            ),
        )
        admin.add_argument(
            "--no-admin-superuser",
            action="store_true",
            help="Make the first administrator staff, but not a superuser.",
        )

        for step, description in STEP_FLAGS.items():
            parser.add_argument(
                f"--no-{step.replace('_', '-')}",
                action="store_true",
                help=f"Do not {description}.",
            )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be written, and write nothing.",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            "--non-interactive",
            dest="noinput",
            action="store_true",
            help=(
                "Never prompt. Values that are missing are left at their "
                "defaults, and a step that has nothing to go on is skipped."
            ),
        )

    # --- input ------------------------------------------------------------

    def handle(self, *args, **options):
        answers = self._answers_from_file(options["answers"])
        self._apply_flags(answers, options)
        if not options["noinput"]:
            self._prompt_for_what_is_missing(answers)

        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write("Dry run: nothing will be written.\n")

        try:
            steps = run_setup(answers, dry_run=dry_run)
        except SetupError as exc:
            raise CommandError("\n".join(exc.problems)) from None
        except ProgrammingError as exc:
            # The usual cause is running this against a database migrate has
            # never been near, or one a release behind the image.
            first_line = str(exc).strip().splitlines()[0]
            raise CommandError(
                "the database is not migrated to this version — run "
                f"`manage.py migrate` first ({first_line})"
            ) from None

        self._report(steps, dry_run=dry_run)

    def _answers_from_file(self, path):
        """The answers file, or an empty mapping when none was named."""
        if not path:
            return {}
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise CommandError(
                f"--answers {path}: cannot be read ({exc.strerror})"
            ) from None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CommandError(
                f"--answers {path}:{exc.lineno}:{exc.colno}: invalid JSON ({exc.msg})"
            ) from None
        try:
            return normalise_answers(data)
        except SetupError as exc:
            raise CommandError("\n".join(exc.problems)) from None

    def _apply_flags(self, answers, options):
        """Fold the flags into the answers, overriding the file."""
        answers.setdefault("settings", {})
        answers.setdefault("steps", {})

        if options["preset"]:
            answers["preset"] = options["preset"]

        for flag, field in SETTINGS_FLAGS.items():
            value = options[flag.lstrip("-").replace("-", "_")]
            if value is not None:
                answers["settings"][field] = value

        if options["languages"] is not None:
            codes = [code.strip() for code in options["languages"].split(",") if code.strip()]
            unknown = [code for code in codes if code not in LANGUAGE_CODES]
            if unknown:
                raise CommandError(
                    f"--languages: {', '.join(unknown)} — this build ships "
                    f"{', '.join(LANGUAGE_CODES)}"
                )
            if not codes:
                raise CommandError("--languages: give at least one language")
            answers["settings"]["enabled_languages"] = codes

        if options["default_language"] is not None:
            answers["settings"]["default_language"] = options["default_language"]

        if options["top_branch_graduates_become_leaders"]:
            answers["settings"]["top_branch_graduates_become_leaders"] = True

        for flag, (month_field, day_field) in DATE_FLAGS.items():
            value = options[flag.lstrip("-").replace("-", "_")]
            if value is None:
                continue
            month, day = self._parse_month_day(value, flag)
            answers["settings"][month_field] = month
            answers["settings"][day_field] = day

        admin = dict(answers.get("admin") or {})
        for flag, key in (
            ("admin_email", "email"),
            ("admin_first_name", "first_name"),
            ("admin_last_name", "last_name"),
            ("admin_password", "password"),
        ):
            if options[flag] is not None:
                admin[key] = options[flag]
        if options["no_admin_superuser"]:
            admin["superuser"] = False
        if admin:
            answers["admin"] = admin

        for step in STEP_FLAGS:
            if options[f"no_{step}"]:
                answers["steps"][step] = False

    def _prompt_for_what_is_missing(self, answers):
        """Ask for the handful of values a first run is no good without.

        Only what is still missing, and only what a terminal can hold a
        conversation about: a name to put on the site, who to reach, which
        languages, and the account the troop will administer it with. Every
        other answer has a defensible default in the model.
        """
        if not self._is_interactive():
            return

        settings_values = answers.setdefault("settings", {})
        troop = TroopSettings.get_settings()

        if "name" not in settings_values:
            # The French column is the one modeltranslation falls back to, so
            # it is the name a visitor sees when a language has none of its own.
            name = self._ask("Unit name", troop.name_fr)
            if name:
                settings_values["name"] = name

        if "short_name" not in settings_values:
            short = self._ask("Short name (optional, Enter to skip)", troop.short_name)
            if short:
                settings_values["short_name"] = short

        if "contact_email" not in settings_values:
            email = self._ask(
                "Public contact email (optional, Enter to skip)", troop.contact_email
            )
            if email:
                settings_values["contact_email"] = email

        if "enabled_languages" not in settings_values:
            current = ",".join(troop.enabled_languages or ["fr"])
            offered_codes = ",".join(LANGUAGE_CODES)
            chosen = self._ask(
                f"Languages offered, comma-separated ({offered_codes})", current
            )
            codes = [code.strip() for code in (chosen or current).split(",") if code.strip()]
            codes = [code for code in codes if code in LANGUAGE_CODES]
            if codes:
                settings_values["enabled_languages"] = codes

        if "default_language" not in settings_values:
            offered = settings_values.get(
                "enabled_languages", troop.enabled_languages or ["fr"]
            )
            fallback = (
                troop.default_language
                if troop.default_language in offered
                else offered[0]
            )
            chosen = self._ask("Default language", fallback)
            settings_values["default_language"] = (
                chosen if chosen in offered else offered[0]
            )

        if not answers.get("steps", {}).get("admin", True):
            return
        answers["admin"] = self._prompt_for_admin(answers.get("admin") or {})

    def _prompt_for_admin(self, admin):
        """Ask for the first administrator, password included."""
        if not admin.get("email"):
            email = self._ask("Administrator email (Enter to skip)")
            if not email:
                return {}
            admin["email"] = email

        # Not setdefault: that would evaluate the question — and print it —
        # even when the answers file already gave a name.
        if not admin.get("first_name"):
            admin["first_name"] = self._ask("Administrator first name", "Admin")
        if not admin.get("last_name"):
            admin["last_name"] = self._ask("Administrator last name", "User")

        if not admin.get("password"):
            password = self._ask_password()
            if password:
                admin["password"] = password
            else:
                self.stdout.write(
                    "  no password given — the account is created without one; "
                    "set it with `manage.py changepassword <email>`."
                )
        return admin

    def _is_interactive(self):
        """Whether there is somebody at a terminal to answer questions.

        A seam of its own so the tests can put a person there: replacing
        ``sys.stdin`` for the length of a test reaches into the interpreter,
        and this is the one question that needs answering.
        """
        return sys.stdin.isatty()

    def _ask(self, question, default=""):
        """Ask one question, returning ``default`` for an empty answer."""
        prompt = f"{question} [{default}]: " if default else f"{question}: "
        try:
            answer = input(prompt).strip()
        except EOFError:
            return default
        return answer or default

    def _ask_password(self):
        """Ask twice for a password, and insist the two agree."""
        while True:
            try:
                first = getpass.getpass("Administrator password: ")
            except (EOFError, KeyboardInterrupt):
                return ""
            if not first:
                return ""
            try:
                second = getpass.getpass("Repeat the password: ")
            except (EOFError, KeyboardInterrupt):
                return ""
            if first == second:
                return first
            self.stdout.write("  the two do not match — try again.")

    def _parse_month_day(self, text, flag):
        """``"08-01"`` as a ``(month, day)`` pair."""
        parts = str(text).split("-")
        try:
            if len(parts) != 2:
                raise ValueError
            month, day = int(parts[0]), int(parts[1])
        except ValueError:
            raise CommandError(f"{flag}: expected MM-DD, e.g. 08-01") from None

        # The model's own validators say what a month and a day may be; reusing
        # them keeps one wording for "13 is not a month".
        try:
            for validators, value in (
                (MONTH_VALIDATORS, month),
                (DAY_VALIDATORS, day),
            ):
                for validator in validators:
                    validator(value)
        except ValidationError as exc:
            raise CommandError(f"{flag}: {exc.messages[0]}") from None
        return month, day

    # --- output -----------------------------------------------------------

    def _report(self, steps, dry_run=False):
        """Print what each step did, and what to do next."""
        width = max((len(step.name) for step in steps), default=0)
        for step in steps:
            self.stdout.write(f"  {step.name:<{width}}  {self._describe(step)}")
        self.stdout.write("")

        if dry_run:
            self.stdout.write("Dry run: nothing was written.")
            return

        wrote = any(step.changed for step in steps)
        if not wrote:
            self.stdout.write("Nothing to do — the instance was already set up.")
            return

        domain = getattr(settings, "SITE_DOMAIN", "")
        if domain:
            self.stdout.write(f"Log in at https://{domain}/")
        self.stdout.write(
            "Everything else is edited in the web UI: /users/settings for the "
            "unit's details,\nand the Django admin for branches and sections."
        )

    def _describe(self, step):
        """One step, in a line."""
        parts = []
        if step.created:
            parts.append("created " + _names(step.created))
        if step.kept:
            parts.append(f"kept {len(step.kept)}")
        if parts:
            return ", ".join(parts)
        return step.note or "nothing to do"


def _names(items, limit=4):
    """A few names, or the count and the first few when there are many."""
    if len(items) <= limit:
        return ", ".join(items)
    return f"{len(items)} ({', '.join(items[:limit])}, …)"
