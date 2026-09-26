"""Bringing a database to a usable state, one step at a time.

A freshly migrated TroopConnect can take a registration, but it is not yet a
*troop*: the branches are missing, nobody is an administrator, Celery has
nothing scheduled. This module is where that is put right. ``manage.py setup``
is one caller; the first-run web wizard is the other, which is why nothing
here knows about a terminal, a form or a translated string — the steps take
plain data and report what they did.

Two rules run through all of it:

* **Fill, never overwrite.** A step writes a value only where there is none:
  a ``TroopSettings`` field is missing while it still holds the model's own
  default, a branch's age or ladder link is missing while it is empty, a
  section is only ever created. A troop that has been running for a year can
  run this again and lose nothing.
* **All or nothing.** :func:`run_setup` wraps every step in one transaction,
  so a run that cannot finish leaves the database as it found it — and so that
  ``--dry-run`` can undo a run that would have succeeded.

The answers mapping :func:`run_setup` takes, every key optional::

    {
      "settings": {"name": "Les Scouts de Limal", "enabled_languages": ["fr", "nl"]},
      "preset": "les-scouts",              # a shipped name, or a path to a file
      "steps": {"preset": True, ...},      # which steps to run; all by default
      "admin": {"email": ..., "password": ..., "first_name": ..., "last_name": ...}
    }

``settings`` keys are ``TroopSettings`` field names. A value for a translated
field (``name``, ``site_description``, …) is either one string, written to
every language, or an object keyed by language.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from allauth.account.models import EmailAddress
from celery.schedules import crontab
from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone, translation

from . import email_templates, permissions
from .models import (
    Account,
    Branch,
    Person,
    PersonRole,
    Role,
    SchoolYear,
    Section,
    TroopSettings,
)
from .presets import DEFAULT_PRESET, PresetError, load_preset

logger = logging.getLogger(__name__)

#: The steps :func:`run_setup` runs, in order, each switchable through
#: ``answers["steps"]``.
STEPS = (
    "settings",
    "preset",
    "school_years",
    "email_templates",
    "site_pages",
    "periodic_tasks",
    "admin",
)

#: ``TroopSettings`` columns a first run has no business filling: the two
#: uploads (an answers file cannot carry a file) and the passage's own
#: bookkeeping, which the model's help text asks nobody to edit by hand.
NOT_ANSWERABLE = ("id", "logo", "favicon", "last_passage_school_year")

#: Template holding the starting point for each editable page, matching what
#: ``homepage.views`` seeds the editor with. Duplicated rather than imported:
#: importing a view module from a service would drag URLs and modules into a
#: management command's import graph.
PAGE_SNIPPETS = {
    "home": "homepage/snippets/home_default.html",
    "faq": "homepage/snippets/faq_default.html",
}


def periodic_task_schedule():
    """The recurring work beat runs, as ``settings.CELERY_BEAT_SCHEDULE``.

    Read from the settings rather than written down again here: that mapping is
    what ``DatabaseScheduler`` installs into the database when beat first
    starts, so a second copy in this module would be a second answer to the
    same question — and the one that drifted would be this one.
    """
    return settings.CELERY_BEAT_SCHEDULE


class SetupError(ValueError):
    """The answers cannot be applied — with every reason they cannot.

    One problem per line, each naming the thing to change
    (``settings.currency``, ``admin.email``), so a run can report all of them
    at once rather than one per attempt.
    """

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


@dataclass
class StepResult:
    """What one step did, in terms both callers can show.

    ``created`` and ``kept`` hold the things a person would recognise — the
    unit's name, a branch, ``home/fr`` — not instead of a count but as well as
    one, so "nothing happened" and "everything already existed" can be told
    apart in the output.
    """

    name: str
    created: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    note: str = ""

    @property
    def changed(self):
        """Whether this step wrote anything."""
        return bool(self.created)

    def __str__(self):
        parts = []
        if self.created:
            parts.append(f"created {len(self.created)}")
        if self.kept:
            parts.append(f"kept {len(self.kept)}")
        return f"{self.name}: " + (", ".join(parts) or "nothing to do")


# --- answers ---------------------------------------------------------------


def normalise_answers(raw=None):
    """Coerce an answers mapping into the shape :func:`run_setup` expects.

    Raises :class:`SetupError` on anything unrecognised, so a typo in an
    answers file is reported rather than silently ignored.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise SetupError([f"answers: expected an object, got {type(raw).__name__}"])

    unknown = sorted(set(raw) - {"settings", "preset", "steps", "admin"})
    if unknown:
        raise SetupError(
            [f"answers: unknown key(s) {', '.join(unknown)} — expected "
             f"settings, preset, steps, admin"]
        )

    values = raw.get("settings") or {}
    if not isinstance(values, dict):
        raise SetupError(["answers.settings: expected an object of field names"])

    steps = dict.fromkeys(STEPS, True)
    requested = raw.get("steps") or {}
    if not isinstance(requested, dict):
        raise SetupError(["answers.steps: expected an object of true/false"])
    unknown = sorted(set(requested) - set(STEPS))
    if unknown:
        raise SetupError(
            [f"answers.steps: unknown step(s) {', '.join(unknown)} — expected "
             f"{', '.join(STEPS)}"]
        )
    steps.update({name: bool(value) for name, value in requested.items()})

    admin = raw.get("admin")
    if admin is not None and not isinstance(admin, dict):
        raise SetupError(["answers.admin: expected an object"])

    return {
        "settings": values,
        "preset": raw.get("preset"),
        "steps": steps,
        "admin": admin,
    }


