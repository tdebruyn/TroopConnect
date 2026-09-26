"""django-modeltranslation registration.

Adds per-language columns (fr/nl/en, defined in settings.MODELTRANSLATION_LANGUAGES)
for editorial/admin-editable content. Untranslated values fall back to French
(settings.MODELTRANSLATION_FALLBACK_LANGUAGES). Source strings here are English
msgids so they also work for Django's static translation catalog.
"""
from modeltranslation.translator import TranslationOptions, register

from .models import Branch, ImportantDocument, Role, Section, TroopSettings


@register(TroopSettings)
class TroopSettingsTranslationOptions(TranslationOptions):
    # Editorial text shown to users; NOT the config fields
    # (enabled_languages, phone_region, currency, contact_*, registration_open,
    #  the calendar fields, the module switches, last_passage_school_year).
    fields = (
        "name",
        "site_description",
        "site_keywords",
        "email_signature",
        "registration_message",
        "photo_consent_text",
        "address_placeholder",
    )


@register(Role)
class RoleTranslationOptions(TranslationOptions):
    # `short` is a stable code, not translated.
    fields = ("name", "description")


@register(Branch)
class BranchTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Section)
class SectionTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ImportantDocument)
class ImportantDocumentTranslationOptions(TranslationOptions):
    fields = ("title",)
