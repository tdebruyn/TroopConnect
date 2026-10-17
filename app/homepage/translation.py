"""django-modeltranslation registration for the homepage app.

Adds per-language columns (fr/nl/en, defined in settings.MODELTRANSLATION_LANGUAGES)
for the superuser-edited page content. Untranslated values fall back to French.
"""
from modeltranslation.translator import TranslationOptions, register

from .models import SiteContent, TimelineActivity


@register(SiteContent)
class SiteContentTranslationOptions(TranslationOptions):
    fields = ("project_json", "html", "css")


@register(TimelineActivity)
class TimelineActivityTranslationOptions(TranslationOptions):
    fields = ("name",)
