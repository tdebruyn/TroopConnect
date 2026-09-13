from django.contrib import admin

from .models import CotisationConfig, FeeRule, Payment


@admin.register(CotisationConfig)
class CotisationConfigAdmin(admin.ModelAdmin):
    list_display = ["school_year", "late_penalty_percent", "late_deadline"]


@admin.register(FeeRule)
class FeeRuleAdmin(admin.ModelAdmin):
    list_display = ["school_year", "branch", "member_type", "rank", "amount"]
    list_filter = ["school_year", "branch", "member_type", "rank"]
    list_editable = ["amount"]
    list_select_related = ["school_year", "branch"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["person", "school_year", "amount", "date", "note"]
    list_filter = ["school_year"]
    search_fields = ["person__first_name", "person__last_name"]
