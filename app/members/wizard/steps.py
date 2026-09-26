"""The wizard's steps: one class each, one page each.

A step owns three things — the form it shows, what saving it does, and any
extra context its template needs — and nothing else. The view walks them, the
templates render them, and the browser never learns more than one at a time.

Four things are worth stating because they shape everything here:

* **Each step writes as it is saved.** Nothing is held back for a final
  commit, so "back" is just showing an earlier step again (with what was
  saved in it), a reload resumes where the last save left off, and abandoning
  the wizard leaves an instance configured as far as it got rather than
  nothing at all. It also means no password is ever held in a session waiting
  for a later step.
* **The wizard reuses the settings page's forms.** The identity, locale,
  calendar and module steps are the very forms ``/users/settings`` binds, so
  the fields, their validation and their translations are the same on both
  sides and cannot drift apart.
* **The administrator is created as staff, and made a superuser at the end.**
  "An instance with an administrator" is what tells the rest of the
  application the wizard is over, so granting that here would close the
  wizard behind itself halfway through.
* **Nothing here knows how it is rendered.** The steps take a request and
  return forms and data; the view and the templates do the rest, which is
  what lets the steps be tested without a browser.
"""

import uuid
from dataclasses import dataclass, field

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as gettext
from django.utils.translation import gettext_lazy as _

from members import setup as provisioning
from members.forms import (
    CalendarSettingsForm,
    LocaleSettingsForm,
    ModuleSettingsForm,
    OrganisationSettingsForm,
)
from members.models import Account, Branch, Enrollment, Section, TroopSettings
from members.presets import load_preset

from . import clear_attempts, client_address, code_matches

#: The sex a section takes, in the wizard's own words. ``Section.Sex``'s
#: labels are not translatable, and this is a page a person reads, so the
#: wizard spells them out rather than inheriting "Both" and "Male".
SECTION_SEXES = (
    ("B", _("Both")),
    ("M", _("Boys")),
    ("F", _("Girls")),
)

#: The languages a branch or section name may be written in, in the order the
#: editor shows them.
NAME_LANGUAGES = ("fr", "nl", "en")

SESSION_KEY = "setup"


class StepError(Exception):
    """This step cannot be saved, and the reason is worth showing as it is.

    Raised for a failure that is not a form error — SMTP refusing the test
    message above all — so the view can put the server's own words on the page
    instead of turning them into a 500.
    """

    def __init__(self, message, detail=""):
        self.message = message
        self.detail = detail
        super().__init__(message)


class Step:
    """One page of the wizard."""

    name = ""
    #: The heading, and the entry in the progress list.
    title = ""
    template = "members/setup/_step_form.html"
    #: False for a page that is read rather than filled in.
    saves = True

    def __init__(self, request):
        self.request = request

    def form(self, data=None, files=None):
        """The form to render, bound to ``data`` when there is any."""
        raise NotImplementedError

    def save(self, form):
        """Apply the step, and return a note for the next page.

        Only ever called on a valid, bound form.
        """
        return ""

    def context(self, form=None):
        """Anything extra this step's template needs."""
        return {}

    @property
    def setup_session(self):
        """This step's own corner of the session."""
        return self.request.session.setdefault(SESSION_KEY, {})


class CodeStep(Step):
    """The gate: nobody gets past here without the code from the logs."""

    name = "code"
    title = _("Setup code")

    def form(self, data=None, files=None):
        return SetupCodeForm(data)

    def save(self, form):
        clear_attempts(client_address(self.request))
        self.setup_session["code_ok"] = True
        return ""

    def context(self, form=None):
        return {"setup_code_hint": _code_hint()}


class AdminStep(Step):
    """The first administrator, who will end up this instance's superuser."""

    name = "admin"
    title = _("Administrator")

    def form(self, data=None, files=None):
        return AdminAccountForm(data)

    def save(self, form):
        email = form.cleaned_data["email"]
        try:
            step = provisioning.ensure_admin_account(
                email=email,
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                superuser=False,
            )
        except provisioning.SetupError as exc:
            # The service checks the address and the password again; a
            # disagreement here is worth showing, not a stack trace.
            raise StepError("\n".join(exc.problems)) from None

        account = Account.objects.get(email__iexact=email)
        self.setup_session["admin"] = str(account.pk)
        return "" if step.created else _("That account already existed; kept it.")


