from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import translation


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
            # Check if we're not already on an exempt URL
            try:
                url_name = request.resolver_match.url_name if request.resolver_match else None
            except Exception:
                url_name = None

            if url_name not in self.EXEMPT_URL_NAMES:
                # Also exempt static/media URLs and check path directly
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
    the language it resolved is not in ``SiteSettings.available_languages``,
    fall back to the first enabled language (the site default). With exactly one
    enabled language the site is locked to it and the navbar selector is hidden.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        available = self._available_languages()
        request.available_languages = available

        active = translation.get_language()
        clamped = False
        if active not in available:
            active = available[0]
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
        # Local import to avoid a circular import at module load time
        # (models imports nothing from middleware, but keep it lazy).
        from .models import SiteSettings

        available = list(SiteSettings.get_settings().available_languages or [])
        if not available:
            available = [settings.LANGUAGE_CODE]
        return available
