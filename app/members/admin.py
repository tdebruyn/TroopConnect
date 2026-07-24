from django.contrib import admin
from django.contrib.postgres.fields import ArrayField
from django.forms import CheckboxSelectMultiple
from django.utils.translation import gettext_lazy as _

# from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.admin import UserAdmin

from django.contrib.auth.models import Group

# from .models import CustomUser, CustomGroup, SchoolYear, Age
from .models import (
    Account,
    SchoolYear,
    Person,
    Section,
    Branch,
    SiteSettings,
    ImportantDocument,
)

from .forms import AccountChangeForm, AccountCreationForm, AdminAccountChangeForm
from django.utils.html import format_html
from django.db.models import F
from django.db.models.functions import Concat

from modeltranslation.admin import TranslationAdmin


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
            _("Personal info"),
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
            _("Preferences"),
            {"fields": ("preferred_language",)},
        ),
        (
            _("Permissions"),
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
                    "preferred_language",
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

    get_full_name.short_description = _("Name")

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


admin.site.register(Account, AccountAdmin)
admin.site.register(SchoolYear)


@admin.register(Section)
class SectionAdmin(TranslationAdmin):
    list_display = ("name", "branch")
    search_fields = ("name",)


@admin.register(Branch)
class BranchAdmin(TranslationAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(SiteSettings)
class SiteSettingsAdmin(TranslationAdmin):
    """Admin interface for site settings (multilingual + language toggle)."""

    # Render the available_languages ArrayField as checkboxes.
    formfield_overrides = {
        ArrayField: {"widget": CheckboxSelectMultiple},
    }

    fieldsets = (
        (_("Languages"), {"fields": ("available_languages",)}),
        (
            _("Site information"),
            {"fields": ("site_name", "site_description", "site_keywords")},
        ),
        (
            _("Contact information"),
            {"fields": ("contact_email", "contact_phone", "contact_address")},
        ),
        (_("Social media"), {"fields": ("facebook_url", "instagram_url")}),
        (_("Email settings"), {"fields": ("email_signature",)}),
        (
            _("Registration settings"),
            {"fields": ("registration_open", "registration_message")},
        ),
        (
            _("Customizable text"),
            {"fields": ("photo_consent_text", "address_placeholder")},
        ),
    )

    def has_add_permission(self, request):
        # Only allow one instance of site settings
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Don't allow deleting the site settings
        return False


@admin.register(ImportantDocument)
class ImportantDocumentAdmin(TranslationAdmin):
    list_display = ("title", "url", "file", "created_at")
    search_fields = ("title",)
