"""Sending the emails the application writes on its own behalf.

Every template in :mod:`members.email_templates` refers to the troop by name
and links with an absolute URL built from the current ``django.contrib.sites``
row. Both are supplied here, so no call site has to remember them, and a
template cannot quietly end up with a bare domain or somebody else's name.
"""

from django.conf import settings
from django.contrib.sites.models import Site
from post_office import mail

from .email_templates import DEFAULT_LANGUAGE, LANGUAGES


def troop_name():
    """Name the outgoing emails speak for.

    For now this is the ``TROOP_NAME`` setting, so that a freshly installed
    instance sends coherent mail before anyone has been into the admin. Moving
    it to the troop-editable settings in the database is a later step and only
    changes this function.
    """
    return settings.TROOP_NAME


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

    Adds ``troop_name`` to the context, picks a language templates exist in,
    and defaults the sender to ``DEFAULT_FROM_EMAIL``, so callers pass only
    what is specific to the message.
    """
    options.setdefault("sender", settings.DEFAULT_FROM_EMAIL)

    return mail.send(
        template=template,
        recipients=recipients,
        language=resolve_language(language),
        context={"troop_name": troop_name(), **(context or {})},
        **options,
    )