class IdentityStep(Step):
    """What the unit is called, and how the outside world reaches it."""

    name = "identity"
    title = _("The unit")

    def form(self, data=None, files=None):
        return OrganisationSettingsForm(
            data, files, instance=TroopSettings.get_settings()
        )

    def save(self, form):
        form.save()
        return ""


class LocaleStep(Step):
    """The languages offered, and the conventions used to display values."""

    name = "locale"
    title = _("Languages and country")

    def form(self, data=None, files=None):
        return LocaleSettingsForm(data, instance=TroopSettings.get_settings())

    def save(self, form):
        form.save()
        TroopSettings.clear_cache()
        return ""


class StructureStep(Step):
    """The branches and sections, starting from the federation's own layout."""

    name = "structure"
    title = _("Sections")
    template = "members/setup/_step_structure.html"

    def form(self, data=None, files=None):
        return StructureForm(data, self.name_languages(), request=self.request)

    def save(self, form):
        change = form.save()
        notes = []
        if change.removed:
            notes.append(gettext("Removed: %(rows)s.") % {"rows": ", ".join(change.removed)})
        if change.created:
            notes.append(
                gettext("%(count)s branches created.") % {"count": len(change.created)}
            )
        return " ".join(notes)

    def context(self, form=None):
        # The rows the template renders are the rows the form will save, bound
        # or not: one representation, so a row the browser added and a row the
        # database holds are the same thing to everything that reads them.
        if not isinstance(form, StructureForm):
            form = self.form()
        return {
            "languages": self.name_languages(),
            "sexes": SECTION_SEXES,
            "branches": form.branch_entries,
        }

    @staticmethod
    def name_languages():
        """The languages a name is written in: the ones this site offers.

        Writing a Dutch name on a site that offers only French is a field
        nobody can read, and leaving that column alone keeps whatever the
        federation's layout put there for the day the troop enables it.
        """
        return list(TroopSettings.get_settings().enabled_languages or ["fr"])


class CalendarStep(Step):
    """The dates that shape a scout year."""

    name = "calendar"
    title = _("The scout year")

    def form(self, data=None, files=None):
        return CalendarSettingsForm(data, instance=TroopSettings.get_settings())

    def save(self, form):
        form.save()
        return ""


class ModulesStep(Step):
    """Which of the optional modules this troop uses."""

    name = "modules"
    title = _("Modules")

    def form(self, data=None, files=None):
        return ModuleSettingsForm(data, instance=TroopSettings.get_settings())

    def save(self, form):
        form.save()
        return ""


