from django.contrib import admin
from .models import CotisationConfig, Payment


@admin.register(CotisationConfig)
class CotisationConfigAdmin(admin.ModelAdmin):
    list_display = ["school_year", "full_fee", "sibling_discount", "animateur_fee", "late_deadline"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["person", "school_year", "amount", "date", "note"]
    list_filter = ["school_year"]
    search_fields = ["person__first_name", "person__last_name"]
