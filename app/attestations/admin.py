from django.contrib import admin

from .models import AttestationCampaign, AttestationItem, NameAlias


@admin.register(AttestationCampaign)
class AttestationCampaignAdmin(admin.ModelAdmin):
    list_display = ["title", "step", "status", "created_by", "created_at"]
    list_filter = ["status"]


@admin.register(AttestationItem)
class AttestationItemAdmin(admin.ModelAdmin):
    list_display = ["campaign", "page_start", "extracted_name", "matched_person", "status"]
    list_filter = ["status"]


@admin.register(NameAlias)
class NameAliasAdmin(admin.ModelAdmin):
    """Where a wrong or stale correspondence gets deleted."""

    list_display = ["name", "person", "created_by", "created_at"]
    search_fields = ["name", "person__first_name", "person__last_name"]
    readonly_fields = ["match_key", "created_at"]
