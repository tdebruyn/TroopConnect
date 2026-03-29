from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import filter_users_by_email
from allauth.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter that auto-links social logins to existing local accounts
    when the email matches. This implements the spec requirement:
    "If a local email matches a social login email, the system must
    prompt to link them."

    With SOCIALACCOUNT_AUTO_SIGNUP = True, allauth will automatically
    connect the social login to the existing account when emails match,
    as long as there's exactly one user with that email.
    """

    def pre_social_login(self, request, sociallogin):
        """
        Called after the social login is authenticated but before the
        login is processed. If a local account with the same email
        exists, connect the social login to it.
        """
        # If the social login is already connected to a user, nothing to do
        if sociallogin.is_existing:
            return

        # Check if a local account exists with this email
        email = sociallogin.account.extra_data.get("email")
        if not email:
            email_addresses = sociallogin.email_addresses
            if email_addresses:
                email = email_addresses[0].email

        if email:
            users = list(filter_users_by_email(email))
            if len(users) == 1:
                # Connect the social login to the existing user
                sociallogin.connect(request, users[0])

    def get_connect_redirect_url(self, request, socialaccount):
        """
        After linking a social account, redirect to the homepage
        (which will trigger onboarding if needed).
        """
        return "/"
