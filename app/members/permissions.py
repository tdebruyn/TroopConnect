"""Canonical role and permission predicates.

The finance, messaging and attestations apps all ask the same questions about
the roles a user holds ("is this person a trésorier?", "may this person act on
behalf of the whole unit?").  Spelling those lookups out per module let the
same predicate drift apart between call sites, so the role short-codes and the
queries that use them live here.

The short-codes themselves are seeded in
`members/migrations/0002_add_static_values.py`.
"""

from django.db.models import Q

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


def can_delete_member(user):
    """Return True when the user may archive or purge a member's record.

    Deliberately narrower than `can_manage_unit()`: purging a member destroys
    their account, enrolments and payment history for good, so it is reserved
    for Django superusers and holders of the ADMIN secondary role.
    """
    return user.is_superuser or has_any_role(user, (ADMIN,))


def can_access_messaging(user):
    """Return True for unit admins and for section animateurs."""
    return can_manage_unit(user) or has_primary_role(user, (ANIMATEUR,))


def visible_sections(user):
    """The sections whose agenda ``user`` may read, in display order.

    Everyone sees the sections they are personally connected to this school
    year: the ones they are enrolled in (a child, an animateur) and the ones
    their children are enrolled in (a parent). Unit admins see every section,
    because "what is the Meute doing in October?" is a question the people
    running the unit have to be able to answer — reading is all that buys them,
    though; writing is :func:`can_edit_section_agenda`.

    ``nav_sections`` in ``context_processors.py`` deliberately keeps its own
    narrower staff-only rule rather than calling this: its dropdown links into
    ``messaging:section_history``, which 404s for an animateur responsable who
    is not on staff.
    """
    # Imported here, not at module level: this module is imported by settings
    # checks and by the context processors, and staying model-free at import
    # time is what keeps that free of cycles.
    from .models import Enrollment, SchoolYear, Section

    if can_manage_unit(user):
        return (
            Section.objects.select_related("branch").order_by("branch__name", "name")
        )

    person = get_person(user)
    if person is None:
        return Section.objects.none()

    current_year = SchoolYear.current()
    if current_year is None:
        return Section.objects.none()

    # Both sides of the link in one pass: `user` covers the person's own
    # enrolments, `user__as_child__parent` the sections of their children.
    enrolled = Enrollment.objects.filter(school_year=current_year).filter(
        Q(user=person) | Q(user__as_child__parent=person)
    )
    return (
        Section.objects.filter(pk__in=enrolled.values_list("section_id", flat=True))
        .select_related("branch")
        .order_by("branch__name", "name")
    )


def can_edit_section_agenda(user, section):
    """True when ``user`` is one of ``section``'s leaders.

    A leader both holds an animateur role *and* is enrolled in the section for
    the current school year: the role says they are a leader, the enrolment
    says which section they lead. Read-only for everyone else — including unit
    admins, who may read every agenda but not write to one.
    """
    from .models import Enrollment, SchoolYear

    if section is None or not has_primary_role(user, ANIMATEUR_ROLES):
        return False
    person = get_person(user)
    if person is None:
        return False
    current_year = SchoolYear.current()
    if current_year is None:
        return False
    return Enrollment.objects.filter(
        user=person, section=section, school_year=current_year
    ).exists()


def reportable_children(user, section):
    """The children ``user`` may report an absence for, in ``section``.

    A parent's own children, and only the ones enrolled in that section this
    school year: a parent of a Baladin and a Louveteau sees each child on that
    child's own agenda and nowhere else. Empty for anyone who is not a parent —
    a leader reads every absence their section's activities carry, but does not
    report one on a family's behalf.
    """
    from .models import Person, SchoolYear

    person = get_person(user)
    if person is None or section is None:
        return Person.objects.none()

    current_year = SchoolYear.current()
    if current_year is None:
        return Person.objects.none()

    return (
        person.children.filter(
            enrollment__section=section, enrollment__school_year=current_year
        )
        .distinct()
        .order_by("last_name", "first_name")
    )


def can_report_absence(user, event, child):
    """True when ``user`` may report ``child`` absent from ``event``.

    Three things have to hold: the user is one of the child's parents, the
    child is enrolled in the activity's section this school year, and the
    activity has not happened yet. The last is what makes an absence a *notice*
    — telling the section about a meeting that is already over is what the
    register is for, not this.
    """
    if event is None or child is None or event.is_past:
        return False
    return reportable_children(user, event.section).filter(pk=child.pk).exists()


def is_htmx(request):
    """Return True when the request was issued by HTMX."""
    return request.META.get("HTTP_HX_REQUEST") == "true"
