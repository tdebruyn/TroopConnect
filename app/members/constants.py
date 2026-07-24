from django.utils.translation import gettext_lazy as _

# # Role names
# PARENT_ROLE = "p"
# ANIMATOR_ROLE = "a"
# ACTIVE_PARENT_ROLE = "pa"
# RESPONSIBLE_ANIMATOR_ROLE = "ar"
# CHILD_ROLE = "e"

# # Role labels
# ROLE_LABELS = {
#     PARENT_ROLE: _("Parent"),
#     ANIMATOR_ROLE: _("Animateur"),
#     ACTIVE_PARENT_ROLE: _("Parent actif"),
#     RESPONSIBLE_ANIMATOR_ROLE: _("Animateur responsable"),
#     CHILD_ROLE: _("Animé"),
# }

# Role choices for forms
ROLE_CHOICES = [
    ("p", _("Parent")),
    ("a", _("Animator")),
    ("e", _("Participant")),
]


# Form labels
FORM_LABELS = {
    "email": _("Email"),
    "first_name": _("First name"),
    "last_name": _("Last name"),
    "address": _("Address"),
    "phone": _("Phone"),
    "primary_role": _("Adult type"),
    "secondary_role_enabled": _("Enable secondary role"),
    "photo_consent": _(
        "I agree that photos or videos in which my child(ren) appear may be used "
        "by Les Scouts ASBL, of which my unit is part"
    ),
}

# Messages
SUCCESS_MESSAGES = {
    "profile_updated": _("Your profile has been updated successfully."),
}

# Error messages
ERROR_MESSAGES = {
    "no_user_found": _("No user found matching this ID."),
    "no_permission": _("You do not have permission to view this profile."),
    "form_requires_account": _(
        "AdultUserChangeForm can only be used with existing accounts"
    ),
    "missing_person": _("Account instance is missing required Person relationship"),
}
