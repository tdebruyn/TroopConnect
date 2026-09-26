from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from post_office import mail
from pypdf import PdfReader

from members.models import Person
from members.modules import SIGNING, requires_module
from members.permissions import can_manage_unit

from . import services
from .forms import DocumentsForm, NameAnchorForm, SendForm, SignatureForm, TitleForm
from .models import AttestationCampaign, AttestationItem


def _resolve_placeholders(text, person, item):
    first = (
        person.first_name
        if person
        else (item.extracted_name.split(" ", 1)[0] if item.extracted_name else "")
    )
    last = (
        person.last_name
        if person
        else (
            item.extracted_name.split(" ", 1)[1]
            if " " in item.extracted_name
            else ""
        )
    )
    return text.replace("{prenom}", first).replace("{nom}", last)


@login_required
@requires_module(SIGNING)
def index(request):
    if not can_manage_unit(request.user):
        raise Http404

    campaigns = (
        AttestationCampaign.objects.annotate(
            item_count=Count("items"),
            sent_count=Count(
                "items", filter=Q(items__status=AttestationItem.Status.SENT)
            ),
        )
        .order_by("-created_at")
    )
    return render(request, "attestations/index.html", {"campaigns": campaigns})


def _refuse_sent(request, campaign):
    """Redirect away from a sent campaign, or None when it may still be edited.

    Once a campaign has gone out it is the record of what was actually sent, so
    reopening a step would rewrite history rather than fix a mistake.
    """
    if campaign.status != AttestationCampaign.Status.SENT:
        return None
    messages.error(
        request, _("A campaign that has been sent can no longer be changed.")
    )
    return redirect("attestations:review", pk=campaign.pk)


def _anchor_text(campaign, lines):
    """Form initial for step 3: whatever already sits at the stored anchor."""
    if not campaign.name_anchor:
        return {}
    text = services.extract_field(lines, campaign.name_anchor)
    return {"name_value": text} if text else {}


@login_required
@requires_module(SIGNING)
def step1(request, pk=None):
    """Step 1: name the campaign — and rename it later, once one exists."""
    if not can_manage_unit(request.user):
        raise Http404

    campaign = (
        get_object_or_404(AttestationCampaign, pk=pk) if pk is not None else None
    )
    if campaign is not None:
        refused = _refuse_sent(request, campaign)
        if refused:
            return refused

    if request.method == "POST":
        form = TitleForm(request.POST, instance=campaign)
        if form.is_valid():
            creating = campaign is None
            campaign = form.save(commit=False)
            if creating:
                campaign.created_by = getattr(request.user, "person", None)
            # A new campaign moves on to step 2; renaming an existing one
            # changes nothing else, so it returns to wherever it had got to.
            campaign.step = max(campaign.step, 2)
            campaign.save()
            if creating:
                return redirect("attestations:step2", pk=campaign.pk)
            return redirect(campaign.resume_url, pk=campaign.pk)
    else:
        form = TitleForm(instance=campaign)

    return render(
        request,
        "attestations/step1.html",
        {"form": form, "campaign": campaign},
    )


