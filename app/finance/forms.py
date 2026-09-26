from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from members.models import Person, SchoolYear
from members.money import currency_symbol

from .models import FeeRule, Household, HouseholdAdjustment


class PriceGridForm(forms.Form):
    """Editable price grid: children (branch × rank) + animators (rank).

    Each cell maps to a FeeRule row. A blank cell deletes the row on save.
    """

    RANKS = [1, 2, 3]

    def __init__(self, *args, school_year, branches, **kwargs):
        super().__init__(*args, **kwargs)
        self.school_year = school_year
        self.branches = branches

        existing = {
            (rule.branch_id, rule.rank, rule.member_type): rule.amount
            for rule in FeeRule.objects.filter(school_year=school_year)
        }

        for rank in self.RANKS:
            self._field(f"child_all_{rank}", existing.get((None, rank, "child")))
        for branch in branches:
            for rank in self.RANKS:
                self._field(
                    f"child_{branch.pk}_{rank}",
                    existing.get((branch.pk, rank, "child")),
                )
        for rank in self.RANKS:
            self._field(f"animator_{rank}", existing.get((None, rank, "animator")))

    def _field(self, name, initial):
        self.fields[name] = forms.DecimalField(
            max_digits=8,
            decimal_places=2,
            required=False,
            min_value=Decimal("0.00"),
            initial=initial,
            widget=forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}
            ),
        )

    def iter_child_rows(self):
        """Yield {branch, cells} rows — generic row first, then each branch."""
        yield {"branch": None, "cells": [self[f"child_all_{r}"] for r in self.RANKS]}
        for branch in self.branches:
            yield {
                "branch": branch,
                "cells": [self[f"child_{branch.pk}_{r}"] for r in self.RANKS],
            }

    def animator_cells(self):
        return [self[f"animator_{r}"] for r in self.RANKS]

    def save(self):
        for branch_id, prefix in [(None, "child_all")] + [
            (b.pk, f"child_{b.pk}") for b in self.branches
        ]:
            for rank in self.RANKS:
                self._save_rule(
                    branch_id, rank, "child", self.cleaned_data.get(f"{prefix}_{rank}")
                )
        for rank in self.RANKS:
            self._save_rule(
                None, rank, "animator", self.cleaned_data.get(f"animator_{rank}")
            )

    def _save_rule(self, branch_id, rank, member_type, amount):
        if amount is None:
            FeeRule.objects.filter(
                school_year=self.school_year,
                branch_id=branch_id,
                rank=rank,
                member_type=member_type,
            ).delete()
            return
        FeeRule.objects.update_or_create(
            school_year=self.school_year,
            branch_id=branch_id,
            rank=rank,
            member_type=member_type,
            defaults={"amount": amount},
        )


class PaymentForm(forms.Form):
    """Form for the Trésorier to record a payment."""

    person_id = forms.CharField(widget=forms.HiddenInput())
    amount = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01"),
        label=_("Amount"),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The currency is troop content rather than a formatting setting, so
        # the label is filled in per request instead of at import.
        self.fields["amount"].label = _("Amount (%(currency)s)") % {
            "currency": currency_symbol()
        }


class HouseholdForm(forms.ModelForm):
    """Create a household, or rename one."""

    class Meta:
        model = Household
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}


class HouseholdAssignmentForm(forms.Form):
    """Put a member in a household, or hand them back to address inference.

    Used from the member page and from the household page, so it posts ids
    rather than objects: the person is looked up by the view (the same shape
    `PaymentForm` uses for the same reason — a hidden `ModelChoiceField` would
    render every member in the troop into the page).
    """

    person_id = forms.CharField(widget=forms.HiddenInput())
    household = forms.ModelChoiceField(
        queryset=Household.objects.order_by("name"),
        required=False,
        label=_("Household"),
        empty_label=_("Inferred from address"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class HouseholdMemberForm(forms.Form):
    """Pick a member to add to a household — the merge half of merge/split."""

    person = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        label=_("Member"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, household, **kwargs):
        super().__init__(*args, **kwargs)
        self.household = household
        self.fields["person"].queryset = (
            Person.objects.filter(status="a")
            .exclude(household_memberships__household=household)
            .select_related("primary_role")
            .order_by("last_name", "first_name")
        )


class HouseholdAdjustmentForm(forms.ModelForm):
    """Add a manual adjustment line to a household."""

    class Meta:
        model = HouseholdAdjustment
        fields = ["school_year", "amount", "reason"]
        widgets = {
            "school_year": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, household, **kwargs):
        super().__init__(*args, **kwargs)
        self.household = household
        self.fields["school_year"].queryset = SchoolYear.objects.order_by(
            "-start_date"
        )
        self.fields["school_year"].initial = SchoolYear.current()
        # Signed on purpose: a write-off is a negative line, so the field must
        # not carry the `min_value=0` the price grid uses.
        self.fields["amount"].help_text = _(
            "Negative writes off, positive adds to what the household owes"
        )

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount == 0:
            raise forms.ValidationError(_("An adjustment of zero changes nothing."))
        return amount

    def save(self, commit=True):
        adjustment = super().save(commit=False)
        adjustment.household = self.household
        if commit:
            adjustment.save()
        return adjustment


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
        # No currency sign here: `{solde}` is replaced with the amount already
        # written in the troop's currency (see finance.views.send_reminders).
        initial=_(
            "Hello {prenom},\n\n"
            "Your membership fee balance is {solde}.\n"
            "Please proceed with the payment.\n\n"
            "Best regards,\n"
            "The treasurer"
        ),
    )
