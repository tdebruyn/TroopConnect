from django.db import models
from django.utils.translation import gettext_lazy as _

from members.models import Person


class AttestationCampaign(models.Model):
    """A batch of attestation PDFs to split, sign and email."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        READY = "ready", _("Ready")
        SENT = "sent", _("Sent")

    title = models.CharField(max_length=200)

    # Step 2: the source PDF (all attestations) and how it is laid out.
    documents = models.FileField(upload_to="attestations/", blank=True, null=True)
    name_page = models.PositiveIntegerField(
        default=1,
        help_text=_("Page number (1-based) on which the first name appears."),
    )
    page_range_start = models.PositiveIntegerField(
        default=1,
        help_text=_("First page (1-based) of one person's document."),
    )
    page_range_end = models.PositiveIntegerField(
        default=1,
        help_text=_("Last page (1-based) of one person's document."),
    )

    # Step 3: bounding box [x0, y0, x1, y1] where the name sits.
    name_anchor = models.JSONField(null=True, blank=True)
    address_anchor = models.JSONField(null=True, blank=True)

    # Step 4: the signature PDF and where to stamp it.
    signature = models.FileField(upload_to="attestations/", blank=True, null=True)
    signature_page = models.PositiveIntegerField(
        default=1,
        help_text=_("Page (1-based, within each person's document) to sign."),
    )
    signature_offset_x = models.FloatField(default=0)
    signature_offset_y = models.FloatField(default=0)

    # Wizard position (1..5) so a half-finished campaign can be resumed.
    step = models.PositiveIntegerField(default=1)

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

    @property
    def pages_per_item(self):
        """Number of pages that make up a single person's document."""
        return max(1, self.page_range_end - self.page_range_start + 1)

    @property
    def resume_url(self):
        """URL name of the next wizard step to resume at."""
        mapping = {
            2: "attestations:step2",
            3: "attestations:step3",
            4: "attestations:step4",
        }
        return mapping.get(self.step, "attestations:review")


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
