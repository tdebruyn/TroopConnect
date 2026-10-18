"""Who a family's message to a leader reaches, and what leaves with it.

A section's communications lead is an animateur carrying the
"Responsable communication" role; their enrolment says which section. When no
one holds that role, the message goes to every animateur of the section, and
when the section has none, to the unit lead and the site administrators. The
fallback chain is resolved here so a parent never has to know the roster.

Targets are always resolved from the reader's own children. Nothing in the
POST body chooses a section, so a crafted request cannot address another
family's leaders.

The emails are composed here rather than from a seeded post-office template:
their subject is the parent's own title, and their body is the parent's own
words. Only the wrapper sentences around it are translated.
"""

from dataclasses import dataclass

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _
from post_office import mail

from .mail import troop_name
from .models import Enrollment, Person, SchoolYear, TroopSettings
from .permissions import (
    ANIMATEUR,
    RESPONSABLE_ANIMATEUR,
    RESPONSABLE_COMMUNICATION,
    TRESORIER,
    get_person,
)


@dataclass(frozen=True)
class ContactRecipient:
    """One address the message goes to, in the language that address reads."""

    email: str
    name: str
    language: str


@dataclass(frozen=True)
class ContactTarget:
    """One choice in the "Send to" field."""

    key: str
    label: str
    recipients: tuple[ContactRecipient, ...]
    section: object | None
    children: tuple[Person, ...]
    #: The section has no communications lead, so this target falls back.
    missing_communication: bool = False


def _person_name(person):
    return f"{person.first_name} {person.last_name}".strip()


def _recipient(person):
    # A Person without a login has no address; Django raises an AttributeError
    # subclass from the reverse accessor, which getattr catches.
    account = getattr(person, "account", None)
    if account is None or not account.email:
        return None
    return ContactRecipient(
        email=account.email,
        name=_person_name(person) or account.email,
        language=account.preferred_language or settings.LANGUAGE_CODE,
    )


def _recipients(people):
    recipients = []
    for person in people:
        recipient = _recipient(person)
        if recipient is not None:
            recipients.append(recipient)
    return tuple(recipients)


def _merge(*groups):
    """Concatenate recipient groups, keeping the first address seen."""
    merged = []
    seen = set()
    for group in groups:
        for recipient in group:
            if recipient.email in seen:
                continue
            seen.add(recipient.email)
            merged.append(recipient)
    return tuple(merged)


def _people_with_role(short, section=None, school_year=None):
    people = Person.objects.filter(roles__short=short)
    if section is not None:
        people = people.filter(
            enrollment__section=section, enrollment__school_year=school_year
        )
    return people.select_related("account").distinct()


def _unit_leads():
    return _recipients(
        _people_with_role(RESPONSABLE_ANIMATEUR).order_by(
            "first_name", "last_name"
        )
    )


def _site_admins():
    people = Person.objects.filter(
        account__is_staff=True, account__is_active=True
    ).select_related("account")
    return _recipients(people.order_by("first_name", "last_name"))


def _treasurers():
    return _recipients(
        _people_with_role(TRESORIER).order_by("first_name", "last_name")
    )


def has_treasurer():
    """Whether the balance tile has someone to offer as a recipient."""
    return bool(_treasurers())


def public_contact_recipients():
    """Who an anonymous visitor's message reaches: the unit lead, else staff.

    The public form never names these people; it says only that the unit's
    animateur responsable will answer. Site staff are the fallback for an
    instance whose unit lead has not been named — the form must still land.
    """
    return _unit_leads() or _site_admins()


def _section_leaders(section, school_year):
    """Every animateur enrolled in the section: its leaders, whoever they are."""
    people = Person.objects.filter(
        primary_role__short=ANIMATEUR,
        enrollment__section=section,
        enrollment__school_year=school_year,
    ).select_related("account")
    return _recipients(people.distinct().order_by("first_name", "last_name"))


def _child_sections(person):
    """The reader's children's sections this year, in display order.

    Returns ``(section, children)`` pairs. A child with no section this year
    contributes nothing: there is no section for the family to write about.
    """
    school_year = SchoolYear.current()
    if school_year is None:
        return []

    enrollments = (
        Enrollment.objects.filter(
            user__as_child__parent=person, school_year=school_year
        )
        .select_related("section__branch", "user")
        .order_by(
            "section__branch__name",
            "section__name",
            "user__first_name",
            "user__last_name",
        )
    )

    grouped = {}
    for enrollment in enrollments:
        grouped.setdefault(enrollment.section, []).append(enrollment.user)
    return list(grouped.items())


def _names(recipients):
    return ", ".join(recipient.name for recipient in recipients)


