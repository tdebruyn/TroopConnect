"""System checks that stop a misconfigured instance from starting.

A troop self-hosting TroopConnect only ever touches environment variables, so
the failure mode we have to design against is "started with a variable missing
or misspelled and now behaves strangely" -- a site that serves the wrong domain,
an instance that cannot send its registration emails.

Every problem is reported as a single plain-language line naming the variable
and what to set it to. In production (``DJANGO_DEBUG`` unset) a bad variable is
an error, so ``migrate``/``runserver``/``gunicorn`` refuse to start. With
``DJANGO_DEBUG=1`` the same problems are warnings instead, so a developer can
get the app running before wiring up mail.
"""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from troopconnect.env import get_problems

# Hosts that only ever mean "this machine", and so are fine to serve DEBUG from.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "web", "testserver"}

# Stable check ids, one per variable, so documentation and CI output can point
# at a specific failure.
CHECK_IDS = {
    "SITE_DOMAIN": "troopconnect.E001",
    "EMAIL_URL": "troopconnect.E002",
    "DEFAULT_FROM_EMAIL": "troopconnect.E003",
    "ACME_EMAIL": "troopconnect.E004",
    "SECRET_KEY": "troopconnect.E005",
}
PARSE_ERROR_ID = "troopconnect.E006"
DEBUG_DOMAIN_ID = "troopconnect.W001"


def _severity():
    """Errors in production, warnings while DJANGO_DEBUG is on.

    Debug mode is the one setting where "let me get it running first" is
    legitimate; everywhere else a missing variable is a hard stop.
    """
    return Warning if settings.DEBUG else Error


def _error(variable, message, fallback_id=PARSE_ERROR_ID):
    return _severity()(
        message,
        id=CHECK_IDS.get(variable, fallback_id),
    )


def _check_required(errors):
    """Each required variable must be present and non-empty."""
    required = {
        "SITE_DOMAIN": (
            "Set it to the domain this instance is served from, for example "
            "SITE_DOMAIN=troop.example.org (no https:// and no trailing slash)."
        ),
        "EMAIL_URL": (
            "Set it to where outgoing mail should go, for example "
            "EMAIL_URL=smtp+tls://user:password@mail.example.org:587, or "
            "EMAIL_URL=console:// to print mail to the logs instead."
        ),
        "DEFAULT_FROM_EMAIL": (
            "Set it to the address your troop's mail is sent from, for example "
            "DEFAULT_FROM_EMAIL=inscriptions@example.org. It must be an address "
            "your mail provider lets you send as."
        ),
        "ACME_EMAIL": (
            "Set it to the address Let's Encrypt should use to warn you about "
            "expiring certificates, for example ACME_EMAIL=admin@example.org."
        ),
    }

    for variable, hint in required.items():
        if not getattr(settings, variable, None):
            errors.append(
                _error(variable, f"{variable} is not set. {hint}")
            )


def _check_site_domain(errors):
    """SITE_DOMAIN feeds ALLOWED_HOSTS verbatim, so it must be a bare hostname."""
    domain = getattr(settings, "SITE_DOMAIN", "") or ""
    if not domain:
        return

    if "://" in domain:
        errors.append(
            _error(
                "SITE_DOMAIN",
                f"SITE_DOMAIN must be a bare hostname without a scheme, but it "
                f"is set to '{domain}'. Use SITE_DOMAIN={domain.split('://')[-1].strip('/')} "
                f"instead.",
            )
        )
        return

    if "/" in domain or ":" in domain or " " in domain:
        errors.append(
            _error(
                "SITE_DOMAIN",
                f"SITE_DOMAIN must be a bare hostname with no path, port or "
                f"spaces, but it is set to '{domain}'.",
            )
        )


def _check_default_from_email(errors):
    """A malformed sender address makes every outgoing email fail silently."""
    address = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    if not address:
        return

    try:
        validate_email(address)
    except ValidationError:
        errors.append(
            _error(
                "DEFAULT_FROM_EMAIL",
                f"DEFAULT_FROM_EMAIL is not a valid email address: '{address}'.",
            )
        )


def _check_debug_domain(warnings):
    """DEBUG leaks source and settings, so it must not be on for a public domain."""
    if not settings.DEBUG:
        return

    domain = (getattr(settings, "SITE_DOMAIN", "") or "").lower()
    if domain and domain not in LOCAL_HOSTS:
        warnings.append(
            Warning(
                f"DEBUG is on but SITE_DOMAIN is '{domain}', which is not a "
                f"local address. Django's error pages expose source code and "
                f"settings. Set DJANGO_DEBUG=0 on any instance reachable from "
                f"the internet.",
                id=DEBUG_DOMAIN_ID,
            )
        )


def _check_recorded_problems(errors):
    """Replay problems recorded while the settings module parsed the environment."""
    for problem in get_problems():
        errors.append(_error(problem.variable, problem.message))


@register(Tags.security)
def troopconnect_settings_checks(app_configs, **kwargs):
    """Validate the environment-driven configuration before the app starts."""
    errors = []
    warnings = []

    _check_recorded_problems(errors)
    _check_required(errors)
    _check_site_domain(errors)
    _check_default_from_email(errors)
    _check_debug_domain(warnings)

    return errors + warnings
