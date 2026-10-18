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
from members.models import Account, TroopSettings
from members.structure import SECTION_SEXES, StructureForm

from . import clear_attempts, client_address, code_matches

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
    template = "members/setup/_step_code.html"

    def form(self, data=None, files=None):
        return SetupCodeForm(data)

    def save(self, form):
        clear_attempts(client_address(self.request))
        self.setup_session["code_ok"] = True
        return ""

    def context(self, form=None):
        return {
            "setup_code_hint": _code_hint(),
            "install_guide_url": INSTALL_GUIDE_URL,
        }


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
            # The row partials post back to whichever page owns them; the
            # wizard and the staff tool share the markup, not the URL.
            "row_url": "setup:structure_row",
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
        about happens here too: the school years, the email templates and the
        beat schedule are the same steps ``manage.py setup`` runs, and an
        instance set up in a browser has to end up as provisioned as one set up
        at a shell. All of it in one transaction, so a wizard that fails here
        leaves a retryable step rather than half a finished instance.
        """
        from django.db import transaction

        with transaction.atomic():
            provisioning.ensure_school_years()
            provisioning.ensure_email_templates()
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


#: The installation guide, which ships with the code that draws this screen —
#: which is why it is a constant and not a setting. The host reading the wizard
#: is the one person who needs it and the one least likely to know it exists.
INSTALL_GUIDE_URL = (
    "https://github.com/tdebruyn/TroopConnect/blob/main/GETTING-STARTED.md"
)


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
