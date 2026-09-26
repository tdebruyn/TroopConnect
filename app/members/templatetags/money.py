"""Template filter for amounts, in the troop's own currency."""

from django import template

from members.money import format_money

register = template.Library()


@register.filter
def money(value):
    """Render an amount in the troop's currency, e.g. ``12.50€``.

    ``None`` renders as the empty string, so a table cell can pass a missing
    amount straight through.
    """
    return format_money(value)
