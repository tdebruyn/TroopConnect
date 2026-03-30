import hashlib

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.http import require_POST

from post_office import mail

from members.models import Person, SchoolYear, Enrollment, ParentChild, ImportantDocument, Section, Role
from homepage.models import Event
from .models import SectionMessage, SectionMessageRecipient, MessageAttachment
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

    Staff or users with secondary role 'ar' or 'ad' can send to all.
    Regular animateurs can only send to their section.
    """
    if user.is_staff:
        return True
    if not hasattr(user, "person"):
        return False
    person = user.person
    if person.roles.filter(short__in=["ar", "ad"]).exists():
        return True
    return False


def _is_authorized(user):
    """Check if user can access the messaging system at all."""
    if _can_send_all(user):
        return True
    return _get_animateur_person(user) is not None


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
        result.append({"person": parent, "detail": ", ".join(c.first_name for c in children)})
    return result


def _get_section_animateurs(section, school_year):
    """Return animateurs enrolled in a section for a given school year."""
    animateurs = (
        Person.objects.filter(
            primary_role__short__in=["a", "ar"],
            enrollment__section=section,
            enrollment__school_year=school_year,
        )
        .distinct()
        .order_by("last_name", "first_name")
    )
    return [{"person": p, "detail": ""} for p in animateurs]


def _get_section_animes(section, school_year):
    """Return animés (children) enrolled in a section for a given school year."""
    animes = (
        Person.objects.filter(
            primary_role__short="e",
            enrollment__section=section,
            enrollment__school_year=school_year,
        )
        .distinct()
        .order_by("last_name", "first_name")
    )
    return [{"person": p, "detail": ""} for p in animes]


def _get_section_all(section, school_year):
    """Return parents, animés, and animateurs of a section (deduplicated)."""
    parents = _get_section_parents(section, school_year)
    animes = _get_section_animes(section, school_year)
    animateurs = _get_section_animateurs(section, school_year)

    seen = set()
    result = []
    for entry in parents + animes + animateurs:
        pk = entry["person"].pk
        if pk not in seen:
            seen.add(pk)
            result.append(entry)
    return result


def _get_all_animateurs():
    """Return all persons with primary role Animateur."""
    animateurs = (
        Person.objects.filter(primary_role__short__in=["a", "ar"])
        .order_by("last_name", "first_name")
    )
    return [{"person": p, "detail": ""} for p in animateurs]


def _get_animateurs_plus_staff():
    """Return all animateurs + persons with staff secondary roles."""
    staff_roles = Role.objects.filter(short__in=["ar", "ad", "t", "ri"])
    animateurs = Person.objects.filter(primary_role__short__in=["a", "ar"])
    staff = Person.objects.filter(roles__in=staff_roles)
    persons = (animateurs | staff).distinct().order_by("last_name", "first_name")
    return [{"person": p, "detail": ""} for p in persons]


def _get_staff():
    """Return persons with staff secondary roles (ar, ad, t, ri)."""
    staff_roles = Role.objects.filter(short__in=["ar", "ad", "t", "ri"])
    persons = (
        Person.objects.filter(roles__in=staff_roles)
        .distinct()
        .order_by("last_name", "first_name")
    )
    return [{"person": p, "detail": ""} for p in persons]


def _get_active_parents():
    """Return parents who have the 'Parent actif' secondary role."""
    persons = (
        Person.objects.filter(
            primary_role__short="p",
            roles__short="pa",
        )
        .distinct()
        .order_by("last_name", "first_name")
    )
    return [{"person": p, "detail": ""} for p in persons]


def _get_everyone():
    """Return all persons who have an account with an email."""
    persons = (
        Person.objects.filter(account__isnull=False, account__email__isnull=False)
        .exclude(account__email="")
        .select_related("account")
        .order_by("last_name", "first_name")
    )
    return [{"person": p, "detail": p.account.email} for p in persons]


SECTION_GROUPS = {"section_parents", "section_animateurs", "section_animes", "section_all"}


def _resolve_recipients(group, section, school_year):
    """Resolve recipient group + section into a list of {person, detail} dicts."""
    if group == "section_parents":
        return _get_section_parents(section, school_year)
    elif group == "section_animateurs":
        return _get_section_animateurs(section, school_year)
    elif group == "section_animes":
        return _get_section_animes(section, school_year)
    elif group == "section_all":
        return _get_section_all(section, school_year)
    elif group == "all_animateurs":
        return _get_all_animateurs()
    elif group == "animateurs_staff":
        return _get_animateurs_plus_staff()
    elif group == "staff":
        return _get_staff()
    elif group == "active_parents":
        return _get_active_parents()
    elif group == "everyone":
        return _get_everyone()
    return []


def _get_doc_url(doc):
    """Return the URL for an ImportantDocument (file URL or external URL)."""
    if doc.file:
        return doc.file.url
    return doc.url


def _handle_attachment_and_docs(request, msg):
    """Process file attachment and ImportantDocument checkboxes.

    Modifies msg.body in place (appends document links) and saves the model.
    Returns a list of (filename, file) tuples for email attachment.
    """
    # Handle file upload with content-hash dedup
    uploaded_file = request.FILES.get("attachment")
    attachment_obj = None
    if uploaded_file:
        file_content = uploaded_file.read()
        content_hash = hashlib.sha256(file_content).hexdigest()
        uploaded_file.seek(0)

        existing = MessageAttachment.objects.filter(content_hash=content_hash).first()
        if existing:
            attachment_obj = existing
        else:
            attachment_obj = MessageAttachment.objects.create(
                file=uploaded_file,
                original_name=uploaded_file.name,
                content_hash=content_hash,
            )
        msg.attachments.add(attachment_obj)

    # Handle ImportantDocument checkboxes — append links to body
    selected_docs = []
    for key, value in request.POST.items():
        if key.startswith("doc_"):
            doc_id = key[4:]
            doc = ImportantDocument.objects.filter(pk=doc_id).first()
            if doc:
                selected_docs.append(doc)

    if selected_docs:
        links = [f"- {doc.title}: {_get_doc_url(doc)}" for doc in selected_docs]
        msg.body += "\n\nDocuments importants :\n" + "\n".join(links)

    msg.save()

    # Build email attachments list
    email_attachments = []
    if attachment_obj:
        email_attachments.append((attachment_obj.original_name, attachment_obj.file))

    return email_attachments


@login_required
def compose_message(request):
    """Unified compose message view with recipient group selection."""
    if not _is_authorized(request.user):
        raise Http404

    person = request.user.person
    can_send_all = _can_send_all(request.user)
    is_animateur = _get_animateur_person(request.user) is not None
    current_year = SchoolYear.current()

    # Determine the animateur's section (if applicable)
    animateur_section = None
    if is_animateur and not can_send_all:
        enrollment = Enrollment.objects.filter(
            user=person, school_year=current_year
        ).first()
        if not enrollment:
            messages.error(request, "Vous n'êtes inscrit dans aucune section cette année.")
            return redirect("homepage")
        animateur_section = enrollment.section

    # Handle HTMX request to load recipients
    if request.method == "POST" and request.POST.get("hx_load_recipients"):
        group = request.POST.get("recipient_group")
        section_id = request.POST.get("section")

        section = None
        if section_id:
            section = Section.objects.filter(pk=section_id).first()

        # Animateurs are locked to their own section for section-based groups
        if is_animateur and not can_send_all and group in SECTION_GROUPS:
            section = animateur_section

        recipients = _resolve_recipients(group, section, current_year)

        # Filter out the sender
        recipients = [r for r in recipients if r["person"].pk != person.pk]

        return render(
            request,
            "messaging/_recipient_list.html",
            {"recipients": recipients},
        )

    # Handle form submission (send message)
    if request.method == "POST":
        form = ComposeMessageForm(request.POST, request.FILES)
        if form.is_valid():
            group = form.cleaned_data["recipient_group"]
            section = form.cleaned_data.get("section")

            # Animateurs are locked to their own section
            if is_animateur and not can_send_all and group in SECTION_GROUPS:
                section = animateur_section

            recipients = _resolve_recipients(group, section, current_year)
            recipients = [r for r in recipients if r["person"].pk != person.pk]

            # Determine the section for the message record
            msg_section = section if group in SECTION_GROUPS else None

            msg = SectionMessage.objects.create(
                sender=person,
                section=msg_section,
                school_year=current_year,
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
            )

            # Create agenda event if a date was provided
            event_date = form.cleaned_data.get("event_date")
            if event_date:
                Event.objects.create(
                    title=form.cleaned_data["subject"],
                    description=form.cleaned_data["body"],
                    date=event_date,
                    section=msg_section,
                    created_from_message=msg,
                )

            email_attachments = _handle_attachment_and_docs(request, msg)

            sent_count = 0
            for entry in recipients:
                recipient = entry["person"]
                checkbox_name = f"recipient_{recipient.pk}"
                is_checked = checkbox_name in request.POST

                if is_checked:
                    SectionMessageRecipient.objects.create(
                        message=msg, parent=recipient, sent_at=timezone.now()
                    )
                    if hasattr(recipient, "account"):
                        mail.send(
                            recipients=[recipient.account.email],
                            sender="MS_M3qCdl@tomctl.be",
                            template="section_message",
                            context={
                                "sender_name": str(person),
                                "section_name": msg_section.name if msg_section else "Tous les membres",
                                "subject": msg.subject,
                                "body": msg.body,
                            },
                            attachments=email_attachments or None,
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

    # For animateurs, filter section field to their own section
    if is_animateur and not can_send_all:
        form.fields["section"].queryset = Section.objects.filter(pk=animateur_section.pk)
        form.fields["section"].initial = animateur_section

    return render(
        request,
        "messaging/compose.html",
        {
            "form": form,
            "important_documents": ImportantDocument.objects.all(),
            "can_send_all": can_send_all,
            "is_animateur": is_animateur,
            "animateur_section": animateur_section,
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
def section_history(request, section_id):
    if not hasattr(request.user, "person"):
        raise Http404

    person = request.user.person
    current_year = SchoolYear.current()
    section = get_object_or_404(Section, pk=section_id)

    # Check access: staff sees all, others need a direct or parent enrollment link
    if not request.user.is_staff:
        has_direct = Enrollment.objects.filter(
            user=person, section=section, school_year=current_year
        ).exists()
        has_parent = Enrollment.objects.filter(
            user__as_child__parent=person, section=section, school_year=current_year
        ).exists()
        if not has_direct and not has_parent:
            raise Http404

    section_messages = (
        SectionMessage.objects.filter(
            section=section,
            school_year=current_year,
        )
        .select_related("sender", "school_year")
    )

    return render(
        request,
        "messaging/section_history.html",
        {"section_messages": section_messages, "section": section},
    )
