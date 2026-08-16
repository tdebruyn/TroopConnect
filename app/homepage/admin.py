from django.contrib import admin

from homepage.models import Event, ImageAsset, SiteContent


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "section", "created_at")
    list_filter = ("section", "date")
    search_fields = ("title", "description")


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
