from django.db import models
from django.utils.translation import gettext_lazy as _

from members.models import Person


class AttestationCampaign(models.Model):
    """A batch of attestation PDFs to split, sign and email."""

    class SplitMode(models.TextChoices):
        ONE_PAGE = "one_page", _("One page per document")
        MARKER = "marker", _("New document on a marker page")

    class SignaturePage(models.TextChoices):
        FIRST = "first", _("First page only")
        ALL = "all", _("Every page")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        CONFIGURING = "configuring", _("Configuring")
        READY = "ready", _("Ready")
        SENT = "sent", _("Sent")

    title = models.CharField(max_length=200)
    documents = models.FileField(upload_to="attestations/")
    signature = models.FileField(upload_to="attestations/")

    split_mode = models.CharField(
        max_length=10, choices=SplitMode.choices, default=SplitMode.ONE_PAGE
    )
    split_marker = models.CharField(
        max_length=200,
        blank=True,
        help_text=_(
            "With marker mode, a new document starts on a page whose text begins "
            "with this marker (e.g. \"Aux parents de\")."
        ),
    )

    # Bounding box [x0, y0, x1, y1] in PDF points where the name/address sit.
    name_anchor = models.JSONField(null=True, blank=True)
    address_anchor = models.JSONField(null=True, blank=True)

    # PDF-point translation applied to the signature before it is overlaid.
    signature_offset_x = models.FloatField(default=0)
    signature_offset_y = models.FloatField(default=0)
    signature_page = models.CharField(
        max_length=5, choices=SignaturePage.choices, default=SignaturePage.FIRST
    )

    created_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attestation_campaigns",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.DRAFT
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Attestation campaign")
        verbose_name_plural = _("Attestation campaigns")

    def __str__(self):
        return self.title


class AttestationItem(models.Model):
    """A single document (one recipient) split from a campaign's PDF."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        READY = "ready", _("Ready")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")
        SKIPPED = "skipped", _("Skipped")

    campaign = models.ForeignKey(
        AttestationCampaign, on_delete=models.CASCADE, related_name="items"
    )
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()

    extracted_name = models.CharField(max_length=300, blank=True)
    extracted_address = models.CharField(max_length=300, blank=True)
    matched_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attestation_items",
    )
    recipients = models.JSONField(default=list)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    generated_pdf = models.FileField(upload_to="attestations/generated/", blank=True)

    class Meta:
        ordering = ["page_start"]
        verbose_name = _("Attestation item")
        verbose_name_plural = _("Attestation items")

    def __str__(self):
        return f"{self.campaign} — pp. {self.page_start + 1}–{self.page_end + 1}"

    @property
    def filename(self):
        """A safe, human-readable filename for the generated PDF."""
        base = self.extracted_name or f"attestation-{self.pk}"
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in base)
        return f"{safe}.pdf"
