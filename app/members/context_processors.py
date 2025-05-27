from django.conf import settings
from .models import SiteSettings


def contact_info(request):
    """Make contact information available to all templates."""
    site_settings = SiteSettings.get_settings()
    return {
        "contact_email": site_settings.contact_email,
        "site_name": site_settings.site_name,
        "site_description": site_settings.site_description,
        "site_keywords": site_settings.site_keywords,
        "registration_open": site_settings.registration_open,
        "registration_message": site_settings.registration_message,
    }
