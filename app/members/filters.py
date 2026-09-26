from datetime import datetime

import django_filters
from django.utils.translation import gettext_lazy as _

from .models import (
    Branch,
    Enrollment,
    Person,
    Role,
    SchoolYear,
    Section,
)


class PersonFilter(django_filters.FilterSet):
    CHOICES = (
        ("ascending", _("Ascending")),
        ("descending", _("Descending")),
    )

    ordering = django_filters.ChoiceFilter(
        label=_("Ordering"), choices=CHOICES, method="filter_by_order"
    )
    first_name = django_filters.CharFilter(
        field_name="first_name", lookup_expr="icontains", label=_("First name")
    )
    last_name = django_filters.CharFilter(
        field_name="last_name", lookup_expr="icontains", label=_("Last name")
    )
    birth_year = django_filters.ChoiceFilter(
        choices=[],
        label=_("Birth year"),
        empty_label=_("Birth year"),
        method="filter_by_birth_year",
    )

    year = django_filters.ModelChoiceFilter(
        queryset=SchoolYear.objects.order_by("name").all(),
        label=_("School year"),
        empty_label=_("School year"),
        method="filter_by_year",
        initial=SchoolYear.current,
    )
    section = django_filters.ModelChoiceFilter(
        queryset=Section.objects.order_by("name").all(),
        label=_("Section"),
        empty_label=_("Section"),
        method="get_section",
    )
    role = django_filters.ModelChoiceFilter(
        queryset=Role.objects.all().order_by("name").filter(is_primary=True),
        label=_("Role"),
        empty_label=_("All roles"),
        method="filter_by_role",
    )

    class Meta:
        model = Person
        fields = ["first_name", "last_name", "section", "birthday", "role"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        current_year = SchoolYear.current().name

        branches = Branch.objects.all().order_by("min_age_dec_31")

        birth_year_choices = []

        current_date = datetime.now().date()
        start_year = current_date.year - 20
        end_year = current_date.year

        for year in range(end_year, start_year, -1):
            age_at_dec_31 = current_year - year

            matching_branch = None
            for branch in branches:
                if (
                    branch.min_age_dec_31 is not None
                    and branch.max_age_dec_31 is not None
                    and branch.min_age_dec_31 <= age_at_dec_31 <= branch.max_age_dec_31
                ):
                    matching_branch = branch
                    break

            if matching_branch:
                label = f"{year} ({matching_branch.name})"
            else:
                label = str(year)

            birth_year_choices.append((year, label))

        self.filters["birth_year"].extra["choices"] = birth_year_choices

    def filter_by_birth_year(self, queryset, name, value):
        """
        Filter persons by their birth year
        """
        if not value:
            return queryset

        birth_year = int(value)

        return queryset.filter(birthday__year=birth_year)

    def filter_by_role(self, queryset, field_name, value):
        """
        Filter persons by their primary role
        """
        if not value:
            return queryset

        return queryset.filter(primary_role=value)

    def get_section(self, queryset, field_name, value):
        """
        Filter persons by their enrollment in a specific section for the selected year
        Since year always has a default value (current year), we can assume it's always present
        """
        if not value:
            return queryset
        year_value = self.form.cleaned_data.get("year")
        enrollments = Enrollment.objects.filter(section=value, school_year=year_value)
        return queryset.filter(id__in=enrollments.values("user_id")).distinct()

    def filter_by_order(self, queryset, name, value):
        expression = "last_name" if value == "ascending" else "-last_name"
        return queryset.order_by(expression)

    def filter_by_year(self, queryset, field_name, value):
        """
        When only year is selected (without section):
        - Return all persons regardless of enrollment status

        The year filter only affects results when combined with section filter
        """
        section_value = self.form.cleaned_data.get("section") if self.form else None

        if not section_value:
            return queryset

        return queryset
