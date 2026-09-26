from django.conf import settings
from django.utils import translation

from . import modules
from .models import TroopSettings
from .modules import module_enabled


def contact_info(request):
    """Make contact information available to all templates."""
    troop_settings = TroopSettings.get_settings()
    available = getattr(request, "enabled_languages", None)
    if available is None:
        available = list(troop_settings.enabled_languages or [settings.LANGUAGE_CODE])
    return {
        "contact_email": troop_settings.contact_email,
        # The templates say `site_name`; the model field is `name`. Keeping the
        # context key means the header templates and their translations do not
        # have to change with the model.
        "site_name": troop_settings.name,
        "site_description": troop_settings.site_description,
        "site_keywords": troop_settings.site_keywords,
        "registration_open": troop_settings.registration_open,
        "registration_message": troop_settings.registration_message,
        "photo_consent_text": troop_settings.photo_consent_text,
        "address_placeholder": troop_settings.address_placeholder,
        "currency": troop_settings.currency,
        "phone_region": troop_settings.phone_region,
        # Module switches, so any template can hide what is turned off. Read
        # through members.modules so this and the {% module_enabled %} tag (and
        # the decorator that 404s the same module's URLs) cannot disagree.
        "fees_enabled": module_enabled(modules.FEES),
        "signing_enabled": module_enabled(modules.SIGNING),
        "public_agenda_enabled": module_enabled(modules.AGENDA),
        # Language selector support (set by AvailableLanguagesMiddleware).
        "available_languages": list(available),
        "current_language": translation.get_language(),
        "show_language_selector": len(available) > 1,
    }


def nav_sections(request):
    """Provide sections the current user is connected to for the navigation dropdown."""
    from .models import Enrollment, SchoolYear, Section

    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"nav_sections": Section.objects.none()}

    if request.user.is_staff:
        sections = Section.objects.select_related("branch").order_by(
            "branch__name", "name"
        )
        return {"nav_sections": sections}

    if not hasattr(request.user, "person"):
        return {"nav_sections": Section.objects.none()}

    person = request.user.person
    current_year = SchoolYear.current()
    if not current_year:
        return {"nav_sections": Section.objects.none()}

    # Direct enrollments (animateurs and children)
    direct_ids = Enrollment.objects.filter(
        user=person, school_year=current_year
    ).values_list("section_id", flat=True)

    # Sections where user is a parent of an enrolled child
    parent_ids = Enrollment.objects.filter(
        user__as_child__parent=person, school_year=current_year
    ).values_list("section_id", flat=True)

    all_ids = set(direct_ids) | set(parent_ids)

    sections = Section.objects.filter(pk__in=all_ids).select_related("branch").order_by(
        "branch__name", "name"
    )
    return {"nav_sections": sections}


def mail_queue_status(request):
    """Expose the failed-email count to staff for the queue warning banner."""
    if not (
        hasattr(request, "user")
        and request.user.is_authenticated
        and request.user.is_staff
    ):
        return {}
    from post_office.models import STATUS, Email

    return {
        "failed_mail_count": Email.objects.filter(status=STATUS.failed).count(),
    }
