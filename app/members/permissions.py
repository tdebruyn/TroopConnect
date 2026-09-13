"""Canonical role and permission predicates.

The finance, messaging and attestations apps all ask the same questions about
the roles a user holds ("is this person a trésorier?", "may this person act on
behalf of the whole unit?").  Spelling those lookups out per module let the
same predicate drift apart between call sites, so the role short-codes and the
queries that use them live here.

The short-codes themselves are seeded in
`members/migrations/0002_add_static_values.py`.
"""

# Primary roles (Role.is_primary is True).
PARENT = "p"
ANIMATEUR = "a"
ANIME = "e"

# Secondary roles (Role.is_primary is False).
PARENT_ACTIF = "pa"
RESPONSABLE_ANIMATEUR = "ar"
TRESORIER = "t"
RESPONSABLE_INSCRIPTIONS = "ri"
ADMIN = "ad"

#: Roles held by a section's animateurs.
ANIMATEUR_ROLES = (ANIMATEUR, RESPONSABLE_ANIMATEUR)

#: Roles that may act on behalf of the whole unit (messaging, attestations).
UNIT_ADMIN_ROLES = (RESPONSABLE_ANIMATEUR, ADMIN)

#: Roles that count as "staff" on internal overview screens.
STAFF_ROLES = (
    RESPONSABLE_ANIMATEUR,
    ADMIN,
    TRESORIER,
    RESPONSABLE_INSCRIPTIONS,
)


def get_person(user):
    """Return the `Person` behind an authenticated user, or None.

    `Account.person` is a OneToOneField whose accessor raises
    `RelatedObjectDoesNotExist` (an `AttributeError` subclass) when the
    onboarding step never created the related `Person`, so this is safe for
    users that are anonymous or only half-provisioned.
    """
    return getattr(user, "person", None)


def has_any_role(user, shorts):
    """Return True when the user's person holds at least one of `shorts`.

    `shorts` are secondary-role short-codes; `is_staff` is deliberately not
    consulted here so callers stay explicit about whether staff bypasses.
    """
    person = get_person(user)
    if person is None:
        return False
    return person.roles.filter(short__in=shorts).exists()


def has_primary_role(user, shorts):
    """Return True when the user's primary role is one of `shorts`."""
    person = get_person(user)
    if person is None or person.primary_role is None:
        return False
    return person.primary_role.short in shorts


def is_tresorier(user):
    """Return True when the user's person holds the Trésorier role."""
    return has_any_role(user, (TRESORIER,))


def can_access_finance(user):
    """Return True when the user may view and edit the cotisation screens."""
    return user.is_staff or is_tresorier(user)


def can_manage_unit(user):
    """Return True for site staff and unit admins (animateur responsable/admin)."""
    return user.is_staff or has_any_role(user, UNIT_ADMIN_ROLES)


def can_access_messaging(user):
    """Return True for unit admins and for section animateurs."""
    return can_manage_unit(user) or has_primary_role(user, (ANIMATEUR,))


def is_htmx(request):
    """Return True when the request was issued by HTMX."""
    return request.META.get("HTTP_HX_REQUEST") == "true"
