from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from members.models import Branch, Enrollment, ParentChild, Person, SchoolYear


class CotisationConfig(models.Model):
    """Year-level fee settings (late penalty only; prices live in FeeRule)."""

    school_year = models.OneToOneField(
        SchoolYear, on_delete=models.CASCADE, related_name="cotisation_config"
    )
    late_penalty_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Late penalty as a percentage (e.g. 10.00 for 10%)"),
    )
    late_deadline = models.DateField(
        null=True, blank=True,
        help_text=_("Deadline before the late penalty applies"),
    )

    class Meta:
        verbose_name = _("Fee configuration")
        verbose_name_plural = _("Fee configurations")

    def __str__(self):
        return _("Membership fees %(range)s") % {"range": self.school_year.range}

    @staticmethod
    def get_for_year(school_year):
        """Get or create config for a school year with zero defaults."""
        config, _ = CotisationConfig.objects.get_or_create(
            school_year=school_year,
            defaults={"late_penalty_percent": Decimal("0.00")},
        )
        return config


class FeeRule(models.Model):
    """A single price in the membership-fee grid.

    Flexible enough to express both pricing methods:
    - Flat method: rows with ``branch=None`` (applies to all branches), e.g.
      rank 1 = full fee, rank 2/3 = discounted.
    - Per-branch method: rows keyed by (branch, rank).
    Animateurs are priced by ``member_type="animator"`` (branch=None).
    """

    class MemberType(models.TextChoices):
        CHILD = "child", _("Child")
        ANIMATOR = "animator", _("Animator")

    class Rank(models.IntegerChoices):
        FIRST = 1, _("1st member")
        SECOND = 2, _("2nd member")
        THIRD = 3, _("3rd member or more")

    school_year = models.ForeignKey(
        SchoolYear, on_delete=models.CASCADE, related_name="fee_rules"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("Leave blank to apply to all branches"),
    )
    rank = models.PositiveSmallIntegerField(choices=Rank.choices)
    member_type = models.CharField(
        max_length=10, choices=MemberType.choices, default=MemberType.CHILD
    )
    amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school_year", "branch", "rank", "member_type"],
                name="uniq_fee_rule",
            ),
        ]
        ordering = ["member_type", "rank", "branch__name"]
        verbose_name = _("Fee rule")
        verbose_name_plural = _("Fee rules")

    def __str__(self):
        branch = self.branch.name if self.branch else _("All branches")
        return f"{self.school_year} — {self.get_member_type_display()} — {branch} — {self.get_rank_display()}: {self.amount}€"

    @classmethod
    def get_fee(cls, school_year, member_type, rank, branch=None):
        """Resolve the amount for (member_type, rank, branch).

        Falls back from the branch-specific rule to the generic (branch=None)
        rule, then to zero.
        """
        rules = cls.objects.filter(school_year=school_year, member_type=member_type)
        rule = rules.filter(branch=branch, rank=rank).first()
        if rule is not None:
            return rule.amount
        rule = rules.filter(branch=None, rank=rank).first()
        if rule is not None:
            return rule.amount
        return Decimal("0.00")


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
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.person} — {self.amount}€ ({self.date})"


def _get_households(school_year):
    """Group enrolled members (children + animateurs) by address.

    Returns a dict: {address: [Person, ...]} sorted by birthday ascending
    (eldest first) within each household.
    """
    members = (
        Person.objects.filter(
            primary_role__short__in=["e", "a", "ar"],
            status="a",
            enrollment__school_year=school_year,
        )
        .select_related("primary_role")
        .distinct()
        .order_by("birthday")
    )

    households = {}
    for member in members:
        addr = member.address or "__no_address__"
        households.setdefault(addr, []).append(member)
    return households


def calculate_balances(school_year):
    """Calculate what each person owes for a school year.

    Returns a list of dicts:
      {person_id, amount_due, amount_paid, balance, is_late}
    """
    config = CotisationConfig.get_for_year(school_year)
    households = _get_households(school_year)

    # Resolve each member's branch from their enrollment section (children only).
    member_ids = [m.pk for h in households.values() for m in h]
    branch_by_person = {}
    for enr in (
        Enrollment.objects.filter(school_year=school_year, user__in=member_ids)
        .select_related("section__branch")
    ):
        if enr.user_id not in branch_by_person and enr.section_id:
            branch_by_person[enr.user_id] = enr.section.branch

    dues = {}  # person_id -> Decimal amount due

    for _addr, members in households.items():
        for i, member in enumerate(members):
            rank = 1 if i == 0 else (2 if i == 1 else 3)
            is_animator = member.primary_role.short in ["a", "ar"]
            member_type = (
                FeeRule.MemberType.ANIMATOR if is_animator else FeeRule.MemberType.CHILD
            )
            branch = None if is_animator else branch_by_person.get(member.pk)
            dues[member.pk] = FeeRule.get_fee(school_year, member_type, rank, branch)

    # Apply late penalty
    now = timezone.now().date()
    is_late = config.late_deadline and now > config.late_deadline
    if is_late:
        factor = Decimal("1") + config.late_penalty_percent / Decimal("100")
        for pk in dues:
            dues[pk] = (dues[pk] * factor).quantize(Decimal("0.01"))

    # Calculate payments
    payments_by_person = {}
    for payment in Payment.objects.filter(school_year=school_year).values(
        "person_id", "amount"
    ):
        payments_by_person.setdefault(payment["person_id"], Decimal("0"))
        payments_by_person[payment["person_id"]] += payment["amount"]

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
