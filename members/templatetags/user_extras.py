from django import template
from members.models import CustomGroup

register = template.Library()


@register.filter(name="has_group")
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


@register.simple_tag(takes_context=True)
def user_groups(context):
    user = context["user"]
    return user.groups.all()
