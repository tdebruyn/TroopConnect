import django_filters
from .models import CustomUser
from django_filters import (
    DateFromToRangeFilter,
    DateFilter,
    CharFilter,
    NumberFilter,
    ModelChoiceFilter,
)
from django.utils.translation import gettext as _
from unidecode import unidecode


class UnaccentCharFilter(CharFilter):
    """
    Custom CharFilter that removes accents before performing the query.
    """

    def filter(self, qs, value):
        if value is not None:
            value = unidecode(value)
        return super().filter(qs, value)


class UsersFilter(django_filters.FilterSet):
    CHOICES = (
        ("ascending", "Ascending"),
        ("descending", "Descending"),
    )
    ordering = django_filters.ChoiceFilter(
        label="Ordering", choices=CHOICES, method="filter_by_order"
    )
    first_name = UnaccentCharFilter(label=_("Prénom"), lookup_expr="icontains")
    last_name = UnaccentCharFilter(label=_("Nom"), lookup_expr="icontains")

    def filter_by_order(self, queryset, name, value):
        expression = "last_name" if value == "ascending" else "-last_name"
        return queryset.order_by(expression)
