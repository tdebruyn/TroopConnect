from django import forms
from decimal import Decimal


class PaymentForm(forms.Form):
    """Form for the Trésorier to record a payment."""

    person_id = forms.IntegerField(widget=forms.HiddenInput())
    amount = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01"),
        label="Montant (€)",
    )
    note = forms.CharField(
        max_length=255, required=False,
        label="Note",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class ReminderForm(forms.Form):
    """Form to send bulk reminder emails."""

    subject = forms.CharField(
        max_length=200, label="Objet",
        initial="Rappel de cotisation",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        label="Message",
        help_text="Utilisez {prenom} et {solde} comme variables.",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6}),
        initial="Bonjour {prenom},\n\nVotre solde de cotisation s'élève à {solde}€.\nMerci de procéder au paiement.\n\nCordialement,\nLe trésorier",
    )
