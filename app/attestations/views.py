from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from post_office import mail
from pypdf import PdfReader

from members.models import Person

from . import services
from .forms import DocumentsForm, NameAnchorForm, SendForm, SignatureForm, TitleForm
from .models import AttestationCampaign, AttestationItem


def _can_manage(user):
    """Site admin or a person holding the 'ar'/'ad' secondary role."""
    if user.is_staff:
        return True
    if not hasattr(user, "person"):
        return False
    return user.person.roles.filter(short__in=["ar", "ad"]).exists()


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
def index(request):
    if not _can_manage(request.user):
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


@login_required
def create(request):
    """Step 1: name the campaign."""
    if not _can_manage(request.user):
        raise Http404

    if request.method == "POST":
        form = TitleForm(request.POST)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.created_by = getattr(request.user, "person", None)
            campaign.step = 2
            campaign.save()
            return redirect("attestations:step2", pk=campaign.pk)
    else:
        form = TitleForm()

    return render(request, "attestations/step1.html", {"form": form})


@login_required
def step2(request, pk):
    """Step 2: upload the source PDF and describe the per-person page range."""
    if not _can_manage(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)

    if request.method == "POST":
        form = DocumentsForm(request.POST, request.FILES, instance=campaign)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.step = 3
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
def step3(request, pk):
    """Step 3: teach the app where the name lives on the indicated page."""
    if not _can_manage(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)

    if request.method == "POST":
        form = NameAnchorForm(request.POST)
        if form.is_valid():
            lines = services.page_lines(
                campaign.documents.path, campaign.name_page - 1
            )
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
                campaign.save()
                return redirect("attestations:step4", pk=campaign.pk)
    else:
        form = NameAnchorForm()

    lines = services.page_lines(campaign.documents.path, campaign.name_page - 1)
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
def step4(request, pk):
    """Step 4: upload the signature, pick its page and preview the merge."""
    if not _can_manage(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)

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
def review(request, pk):
    """Step 5: review the recipients, then send."""
    if not _can_manage(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    return _render_review(request, campaign, SendForm())


def _unmatched_only(request):
    """Whether the 'recipient not found' filter is on.

    Read from POST as well as GET so the filter survives a send that comes back
    with an invalid email form.
    """
    value = request.POST.get("unmatched_only")
    if value is None:
        value = request.GET.get("unmatched_only")
    return value in ("1", "on", "true")


def _render_review(request, campaign, form):
    unmatched_only = _unmatched_only(request)

    items = campaign.items.select_related("matched_person")
    unmatched_items = campaign.items.filter(matched_person__isnull=True)
    if unmatched_only:
        items = unmatched_items

    persons = Person.objects.filter(status="a").order_by("last_name", "first_name")
    return render(
        request,
        "attestations/review.html",
        {
            "campaign": campaign,
            "items": items,
            "persons": persons,
            "form": form,
            "unmatched_only": unmatched_only,
            "total_count": campaign.items.count(),
            "unmatched_count": unmatched_items.count(),
        },
    )


@login_required
def send(request, pk):
    if not _can_manage(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    form = SendForm(request.POST)
    if not form.is_valid():
        return _render_review(request, campaign, form)

    reader = PdfReader(campaign.documents.path)
    signature_path = campaign.signature.path

    sent = 0
    failed = 0
    for item in campaign.items.all():
        if f"skip_{item.pk}" in request.POST:
            item.status = AttestationItem.Status.SKIPPED
            item.save()
            continue

        person = item.matched_person
        person_id = request.POST.get(f"person_{item.pk}")
        if person_id and (person is None or str(person.pk) != person_id):
            person = Person.objects.filter(pk=person_id).first()
            item.matched_person = person

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