# --- the steps -------------------------------------------------------------


def fill_settings(values):
    """Write the troop settings that still hold the model's own default.

    A field counts as missing while it is empty or still carries its default —
    ``"Scouts"`` for the name, ``["fr"]`` for the languages. That is what lets
    this run on an instance that has been configured for a year: every value
    somebody chose is kept, and only the blanks are filled.
    """
    troop = TroopSettings.get_settings()
    answerable = answerable_fields()
    translated = translated_fields()
    languages = list(settings.MODELTRANSLATION_LANGUAGES)

    created, kept, touched = [], [], set()

    for name, value in values.items():
        if name not in answerable:
            raise SetupError(
                [f"settings.{name}: not a troop setting a first run can fill"]
            )
        touched.add(name)

        if name in translated:
            pairs = (
                [(language, value[language]) for language in languages
                 if language in value]
                if isinstance(value, dict)
                else [(language, value) for language in languages]
            )
            for language, text in pairs:
                column = f"{name}_{language}"
                if not _is_missing(troop, name, language):
                    kept.append(column)
                elif getattr(troop, column) == text:
                    kept.append(column)
                else:
                    setattr(troop, column, str(text))
                    created.append(column)
            continue

        value = _as_field_type(name, value)
        if _is_missing(troop, name) and getattr(troop, name) != value:
            setattr(troop, name, value)
            created.append(name)
        else:
            kept.append(name)

    # A run that filled nothing writes nothing — no pointless save, and no
    # cache invalidation on an instance that was already configured.
    if created:
        _check_settings(troop, touched)
        troop.save()
    return StepResult("settings", created=created, kept=kept)


def answerable_fields():
    """The ``TroopSettings`` fields an answers file may set, by name.

    Modeltranslation's per-language columns (``name_fr``, …) are left out: a
    value names the field, and a language is expressed by giving an object.
    """
    names = {field.name for field in TroopSettings._meta.concrete_fields}
    return names - set(NOT_ANSWERABLE) - {
        f"{name}_{language}"
        for name in translated_fields()
        for language in settings.MODELTRANSLATION_LANGUAGES
    }


def translated_fields():
    """The ``TroopSettings`` fields modeltranslation keeps a column per language for."""
    from modeltranslation.translator import translator

    return set(translator.get_options_for_model(TroopSettings).fields)


def ensure_school_years(today=None):
    """Create the school year ``today`` falls in, and the one after it.

    The same two years the nightly ``create_year_task`` keeps in place, from
    the same calendar helpers, so a first run and a year of Celery ticks
    cannot disagree about where the year boundary is.
    """
    troop = TroopSettings.get_settings()
    today = today or timezone.localdate()

    current_start = troop.school_year_for(today)
    created, kept = [], []
    for name in (current_start, current_start + 1):
        if SchoolYear.objects.filter(name=name).exists():
            kept.append(str(name))
            continue
        SchoolYear.objects.create_year(name)
        created.append(str(name))
        logger.info("Created school year %s", name)

    return StepResult("school_years", created=created, kept=kept)


