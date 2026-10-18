from django.contrib import admin
from modeltranslation.admin import TranslationAdmin

from homepage.models import TimelineActivity


@admin.register(TimelineActivity)
class TimelineActivityAdmin(TranslationAdmin):
    """The dates the public year-line is drawn from, one activity per row."""

    list_display = ("name", "start_date", "end_date")
    list_filter = ("start_date",)
    date_hierarchy = "start_date"
    search_fields = ("name",)
    ordering = ("start_date", "id")
