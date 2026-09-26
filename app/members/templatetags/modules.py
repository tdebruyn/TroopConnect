"""Ask the troop's module switches from a template.

    {% load modules %}
    {% module_enabled "fees" as fees_on %}
    {% if fees_on %}<a href="{% url 'finance:billing' %}">…</a>{% endif %}

Wraps `members.modules.module_enabled`, so a template and the decorator that
gates the same feature cannot disagree about whether it is on.
"""

from django import template

from members import modules

register = template.Library()


@register.simple_tag
def module_enabled(name):
    """True when the named module is switched on for this troop."""
    return modules.module_enabled(name)
