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
from .forms import CampaignCreateForm, ConfigureForm, SendForm
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
    if not _can_manage(request.user):
        raise Http404

    if request.method == "POST":
        form = CampaignCreateForm(request.POST, request.FILES)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.created_by = getattr(request.user, "person", None)
            campaign.save()
            return redirect("attestations:configure", pk=campaign.pk)
    else:
        form = CampaignCreateForm()

    return render(request, "attestations/create.html", {"form": form})


@login_required
def configure(request, pk):
    if not _can_manage(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)

    if request.method == "POST":
        form = ConfigureForm(request.POST)
        if form.is_valid():
            lines = services.page_lines(campaign.documents.path, 0)
            name_anchor = services.locate_anchor(form.cleaned_data["name_value"], lines)
            if name_anchor is None:
                form.add_error(
                    "name_value", _("Could not find that value on the first page.")
                )
            address_anchor = None
            address_value = form.cleaned_data["address_value"]
            if name_anchor is not None and address_value:
                address_anchor = services.locate_anchor(address_value, lines)
                if address_anchor is None:
                    form.add_error(
                        "address_value",
                        _("Could not find that value on the first page."),
                    )

            if form.is_valid() and name_anchor is not None:
                campaign.name_anchor = name_anchor
                campaign.address_anchor = address_anchor
                campaign.signature_offset_x = (
                    form.cleaned_data["signature_offset_x"] or 0
                )
                campaign.signature_offset_y = (
                    form.cleaned_data["signature_offset_y"] or 0
                )
                campaign.status = AttestationCampaign.Status.READY
                campaign.save()
                services.process_campaign(campaign)
                return redirect("attestations:review", pk=campaign.pk)
    else:
        form = ConfigureForm()

    lines = services.page_lines(campaign.documents.path, 0)
    page_one_text = "\n".join(line["text"] for line in lines)

    return render(
        request,
        "attestations/configure.html",
        {
            "form": form,
            "campaign": campaign,
            "page_one_text": page_one_text,
        },
    )


@login_required
def review(request, pk):
    if not _can_manage(request.user):
        raise Http404

    campaign = get_object_or_404(AttestationCampaign, pk=pk)
    return _render_review(request, campaign, SendForm())


def _render_review(request, campaign, form):
    items = campaign.items.select_related("matched_person")
    persons = Person.objects.filter(status="a").order_by("last_name", "first_name")
    return render(
        request,
        "attestations/review.html",
        {
            "campaign": campaign,
            "items": items,
            "persons": persons,
            "form": form,
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
