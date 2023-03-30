from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
from .models import CustomUser, CustomGroup, SchoolYear, Age
from .forms import CustomUserChangeForm, AccountCreationForm
from django.utils.html import format_html
from django.db.models import F
from django.db.models.functions import Concat


class CustomUserAdmin(UserAdmin):
    add_form = AccountCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    list_display = (
        "username",
        "email",
        "is_staff",
        "is_active",
    )
    list_filter = (
        "email",
        "is_staff",
        "is_active",
    )
    fieldsets = (
        (None, {"fields": ("email", "password", "parents")}),
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
                    "first_name",
                    "last_name",
                    "username",
                    "birthday",
                    "email",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                    "groups",
                    "user_permissions",
                    "parents",
                ),
            },
        ),
    )
    search_fields = ("email",)
    ordering = ("email",)


class CustomGroupAdmin(GroupAdmin):
    model = CustomGroup
    list_display = ["colored_name", "parents"]
    ordering = []
    fieldsets = (
        (
            None,
            {"fields": ("group_name", "year", "parents", "description", "permissions")},
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            full_name=Concat(F("parents__parents__name"), F("parents__name"), F("name"))
        ).order_by("full_name")
        return queryset

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parents":
            queryset = CustomGroup.objects.filter(
                parents__isnull=True
            ) | CustomGroup.objects.filter(parents__parents__isnull=True)
            queryset = queryset.order_by("name")
            kwargs["queryset"] = queryset
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display()
    def colored_name(self, obj):
        if obj.is_base():
            return format_html(f"<span style='color:darkblue'>{obj.name}</span>")
        elif obj.parents.is_base():
            if obj.year:
                return f"{obj.name}"
            else:
                return obj.name

        else:
            if obj.year:
                return format_html(f"<span style='color:lightblue'>{obj.name}</span>")
            else:
                return format_html(f"<span style='color:lightblue'>{obj.name}</span>")


admin.site.unregister(Group)
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(CustomGroup, CustomGroupAdmin)
admin.site.register(SchoolYear)
admin.site.register(Age)
