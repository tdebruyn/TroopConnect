from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import FeeRule


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
            (r.branch_id, r.rank, r.member_type): r.amount
            for r in FeeRule.objects.filter(school_year=school_year)
        }

        # Generic (all branches) child row.
        for rank in self.RANKS:
            self._field(f"child_all_{rank}", existing.get((None, rank, "child")))
        # Per-branch child rows.
        for branch in branches:
            for rank in self.RANKS:
                self._field(
                    f"child_{branch.pk}_{rank}",
                    existing.get((branch.pk, rank, "child")),
                )
        # Animator row (all branches).
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
