from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal

from post_office import mail

from members.models import Person, SchoolYear
from .models import CotisationConfig, Payment, calculate_balances, get_adults_with_balance
from .forms import PaymentForm, ReminderForm


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
        messages.error(request, "Aucune année scolaire courante définie.")
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

    return render(request, "finance/billing_overview.html", {
        "config": config,
        "school_year": current_year,
        "children_balances": children_balances,
        "animateur_balances": animateur_balances,
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
        messages.error(request, "Aucune année scolaire courante définie.")
        return redirect("homepage")

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            person = Person.objects.filter(pk=form.cleaned_data["person_id"]).first()
            if not person:
                if _is_htmx(request):
                    return HttpResponse("")
                messages.error(request, "Personne introuvable.")
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
            messages.success(request, f"Paiement de {form.cleaned_data['amount']}€ enregistré pour {person}.")
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
        messages.error(request, "Aucune année scolaire courante définie.")
        return redirect("homepage")

    adults = get_adults_with_balance(current_year)

    if request.method == "POST":
        form = ReminderForm(request.POST)
        if form.is_valid():
            sent_count = 0
            for adult in adults:
                body = form.cleaned_data["body"]
                body = body.replace("{prenom}", adult["person"].first_name)
                body = body.replace("{solde}", str(adult["balance"]))

                mail.send(
                    recipients=[adult["email"]],
                    sender="MS_M3qCdl@tomctl.be",
                    subject=form.cleaned_data["subject"],
                    message=body,
                )
                sent_count += 1

            messages.success(request, f"Rappels envoyés à {sent_count} adulte(s).")
            return redirect("finance:billing")
    else:
        form = ReminderForm()

    return render(request, "finance/send_reminders.html", {
        "form": form,
        "adults": adults,
    })
