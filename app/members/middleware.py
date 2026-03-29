from django.shortcuts import redirect
from django.urls import reverse


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
