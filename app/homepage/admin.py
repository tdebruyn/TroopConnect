from django.contrib import admin
from homepage.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "section", "created_at")
    list_filter = ("section", "date")
    search_fields = ("title", "description")
