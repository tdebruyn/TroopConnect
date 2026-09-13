from django.contrib import admin

from .models import AttestationCampaign, AttestationItem


@admin.register(AttestationCampaign)
class AttestationCampaignAdmin(admin.ModelAdmin):
    list_display = ["title", "step", "status", "created_by", "created_at"]
    list_filter = ["status"]


@admin.register(AttestationItem)
class AttestationItemAdmin(admin.ModelAdmin):
    list_display = ["campaign", "page_start", "extracted_name", "matched_person", "status"]
    list_filter = ["status"]