def apply_preset(preset=None):
    """Create the preset's branches and sections, and link the ladder.

    A branch is recognised by its ``key`` first — the stable identity a preset
    writes onto the row — and by its name in any language second, which is all
    a branch created before the key existed has. Whatever it already holds is
    kept: the names, ages and ladder links are filled in only where they are
    empty, ``is_top`` and the sections are only ever written on a branch the
    preset itself created. Applying the same preset twice therefore adds
    nothing, and applying it to an instance that has been renamed and
    reorganised adds only what is genuinely new.
    """
    if preset is None:
        preset = DEFAULT_PRESET
    if isinstance(preset, (str, bytes, Path)):
        try:
            preset = load_preset(preset)
        except PresetError as exc:
            raise SetupError(
                [f"preset: {problem}" for problem in exc.problems]
            ) from None

    created_branches, created_sections, kept = [], [], []
    branches = {}

    for rung in preset.branches:
        branch = _find_branch(rung)
        if branch is None:
            branch = Branch()
            created_branches.append(rung.name_for("fr"))
            _write_names(branch, rung.names)
            # Only a branch this preset made gets its `is_top`: on an existing
            # one, False is what the column already holds and cannot be told
            # apart from a troop that decided this branch is not the last.
            branch.is_top = rung.is_top
        else:
            kept.append(f"branch {branch.name}")
            _write_names(branch, rung.names, only_missing=True)

        if not branch.key:
            branch.key = rung.key
        if branch.min_age_dec_31 is None and rung.min_age is not None:
            branch.min_age_dec_31 = rung.min_age
        if branch.max_age_dec_31 is None and rung.max_age is not None:
            branch.max_age_dec_31 = rung.max_age
        branch.save()
        branches[rung.key] = branch

    # The links come second: every branch they point at has to exist first,
    # or a preset that names its ladder out of order would fail.
    for rung in preset.branches:
        branch = branches[rung.key]
        if branch.promotes_to_id is not None:
            kept.append(f"{branch.name} → {branch.promotes_to}")
        elif rung.promotes_to is not None:
            branch.promotes_to = branches[rung.promotes_to]
            branch.save(update_fields=["promotes_to"])

    for rung in preset.branches:
        branch = branches[rung.key]
        # A branch that already has sections is the troop's: the preset's are
        # a stand-in for "one section per branch", and adding "Louveteaux"
        # beside a unit's own "Meute Waigunga" would be nobody's idea of
        # filling in what is missing.
        if branch.section_set.exists():
            kept.append(f"sections of {branch.name}")
            continue
        for wanted in rung.sections:
            section = Section(branch=branch, sex=wanted.sex)
            _write_names(section, wanted.names)
            section.save()
            created_sections.append(f"{branch.name} / {wanted.name_for('fr')}")

    return StepResult(
        "preset",
        created=[f"branch {name}" for name in created_branches]
        + [f"section {name}" for name in created_sections],
        kept=kept,
        note=str(preset),
    )


def ensure_email_templates():
    """Write the shipped email copy into every language it exists in.

    ``email_templates.seed`` already carries the rule this needs: a missing row
    is created, and an existing one is replaced only while it still holds copy
    this project wrote, so wording a troop has rewritten survives. The copy is
    seeded in all three shipped languages rather than only the enabled ones —
    post_office resolves a template by the exact ``(name, language)`` pair with
    no fallback, and a troop that enables a language later should find the
    templates already there.
    """
    from post_office.models import EmailTemplate

    before = set(
        EmailTemplate.objects.filter(name__in=email_templates.TEMPLATES).values_list(
            "name", "language"
        )
    )
    email_templates.seed(EmailTemplate)

    after = set(
        EmailTemplate.objects.filter(name__in=email_templates.TEMPLATES).values_list(
            "name", "language"
        )
    )
    created = sorted(f"{name}/{language}" for name, language in after - before)
    kept = sorted(f"{name}/{language}" for name, language in before)
    return StepResult("email_templates", created=created, kept=kept)


def ensure_site_pages():
    """Give the editable pages somewhere to start, in every enabled language.

    Each language gets the markup the GrapesJS editor would have seeded it
    with, so the page holds real content from the first request instead of
    being filled in on the fly — and an editor opening it sees what a visitor
    sees. A language that already has content is left alone.
    """
    from homepage.models import SiteContent

    languages = TroopSettings.get_settings().enabled_languages or ["fr"]
    created, kept = [], []

    for page, snippet in PAGE_SNIPPETS.items():
        content = SiteContent.objects.filter(page=page).first()
        if content is None:
            content = SiteContent(page=page)

        wrote = False
        for language in languages:
            column = f"html_{language}"
            if getattr(content, column):
                kept.append(f"{page}/{language}")
                continue
            with translation.override(language):
                setattr(content, column, render_to_string(snippet))
            created.append(f"{page}/{language}")
            wrote = True

        if wrote:
            content.save()

    return StepResult("site_pages", created=created, kept=kept)


