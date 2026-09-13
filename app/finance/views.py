
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from post_office import mail

from members.models import Branch, Person, SchoolYear

from .forms import PaymentForm, PriceGridForm, ReminderForm
from .models import (
    CotisationConfig,
    FeeRule,
    Payment,
    calculate_balances,
    get_adults_with_balance,
)


def _is_tresorier(user):
    """Check if user has Trésorier role."""
    if not hasattr(user, "person"):
        return False
    return user.person.roles.filter(short="t").exists()


def _check_access(user):
    """Return True if user can access finance views."""
    return _is_tresorier(user) or user.is_staff


def _is_htmx(request):
    """Check if request comes from HTMX."""
    return request.META.get("HTTP_HX_REQUEST") == "true"


@login_required
def billing_overview(request):
    """Overview of all household balances for the current year."""
    if not _is_tresorier(request.user) and not request.user.is_staff:
        raise Http404

    current_year = SchoolYear.current()
    if not current_year:
        messages.error(request, _("No current school year defined."))
        return redirect("homepage")

    config = CotisationConfig.get_for_year(current_year)
    balances = calculate_balances(current_year)

    # Enrich with person data
    person_ids = [b["person_id"] for b in balances]
    persons = {p.pk: p for p in Person.objects.filter(pk__in=person_ids)}
    for b in balances:
        b["person"] = persons.get(b["person_id"])

    # Split into children and animateurs
    children_balances = [b for b in balances if b["person"] and b["person"].primary_role.short == "e"]
    animateur_balances = [b for b in balances if b["person"] and b["person"].primary_role.short in ["a", "ar"]]

    # Build the price grid for display.
    ranks = [FeeRule.Rank.FIRST, FeeRule.Rank.SECOND, FeeRule.Rank.THIRD]
    child_by_branch = {}
    branch_order = []
    for rule in (
        FeeRule.objects.filter(
            school_year=current_year, member_type=FeeRule.MemberType.CHILD
        ).select_related("branch")
    ):
        if rule.branch_id not in child_by_branch:
            child_by_branch[rule.branch_id] = {"branch": rule.branch, "amounts": {}}
            branch_order.append(rule.branch_id)
        child_by_branch[rule.branch_id]["amounts"][rule.rank] = rule.amount

    # Sort branches: named branches first (alphabetical), "all branches" (None) last.
    branch_order.sort(
        key=lambda b_id: (
            child_by_branch[b_id]["branch"] is None,
            child_by_branch[b_id]["branch"].name if child_by_branch[b_id]["branch"] else "",
        )
    )
    child_grid = [
        {
            "branch": child_by_branch[b_id]["branch"],
            "amounts": [child_by_branch[b_id]["amounts"].get(rank) for rank in ranks],
        }
        for b_id in branch_order
    ]

    animator_by_rank = {
        rule.rank: rule.amount
        for rule in FeeRule.objects.filter(
            school_year=current_year, member_type=FeeRule.MemberType.ANIMATOR
        )
    }
    animator_amounts = [animator_by_rank.get(rank) for rank in ranks]
    has_animator = any(amount is not None for amount in animator_amounts)

    return render(request, "finance/billing_overview.html", {
        "config": config,
        "school_year": current_year,
        "ranks": ranks,
        "child_grid": child_grid,
        "animator_amounts": animator_amounts,
        "has_animator": has_animator,
        "children_balances": children_balances,
        "animateur_balances": animateur_balances,
    })


@login_required
def edit_prices(request):
    """Editable price grid for the trésorier, per school year."""
    if not _is_tresorier(request.user) and not request.user.is_staff:
        raise Http404

    years = SchoolYear.objects.order_by("-start_date")
    if not years.exists():
        messages.error(request, _("No current school year defined."))
        return redirect("homepage")

    selected_year_id = request.GET.get("year") or request.POST.get("year")
    selected_year = years.filter(pk=selected_year_id).first() if selected_year_id else None
    if selected_year is None:
        selected_year = SchoolYear.current() or years.first()

    branches = list(Branch.objects.order_by("min_age_dec_31", "name"))

    if request.method == "POST":
        form = PriceGridForm(request.POST, school_year=selected_year, branches=branches)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                _("Prices saved for %(range)s.")
                % {"range": selected_year.range or selected_year.name},
            )
            return redirect(f"{reverse('finance:prices')}?year={selected_year.pk}")
    else:
        form = PriceGridForm(school_year=selected_year, branches=branches)

    return render(request, "finance/price_edit.html", {
        "form": form,
        "selected_year": selected_year,
        "years": years,
        "child_rows": list(form.iter_child_rows()),
        "animator_cells": form.animator_cells(),
        "ranks": PriceGridForm.RANKS,
    })


