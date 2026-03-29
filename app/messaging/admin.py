from django.contrib import admin
from .models import SectionMessage, SectionMessageRecipient


class SectionMessageRecipientInline(admin.TabularInline):
    model = SectionMessageRecipient
    extra = 0
    readonly_fields = ("parent", "sent_at")


@admin.register(SectionMessage)
class SectionMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "section", "sender", "created_at")
    list_filter = ("section", "created_at")
    inlines = [SectionMessageRecipientInline]
