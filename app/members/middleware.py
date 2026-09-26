from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import translation


class SetupRequiredMiddleware:
    """Send every request to the wizard until this instance has an admin.

    A self-hosted instance starts as an empty database behind a domain: the
    first thing anybody sees should be the wizard that makes it a troop, not a
    site with no sections, no members and nobody able to administer it. So
    while ``members.wizard.setup_required()`` — an instance with no superuser
    that its deployment armed for setup — this redirects everything to
    ``/setup``.

    Four things are let through, each for a reason of its own:

    * the wizard itself, or it could never be used;
    * ``/static/`` and ``/media/``, or it would have no stylesheet — Caddy
      serves those in production, but the dev server and a bare ``runserver``
      do not;
    * ``/healthz``, because the container's own healthcheck asks for it and a
      redirect would leave a fresh instance permanently unhealthy, which is
      precisely when Caddy refuses to start and nobody can reach the wizard;
    * ``/i18n/setlang/``, which only writes the visitor's language choice.

    Being off is as important as being on: an unarmed deployment — a test run,
    or an instance started without the entrypoint — is left entirely alone,
    rather than being redirected by a wizard it has no code for.
    """

    EXEMPT_PREFIXES = ("/setup", "/static/", "/media/", "/__debug__/")
    EXEMPT_PATHS = ("/healthz", "/i18n/setlang/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._exempt(request.path) or not self._required():
            return self.get_response(request)
        return redirect("setup:index")

    def _exempt(self, path):
        return path.startswith(self.EXEMPT_PREFIXES) or path in self.EXEMPT_PATHS

    def _required(self):
        """Ask the wizard, not the database directly, so the two cannot disagree."""
        from members.wizard import setup_required

        return setup_required()


class OnboardingMiddleware:
    """
    Redirects authenticated users who haven't completed their profile
    to the onboarding page. Exempts the onboarding page itself, static files,
    admin, and auth URLs.
    """

    EXEMPT_URL_NAMES = [
        "onboarding",
        "account_logout",
        "account_login",
        "account_signup",
        "account_email_verification_sent",
        "account_confirm_email",
        "account_reset_password",
        "account_reset_password_done",
        "account_reset_password_from_key",
        "account_reset_password_from_key_done",
        "socialaccount_login",
        "socialaccount_signup",
        "socialaccount_login_cancelled",
        "socialaccount_authentication_error",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not request.user.is_staff
            and hasattr(request.user, "person")
            and request.user.person.status == "r"
        ):
            try:
                url_name = request.resolver_match.url_name if request.resolver_match else None
            except Exception:
                url_name = None

            if url_name not in self.EXEMPT_URL_NAMES:
                onboarding_path = reverse("members:onboarding")
                if (
                    not request.path.startswith(("/static/", "/media/", "/__debug__/", "/accounts/"))
                    and request.path != onboarding_path
                ):
                    return redirect("members:onboarding")

        return self.get_response(request)


class AvailableLanguagesMiddleware:
    """Restrict the active language to those enabled by the superadmin.

    Placed immediately after ``django.middleware.locale.LocaleMiddleware``. If
    the language it resolved is not in ``TroopSettings.enabled_languages``,
    fall back to ``TroopSettings.default_language``. With exactly one enabled
    language the site is locked to it and the navbar selector is hidden.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        available = self._available_languages()
        request.enabled_languages = available

        active = translation.get_language()
        clamped = False
        if active not in available:
            default = self._default_language()
            active = default if default in available else available[0]
            translation.activate(active)
            request.LANGUAGE_CODE = active
            clamped = True

        response = self.get_response(request)

        # Persist a clamped language so a now-disabled language stored in the
        # session/cookie doesn't keep retriggering the clamp on every request.
        # LocaleMiddleware.process_response (which runs after this) also sets
        # this cookie on 200 responses via the updated request.LANGUAGE_CODE.
        if clamped:
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                active,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN,
                secure=settings.LANGUAGE_COOKIE_SECURE,
                httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )
        return response

    @staticmethod
    def _available_languages():
        # Local import to avoid a circular import at module load time.
        from .models import TroopSettings

        available = list(TroopSettings.get_settings().enabled_languages or [])
        if not available:
            available = [settings.LANGUAGE_CODE]
        return available

    @staticmethod
    def _default_language():
        # Local import to avoid a circular import at module load time.
        from .models import TroopSettings

        default = TroopSettings.get_settings().default_language
        return default or settings.LANGUAGE_CODE
