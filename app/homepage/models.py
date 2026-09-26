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
