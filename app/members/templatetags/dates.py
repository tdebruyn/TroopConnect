from django import template
from django.utils import translation
from django.utils.formats import date_format

register = template.Library()


@register.filter
def french_date(value):
    """A date with the French ordinal for the first of the month.

    "1 avril" is not French; "1er avril" is, and the product already writes
    "1er août" and "1er septembre" wherever a scout-year boundary is named.
    Other days take no ordinal, and the other interface languages never add
    one, so this is a French-only rewrite of an otherwise ordinary format.
    """
    if not value:
        return ""
    label = date_format(value, "j F Y")
    if value.day == 1 and (translation.get_language() or "").startswith("fr"):
        label = label.replace("1 ", "1er ", 1)
    return label