class EmailStep(Step):
    """Send one real message, so a troop finds out now rather than later.

    Mail is the part of a self-hosted instance that is configured outside the
    application and fails quietly: a wrong port or a rejected sender shows up
    as nothing at all, weeks later, as parents who never heard anything. So
    the wizard sends a message through the backend the application itself uses
    — synchronously, where a failure can still be reported — and does not let
    go until it has arrived.
    """

    name = "email"
    title = _("Test email")
    template = "members/setup/_step_email.html"

    def form(self, data=None, files=None):
        return forms.Form(data)

    def save(self, form):
        account = self.account()
        if account is None:
            raise StepError(
                _("The administrator account is missing. Go back and create it.")
            )

        from django.core.mail import send_mail

        troop = TroopSettings.get_settings()
        subject = gettext("Test message from %(site)s") % {
            "site": troop.display_short_name()
        }
        body = gettext(
            "This is a test message from %(site)s.\n\n"
            "If you are reading it, this instance can send mail: registration "
            "confirmations, section messages and reminders will all arrive."
        ) % {"site": troop.display_short_name()}

        try:
            sent = send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[account.email],
                fail_silently=False,
            )
        except Exception as exc:  # noqa: BLE001 — see below
            # Deliberately broad. smtplib raises a dozen subclasses, the
            # MailerSend backend raises its own, a wrong host raises a socket
            # error and a bad address raises a Django one. What the operator
            # needs is the message their mail server gave, not a category this
            # code invented.
            raise StepError(
                _("The message could not be sent."),
                detail=f"{type(exc).__name__}: {exc}",
            ) from None

        if not sent:
            raise StepError(
                _("The mail backend reported that it sent nothing."),
                detail=gettext(
                    "Check EMAIL_URL (or MAIL_SEND_MODE) and DEFAULT_FROM_EMAIL "
                    "in this instance's environment."
                ),
            )

        self.finish(account)
        return ""

    def account(self):
        """The administrator this instance is being set up for."""
        pk = self.request.session.get(SESSION_KEY, {}).get("admin")
        if pk:
            account = Account.objects.filter(pk=pk).first()
            if account is not None:
                return account
        # The session can be lost between steps; the account it created is
        # still the one the wizard made.
        return Account.objects.filter(is_staff=True).order_by("-date_joined").first()

    def finish(self, account):
        """Make it this instance's administrator, and so mark it set up.

        The last thing the wizard does, which is why the work it never asked
        about happens here too: the school years, the email templates, the
        starter pages and the beat schedule are the same steps
        ``manage.py setup`` runs, and an instance set up in a browser has to
        end up as provisioned as one set up at a shell. All of it in one
        transaction, so a wizard that fails here leaves a retryable step
        rather than half a finished instance.
        """
        from django.db import transaction

        with transaction.atomic():
            provisioning.ensure_school_years()
            provisioning.ensure_email_templates()
            provisioning.ensure_site_pages()
            provisioning.ensure_periodic_tasks()

            if not account.is_superuser:
                account.is_superuser = True
                account.save(update_fields=["is_superuser"])

        self.request.session["setup_finished"] = str(account.pk)

    def context(self, form=None):
        account = self.account()
        return {
            "admin_email": account.email if account else "",
            "from_email": settings.DEFAULT_FROM_EMAIL,
            "next_label": _("Send and finish"),
        }


class DoneStep(Step):
    """What to do next, now that the instance is a troop."""

    name = "done"
    title = _("Done")
    template = "members/setup/_step_done.html"
    saves = False

    def form(self, data=None, files=None):
        return None

    def context(self, form=None):
        pk = self.request.session.get("setup_finished")
        account = Account.objects.filter(pk=pk).first() if pk else None
        return {"admin_email": account.email if account else ""}


#: Every step, in the order they are walked.
STEP_CLASSES = (
    CodeStep,
    AdminStep,
    IdentityStep,
    LocaleStep,
    StructureStep,
    CalendarStep,
    ModulesStep,
    EmailStep,
    DoneStep,
)

STEPS = {step.name: step for step in STEP_CLASSES}
ORDER = tuple(step.name for step in STEP_CLASSES)


def _code_hint():
    """Where to find the code, said the way this deployment stores it."""
    return _(
        "The code is in the web container's log, printed when the instance "
        "started. `docker compose logs web | grep -i \"setup code\"` shows it "
        "again, and `manage.py setup_code` prints it on demand."
    )


# --- forms -----------------------------------------------------------------


