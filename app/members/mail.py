"""Sending the emails the application writes on its own behalf.

Every template in :mod:`members.email_templates` refers to the troop by name
and links with an absolute URL built from the current ``django.contrib.sites``
row. Both are supplied here, so no call site has to remember them, and a
template cannot quietly end up with a bare domain or somebody else's name.
"""

from django.conf import settings
from django.contrib.sites.models import Site
from django.utils import translation
from post_office import mail

from .email_templates import DEFAULT_LANGUAGE, LANGUAGES
from .models import TroopSettings


def troop_name(language=None):
    """Name the outgoing emails speak for.

    Read from the troop's own settings rather than the environment, so the name
    a family sees in a confirmation is the one the troop typed into the settings
    page, and it survives a redeploy.

    ``name`` is translated, so pass the language the message is being written in
    and the troop's own translation for that language is used; without it the
    *sender's* current language would leak into a recipient's email.
    """
    if language is None:
        return TroopSettings.get_settings().name

    with translation.override(language):
        return TroopSettings.get_settings().name


def troop_logo_url():
    """Absolute URL of the troop's logo, for the HTML bodies.

    Absolute because a mail client has no page to resolve a relative path
    against. Falls back to the mark shipped with the application, so every
    template can rely on it existing — see
    :meth:`members.models.TroopSettings.logo_url`.
    """
    return absolute_url(TroopSettings.get_settings().logo_url())


def absolute_url(path):
    """Build an absolute URL for ``path`` from the current Site row.

    ``Site.domain`` is a bare hostname, so the scheme has to be added here:
    without it a link in an email is not clickable. Instances are served over
    TLS by the reverse proxy, so https is the right choice.
    """
    if path.startswith(("http://", "https://", "//")):
        return path

    if not path.startswith("/"):
        path = "/" + path

    return f"https://{Site.objects.get_current().domain}{path}"


def resolve_language(language):
    """Return a language that templates are actually seeded in.

    ``Account.preferred_language`` is free-form enough that a value outside the
    site's languages would otherwise make post_office raise ``DoesNotExist``
    mid-send, which surfaces as an email that simply never arrives.
    """
    if language in LANGUAGES:
        return language

    configured = getattr(settings, "LANGUAGE_CODE", None)
    if configured in LANGUAGES:
        return configured

    return DEFAULT_LANGUAGE


def send_templated(*, template, recipients, context=None, language=None, **options):
    """``post_office.mail.send`` with the troop's own context filled in.

    Adds ``troop_name`` and the absolute ``logo_url`` to the context, picks a
    language templates exist in,
    defaults the sender to ``DEFAULT_FROM_EMAIL`` and the ``Reply-To`` to the
    troop's own reply-to address when it has one, so callers pass only what is
    specific to the message.
    """
    resolved = resolve_language(language)
    options.setdefault("sender", settings.DEFAULT_FROM_EMAIL)

    reply_to = TroopSettings.get_settings().reply_to_email
    if reply_to:
        # post_office stores no reply-to column of its own; the header is how a
        # mail client learns where an answer should go. A caller that set its
        # own header wins.
        headers = dict(options.get("headers") or {})
        headers.setdefault("Reply-To", reply_to)
        options["headers"] = headers

    return mail.send(
        template=template,
        recipients=recipients,
        language=resolved,
        context={
            "troop_name": troop_name(resolved),
            "logo_url": troop_logo_url(),
            **(context or {}),
        },
        **options,
    )
