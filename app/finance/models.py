from django.db import models
from django.utils import timezone
from decimal import Decimal

from members.models import Person, SchoolYear, ParentChild, Enrollment


class CotisationConfig(models.Model):
    """Fee configuration for a school year."""

    school_year = models.OneToOneField(
        SchoolYear, on_delete=models.CASCADE, related_name="cotisation_config"
    )
    full_fee = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text="Cotisation pleine (enfant aîné)",
    )
    sibling_discount = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=Decimal("0.00"),
        help_text="Réduction pour fratrie (montant déduit par frère/sœur supplémentaire)",
    )
    animateur_fee = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=Decimal("0.00"),
        help_text="Cotisation forfaitaire pour animateurs/staff",
    )
    late_penalty_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal("0.00"),
        help_text="Pénalité de retard en pourcentage (ex: 10.00 pour 10%)",
    )
    late_deadline = models.DateField(
        null=True, blank=True,
        help_text="Date limite avant pénalité de retard",
    )

    class Meta:
        verbose_name = "Configuration de cotisation"
        verbose_name_plural = "Configurations de cotisations"

    def __str__(self):
        return f"Cotisations {self.school_year.range}"

    @staticmethod
    def get_for_year(school_year):
        """Get or create config for a school year with zero defaults."""
        config, _ = CotisationConfig.objects.get_or_create(
            school_year=school_year,
            defaults={
                "full_fee": Decimal("0.00"),
                "sibling_discount": Decimal("0.00"),
                "animateur_fee": Decimal("0.00"),
                "late_penalty_percent": Decimal("0.00"),
            },
        )
        return config


class Payment(models.Model):
    """A payment recorded by the Trésorier."""

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="payments"
    )
    school_year = models.ForeignKey(
        SchoolYear, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    date = models.DateField(default=timezone.now)
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.person} — {self.amount}€ ({self.date})"


def _get_households(school_year):
    """Group enrolled children by address.

    Returns a dict: {address: [Person, ...]} sorted by birthday ascending
    (eldest first) within each household.
    """
    children = (
        Person.objects.filter(
            primary_role__short="e",
            status="a",
            enrollment__school_year=school_year,
        )
        .distinct()
        .order_by("birthday")
    )

    households = {}
    for child in children:
        addr = child.address or "__no_address__"
        households.setdefault(addr, []).append(child)
    return households


def calculate_balances(school_year):
    """Calculate what each person owes for a school year.

    Returns a list of dicts:
      {person_id, amount_due, amount_paid, balance, is_late}
    """
    config = CotisationConfig.get_for_year(school_year)
    households = _get_households(school_year)

    dues = {}  # person_id -> Decimal amount due

    # Children: eldest full fee, siblings discounted
    for addr, children in households.items():
        for i, child in enumerate(children):
            if i == 0:
                dues[child.pk] = config.full_fee
            else:
                dues[child.pk] = max(
                    config.full_fee - config.sibling_discount, Decimal("0.00")
                )

    # Animateurs / staff: flat rate (anyone with primary role "a" or "ar" who is enrolled)
    animateurs = (
        Person.objects.filter(
            primary_role__short__in=["a", "ar"],
            status="a",
            enrollment__school_year=school_year,
        )
        .distinct()
    )
    for anim in animateurs:
        dues[anim.pk] = config.animateur_fee

    # Apply late penalty
    now = timezone.now().date()
    is_late = config.late_deadline and now > config.late_deadline
    if is_late:
        factor = Decimal("1") + config.late_penalty_percent / Decimal("100")
        for pk in dues:
            dues[pk] = (dues[pk] * factor).quantize(Decimal("0.01"))

    # Calculate payments
    payments_by_person = {}
    for p in Payment.objects.filter(school_year=school_year).values("person_id", "amount"):
        payments_by_person.setdefault(p["person_id"], Decimal("0"))
        payments_by_person[p["person_id"]] += p["amount"]

    results = []
    for person_id, amount_due in dues.items():
        amount_paid = payments_by_person.get(person_id, Decimal("0"))
        balance = amount_due - amount_paid
        results.append({
            "person_id": person_id,
            "amount_due": amount_due,
            "amount_paid": amount_paid,
            "balance": balance,
            "is_late": is_late and balance > 0,
        })

    return results


def get_adults_with_balance(school_year):
    """Get all adults (parents of enrolled children) who have an unpaid balance.

    Returns list of dicts: {person, email, children_names, balance}
    """
    balances = calculate_balances(school_year)
    balance_by_person = {b["person_id"]: b for b in balances if b["balance"] > 0}

    if not balance_by_person:
        return []

    person_ids = list(balance_by_person.keys())

    # Find parents of these children
    children_with_balance = Person.objects.filter(pk__in=person_ids, primary_role__short="e")
    child_ids = list(children_with_balance.values_list("pk", flat=True))

    parent_links = ParentChild.objects.filter(child_id__in=child_ids).select_related(
        "parent", "parent__account"
    )

    results = []
    seen_parents = set()
    for link in parent_links:
        parent = link.parent
        if parent.pk in seen_parents:
            continue
        if not hasattr(parent, "account"):
            continue
        seen_parents.add(parent.pk)

        # Find this parent's children who have balance
        parent_children = Person.objects.filter(
            as_child__parent=parent,
            pk__in=child_ids,
        )
        total_balance = sum(
            balance_by_person[c.pk]["balance"] for c in parent_children
            if c.pk in balance_by_person
        )

        if total_balance > 0:
            results.append({
                "person": parent,
                "email": parent.account.email,
                "children_names": ", ".join(str(c) for c in parent_children),
                "balance": total_balance,
            })

    return results
