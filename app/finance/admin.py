from django.contrib import admin

from .models import (
    CotisationConfig,
    FeeRule,
    Household,
    HouseholdAdjustment,
    HouseholdMember,
    Payment,
)


@admin.register(CotisationConfig)
class CotisationConfigAdmin(admin.ModelAdmin):
    list_display = ["school_year", "late_penalty_percent", "late_deadline"]


@admin.register(FeeRule)
class FeeRuleAdmin(admin.ModelAdmin):
    list_display = ["school_year", "branch", "member_type", "rank", "amount"]
    list_filter = ["school_year", "branch", "member_type", "rank"]
    list_editable = ["amount"]
    list_select_related = ["school_year", "branch"]


class HouseholdMemberInline(admin.TabularInline):
    model = HouseholdMember
    extra = 0
    raw_id_fields = ["person"]


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    inlines = [HouseholdMemberInline]


@admin.register(HouseholdAdjustment)
class HouseholdAdjustmentAdmin(admin.ModelAdmin):
    list_display = ["household", "school_year", "amount", "reason", "author"]
    list_filter = ["school_year"]
    search_fields = ["household__name", "reason"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["person", "school_year", "amount", "date", "note"]
    list_filter = ["school_year"]
    search_fields = ["person__first_name", "person__last_name"]