@login_required
@requires_module(SIGNING)
def step2(request, pk):
    """Step 2: upload the source PDF and describe the per-person page range."""
    if not can_manage_unit(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    refused = _refuse_sent(request, campaign)
    if refused:
        return refused

    if request.method == "POST":
        form = DocumentsForm(request.POST, request.FILES, instance=campaign)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.step = 3
            # Re-editing an earlier step invalidates the ones after it.
            campaign.status = AttestationCampaign.Status.DRAFT
            campaign.save()
            return redirect("attestations:step3", pk=campaign.pk)
    else:
        form = DocumentsForm(instance=campaign)

    return render(
        request,
        "attestations/step2.html",
        {"form": form, "campaign": campaign},
    )


@login_required
@requires_module(SIGNING)
def step3(request, pk):
    """Step 3: teach the app where the name lives on the indicated page."""
    if not can_manage_unit(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    refused = _refuse_sent(request, campaign)
    if refused:
        return refused

    lines = services.page_lines(campaign.documents.path, campaign.name_page - 1)

    if request.method == "POST":
        form = NameAnchorForm(request.POST)
        if form.is_valid():
            name_anchor = services.locate_anchor(
                form.cleaned_data["name_value"], lines
            )
            if name_anchor is None:
                form.add_error(
                    "name_value",
                    _("Could not find that name on page %(page)s.")
                    % {"page": campaign.name_page},
                )
            else:
                campaign.name_anchor = name_anchor
                campaign.step = 4
                campaign.status = AttestationCampaign.Status.DRAFT
                campaign.save()
                return redirect("attestations:step4", pk=campaign.pk)
    else:
        # Reopening this step should not mean retyping the name: offer back
        # whatever already sits at the anchor we found last time.
        form = NameAnchorForm(initial=_anchor_text(campaign, lines))

    page_text = "\n".join(line["text"] for line in lines)

    return render(
        request,
        "attestations/step3.html",
        {
            "form": form,
            "campaign": campaign,
            "page_text": page_text,
        },
    )


@login_required
@requires_module(SIGNING)
def step4(request, pk):
    """Step 4: upload the signature, pick its page and preview the merge."""
    if not can_manage_unit(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    refused = _refuse_sent(request, campaign)
    if refused:
        return refused

    if request.method == "POST":
        form = SignatureForm(request.POST, request.FILES, instance=campaign)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.step = 5
            campaign.status = AttestationCampaign.Status.READY
            campaign.save()
            services.process_campaign(campaign)
            return redirect("attestations:review", pk=campaign.pk)
    else:
        form = SignatureForm(instance=campaign)

    return render(
        request,
        "attestations/step4.html",
        {
            "form": form,
            "campaign": campaign,
            "page_range_start": campaign.page_range_start,
            "signature_url": campaign.signature.url if campaign.signature else "",
        },
    )


@login_required
@requires_module(SIGNING)
def review(request, pk):
    """Step 5: review the recipients, then send."""
    if not can_manage_unit(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    return _render_review(request, campaign, SendForm())


# The three ways a document's recipient can have turned out, which the review
# page filters on: everything, the suggestions waiting for a decision, and the
# documents for which no recipient was found at all.
FILTER_ALL = "all"
FILTER_SUGGESTED = "suggested"
FILTER_UNMATCHED = "unmatched"
FILTERS = (FILTER_ALL, FILTER_SUGGESTED, FILTER_UNMATCHED)

# No confirmed recipient yet...
_UNMATCHED = Q(matched_person__isnull=True)
# ...but the name was close enough to propose one, and nobody has decided yet.
_SUGGESTED = _UNMATCHED & Q(suggested_person__isnull=False, suggestion_dismissed=False)
# ...and nothing to propose, or the suggestion was rejected. Both go through the
# same "search the whole database" fallback.
_UNRESOLVED = _UNMATCHED & (Q(suggested_person__isnull=True) | Q(suggestion_dismissed=True))


def _review_filter(request):
    """Which rows the review table shows.

    Read from POST as well as GET so the filter survives a send that comes back
    with an invalid email form.
    """
    value = request.POST.get("filter") or request.GET.get("filter")
    return value if value in FILTERS else FILTER_ALL


def _annotate_suggestions(items):
    """Attach ``suggested_emails`` to the rows of the review table.

    Confirming a suggestion sends to the recipients resolved from that person,
    so showing them up front says whether accepting it is worth anything.
    """
    for item in items:
        item.suggested_emails = (
            services.resolve_recipients(item.suggested_person)
            if item.has_suggestion
            else []
        )
    return items


def _render_review(request, campaign, form):
    filter_name = _review_filter(request)

    items = campaign.items.select_related(
        "matched_person", "suggested_person__primary_role"
    )
    if filter_name == FILTER_SUGGESTED:
        items = items.filter(_SUGGESTED)
    elif filter_name == FILTER_UNMATCHED:
        items = items.filter(_UNRESOLVED)
    _annotate_suggestions(items)

    persons = (
        Person.objects.filter(status="a")
        .select_related("primary_role")
        .order_by("last_name", "first_name")
    )
    return render(
        request,
        "attestations/review.html",
        {
            "campaign": campaign,
            "items": items,
            "persons": persons,
            "form": form,
            "filter_name": filter_name,
            "total_count": campaign.items.count(),
            "suggested_count": campaign.items.filter(_SUGGESTED).count(),
            "unmatched_count": campaign.items.filter(_UNRESOLVED).count(),
        },
    )


def _suggestion_item(request, pk, item_pk):
    """The item a suggestion action applies to, once the caller is authorised."""
    if not can_manage_unit(request.user):
        raise Http404
    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    return get_object_or_404(AttestationItem, pk=item_pk, campaign=campaign)


def _render_row(request, item):
    """Re-render one review row, the HTMX response to a suggestion decision.

    The whole row is swapped rather than a fragment of it: confirming fills in
    the recipient picker and the addresses, and rejecting hides the proposal,
    so every cell the decision touches has to be redrawn.
    """
    item = AttestationItem.objects.select_related(
        "matched_person", "suggested_person__primary_role", "campaign"
    ).get(pk=item.pk)
    _annotate_suggestions([item])
    persons = (
        Person.objects.filter(status="a")
        .select_related("primary_role")
        .order_by("last_name", "first_name")
    )
    return render(
        request,
        "attestations/_review_row.html",
        {"campaign": item.campaign, "item": item, "persons": persons},
    )


@login_required
@requires_module(SIGNING)
@require_POST
def accept_suggestion(request, pk, item_pk):
    """Confirm a probable match: it becomes the document's recipient.

    Nothing is sent here — the item is left ready, and sending re-resolves the
    recipients from the selected person as it does for a match found outright.
    """
    item = _suggestion_item(request, pk, item_pk)
    item.matched_person = item.suggested_person
    item.recipients = services.resolve_recipients(item.matched_person)
    item.status = (
        AttestationItem.Status.READY
        if item.recipients
        else AttestationItem.Status.PENDING
    )
    item.save(update_fields=["matched_person", "recipients", "status"])
    return _render_row(request, item)


@login_required
@requires_module(SIGNING)
@require_POST
def dismiss_suggestion(request, pk, item_pk):
    """Reject a probable match: the row falls back to the plain "not found".

    The suggestion is kept on the item for the record, but no longer offered —
    the operator searches the whole database from the (now empty) picker.
    """
    item = _suggestion_item(request, pk, item_pk)
    item.suggestion_dismissed = True
    item.save(update_fields=["suggestion_dismissed"])
    return _render_row(request, item)


@login_required
@requires_module(SIGNING)
def send(request, pk):
    if not can_manage_unit(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    form = SendForm(request.POST)
    if not form.is_valid():
        return _render_review(request, campaign, form)

    reader = PdfReader(campaign.documents.path)
    signature_path = campaign.signature.path

    sent = 0
    failed = 0
    for item in campaign.items.select_related("matched_person"):
        if f"skip_{item.pk}" in request.POST:
            item.status = AttestationItem.Status.SKIPPED
            item.save()
            continue

        person = item.matched_person
        person_id = request.POST.get(f"person_{item.pk}")
        if person_id and (person is None or str(person.pk) != person_id):
            person = Person.objects.filter(pk=person_id).first()
            item.matched_person = person
            # The operator just paired this spelling with a person by hand;
            # keep the correspondence so the next campaign reads it back.
            services.remember_alias(
                item.extracted_name,
                person,
                created_by=getattr(request.user, "person", None),
            )

        recipients = services.resolve_recipients(person)
        item.recipients = recipients
        if not recipients:
            item.status = AttestationItem.Status.PENDING
            item.save()
            continue

        pages = [reader.pages[i] for i in range(item.page_start, item.page_end + 1)]
        pdf_bytes = services.build_signed_pdf(
            signature_path,
            pages,
            offset_x=campaign.signature_offset_x,
            offset_y=campaign.signature_offset_y,
            signature_page=campaign.signature_page,
        )
        filename = item.filename
        item.generated_pdf.save(filename, ContentFile(pdf_bytes), save=False)

        subject = _resolve_placeholders(
            form.cleaned_data["subject"], person, item
        )
        body = _resolve_placeholders(form.cleaned_data["body"], person, item)

        try:
            mail.send(
                recipients=recipients,
                sender=settings.DEFAULT_FROM_EMAIL,
                subject=subject,
                message=body,
                attachments={filename: BytesIO(pdf_bytes)},
            )
            item.status = AttestationItem.Status.SENT
            sent += 1
        except Exception:
            item.status = AttestationItem.Status.FAILED
            failed += 1
        item.save()

    campaign.status = AttestationCampaign.Status.SENT
    campaign.save()

    messages.success(
        request,
        _("%(sent)s sent, %(failed)s failed.") % {"sent": sent, "failed": failed},
    )
    return redirect("attestations:index")
