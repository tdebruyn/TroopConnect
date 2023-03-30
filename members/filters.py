import django_filters
from .models import CustomUser, SchoolYear, CustomGroup
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


class UsersFilter(django_filters.FilterSet):
    CHOICES = (
        ("ascending", "Ascending"),
        ("descending", "Descending"),
    )
    QUALITY = (
        (0, "Animé"),
        (1, "Membre adulte"),
        (2, "Parent"),
        (3, "Demandée"),
        (4, "Archivée"),
        (5, "Tous"),
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
    # birthday_gt = django_filters.DateFilter(field_name="birthday", lookup_expr="gt")
    # birthday_lt = django_filters.DateFilter(field_name="birthday", lookup_expr="lt")
    birthday_year = django_filters.ChoiceFilter(
        choices=SchoolYear.birth_year_range()[1],
        field_name="birthday",
        label=_("Année de naissance"),
        empty_label=_("Année de naissance"),
        lookup_expr="year",
    )

    year = django_filters.ModelChoiceFilter(
        queryset=SchoolYear.objects.order_by("name").all(),
        label=_("Année scolaire"),
        empty_label=_("Année scolaire"),
        method="group_year",
    )
    section = django_filters.ModelChoiceFilter(
        queryset=CustomGroup.get_children("Section").all(),
        label=_("Section"),
        empty_label=_("Section"),
        method="get_section",
    )
    quality = django_filters.ChoiceFilter(
        choices=QUALITY,
        label=_("Qualité"),
        method="get_quality",
        empty_label=_("Qualité"),
    )

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "groups", "birthday"]

    def get_quality(self, queryset, field_name, value):
        if value != "5":
            groups = CustomGroup.get_all_leaf_nodes().filter(
                Q(name=self.QUALITY[int(value)][1])
                | Q(parents__name=self.QUALITY[int(value)][1])
            )
        else:
            return queryset
        return queryset.filter(groups__in=groups)

    def group_year(self, queryset, field_name, value):
        groups = CustomGroup.objects.filter(year=value)
        return queryset.filter(groups__in=groups).distinct()

    def get_section(self, queryset, field_name, value):
        groups = CustomGroup.objects.get(name=value).children.all()
        return queryset.filter(groups__in=groups).distinct()

    def filter_by_order(self, queryset, name, value):
        expression = "last_name" if value == "ascending" else "-last_name"
        return queryset.order_by(expression)