def contact_targets(user):
    """The contacts the reader may write to, the section's lead first.

    Each section option names the people behind it. A section with no
    communications lead still gets an option: its leaders, or the unit lead and
    the site administrators when even those are missing. The unit option is
    always worth offering, and the troop's public contact address is the last
    resort for an instance that has named nobody.
    """
    person = get_person(user)
    if person is None:
        return []

    school_year = SchoolYear.current()
    unit_leads = _unit_leads()
    site_admins = _site_admins()
    targets = []

    for section, children in _child_sections(person):
        communication_leads = _recipients(
            _people_with_role(
                RESPONSABLE_COMMUNICATION, section, school_year
            ).order_by("first_name", "last_name")
        )
        if communication_leads:
            recipients = communication_leads
            missing_communication = False
            label = _("%(section)s — communications lead: %(names)s") % {
                "section": section.name,
                "names": _names(communication_leads),
            }
        else:
            leaders = _section_leaders(section, school_year)
            if leaders:
                recipients = leaders
                fallback = _("the section's leaders")
            else:
                recipients = _merge(unit_leads, site_admins)
                if unit_leads and site_admins:
                    fallback = _("the unit lead and the site administrator")
                elif unit_leads:
                    fallback = _("the unit lead")
                else:
                    fallback = _("the site administrator")
            if not recipients:
                continue
            missing_communication = True
            label = _(
                "%(section)s — no communications lead yet (goes to %(fallback)s)"
            ) % {"section": section.name, "fallback": fallback}

        targets.append(
            ContactTarget(
                key=f"section:{section.pk}",
                label=label,
                recipients=recipients,
                section=section,
                children=tuple(children),
                missing_communication=missing_communication,
            )
        )

    if unit_leads:
        targets.append(
            ContactTarget(
                key="unit",
                label=_("The unit — unit lead: %(names)s")
                % {"names": _names(unit_leads)},
                recipients=unit_leads,
                section=None,
                children=(),
            )
        )
    elif site_admins:
        targets.append(
            ContactTarget(
                key="unit",
                label=_("The unit — the site administrator"),
                recipients=site_admins,
                section=None,
                children=(),
            )
        )

    # The balance tile links here with this target preselected, so a family
    # asking about money is one step from the person who records it.
    treasurers = _treasurers()
    if treasurers:
        targets.append(
            ContactTarget(
                key="treasurer",
                label=_("The unit — treasurer: %(names)s")
                % {"names": _names(treasurers)},
                recipients=treasurers,
                section=None,
                children=(),
            )
        )

    if not targets:
        contact_email = TroopSettings.get_settings().contact_email
        if contact_email:
            targets.append(
                ContactTarget(
                    key="contact",
                    label=_("The unit — %(email)s") % {"email": contact_email},
                    recipients=(
                        ContactRecipient(
                            email=contact_email,
                            name=contact_email,
                            language=settings.LANGUAGE_CODE,
                        ),
                    ),
                    section=None,
                    children=(),
                )
            )

    return targets


def _send(*, to, subject, body, reply_to):
    mail.send(
        sender=settings.DEFAULT_FROM_EMAIL,
        recipients=[to],
        subject=subject,
        message=body,
        headers={"Reply-To": reply_to} if reply_to else {},
    )


def _leader_message(
    recipient,
    *,
    sender_name,
    sender_email,
    section_name,
    children,
    subject,
    body,
):
    """The parent's message with the context a leader needs to answer it."""
    with translation.override(recipient.language):
        lines = [
            _("Hello,"),
            "",
            _(
                "%(sender)s (%(email)s) sent you a message through the "
                "%(troop)s site."
            )
            % {
                "sender": sender_name,
                "email": sender_email,
                "troop": troop_name(recipient.language),
            },
        ]
        if section_name:
            lines.append(_("Section: %(section)s") % {"section": section_name})
        if children:
            lines.append(_("About: %(children)s") % {"children": children})
        lines += [
            "",
            subject,
            "",
            body,
            "",
            _(
                "Reply directly to this email: your answer will reach "
                "%(email)s."
            )
            % {"email": sender_email},
        ]
        signature = TroopSettings.get_settings().email_signature
        if signature:
            lines += ["", signature]
        return "\n".join(lines)


def _copy_message(language, *, sender_name, recipient_names, subject, body):
    with translation.override(language):
        copy_subject = _("Copy of your message – %(title)s") % {"title": subject}
        lines = [
            _("Hello %(name)s,") % {"name": sender_name},
            "",
            _("Your message was sent to %(recipients)s.")
            % {"recipients": recipient_names},
            "",
            _("Here is a copy:"),
            "",
            subject,
            "",
            body,
            "",
            _("A response will arrive by email at this address."),
        ]
        return copy_subject, "\n".join(lines)


def send_parent_message(*, account, target, subject, body):
    """Send one parent's message and its copy; return how many people it reached.

    The leader's email carries the parent's address as ``Reply-To``, so a reply
    needs no second step. The parent's copy is addressed back to the first
    recipient, so replying to the copy also reaches a person rather than the
    site's own sending address.
    """
    person = get_person(account)
    sender_name = _person_name(person) or account.email
    recipient_names = _names(target.recipients)
    section_name = target.section.name if target.section else ""
    children = ", ".join(_person_name(child) for child in target.children)

    for recipient in target.recipients:
        _send(
            to=recipient.email,
            subject=subject,
            body=_leader_message(
                recipient,
                sender_name=sender_name,
                sender_email=account.email,
                section_name=section_name,
                children=children,
                subject=subject,
                body=body,
            ),
            reply_to=account.email,
        )

    copy_subject, copy_body = _copy_message(
        account.preferred_language,
        sender_name=sender_name,
        recipient_names=recipient_names,
        subject=subject,
        body=body,
    )
    _send(
        to=account.email,
        subject=copy_subject,
        body=copy_body,
        reply_to=target.recipients[0].email if target.recipients else "",
    )

    return len(target.recipients)
