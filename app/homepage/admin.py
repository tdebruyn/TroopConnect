from django.contrib import admin
from modeltranslation.admin import TranslationAdmin

from homepage.models import ImageAsset, SiteContent, TimelineActivity


@admin.register(TimelineActivity)
class TimelineActivityAdmin(TranslationAdmin):
    """The dates the public year-line is drawn from, one activity per row."""

    list_display = ("name", "start_date", "end_date")
    list_filter = ("start_date",)
    date_hierarchy = "start_date"
    search_fields = ("name",)
    ordering = ("start_date", "id")


@admin.register(SiteContent)
class SiteContentAdmin(admin.ModelAdmin):
    """Emergency raw-edit UI for the superuser-edited page content.

    Editing normally happens in the GrapesJS editor; one row per page.
    """

    list_display = ("page", "updated_at")
    readonly_fields = ("page", "updated_at")

    def has_add_permission(self, request):
        # Rows are created by the editor on first save; none left to add manually.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImageAsset)
class ImageAssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "file", "created_at")
    search_fields = ("original_name",)
