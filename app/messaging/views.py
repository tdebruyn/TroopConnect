from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.utils import timezone
from django.contrib import messages

from post_office import mail

from members.models import Person, SchoolYear, Enrollment, ParentChild
from .models import SectionMessage, SectionMessageRecipient
from .forms import ComposeMessageForm


def _get_animateur_person(user):
    """Return the Person for an animateur user, or None."""
    if not hasattr(user, "person"):
        return None
    person = user.person
    if person.primary_role.short not in ["a", "ar"]:
        return None
    return person


def _can_send_all(user):
    """Check if user can send messages to all members.

    Only staff d'unité (secondary role 'ar' or 'ad') can send to all.
    Regular animateurs can only send to their section.
    """
    if not hasattr(user, "person"):
        return False
    person = user.person
    if person.roles.filter(short__in=["ar", "ad"]).exists():
        return True
    return False


def _get_section_parents(section, school_year):
    """Return parents of children enrolled in a section, with annotated children list."""
    parents = (
        Person.objects.filter(
            as_parent__child__enrollment__section=section,
            as_parent__child__enrollment__school_year=school_year,
        )
        .distinct()
        .order_by("last_name", "first_name")
    )

    result = []
    for parent in parents:
        children = Person.objects.filter(
            as_child__parent=parent,
            enrollment__section=section,
            enrollment__school_year=school_year,
        ).distinct()
        result.append({"parent": parent, "children": list(children)})
    return result


@login_required
def compose_message(request):
    person = _get_animateur_person(request.user)
    if person is None:
        raise Http404

    current_year = SchoolYear.current()
    enrollment = Enrollment.objects.filter(
        user=person, school_year=current_year
    ).first()
    if not enrollment:
        messages.error(request, "Vous n'êtes inscrit dans aucune section cette année.")
        return redirect("homepage")

    section = enrollment.section
    parents_data = _get_section_parents(section, current_year)

    if request.method == "POST":
        form = ComposeMessageForm(request.POST)
        if form.is_valid():
            msg = SectionMessage.objects.create(
                sender=person,
                section=section,
                school_year=current_year,
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
            )

            sent_count = 0
            for entry in parents_data:
                parent = entry["parent"]
                checkbox_name = f"parent_{parent.pk}"
                is_checked = checkbox_name in request.POST

                if is_checked:
                    SectionMessageRecipient.objects.create(
                        message=msg, parent=parent, sent_at=timezone.now()
                    )
                    # Send email if parent has an account
                    if hasattr(parent, "account"):
                        mail.send(
                            recipients=[parent.account.email],
                            sender="MS_M3qCdl@tomctl.be",
                            template="section_message",
                            context={
                                "sender_name": str(person),
                                "section_name": section.name,
                                "subject": msg.subject,
                                "body": msg.body,
                            },
                        )
                    sent_count += 1
                else:
                    SectionMessageRecipient.objects.create(
                        message=msg, parent=parent, sent_at=None
                    )

            messages.success(
                request, f"Message envoyé à {sent_count} parent(s)."
            )
            return redirect("messaging:animateur_history")
    else:
        form = ComposeMessageForm()

    return render(
        request,
        "messaging/compose.html",
        {
            "form": form,
            "section": section,
            "parents_data": parents_data,
        },
    )


@login_required
def compose_all_message(request):
    """Compose a message to all users who have an account/email."""
    if not _can_send_all(request.user):
        raise Http404

    person = request.user.person
    current_year = SchoolYear.current()

    # Get all persons who have an account with an email
    recipients = (
        Person.objects.filter(account__isnull=False, account__email__isnull=False)
        .exclude(account__email="")
        .exclude(pk=person.pk)
        .select_related("account")
        .order_by("last_name", "first_name")
    )

    if request.method == "POST":
        form = ComposeMessageForm(request.POST)
        if form.is_valid():
            msg = SectionMessage.objects.create(
                sender=person,
                section=None,
                school_year=current_year,
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
            )

            sent_count = 0
            for recipient in recipients:
                checkbox_name = f"recipient_{recipient.pk}"
                is_checked = checkbox_name in request.POST

                if is_checked:
                    SectionMessageRecipient.objects.create(
                        message=msg, parent=recipient, sent_at=timezone.now()
                    )
                    mail.send(
                        recipients=[recipient.account.email],
                        sender="MS_M3qCdl@tomctl.be",
                        template="section_message",
                        context={
                            "sender_name": str(person),
                            "section_name": "Tous les membres",
                            "subject": msg.subject,
                            "body": msg.body,
                        },
                    )
                    sent_count += 1
                else:
                    SectionMessageRecipient.objects.create(
                        message=msg, parent=recipient, sent_at=None
                    )

            messages.success(
                request, f"Message envoyé à {sent_count} destinataire(s)."
            )
            return redirect("messaging:animateur_history")
    else:
        form = ComposeMessageForm()

    return render(
        request,
        "messaging/compose_all.html",
        {
            "form": form,
            "recipients": recipients,
        },
    )


@login_required
def animateur_history(request):
    person = _get_animateur_person(request.user)
    if person is None and not _can_send_all(request.user):
        raise Http404

    person = request.user.person

    sent_messages = (
        SectionMessage.objects.filter(sender=person)
        .select_related("section", "school_year")
    )

    messages_data = []
    for msg in sent_messages:
        total = msg.recipients.count()
        sent = msg.recipients.filter(sent_at__isnull=False).count()
        messages_data.append({"message": msg, "total": total, "sent": sent})

    return render(
        request,
        "messaging/animateur_history.html",
        {"messages_data": messages_data},
    )


@login_required
def section_history(request):
    if not hasattr(request.user, "person"):
        raise Http404

    person = request.user.person
    current_year = SchoolYear.current()

    # Get sections the user is connected to (as animateur or as parent of enrolled child)
    person_sections = set(
        Enrollment.objects.filter(user=person, school_year=current_year)
        .values_list("section_id", flat=True)
    )

    # Also include sections where user is a parent of an enrolled child
    parent_sections = set(
        Enrollment.objects.filter(
            user__as_child__parent=person, school_year=current_year
        ).values_list("section_id", flat=True)
    )

    all_section_ids = person_sections | parent_sections

    section_messages = (
        SectionMessage.objects.filter(
            section_id__in=all_section_ids,
            school_year=current_year,
        )
        .select_related("sender", "section", "school_year")
    )

    return render(
        request,
        "messaging/section_history.html",
        {"section_messages": section_messages},
    )
