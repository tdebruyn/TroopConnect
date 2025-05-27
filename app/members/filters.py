import django_filters
from .models import (
    Account,
    Person,
    SchoolYear,
    Section,
    Role,
    Enrollment,
    PersonRole,
    Branch,
)
from django_filters import (
    DateFromToRangeFilter,
    DateFilter,
    CharFilter,
    NumberFilter,
    ModelChoiceFilter,
)
from django.utils.translation import gettext as _
from unidecode import unidecode
from django.db.models import Q
from datetime import datetime


class PersonFilter(django_filters.FilterSet):
    CHOICES = (
        ("ascending", "Ascending"),
        ("descending", "Descending"),
    )

    ordering = django_filters.ChoiceFilter(
        label="Ordering", choices=CHOICES, method="filter_by_order"
    )
    first_name = django_filters.CharFilter(
        field_name="first_name", lookup_expr="icontains", label=_("Prénom")
    )
    last_name = django_filters.CharFilter(
        field_name="last_name", lookup_expr="icontains", label=_("Nom")
    )
    birth_year = django_filters.ChoiceFilter(
        choices=[],  # Will be populated in __init__
        label=_("Année de naissance"),
        empty_label=_("Année de naissance"),
        method="filter_by_birth_year",
    )

    year = django_filters.ModelChoiceFilter(
        queryset=SchoolYear.objects.order_by("name").all(),
        label=_("Année scolaire"),
        empty_label=_("Année scolaire"),
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
        label=_("Rôle"),
        empty_label=_("Tous les rôles"),
        method="filter_by_role",
    )

    class Meta:
        model = Person
        fields = ["first_name", "last_name", "section", "birthday", "role"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Get current year for age calculations
        current_year = SchoolYear.current().name

        # Get all branches ordered by age range
        branches = Branch.objects.all().order_by("min_age_dec_31")

        # Generate birth year choices with branch information
        birth_year_choices = []

        # Calculate the range of years to include (e.g., last 20 years)
        current_date = datetime.now().date()
        start_year = current_date.year - 20  # Adjust range as needed
        end_year = current_date.year

        for year in range(end_year, start_year, -1):
            # Calculate age at December 31st of current year
            age_at_dec_31 = current_year - year

            # Find which branch this age corresponds to
            matching_branch = None
            for branch in branches:
                if (
                    branch.min_age_dec_31 is not None
                    and branch.max_age_dec_31 is not None
                    and branch.min_age_dec_31 <= age_at_dec_31 <= branch.max_age_dec_31
                ):
                    matching_branch = branch
                    break

            # Format the choice label
            if matching_branch:
                label = f"{year} ({matching_branch.name})"
            else:
                label = str(year)

            birth_year_choices.append((year, label))

        # Update the choices for the birth_year filter
        self.filters["birth_year"].extra["choices"] = birth_year_choices

    def filter_by_birth_year(self, queryset, name, value):
        """
        Filter persons by their birth year
        """
        if not value:
            return queryset

        # Convert value to integer (it comes as string from the form)
        birth_year = int(value)

        # Filter persons born in the selected year
        return queryset.filter(birthday__year=birth_year)

    def filter_by_role(self, queryset, field_name, value):
        """
        Filter persons by their assigned roles through the PersonRole model
        """
        if not value:
            return queryset

        # Get all PersonRole entries for the selected role
        person_roles = PersonRole.objects.filter(role=value)

        # Filter persons who have this role assigned
        return queryset.filter(id__in=person_roles.values("person_id")).distinct()

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
        # When only year is selected without section, return all persons
        section_value = self.form.cleaned_data.get("section") if self.form else None

        if not section_value:
            return queryset

        return queryset
