from django.utils.translation import gettext_lazy as _

# What the site header and the emails show when a troop has uploaded no logo of
# its own. A path into the static files, next to the theme rather than inside
# it: the vendored Les Scouts theme deliberately carries no unit's mark.
#
# Lives here and not on ``TroopSettings`` so that the migration which copies it
# into the troop's own uploads can import it — a historical model from
# ``apps.get_model`` carries its fields and nothing else, so a class attribute
# there would be invisible to it.
DEFAULT_LOGO = "images/troop/mini-logo-moutons.png"

# Where :meth:`members.models.TroopSettings.get_settings` caches the singleton
# row. Lives here for the same reason as DEFAULT_LOGO: a data migration that
# writes that row has to drop the cached copy — the cache has no expiry, so a
# deployment that upgraded would keep serving the row it cached before the
# migration, and the change would look like it never happened — and a
# migration cannot read a class attribute off ``apps.get_model``, which returns
# the fields and nothing else.
TROOP_SETTINGS_CACHE_KEY = "members.TroopSettings"

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
