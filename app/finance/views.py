from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from post_office import mail

from members.models import Branch, Person, SchoolYear
from members.modules import FEES, requires_module
from members.money import format_money
from members.permissions import (
    ANIMATEUR_ROLES,
    ANIME,
    can_access_finance,
    get_person,
    is_htmx,
)

from .forms import (
    HouseholdAdjustmentForm,
    HouseholdAssignmentForm,
    HouseholdForm,
    HouseholdMemberForm,
    PaymentForm,
    PriceGridForm,
    ReminderForm,
)
from .models import (
    CotisationConfig,
    FeeRule,
    Household,
    HouseholdMember,
    Payment,
    calculate_balances,
    get_adults_with_balance,
    household_summaries,
)


@login_required
@requires_module(FEES)
def billing_overview(request):
    """Overview of all household balances for the current year."""
    if not can_access_finance(request.user):
        raise Http404

    current_year = SchoolYear.current()
    if not current_year:
        messages.error(request, _("No current school year defined."))
        return redirect("homepage")

    config = CotisationConfig.get_for_year(current_year)
    balances = calculate_balances(current_year)

    # Enrich with person data; select_related avoids a role query per household.
    person_ids = [balance["person_id"] for balance in balances]
    persons = {
        person.pk: person
        for person in Person.objects.filter(pk__in=person_ids).select_related(
            "primary_role"
        )
    }
    for balance in balances:
        balance["person"] = persons.get(balance["person_id"])

    children_balances = [
        balance
        for balance in balances
        if balance["person"] and balance["person"].primary_role.short == ANIME
    ]
    animateur_balances = [
        balance
        for balance in balances
        if balance["person"]
        and balance["person"].primary_role.short in ANIMATEUR_ROLES
    ]

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
        # Passed the balances already computed above rather than letting the
        # summary recompute the whole year.
        "household_rows": [
            s
            for s in household_summaries(current_year, balances)
            if s["household"]
        ],
    })


@login_required
@requires_module(FEES)
def edit_prices(request):
    """Editable price grid for the trésorier, per school year."""
    if not can_access_finance(request.user):
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
@requires_module(FEES)
def record_payment(request):
    """Trésorier records a payment for a person."""
    if not can_access_finance(request.user):
        raise Http404

    current_year = SchoolYear.current()
    if not current_year:
        if is_htmx(request):
            return HttpResponse("")
        messages.error(request, _("No current school year defined."))
        return redirect("homepage")

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            person = Person.objects.filter(pk=form.cleaned_data["person_id"]).first()
            if not person:
                if is_htmx(request):
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
            if is_htmx(request):
                response = HttpResponse("")
                response["HX-Redirect"] = reverse("finance:billing")
                return response
            messages.success(
                request,
                _("Payment of %(amount)s recorded for %(person)s.")
                % {
                    "amount": format_money(form.cleaned_data["amount"]),
                    "person": person,
                },
            )
            return redirect("finance:billing")
    else:
        initial = {"date": timezone.now().date()}
        person_id = request.GET.get("person_id")
        if person_id:
            initial["person_id"] = person_id
        form = PaymentForm(initial=initial)

    if is_htmx(request):
        return render(request, "finance/record_payment_modal.html", {"form": form})
    return render(request, "finance/record_payment.html", {"form": form})


@login_required
@requires_module(FEES)
def payment_history(request, person_id):
    """Show payment history for a person in an HTMX modal."""
    if not can_access_finance(request.user):
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

    # Manual adjustments are part of what this person owes, so they belong in
    # the history next to the payments rather than only on the billing page.
    household = person.households.first()
    adjustments = (
        household.adjustments.filter(school_year=current_year)
        .select_related("school_year", "author")
        .order_by("-created_at")
        if household
        else []
    )

    return render(request, "finance/payment_history.html", {
        "person": person,
        "payments": payments,
        "household": household,
        "adjustments": adjustments,
    })


@login_required
@requires_module(FEES)
def send_reminders(request):
    """Bulk send reminder emails to adults with unpaid balances."""
    if not can_access_finance(request.user):
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
                body = body.replace("{solde}", format_money(adult["balance"]))

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


def _back_after_assignment(request, fallback="members:admin_list"):
    """Where to land after a household change: the page that asked for it.

    The member page and the household page both post to the same endpoint, so
    the caller passes its own URL in ``next``. An off-site target is refused.
    """
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect(fallback)


@login_required
@requires_module(FEES)
def household_list(request):
    """The troop's explicit households, and the form that adds one."""
    if not can_access_finance(request.user):
        raise Http404

    if request.method == "POST":
        form = HouseholdForm(request.POST)
        if form.is_valid():
            household = form.save()
            messages.success(
                request,
                _("Household “%(name)s” created.") % {"name": household.name},
            )
            return redirect("finance:household_detail", pk=household.pk)
    else:
        form = HouseholdForm()

    current_year = SchoolYear.current()
    summaries = (
        # Inference-only groups have no household and no row here.
        {s["household"].pk: s for s in household_summaries(current_year) if s["household"]}
        if current_year
        else {}
    )
    rows = [
        {
            "household": household,
            # None when no member of the household is enrolled this year, or
            # when there is no current school year at all.
            "summary": summaries.get(household.pk),
            "members": household.members.all(),
        }
        for household in Household.objects.prefetch_related("members").order_by("name")
    ]

    return render(request, "finance/household_list.html", {
        "form": form,
        "rows": rows,
        "school_year": current_year,
    })


