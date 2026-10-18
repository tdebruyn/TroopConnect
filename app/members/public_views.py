"""The contact form on the public site, and its anti-spam challenge.

The instance is self-hosted and the product promises not to route member data
through a third party, so the challenge is ALTCHA's proof-of-work rather than a
hosted captcha: the browser solves a signed challenge, the server verifies the
solution with the site's own secret, and no visitor data leaves the instance.
A honeypot and a session rate limit stand beside it.

No name of the recipient is ever shown; the form says the unit's animateur
responsable answers.
"""

import json
import time
from datetime import UTC, datetime, timedelta

from altcha import create_challenge_v1, verify_solution_v1
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods
from post_office import mail

from .contacts import public_contact_recipients
from .mail import troop_name
from .permissions import is_htmx

WINDOW_SESSION_KEY = "public_contact_window"
MAX_MESSAGES_PER_HOUR = 5

#: The proof-of-work ceiling. The browser finds a number under it; a higher
#: ceiling makes a mass sender pay far more than a visitor answering once.
ALTCHA_MAX_NUMBER = 100000
ALTCHA_ALGORITHM = "SHA-256"
CHALLENGE_TTL = 600


class PublicContactForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        label=_("Your name"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        label=_("Your email"),
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    message = forms.CharField(
        max_length=5000,
        label=_("Message"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 7}),
    )
    # Filled by the ALTCHA widget, which creates its own hidden input with this
    # name. The field is never rendered as a second input: two inputs with one
    # name would submit one payload twice.
    altcha = forms.CharField(
        widget=forms.HiddenInput,
        error_messages={
            "required": _("Please complete the anti-spam check."),
        },
    )
    # A field no person fills in. The template hides it from the eye and the
    # accessibility tree; a bot that fills every input gives itself away.
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "d-none", "tabindex": "-1", "autocomplete": "off"}
        ),
    )

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if "\n" in name or "\r" in name:
            raise ValidationError(_("The name cannot contain a line break."))
        return name

    def clean_altcha(self):
        payload = self.cleaned_data["altcha"]
        try:
            verified, _error = verify_solution_v1(
                payload, settings.SECRET_KEY
            )
        except Exception:
            # The payload is untrusted input; a malformed one is a failed
            # check, not a server error.
            verified = False
        if not verified:
            raise ValidationError(
                _("The anti-spam check did not pass. Try again.")
            )
        return payload

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("website"):
            raise ValidationError(_("The message could not be sent."))
        return cleaned_data


def _rate_limited(request):
    window = request.session.get(WINDOW_SESSION_KEY)
    if not window or time.time() - window.get("start", 0) > 3600:
        return False
    return window.get("count", 0) >= MAX_MESSAGES_PER_HOUR


def _count_message(request):
    now = time.time()
    window = request.session.get(WINDOW_SESSION_KEY)
    if not window or now - window.get("start", 0) > 3600:
        window = {"start": now, "count": 0}
    window["count"] = window.get("count", 0) + 1
    request.session[WINDOW_SESSION_KEY] = window


def _send_public_message(*, name, email, message):
    """Email the unit lead, with the visitor's address as the Reply-To."""
    recipients = public_contact_recipients()
    if not recipients:
        return False

    language = settings.LANGUAGE_CODE
    with translation.override(language):
        subject = _("Website contact — %(name)s") % {"name": name}
        body = "\n".join(
            [
                _(
                    "A visitor wrote through the contact form on the "
                    "%(troop)s site."
                )
                % {"troop": troop_name(language)},
                "",
                _("Name: %(name)s") % {"name": name},
                _("Email: %(email)s") % {"email": email},
                "",
                message,
            ]
        )

    mail.send(
        sender=settings.DEFAULT_FROM_EMAIL,
        recipients=[recipient.email for recipient in recipients],
        subject=subject,
        message=body,
        headers={"Reply-To": email},
    )
    return True


def _render(request, form):
    template = (
        "members/public_contact_modal.html"
        if is_htmx(request)
        else "members/public_contact.html"
    )
    return render(request, template, {"form": form})


@require_GET
def public_contact_challenge(request):
    """A fresh signed challenge for the widget, never cached."""
    challenge = create_challenge_v1(
        algorithm=ALTCHA_ALGORITHM,
        max_number=ALTCHA_MAX_NUMBER,
        hmac_key=settings.SECRET_KEY,
        expires=datetime.now(UTC) + timedelta(seconds=CHALLENGE_TTL),
    )
    response = JsonResponse(challenge.to_dict())
    response["Cache-Control"] = "no-store"
    return response


@require_http_methods(["GET", "POST"])
def public_contact(request):
    if request.method == "POST":
        form = PublicContactForm(request.POST)
        if form.is_valid():
            if _rate_limited(request):
                form.add_error(
                    None,
                    _(
                        "Too many messages from this browser. Try again later."
                    ),
                )
            elif not _send_public_message(
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                message=form.cleaned_data["message"],
            ):
                form.add_error(None, _("No contact is configured yet."))
            else:
                _count_message(request)
                if is_htmx(request):
                    return HttpResponse(
                        status=204,
                        headers={
                            "HX-Trigger": json.dumps(
                                {
                                    "showMessage": _(
                                        "Your message has been sent. The "
                                        "animateur responsable will answer you "
                                        "by email."
                                    )
                                }
                            )
                        },
                    )
                return redirect("public_contact_sent")
    else:
        form = PublicContactForm()

    return _render(request, form)


def public_contact_sent(request):
    return render(request, "members/public_contact_sent.html")
