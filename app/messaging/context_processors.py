"""Template-wide role flags, used to decide which nav entries to show.

These booleans gate navigation, so they must agree with the checks the views
themselves enforce — both sides go through `members.permissions`.
"""

from members.permissions import (
    ANIMATEUR_ROLES,
    can_access_finance,
    can_manage_unit,
    has_primary_role,
)


def is_animateur(request):
    if not request.user.is_authenticated:
        return {
            "user_is_animateur": False,
            "user_can_send_all": False,
            "user_is_tresorier": False,
        }

    return {
        "user_is_animateur": has_primary_role(request.user, ANIMATEUR_ROLES),
        "user_can_send_all": can_manage_unit(request.user),
        "user_is_tresorier": can_access_finance(request.user),
    }