def ensure_periodic_tasks():
    """Write the beat schedule into the database.

    Beat reads its schedule out of ``django_celery_beat`` tables, so on a
    fresh database there is nothing to run until either beat starts — which
    installs ``CELERY_BEAT_SCHEDULE`` itself, on the first run — or this does.
    Doing it here means a troop can see and change the schedule the moment the
    instance is set up, rather than after beat's first start.

    An entry is recognised by its name *or* by the task it runs, so an
    instance that already schedules a task keeps its own wording and its own
    timing.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    created, kept = [], []
    for name, entry in periodic_task_schedule().items():
        task = entry["task"]
        if PeriodicTask.objects.filter(Q(name=name) | Q(task=task)).exists():
            kept.append(name)
            continue

        schedule = entry["schedule"]
        if not isinstance(schedule, crontab):
            raise SetupError(
                [
                    f"CELERY_BEAT_SCHEDULE[{name!r}]: only crontab schedules are "
                    f"supported, got {type(schedule).__name__}"
                ]
            )

        row = CrontabSchedule.from_schedule(schedule)
        row.timezone = timezone.get_current_timezone()
        row.save()

        PeriodicTask.objects.create(
            name=name,
            task=task,
            crontab=row,
            description=entry.get("description", ""),
            enabled=True,
        )
        created.append(name)

    return StepResult("periodic_tasks", created=created, kept=kept)


def ensure_admin_account(
    email, password, first_name="", last_name="", superuser=True
):
    """Create the first administrator, unless that address already has one.

    The account is what the Django admin and the staff pages need; the person
    behind it gets the Animator primary role and the Admin secondary one, so
    the first way in is the unit's own staff rather than a nameless superuser.
    The address is marked verified, because allauth is configured to refuse a
    login until it is — an administrator who cannot log in is no use.
    """
    from django.core.validators import validate_email

    email = (email or "").strip()
    if not email:
        raise SetupError(["admin.email: required to create the administrator"])
    try:
        validate_email(email)
    except ValidationError:
        raise SetupError([f"admin.email: {email!r} is not an email address"]) from None

    if Account.objects.filter(email__iexact=email).exists():
        return StepResult(
            "admin",
            kept=[email],
            note="an account with that address already exists",
        )

    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    if not first_name or not last_name:
        raise SetupError(["admin.first_name and admin.last_name are required"])

    troop = TroopSettings.get_settings()
    person = Person(
        first_name=first_name,
        last_name=last_name,
        primary_role=Role.objects.get(short=permissions.ANIMATEUR),
        status="a",
    )
    person.full_clean()
    person.save()

    account = Account(
        email=email,
        person=person,
        is_staff=True,
        is_superuser=bool(superuser),
        is_active=True,
        preferred_language=troop.default_language,
    )
    if password:
        try:
            password_validation.validate_password(password, account)
        except ValidationError as exc:
            raise SetupError(
                [f"admin.password: {message}" for message in exc.messages]
            ) from None
        account.set_password(password)
    else:
        account.set_unusable_password()
    account.save()

    PersonRole.objects.get_or_create(
        person=person, role=Role.objects.get(short=permissions.ADMIN)
    )
    # allauth refuses a login until the address is verified
    # (ACCOUNT_EMAIL_VERIFICATION = "mandatory"), and this address was given by
    # whoever is setting the instance up.
    EmailAddress.objects.get_or_create(
        user=account,
        email=email,
        defaults={"verified": True, "primary": True},
    )

    return StepResult("admin", created=[email])


# --- the run ---------------------------------------------------------------


def run_setup(answers=None, dry_run=False):
    """Run every enabled step, and return what each one did.

    The whole run is one transaction. A step that raises takes the rest of the
    run with it, so a failure — a mistyped currency, a preset that will not
    load — leaves the database as it was rather than half provisioned. With
    ``dry_run`` the transaction is rolled back on purpose, and the results
    describe what a real run would have written.
    """
    answers = normalise_answers(answers)

    with transaction.atomic():
        steps = _run_steps(answers)
        if dry_run:
            transaction.set_rollback(True)

    # A dry run leaves the cache holding the row the rollback undid. The
    # receiver on the real model already cleared it on save, so this only has
    # to matter for the read that ran before the write.
    if dry_run:
        TroopSettings.clear_cache()

    return steps


def _run_steps(answers):
    """The steps themselves, in order, inside the caller's transaction."""
    steps = []
    wanted = answers["steps"]

    if answers["settings"]:
        steps.append(fill_settings(answers["settings"]))
    if wanted["preset"]:
        steps.append(apply_preset(answers["preset"]))
    if wanted["school_years"]:
        steps.append(ensure_school_years())
    if wanted["email_templates"]:
        steps.append(ensure_email_templates())
    if wanted["site_pages"]:
        steps.append(ensure_site_pages())
    if wanted["periodic_tasks"]:
        steps.append(ensure_periodic_tasks())
    if wanted["admin"]:
        steps.append(_run_admin(answers["admin"]))

    return steps


