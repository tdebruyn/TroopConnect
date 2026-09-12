from django import forms
from django.utils.translation import gettext_lazy as _
from pypdf import PdfReader

from .models import AttestationCampaign


class TitleForm(forms.ModelForm):
    """Step 1: give the campaign a name."""

    class Meta:
        model = AttestationCampaign
        fields = ["title"]
        widgets = {"title": forms.TextInput(attrs={"class": "form-control"})}


class DocumentsForm(forms.ModelForm):
    """Step 2: upload the source PDF and describe its layout."""

    class Meta:
        model = AttestationCampaign
        fields = [
            "documents",
            "name_page",
            "page_range_start",
            "page_range_end",
        ]
        widgets = {
            "documents": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "name_page": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "page_range_start": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
            "page_range_end": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        documents = cleaned.get("documents")
        name_page = cleaned.get("name_page")
        start = cleaned.get("page_range_start")
        end = cleaned.get("page_range_end")

        if start and end and start > end:
            self.add_error(
                "page_range_end",
                _("The last page must be greater than or equal to the first page."),
            )

        if documents:
            documents.seek(0)
            try:
                page_count = len(PdfReader(documents).pages)
            except Exception:
                page_count = 0
            if page_count:
                for field, value in (
                    ("name_page", name_page),
                    ("page_range_start", start),
                    ("page_range_end", end),
                ):
                    if value and value > page_count:
                        self.add_error(
                            field,
                            _("Page %(page)s is beyond the %(count)s pages of this document.")
                            % {"page": value, "count": page_count},
                        )
        return cleaned


class NameAnchorForm(forms.Form):
    """Step 3: teach the app where the name lives on the indicated page."""

    name_value = forms.CharField(
        label=_("Name as shown on that page"),
        help_text=_("Type exactly what you see (e.g. \"Dupont Jean\")."),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class SignatureForm(forms.ModelForm):
    """Step 4: upload the signature and choose where it is stamped."""

    class Meta:
        model = AttestationCampaign
        fields = [
            "signature",
            "signature_page",
            "signature_offset_x",
            "signature_offset_y",
        ]
        widgets = {
            "signature": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "signature_page": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
            "signature_offset_x": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "id": "signature_offset_x",
                }
            ),
            "signature_offset_y": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "id": "signature_offset_y",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        signature_page = cleaned.get("signature_page")
        pages = self.instance.pages_per_item
        if signature_page and signature_page > pages:
            self.add_error(
                "signature_page",
                _("Each document has %(pages)s pages; pick a page between 1 and that.")
                % {"pages": pages},
            )
        return cleaned


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