@login_required
def record_payment(request):
    """Trésorier records a payment for a person."""
    if not _check_access(request.user):
        raise Http404

    current_year = SchoolYear.current()
    if not current_year:
        if _is_htmx(request):
            return HttpResponse("")
        messages.error(request, _("No current school year defined."))
        return redirect("homepage")

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            person = Person.objects.filter(pk=form.cleaned_data["person_id"]).first()
            if not person:
                if _is_htmx(request):
                    return HttpResponse("")
                messages.error(request, _("Person not found."))
                return redirect("finance:billing")

            Payment.objects.create(
                person=person,
                school_year=current_year,
                amount=form.cleaned_data["amount"],
                date=form.cleaned_data["date"],
                note=form.cleaned_data.get("note", ""),
                recorded_by=request.user.person,
            )
            if _is_htmx(request):
                response = HttpResponse("")
                response["HX-Redirect"] = reverse("finance:billing")
                return response
            messages.success(
                request,
                _("Payment of %(amount)s€ recorded for %(person)s.")
                % {"amount": form.cleaned_data["amount"], "person": person},
            )
            return redirect("finance:billing")
    else:
        initial = {"date": timezone.now().date()}
        person_id = request.GET.get("person_id")
        if person_id:
            initial["person_id"] = person_id
        form = PaymentForm(initial=initial)

    if _is_htmx(request):
        return render(request, "finance/record_payment_modal.html", {"form": form})
    return render(request, "finance/record_payment.html", {"form": form})


@login_required
def payment_history(request, person_id):
    """Show payment history for a person in an HTMX modal."""
    if not _check_access(request.user):
        raise Http404

    current_year = SchoolYear.current()
    if not current_year:
        return HttpResponse("")

    person = Person.objects.filter(pk=person_id).first()
    if not person:
        return HttpResponse("")

    payments = Payment.objects.filter(
        person=person, school_year=current_year
    ).order_by("-date")

    return render(request, "finance/payment_history.html", {
        "person": person,
        "payments": payments,
    })


@login_required
def send_reminders(request):
    """Bulk send reminder emails to adults with unpaid balances."""
    if not _is_tresorier(request.user) and not request.user.is_staff:
        raise Http404

    current_year = SchoolYear.current()
    if not current_year:
        messages.error(request, _("No current school year defined."))
        return redirect("homepage")

    adults = get_adults_with_balance(current_year)

    if request.method == "POST":
        form = ReminderForm(request.POST)
        if form.is_valid():
            sent_count = 0
            failed_count = 0
            for adult in adults:
                body = form.cleaned_data["body"]
                body = body.replace("{prenom}", adult["person"].first_name)
                body = body.replace("{solde}", str(adult["balance"]))

                try:
                    mail.send(
                        recipients=[adult["email"]],
                        sender=settings.DEFAULT_FROM_EMAIL,
                        subject=form.cleaned_data["subject"],
                        message=body,
                    )
                except Exception:
                    # Count the outcome, not the attempt: reporting "sent" for
                    # a failed send would tell the trésorier a household was
                    # chased when the email never left.
                    failed_count += 1
                    messages.error(
                        request,
                        _("Failed to send to %(email)s.") % {"email": adult["email"]},
                    )
                else:
                    sent_count += 1

            messages.success(
                request,
                _("Reminders sent to %(count)s adult(s).") % {"count": sent_count},
            )
            if failed_count:
                messages.warning(
                    request,
                    _("%(count)s reminder(s) could not be sent.")
                    % {"count": failed_count},
                )
            return redirect("finance:billing")
    else:
        form = ReminderForm()

    return render(request, "finance/send_reminders.html", {
        "form": form,
        "adults": adults,
    })