@login_required
@requires_module(FEES)
def household_detail(request, pk):
    """One household: its members, their fee lines, its adjustments."""
    if not can_access_finance(request.user):
        raise Http404

    household = get_object_or_404(Household, pk=pk)
    current_year = SchoolYear.current()

    # Three forms share this page, told apart by the submit that sent them.
    # A bound form that failed validation is re-rendered; an unbound one is
    # only re-rendered after a different action was handled, which is why each
    # branch falls through to the same render rather than returning early.
    rename_form = HouseholdForm(instance=household)
    member_form = HouseholdMemberForm(household=household)
    adjustment_form = HouseholdAdjustmentForm(household=household)

    action = request.POST.get("action") if request.method == "POST" else None

    if action == "rename":
        rename_form = HouseholdForm(request.POST, instance=household)
        if rename_form.is_valid():
            rename_form.save()
            messages.success(
                request,
                _("Household renamed to “%(name)s”.") % {"name": household.name},
            )
            return redirect("finance:household_detail", pk=household.pk)
    elif action == "add_member":
        member_form = HouseholdMemberForm(request.POST, household=household)
        if member_form.is_valid():
            person = member_form.cleaned_data["person"]
            HouseholdMember.objects.update_or_create(
                person=person, defaults={"household": household}
            )
            messages.success(
                request,
                _("%(person)s is now billed with “%(household)s”.")
                % {"person": person, "household": household},
            )
            return redirect("finance:household_detail", pk=household.pk)
    elif action == "add_adjustment":
        adjustment_form = HouseholdAdjustmentForm(request.POST, household=household)
        if adjustment_form.is_valid():
            adjustment = adjustment_form.save(commit=False)
            adjustment.author = get_person(request.user)
            adjustment.save()
            messages.success(
                request,
                _("Adjustment of %(amount)s recorded for “%(household)s”.")
                % {
                    "amount": format_money(adjustment.amount),
                    "household": household,
                },
            )
            return redirect("finance:household_detail", pk=household.pk)

    # The fee lines exactly as the rest of the module computes them, so this
    # page shows the same ranks and amounts as the billing overview.
    billed = (
        [
            b
            for b in calculate_balances(current_year)
            if b["household"] and b["household"].pk == household.pk
        ]
        if current_year
        else []
    )
    balance_by_person = {b["person_id"]: b for b in billed}
    rank_by_person = {b["person_id"]: i + 1 for i, b in enumerate(billed)}

    # Every explicit member, enrolled or not: a member who is not billed this
    # year still has to be visible here, or there would be no way to take them
    # out of the household.
    member_rows = [
        {
            "person": member,
            "rank": rank_by_person.get(member.pk),
            "balance": balance_by_person.get(member.pk),
        }
        for member in household.members.select_related("primary_role").order_by(
            "birthday"
        )
    ]

    adjustments = household.adjustments.select_related(
        "school_year", "author"
    ).order_by("-school_year__start_date", "-created_at")

    # An adjustment on a household with nobody enrolled is never applied to
    # anyone's balance. Say so rather than let the line sit there looking
    # effective.
    unapplied = None
    if current_year and not billed:
        year_total = sum(
            (a.amount for a in adjustments if a.school_year_id == current_year.pk),
            start=Decimal("0"),
        )
        if year_total:
            unapplied = year_total

    return render(request, "finance/household_detail.html", {
        "household": household,
        "school_year": current_year,
        "rename_form": rename_form,
        "member_form": member_form,
        "adjustment_form": adjustment_form,
        "member_rows": member_rows,
        "adjustments": adjustments,
        "unapplied": unapplied,
    })


@login_required
@requires_module(FEES)
@require_POST
def assign_household(request):
    """Set — or clear — a member's explicit household override.

    Shared by the member page and the household page. Clearing the field is how
    a member goes back to being billed by address, so there is no separate
    "split" action to keep in step with this one.
    """
    if not can_access_finance(request.user):
        raise Http404

    form = HouseholdAssignmentForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Could not change the household."))
        return _back_after_assignment(request)

    person = Person.objects.filter(pk=form.cleaned_data["person_id"]).first()
    if person is None:
        messages.error(request, _("Person not found."))
        return _back_after_assignment(request)

    household = form.cleaned_data["household"]
    if household is None:
        if HouseholdMember.objects.filter(person=person).delete()[0]:
            messages.success(
                request,
                _("%(person)s is billed by address again.") % {"person": person},
            )
    else:
        HouseholdMember.objects.update_or_create(
            person=person, defaults={"household": household}
        )
        messages.success(
            request,
            _("%(person)s is now billed with “%(household)s”.")
            % {"person": person, "household": household},
        )

    return _back_after_assignment(request)


@login_required
@requires_module(FEES)
@require_POST
def household_delete(request, pk):
    """Delete a household; its members fall back to address inference."""
    if not can_access_finance(request.user):
        raise Http404

    household = get_object_or_404(Household, pk=pk)
    name = household.name
    household.delete()
    messages.success(
        request,
        _("Household “%(name)s” deleted. Its members are billed by address again.")
        % {"name": name},
    )
    return redirect("finance:households")


@login_required
@requires_module(FEES)
@require_POST
def adjustment_delete(request, pk, adjustment_pk):
    """Delete one manual adjustment line."""
    if not can_access_finance(request.user):
        raise Http404

    household = get_object_or_404(Household, pk=pk)
    adjustment = get_object_or_404(
        household.adjustments, pk=adjustment_pk
    )
    adjustment.delete()
    messages.success(request, _("Adjustment deleted."))
    return redirect("finance:household_detail", pk=household.pk)
