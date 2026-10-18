"""django-modeltranslation registration for the homepage app.

Adds per-language columns (fr/nl/en, defined in settings.MODELTRANSLATION_LANGUAGES)
for the timeline activities. Untranslated values fall back to French.
"""
from modeltranslation.translator import TranslationOptions, register

from .models import TimelineActivity


@register(TimelineActivity)
class TimelineActivityTranslationOptions(TranslationOptions):
    fields = ("name",)
