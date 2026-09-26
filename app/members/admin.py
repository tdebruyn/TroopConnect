from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TranslationAdmin

from .forms import (
    AccountCreationForm,
    AdminAccountChangeForm,
    LanguageSelectionMixin,
)
from .models import (
    Account,
    Branch,
    ImportantDocument,
    Person,
    SchoolYear,
    Section,
    SectionEvent,
    TroopSettings,
)


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


@admin.register(SectionEvent)
class SectionEventAdmin(admin.ModelAdmin):
    """The escape hatch for an agenda entry a leader can no longer fix.

    Day-to-day editing happens on the section agenda itself, which is
    restricted to that section's leaders; this is where a unit admin repairs an
    entry after a leader leaves.
    """

    list_display = ("title", "start_date", "section", "activity_type")
    list_filter = ("section", "activity_type", "start_date")
    search_fields = ("title", "description")
    date_hierarchy = "start_date"


@admin.register(Section)
class SectionAdmin(TranslationAdmin):
    list_display = ("name", "branch", "email")
    search_fields = ("name", "email")


@admin.register(Branch)
class BranchAdmin(TranslationAdmin):
    # `promotes_to` / `is_top` are the ladder the passage walks: the columns are
    # here so a troop can see and change its shape without reading the code.
    list_display = (
        "name",
        "key",
        "min_age_dec_31",
        "max_age_dec_31",
        "promotes_to",
        "is_top",
    )
    search_fields = ("name", "key")


class TroopSettingsForm(LanguageSelectionMixin, forms.ModelForm):
    """The admin's view of the troop settings: one form, every field.

    The enabled/default language pair and its validation are shared with the
    staff settings page's locale form (``members.forms.LanguageSelectionMixin``)
    so the two cannot drift apart.
    """

    class Meta:
        model = TroopSettings
        fields = "__all__"  # noqa: DJ007 — admin-only singleton form


@admin.register(TroopSettings)
class TroopSettingsAdmin(TranslationAdmin):
    """Admin interface for troop settings (multilingual + language toggle)."""

    form = TroopSettingsForm

    fieldsets = (
        (
            _("Organisation"),
            {
                "fields": (
                    "name",
                    "short_name",
                    "federation",
                    "contact_email",
                    "contact_phone",
                    "reply_to_email",
                    "footer_address",
                    "privacy_policy",
                )
            },
        ),
        (
            _("Branding"),
            {"fields": ("logo", "favicon")},
        ),
        (
            _("Locale"),
            {
                "fields": (
                    "enabled_languages",
                    "default_language",
                    "phone_region",
                    "currency",
                )
            },
        ),
        (
            _("Calendar"),
            {
                "fields": (
                    "year_start_month",
                    "year_start_day",
                    "age_reference_month",
                    "age_reference_day",
                    "passage_month",
                    "passage_day",
                    "passage_mode",
                    "top_branch_graduates_become_leaders",
                    "archive_retention_years",
                )
            },
        ),
        (
            _("Modules"),
            {"fields": ("fees_enabled", "signing_enabled", "agenda_enabled")},
        ),
        (
            _("Site information"),
            {"fields": ("site_description", "site_keywords")},
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
        # Only allow one instance of the troop settings
        return not TroopSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Don't allow deleting the troop settings
        return False


@admin.register(ImportantDocument)
class ImportantDocumentAdmin(TranslationAdmin):
    list_display = ("title", "url", "file", "created_at")
    search_fields = ("title",)
