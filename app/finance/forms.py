from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _


class PaymentForm(forms.Form):
    """Form for the Trésorier to record a payment."""

    person_id = forms.CharField(widget=forms.HiddenInput())
    amount = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01"),
        label=_("Amount (€)"),
    )
    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    note = forms.CharField(
        max_length=255, required=False,
        label=_("Note"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class ReminderForm(forms.Form):
    """Form to send bulk reminder emails."""

    subject = forms.CharField(
        max_length=200, label=_("Subject"),
        initial=_("Membership fee reminder"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        label=_("Message"),
        help_text=_("Use {prenom} and {solde} as variables."),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6}),
        initial=_(
            "Hello {prenom},\n\n"
            "Your membership fee balance is {solde}€.\n"
            "Please proceed with the payment.\n\n"
            "Best regards,\n"
            "The treasurer"
        ),
    )