def _run_admin(admin):
    """The administrator step, or a note that there is nobody to create."""
    if not admin or not admin.get("email"):
        return StepResult(
            "admin",
            note="no admin email was given — create one with "
            "`manage.py createsuperuser`, or run this again with one",
        )
    return ensure_admin_account(
        email=admin.get("email"),
        password=admin.get("password"),
        first_name=admin.get("first_name", ""),
        last_name=admin.get("last_name", ""),
        superuser=admin.get("superuser", True),
    )


# --- helpers ---------------------------------------------------------------


def _as_field_type(name, value):
    """``value`` as the model field would hold it.

    A flag or a JSON file hands over a string where the column is a number or
    a boolean, and the model's own ``to_python`` is the one place that knows
    how each of them converts.
    """
    try:
        return TroopSettings._meta.get_field(name).to_python(value)
    except ValidationError as exc:
        raise SetupError(
            [f"settings.{name}: {message}" for message in exc.messages]
        ) from None


def _is_missing(troop, name, language=None):
    """Whether a ``TroopSettings`` value still holds nothing of its own.

    True while the column is empty or still carries the field's default — the
    two states a value nobody has chosen is in.
    """
    column = name if language is None else f"{name}_{language}"
    current = getattr(troop, column)
    if current is None or current == "" or current == []:
        return True
    return current == TroopSettings._meta.get_field(name).get_default()


def _check_settings(troop, touched):
    """Validate the row, reporting only the fields this run touched.

    ``full_clean`` runs over the whole row, and an instance that has been in
    use can hold a value some later constraint would reject. Complaining about
    a field nobody asked this run to change would block setup over somebody
    else's data, so only the touched fields — and the cross-field rules, which
    have no field of their own — are reported.
    """
    try:
        troop.full_clean()
    except ValidationError as exc:
        languages = tuple(settings.MODELTRANSLATION_LANGUAGES)
        problems = []
        for field_name, messages in exc.message_dict.items():
            base = field_name
            for language in languages:
                if field_name.endswith(f"_{language}"):
                    base = field_name[: -(len(language) + 1)]
                    break
            if field_name != NON_FIELD_ERRORS and base not in touched:
                continue
            label = "settings" if field_name == NON_FIELD_ERRORS else f"settings.{base}"
            problems.extend(f"{label}: {message}" for message in messages)
        if problems:
            raise SetupError(problems) from None


def _write_names(instance, names, only_missing=False):
    """Write a preset's names onto a branch or section, language by language.

    ``only_missing`` is what an existing row gets: a language column that
    already holds a name is left alone, so re-applying a preset never renames
    anything a troop has named.
    """
    for language, name in names.items():
        if language not in settings.MODELTRANSLATION_LANGUAGES:
            continue
        column = f"name_{language}"
        current = getattr(instance, column)
        if only_missing and current:
            continue
        if current != name:
            setattr(instance, column, name)


def _find_branch(rung):
    """The branch this rung of the preset is already on this database, if any."""
    existing = Branch.objects.filter(key=rung.key).first()
    if existing is not None:
        return existing
    for language, name in rung.names.items():
        if language not in settings.MODELTRANSLATION_LANGUAGES:
            continue
        existing = Branch.objects.filter(**{f"name_{language}": name}).first()
        if existing is not None:
            return existing
    return None
