from django import forms
from django.contrib import admin

# from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TranslationAdmin

from .forms import AccountCreationForm, AdminAccountChangeForm

# from .models import CustomUser, CustomGroup, SchoolYear, Age
from .models import (
    AVAILABLE_LANGUAGE_CHOICES,
    Account,
    Branch,
    ImportantDocument,
    Person,
    SchoolYear,
    Section,
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


@admin.register(Section)
class SectionAdmin(TranslationAdmin):
    list_display = ("name", "branch")
    search_fields = ("name",)


@admin.register(Branch)
class BranchAdmin(TranslationAdmin):
    list_display = ("name",)
    search_fields = ("name",)


class TroopSettingsForm(forms.ModelForm):
    """Explicit selectors for enabled + default languages.

    Declaring the fields here (rather than relying on formfield_overrides for the
    ArrayField) guarantees the checkboxes/dropdown render reliably. The same
    field pair is declared on the staff settings page's locale form, which is
    where a troop normally edits it.
    """

    enabled_languages = forms.MultipleChoiceField(
        required=True,
        choices=AVAILABLE_LANGUAGE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label=_("Enabled languages"),
        help_text=_("Languages available to users in the site language selector."),
    )
    default_language = forms.ChoiceField(
        required=True,
        choices=AVAILABLE_LANGUAGE_CHOICES,
        widget=forms.Select,
        label=_("Default language"),
        help_text=_("Default language for visitors. Must be one of the enabled languages."),
    )

    class Meta:
        model = TroopSettings
        fields = "__all__"  # noqa: DJ007 — admin-only singleton form

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Constrain the default-language dropdown to the currently-selected
        # enabled languages (from POST when saving, else the stored value).
        enabled = self._selected_enabled()
        if enabled:
            self.fields["default_language"].choices = [
                (code, label) for code, label in AVAILABLE_LANGUAGE_CHOICES if code in enabled
            ]

    def _selected_enabled(self):
        """Languages the user has marked enabled, from bound data or instance."""
        if self.is_bound:
            if hasattr(self.data, "getlist"):  # QueryDict (real request)
                return self.data.getlist("enabled_languages")
            value = self.data.get("enabled_languages", [])
        elif self.instance and self.instance.pk:
            value = self.instance.enabled_languages or []
        else:
            value = self.initial.get("enabled_languages", [])
        if isinstance(value, str):
            return [value]
        return list(value or [])

    def clean(self):
        cleaned = super().clean()
        enabled = cleaned.get("enabled_languages") or []
        default = cleaned.get("default_language")
        if not enabled:
            self.add_error(
                "enabled_languages", _("Select at least one available language.")
            )
        elif default and default not in enabled:
            self.add_error(
                "default_language",
                _("The default language must be one of the available languages."),
            )
        return cleaned


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
                    "archive_retention_years",
                )
            },
        ),
        (
            _("Modules"),
            {"fields": ("fees_enabled", "signing_enabled", "public_agenda_enabled")},
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
