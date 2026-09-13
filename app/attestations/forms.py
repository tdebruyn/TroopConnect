from django import forms
from django.utils.translation import gettext_lazy as _

from .models import AttestationCampaign


class CampaignCreateForm(forms.ModelForm):
    """Upload the source PDF and signature, and choose how documents split."""

    class Meta:
        model = AttestationCampaign
        fields = [
            "title",
            "documents",
            "signature",
            "split_mode",
            "split_marker",
            "signature_page",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "documents": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "signature": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "split_mode": forms.Select(attrs={"class": "form-select"}),
            "split_marker": forms.TextInput(attrs={"class": "form-control"}),
            "signature_page": forms.Select(attrs={"class": "form-select"}),
        }


class ConfigureForm(forms.Form):
    """Teach the app where the name/address live, and position the signature."""

    name_value = forms.CharField(
        label=_("Name as shown on the first page"),
        help_text=_("Type exactly what you see (e.g. \"Dupont Jean\")."),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    address_value = forms.CharField(
        required=False,
        label=_("Address as shown on the first page (optional)"),
        help_text=_("Used to disambiguate people who share a name."),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    signature_offset_x = forms.FloatField(
        required=False,
        initial=0,
        label=_("Signature offset X (points)"),
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.5", "id": "signature_offset_x"}
        ),
    )
    signature_offset_y = forms.FloatField(
        required=False,
        initial=0,
        label=_("Signature offset Y (points)"),
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.5", "id": "signature_offset_y"}
        ),
    )


class SendForm(forms.Form):
    """Subject and cover note for the outgoing attestation emails."""

    subject = forms.CharField(
        label=_("Subject"),
        initial=_("Attestation for {prenom} {nom}"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        label=_("Message"),
        help_text=_("Use {prenom} and {nom} as variables."),
        initial=_(
            "Dear parent,\n\n"
            "Please find attached the attestation for {prenom} {nom}.\n\n"
            "Best regards,\n"
            "The unit staff"
        ),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6}),
    )
