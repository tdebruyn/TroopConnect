from django import forms
from django.utils.translation import gettext_lazy as _

from members.models import Section

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
