from django.contrib import admin

# from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.admin import UserAdmin

from django.contrib.auth.models import Group

# from .models import CustomUser, CustomGroup, SchoolYear, Age
from .models import Account, SchoolYear, Person, Section, Branch, SiteSettings

from .forms import AccountChangeForm, AccountCreationForm, AdminAccountChangeForm
from django.utils.html import format_html
from django.db.models import F
from django.db.models.functions import Concat


class AccountAdmin(UserAdmin):
    add_form = AccountCreationForm
    form = AdminAccountChangeForm
    model = Account
    list_display = (
        "email",
        "get_full_name",
        "is_staff",
        "is_active",
    )
    list_filter = (
        "email",
        "is_staff",
        "is_active",
    )
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal Info",
            {
                "fields": (
                    "person_first_name",
                    "person_last_name",
                    "person_birthday",
                    "person_sex",
                    "person_address",
                    "person_phone",
                    "person_photo_consent",
                    "person_note",
                )
            },
        ),
        (
            "Permissions",
            {"fields": ("is_staff", "is_active", "groups", "user_permissions")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                    "person_first_name",
                    "person_last_name",
                    "person_birthday",
                    "person_sex",
                    "person_address",
                    "person_phone",
                    "person_photo_consent",
                    "person_note",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )
    search_fields = ("email", "person__first_name", "person__last_name")
    ordering = ("email",)

    def get_full_name(self, obj):
        return f"{obj.person.first_name} {obj.person.last_name}"

    get_full_name.short_description = "Name"

    def save_model(self, request, obj, form, change):
        # Save Person data
        person = obj.person if hasattr(obj, "person") else Person()
        person.first_name = form.cleaned_data.get("person_first_name")
        person.last_name = form.cleaned_data.get("person_last_name")
        person.birthday = form.cleaned_data.get("person_birthday")
        person.sex = form.cleaned_data.get("person_sex")
        person.address = form.cleaned_data.get("person_address")
        person.phone = form.cleaned_data.get("person_phone")
        person.photo_consent = form.cleaned_data.get("person_photo_consent")
        person.note = form.cleaned_data.get("person_note")
        person.save()

        # Link Person to Account
        if not hasattr(obj, "person"):
            obj.person = person

        # Save Account
        super().save_model(request, obj, form, change)


# class CustomGroupAdmin(GroupAdmin):
#     model = CustomGroup
#     list_display = ["colored_name", "parents"]
#     ordering = []
#     fieldsets = (
#         (
#             None,
#             {"fields": ("group_name", "year", "parents", "description", "permissions")},
#         ),
#     )

#     def get_queryset(self, request):
#         queryset = super().get_queryset(request)
#         queryset = queryset.annotate(
#             full_name=Concat(F("parents__parents__name"), F("parents__name"), F("name"))
#         ).order_by("full_name")
#         return queryset

#     def formfield_for_foreignkey(self, db_field, request, **kwargs):
#         if db_field.name == "parents":
#             queryset = CustomGroup.objects.filter(
#                 parents__isnull=True
#             ) | CustomGroup.objects.filter(parents__parents__isnull=True)
#             queryset = queryset.order_by("name")
#             kwargs["queryset"] = queryset
#         return super().formfield_for_foreignkey(db_field, request, **kwargs)

#     @admin.display()
#     def colored_name(self, obj):
#         if obj.is_base():
#             return format_html(f"<span style='color:darkblue'>{obj.name}</span>")
#         elif obj.parents.is_base():
#             if obj.year:
#                 return f"{obj.name}"
#             else:
#                 return obj.name

#         else:
#             if obj.year:
#                 return format_html(f"<span style='color:lightblue'>{obj.name}</span>")
#             else:
#                 return format_html(f"<span style='color:lightblue'>{obj.name}</span>")


admin.site.register(Account, AccountAdmin)
admin.site.register(SchoolYear)
admin.site.register(Section)
admin.site.register(Branch)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Admin interface for site settings."""

    fieldsets = (
        (
            "Site Information",
            {"fields": ("site_name", "site_description", "site_keywords")},
        ),
        (
            "Contact Information",
            {"fields": ("contact_email", "contact_phone", "contact_address")},
        ),
        ("Social Media", {"fields": ("facebook_url", "instagram_url")}),
        ("Email Settings", {"fields": ("email_signature",)}),
        (
            "Registration Settings",
            {"fields": ("registration_open", "registration_message")},
        ),
    )

    def has_add_permission(self, request):
        # Only allow one instance of site settings
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Don't allow deleting the site settings
        return False
