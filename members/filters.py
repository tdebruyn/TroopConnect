import django_filters
from .models import CustomUser


class UsersFilter(django_filters.FilterSet):
    CHOICES = (
        ("ascending", "Ascending"),
        ("descending", "Descending"),
    )
    ordering = django_filters.ChoiceFilter(
        label="Ordering", choices=CHOICES, method="filter_by_order"
    )

    class Meta:
        model = CustomUser
        fields = {
            "first_name": ["icontains"],
            "last_name": ["icontains"],
        }

    def filter_by_order(self, queryset, name, value):
        expression = "last_name" if value == "ascending" else "-last_name"
        return queryset.order_by(expression)
