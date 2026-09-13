from django import forms
from django.utils.translation import gettext_lazy as _

from members.models import SchoolYear, Section

RECIPIENT_GROUP_CHOICES = [
    ("section_parents", _("Parents of a section")),
    ("section_animateurs", _("Animators of a section")),
    ("section_animes", _("Participants of a section")),
    ("section_all", _("Everyone of a section (parents, participants and animators)")),
    ("all_animateurs", _("All animators")),
    ("animateurs_staff", _("Unit council")),
    ("staff", _("Unit staff")),
    ("active_parents", _("Active parents")),
    ("everyone", _("Everyone")),
]


def _recent_school_years(limit=5):
    """Return the current school year, the ``limit - 1`` before it, and the next.

    Drives the compose dropdown so a sender can target the members of a section
    as they were enrolled in a past (or upcoming) year, not just the current one.
    """
    current = SchoolYear.current()
    if current is None:
        return SchoolYear.objects.none()

    previous = list(
        SchoolYear.objects.filter(start_date__lt=current.start_date).order_by(
            "-start_date"
        )[: limit - 1]
    )
    years = previous + [current]

    next_year = SchoolYear.next_school_year()
    if next_year is not None:
        years.append(next_year)

    years.sort(key=lambda year: year.start_date)
    return SchoolYear.objects.filter(pk__in=[year.pk for year in years]).order_by(
        "start_date"
    )


class SchoolYearModelChoiceField(forms.ModelChoiceField):
    """School-year dropdown labelled by its ``range`` (e.g. "2025-2026")."""

    def label_from_instance(self, obj):
        return obj.range or str(obj.name)


class ComposeMessageForm(forms.Form):
    recipient_group = forms.ChoiceField(
        choices=RECIPIENT_GROUP_CHOICES,
        label=_("Recipients"),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_recipient_group"}),
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.all(),
        required=False,
        label=_("Section"),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_section"}),
    )
    school_year = SchoolYearModelChoiceField(
        queryset=SchoolYear.objects.none(),
        required=False,
        empty_label=None,
        label=_("School year"),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_school_year"}),
    )
    subject = forms.CharField(
        max_length=200,
        label=_("Message subject"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        label=_("Message content"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 10}),
    )
    attachment = forms.FileField(
        required=False,
        label=_("Attachment (optional)"),
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
    event_date = forms.DateField(
        required=False,
        label=_("Date (agenda)"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text=_("Optional. If provided, an event will be added to the agenda."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        recent_years = _recent_school_years()
        self.fields["school_year"].queryset = recent_years
        current = SchoolYear.current()
        if current is not None:
            self.fields["school_year"].initial = current
