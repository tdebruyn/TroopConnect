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
    registrations_open = troop_settings.registrations_are_open()
    return {
        "contact_email": troop_settings.contact_email,
        "contact_phone": troop_settings.contact_phone,
        # Which federation the unit belongs to, as free text. A fact about the
        # unit, never a claim of endorsement: the project does not know the
        # federations its users belong to and does not speak for any of them.
        "federation": troop_settings.federation,
        # The site footer's legal line. Both forms are offered because the
        # field holds either: a troop with its own legal page stores the URL
        # and gets a link, and one that wrote its policy here gets the words.
        "privacy_policy": troop_settings.privacy_policy,
        "privacy_policy_url": troop_settings.privacy_policy_url(),
        "facebook_url": troop_settings.facebook_url,
        "instagram_url": troop_settings.instagram_url,
        # Where the unit meets: the address it stores, whatever it calls the
        # place, and its own picture of it. All three are optional and any of
        # them may be empty, so whoever renders them decides what to leave out
        # rather than filling a blank in here.
        "unit_address": troop_settings.footer_address,
        "meeting_place": troop_settings.meeting_place,
        # Through `map_url()`, never the field: an ImageField with no file has
        # no URL to ask for.
        "unit_map_url": troop_settings.map_url(),
        # The address as a map query, so the page can offer directions without
        # embedding anything that calls out to a map service on its own.
        "unit_address_url": troop_settings.address_search_url(),
        # The templates say `site_name`; the model field is `name`. Keeping the
        # context key means the header templates and their translations do not
        # have to change with the model.
        "site_name": troop_settings.name,
        "site_description": troop_settings.site_description,
        "site_keywords": troop_settings.site_keywords,
        # Resolved here rather than in each template: a template that reached
        # for ``troop_settings.logo.url`` would render nothing at all when the
        # field is empty, which is the normal case.
        "logo_url": troop_settings.logo_url(),
        "favicon_url": troop_settings.favicon_url(),
        # The effective window, not the stored switch: a troop that sets an
        # opening date is closed until that day arrives. The date itself is
        # only handed over while it is still ahead and the switch is on, so the
        # page never promises an opening the switch has cancelled.
        "registration_open": registrations_open,
        "registration_opens_on": troop_settings.registration_opens_on(),
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
        "agenda_enabled": module_enabled(modules.AGENDA),
        # The public page's blocks, composed on the public page card. The
        # template tests the switch and the words together: a content module
        # with nothing in it is not a block, and rendering its heading alone
        # would read as a page that broke rather than as one not written yet.
        "homepage_band_enabled": troop_settings.homepage_band_enabled,
        "homepage_desk_enabled": troop_settings.homepage_desk_enabled,
        "homepage_place_enabled": troop_settings.homepage_place_enabled,
        "homepage_about_enabled": troop_settings.homepage_about_enabled,
        "homepage_about_text": troop_settings.homepage_about_text,
        "homepage_faq_enabled": troop_settings.homepage_faq_enabled,
        "homepage_faq_text": troop_settings.homepage_faq_text,
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

    direct_ids = Enrollment.objects.filter(
        user=person, school_year=current_year
    ).values_list("section_id", flat=True)

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
