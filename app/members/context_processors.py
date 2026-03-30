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
        "photo_consent_text": site_settings.photo_consent_text,
        "address_placeholder": site_settings.address_placeholder,
    }


def nav_sections(request):
    """Provide sections the current user is connected to for the navigation dropdown."""
    from .models import Section, SchoolYear, Enrollment

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
