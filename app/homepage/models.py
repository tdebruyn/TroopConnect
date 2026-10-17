from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}


def validate_image_extension(value):
    # SVG is allowed for logos but can embed scripts; uploads are
    # superuser-only, same trust level as the Django admin.
    extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
    if extension not in IMAGE_EXTENSIONS:
        raise ValidationError(
            _("Unsupported image extension. Allowed: %(extensions)s."),
            code="invalid",
            params={"extensions": ", ".join(sorted(IMAGE_EXTENSIONS))},
        )


class SiteContent(models.Model):
    """Superuser-edited page content (GrapesJS output) for one editable page.

    One row per page slug. `project_json` is the editing source of truth;
    `html`/`css` are the render outputs GrapesJS produced at save time.
    Translated fields (fr/nl/en) fall back to French when unset (NULL).
    """

    class Page(models.TextChoices):
        HOME = "home", _("Home")
        FAQ = "faq", _("FAQ")

    page = models.CharField(max_length=20, choices=Page.choices, unique=True)
    project_json = models.TextField(null=True, blank=True)
    html = models.TextField(null=True, blank=True)
    css = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Site content")
        verbose_name_plural = _("Site contents")

    def __str__(self):
        return self.get_page_display()

    @classmethod
    def get_content(cls, page):
        """Return the row for `page`, or None when the page was never edited."""
        return cls.objects.filter(page=page).first()


class TimelineActivity(models.Model):
    """One rendezvous on the public page's year-line.

    The date *is* the position: the site lays the activity on the September
    to July axis by the day it falls on, and an activity with an end date is
    drawn as a short bar rather than a dot. The homepage draws the current
    school year's activities and no others, so a troop can enter next year's
    dates without them appearing early.

    The window is fixed at September 1 to July 31 by the band's axis. A date
    outside it is rejected here rather than silently omitted from the line.
    """

    name = models.CharField(
        max_length=40,
        help_text=_(
            "Keep it short: the year-line has room for a short label and "
            "does not truncate it."
        ),
    )
    start_date = models.DateField(
        help_text=_("The day the activity starts; that day's position draws the dot.")
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text=_(
            "The last day, for an activity spanning several days. Leave empty "
            "for a single-day activity."
        ),
    )

    class Meta:
        ordering = ("start_date", "id")
        verbose_name = _("Timeline activity")
        verbose_name_plural = _("Timeline activities")

    def __str__(self):
        return f"{self.name} — {self.start_date}"

    def clean(self):
        super().clean()
        from homepage.timeline import axis_for

        if not self.start_date:
            return
        axis_start, axis_end = axis_for(self.start_date)
        if not axis_start <= self.start_date < axis_end:
            raise ValidationError(
                {
                    "start_date": _(
                        "The year-line runs from 1 September to 31 July. "
                        "Enter a date inside that window."
                    )
                }
            )
        if self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError(
                    {"end_date": _("The end date cannot be before the start date.")}
                )
            if self.end_date >= axis_end:
                raise ValidationError(
                    {
                        "end_date": _(
                            "The activity must end by 31 July to fit the year-line."
                        )
                    }
                )


class ImageAsset(models.Model):
    """Image uploaded through the homepage editor's asset manager."""

    file = models.FileField(
        upload_to="homepage_images/%Y/",
        validators=[validate_image_extension],
    )
    original_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Image asset")
        verbose_name_plural = _("Image assets")
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name