class SetupCodeForm(forms.Form):
    """The one-time code, read off the container's log."""

    code = forms.CharField(
        label=_("Setup code"),
        max_length=64,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "autofocus": True,
                "placeholder": "XXXX-XXXX-XXXX-XXXX",
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"]
        if not code_matches(code):
            raise ValidationError(_("That is not this instance's setup code."))
        return code


class AdminAccountForm(forms.Form):
    """The person who will administer this instance."""

    email = forms.EmailField(label=_("Email address"))
    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("The password for this account. Make it a long one."),
    )
    password_confirm = forms.CharField(
        label=_("Password (again)"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned = super().clean()
        first = cleaned.get("password")
        second = cleaned.get("password_confirm")
        if first and second and first != second:
            self.add_error("password_confirm", _("The two passwords do not match."))
        elif first:
            try:
                password_validation.validate_password(first)
            except ValidationError as exc:
                for message in exc.messages:
                    self.add_error("password", message)

        email = cleaned.get("email")
        if email and Account.objects.filter(email__iexact=email).exists():
            self.add_error(
                "email",
                _(
                    "An account with this address already exists. Use a "
                    "different address, or sign in with that one."
                ),
            )
        return cleaned


# --- the structure editor --------------------------------------------------


@dataclass
class SectionEntry:
    """One row of the structure editor's section list."""

    id: str
    names: dict
    sex: str = "B"
    branch: str = ""
    #: The languages this row is being edited in. Carried on the row because a
    #: template cannot index a dict by a variable, and the alternative — one
    #: branch of markup per language — is worse.
    languages: tuple = ()

    @property
    def name_fields(self):
        """The name inputs to render, in the order they are edited in."""
        return [
            {"language": language, "value": self.names.get(language, "")}
            for language in self.languages
        ]


@dataclass
class BranchEntry:
    """One row of the structure editor's branch list."""

    id: str
    key: str = ""
    names: dict = field(default_factory=dict)
    min_age: int | None = None
    max_age: int | None = None
    sections: list = field(default_factory=list)
    languages: tuple = ()

    @property
    def name_fields(self):
        """The name inputs to render, in the order they are edited in."""
        return [
            {"language": language, "value": self.names.get(language, "")}
            for language in self.languages
        ]


@dataclass
class StructureChange:
    """What saving the structure editor did."""

    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    removed: list = field(default_factory=list)


def new_row_id():
    """A fresh identifier for a row the browser just added."""
    return uuid.uuid4().hex[:8]


def default_structure(languages=()):
    """The federation's own layout, as the editor's starting rows."""
    return [
        BranchEntry(
            id=rung.key,
            key=rung.key,
            names={
                language: rung.names.get(language, rung.names["fr"])
                for language in NAME_LANGUAGES
            },
            min_age=rung.min_age,
            max_age=rung.max_age,
            languages=tuple(languages),
            sections=[
                SectionEntry(
                    id=f"{rung.key}-{index}",
                    names={
                        language: section.names.get(language, section.names["fr"])
                        for language in NAME_LANGUAGES
                    },
                    sex=section.sex,
                    branch=rung.key,
                    languages=tuple(languages),
                )
                for index, section in enumerate(rung.sections)
            ],
        )
        for rung in load_preset().branches
    ]


def structure_from_database(languages=()):
    """The branches and sections this instance already has, as editor rows."""
    return [
        BranchEntry(
            id=branch.key or f"branch-{branch.pk}",
            key=branch.key,
            names={
                language: getattr(branch, f"name_{language}") or ""
                for language in NAME_LANGUAGES
            },
            min_age=branch.min_age_dec_31,
            max_age=branch.max_age_dec_31,
            languages=tuple(languages),
            sections=[
                SectionEntry(
                    id=f"section-{section.pk}",
                    names={
                        language: getattr(section, f"name_{language}") or ""
                        for language in NAME_LANGUAGES
                    },
                    sex=section.sex or Section.Sex.BOTH,
                    branch=branch.key or f"branch-{branch.pk}",
                    languages=tuple(languages),
                )
                for section in branch.section_set.order_by("pk")
            ],
        )
        for branch in Branch.objects.order_by("min_age_dec_31", "name")
    ]


def new_section_entry(branch_id, languages=()):
    """An empty section row, for the editor's "add a section" button."""
    return SectionEntry(
        id=f"new-{new_row_id()}", names={}, branch=branch_id, languages=tuple(languages)
    )


def new_branch_entry(languages=()):
    """An empty branch row, for the editor's "add a branch" button."""
    return BranchEntry(id=f"new-{new_row_id()}", key="", names={}, languages=tuple(languages))


def sex_label(value):
    """The editor's word for a section's sex, for a template."""
    return dict(SECTION_SEXES).get(value or Section.Sex.BOTH, "")


class StructureForm(forms.Form):
    """The branch and section editor, parsed from the rows that were posted.

    Rows are read back by *position* rather than by index — one list of values
    per field, in document order — which is what lets the editor add and
    remove rows with no bookkeeping in the browser at all: a row that is no
    longer on the page is simply no longer in the post, and a row that was
    added is at the end. Each section carries the id of the branch it sits
    under, so the two lists stay in step however the page was rearranged.
    """

    def __init__(self, data=None, languages=("fr",), request=None):
        super().__init__(data)
        self.request = request
        # Only the languages the site offers are edited; see
        # StructureStep.name_languages. Names are still read in every language
        # so a preset's other-language names are carried through untouched.
        self.languages = [language for language in languages if language in NAME_LANGUAGES]
        self.branch_entries = []

        if data is None:
            self.branch_entries = structure_from_database(self.languages) or (
                default_structure(self.languages)
            )
            return

        self.branch_entries = self._parse(data)
        self._attach_sections()

    # -- reading the posted rows -------------------------------------------

    @staticmethod
    def _many(data, name):
        """Every value posted under ``name``, in document order."""
        if hasattr(data, "getlist"):
            return data.getlist(name)
        return [value for key, value in data.items() if key == name]

    def _parse(self, data):
        ids = self._many(data, "branch-id")
        keys = self._many(data, "branch-key")
        minimums = self._many(data, "branch-min")
        maximums = self._many(data, "branch-max")
        names = {
            language: self._many(data, f"branch-name-{language}")
            for language in self.languages
        }

        entries = []
        for position, row_id in enumerate(ids):
            entries.append(
                BranchEntry(
                    id=row_id,
                    key=_at(keys, position).strip(),
                    languages=tuple(self.languages),
                    names={
                        language: _at(names[language], position).strip()
                        for language in self.languages
                    },
                    min_age=_age(_at(minimums, position)),
                    max_age=_age(_at(maximums, position)),
                )
            )

        self.section_entries = []
        section_ids = self._many(data, "section-id")
        parents = self._many(data, "section-branch")
        sexes = self._many(data, "section-sex")
        section_names = {
            language: self._many(data, f"section-name-{language}")
            for language in self.languages
        }
        for position, row_id in enumerate(section_ids):
            self.section_entries.append(
                SectionEntry(
                    id=row_id,
                    names={
                        language: _at(section_names[language], position).strip()
                        for language in self.languages
                    },
                    sex=_at(sexes, position) or Section.Sex.BOTH,
                    branch=_at(parents, position),
                    languages=tuple(self.languages),
                )
            )
        return entries

    def _attach_sections(self):
        """Put each section under the branch row it names."""
        by_id = {entry.id: entry for entry in self.branch_entries}
        for entry in self.section_entries:
            parent = by_id.get(entry.branch)
            if parent is not None:
                parent.sections.append(entry)

    # -- validating --------------------------------------------------------

    def clean(self):
        cleaned = super().clean()
        if not self.branch_entries:
            raise ValidationError(_("A unit needs at least one branch."))
        if not self.languages:
            raise ValidationError(_("Enable at least one language first."))

        first_language = self.languages[0]
        for position, branch in enumerate(self.branch_entries, start=1):
            name = branch.names.get(first_language, "")
            label = name or gettext("Branch %(number)s") % {"number": position}
            if not name:
                raise ValidationError(
                    _("Branch %(number)s needs a name.") % {"number": position}
                )
            if (
                branch.min_age is not None
                and branch.max_age is not None
                and branch.min_age > branch.max_age
            ):
                raise ValidationError(
                    _("%(branch)s: the youngest age is above the oldest.") % {
                        "branch": label
                    }
                )
            if not branch.sections:
                raise ValidationError(
                    _("%(branch)s needs at least one section.") % {"branch": label}
                )
            for section in branch.sections:
                if not section.names.get(first_language, ""):
                    raise ValidationError(
                        _("%(branch)s: every section needs a name.") % {
                            "branch": label
                        }
                    )
        return cleaned

    # -- writing -----------------------------------------------------------

    def save(self):
        """Write the structure, and report what changed.

        The editor *is* the troop's structure, so what it describes is what
        ends up in the database: branches and sections that are no longer in
        it are removed. Nothing can be lost by that — the wizard only runs
        before the instance has an administrator, which is to say before
        anybody could have enrolled in anything — but :func:`_delete_safely`
        holds back anything that somehow has an enrolment anyway.
        """
        change = StructureChange()
        branches = {}

        for entry in self.branch_entries:
            branch = self._branch_for(entry)
            is_new = branch.pk is None
            for language in NAME_LANGUAGES:
                if language in entry.names:
                    setattr(branch, f"name_{language}", entry.names[language])
            name = branch.name_fr or ""
            if not branch.key:
                branch.key = entry.key or entry.id
            branch.min_age_dec_31 = entry.min_age
            branch.max_age_dec_31 = entry.max_age
            branch.save()
            branches[entry.id] = branch
            (change.created if is_new else change.updated).append(name)

        # The ladder is the order of the list: each rung leads to the next, and
        # the last one is where members leave the unit for good.
        for position, entry in enumerate(self.branch_entries):
            branch = branches[entry.id]
            following = self.branch_entries[position + 1 : position + 2]
            branch.promotes_to = branches[following[0].id] if following else None
            branch.is_top = not following
            branch.save(update_fields=["promotes_to", "is_top"])

        kept = self._save_sections(branches)
        change.removed += _delete_safely(Section.objects.exclude(pk__in=kept))
        change.removed += _delete_safely(
            Branch.objects.exclude(pk__in=[b.pk for b in branches.values()])
        )
        return change

    def _branch_for(self, entry):
        """The branch this row is, whether or not it exists yet.

        Matched by the key a previous save gave it, then by its name in any
        language being edited: re-opening the wizard edits the branches it
        created rather than adding a second set beside them, and a branch the
        troop renamed is still recognised after a reload.
        """
        if entry.key:
            existing = Branch.objects.filter(key=entry.key).first()
            if existing is not None:
                return existing
        if entry.id:
            existing = Branch.objects.filter(key=entry.id).first()
            if existing is not None:
                return existing
        for language in NAME_LANGUAGES:
            name = entry.names.get(language)
            if name:
                existing = Branch.objects.filter(**{f"name_{language}": name}).first()
                if existing is not None:
                    return existing
        return Branch()

    def _save_sections(self, branches):
        """Write every section row, and return the pks that are still wanted."""
        kept = set()
        for entry in self.branch_entries:
            branch = branches[entry.id]
            for section in entry.sections:
                row = self._section_for(section, branch)
                for language in NAME_LANGUAGES:
                    if language in section.names:
                        setattr(row, f"name_{language}", section.names[language])
                row.sex = section.sex if section.sex in dict(SECTION_SEXES) else Section.Sex.BOTH
                row.branch = branch
                row.save()
                kept.add(row.pk)
        return kept

    def _section_for(self, entry, branch):
        """The section this row is, whether or not it exists yet.

        Sections have no key of their own, so they are matched by name inside
        the branch they belong to — which is also how a troop tells one of its
        sections from another.
        """
        for language in NAME_LANGUAGES:
            name = entry.names.get(language)
            if name:
                existing = (
                    Section.objects.filter(branch=branch)
                    .filter(**{f"name_{language}": name})
                    .first()
                )
                if existing is not None:
                    return existing
        return Section(branch=branch)


def _delete_safely(queryset):
    """Delete what the editor no longer describes, holding back what it must.

    A branch or section that somehow has an enrolment is left where it is: the
    wizard runs before anybody can have enrolled, so this should never find
    one, and if it does, the right answer is to leave the member's data alone
    and let staff decide in the admin rather than cascade it away.
    """
    removed = []
    for row in queryset:
        if isinstance(row, Section):
            in_use = Enrollment.objects.filter(section=row).exists()
        else:
            in_use = Enrollment.objects.filter(section__branch=row).exists()
        if in_use:
            continue
        removed.append(str(row))
        row.delete()
    return removed


def _at(values, position):
    """``values[position]``, or ``""`` when the lists are uneven."""
    if position < len(values):
        return values[position] or ""
    return ""


def _age(text):
    """An age from a number input, or None when it was left empty."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return max(0, min(99, value))
