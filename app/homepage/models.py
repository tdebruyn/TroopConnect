from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta


class Event(models.Model):
    title = models.CharField(max_length=200, verbose_name=_("Title"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    date = models.DateField(verbose_name=_("Date"))
    section = models.ForeignKey(
        "members.Section",
        on_delete=models.CASCADE,
        related_name="events",
        null=True,
        blank=True,
        verbose_name=_("Section"),
    )
    created_from_message = models.ForeignKey(
        "messaging.SectionMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_event",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "title"]

    def __str__(self):
        return f"{self.title} ({self.date:%d/%m/%Y})"

    @property
    def is_past(self):
        return self.date < timezone.now().date()

    @property
    def is_recent_past(self):
        today = timezone.now().date()
        return self.date < today and self.date >= today - timedelta(days=30)

    @property
    def css_class(self):
        if self.is_recent_past:
            return "text-muted"
        return ""
