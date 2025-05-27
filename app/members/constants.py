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
    ("p", "Parent"),
    ("a", "Animateur"),
    ("e", "Animé"),
]


# Form labels
FORM_LABELS = {
    "email": _("E-mail"),
    "first_name": _("Prénom"),
    "last_name": _("Nom"),
    "address": _("Adresse"),
    "phone": _("Téléphone"),
    "primary_role": _("Type d'adulte"),
    "secondary_role_enabled": _("Activer le rôle secondaire"),
    "photo_consent": _(
        "J'accepte que les photos ou vidéos sur lesquelles mon (mes) enfant(s) figure(nt) soient utilisées "
        "par Les Scouts ASBL, dont l'unité de Limal fait partie"
    ),
}

# Messages
SUCCESS_MESSAGES = {
    "profile_updated": _("Votre profil a été mis à jour avec succès."),
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
