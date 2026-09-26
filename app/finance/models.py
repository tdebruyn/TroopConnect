from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from members.models import Branch, Enrollment, ParentChild, Person, SchoolYear
from members.money import format_money


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
        return f"{self.school_year} — {self.get_member_type_display()} — {branch} — {self.get_rank_display()}: {format_money(self.amount)}"

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


class Household(models.Model):
    """A named billing household, overriding address inference.

    By default the fees module infers a household from the postal address: every
    enrolled member sharing an address is billed together and ranked by age.
    That is right most of the time and wrong exactly when it matters — a
    blended family, two families sharing a building, a data-entry slip that
    left a sibling with a different address.

    A member named here is billed with *this* household and is not folded back
    into their address group, so the two operations the trésorier needs are
    both just membership edits:

    * **merge** — put members that inference would separate into one household;
    * **split** — give a member their own household, which takes them (and only
      them) out of the inferred group at their address.

    Membership is not scoped to a school year: a family stays a family. Which of
    its members are billed, and in which order they rank, is recomputed per
    school year from that year's enrolments (see :func:`household_groups`).
    """

    name = models.CharField(
        max_length=120,
        help_text=_("A name the treasurer recognises, e.g. “Famille Dupont”"),
    )
    members = models.ManyToManyField(
        Person,
        through="HouseholdMember",
        related_name="households",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Household")
        verbose_name_plural = _("Households")

    def __str__(self):
        return self.name


class HouseholdMember(models.Model):
    """One person's explicit household.

    ``person`` is unique rather than merely indexed: a member belongs to at most
    one household, so the "merge" operation is a reassignment rather than an
    accumulation.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="memberships"
    )
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="household_memberships"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["person"], name="uniq_household_per_person"
            ),
        ]
        verbose_name = _("Household member")
        verbose_name_plural = _("Household members")

    def __str__(self):
        return f"{self.person} → {self.household}"


class HouseholdAdjustment(models.Model):
    """A manual correction to what a household owes for one school year.

    A signed amount (negative writes off, positive adds) plus the reason and
    who wrote it — the audit trail a treasurer needs when a fee line does not
    follow the grid. Applied on top of the computed fees *after* the late
    penalty, since it corrects the total rather than the price.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="adjustments"
    )
    school_year = models.ForeignKey(
        SchoolYear, on_delete=models.CASCADE, related_name="household_adjustments"
    )
    amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text=_("Negative writes off, positive adds to what is owed"),
    )
    reason = models.CharField(max_length=255)
    author = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_household_adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["school_year__start_date", "household__name", "created_at"]
        verbose_name = _("Household adjustment")
        verbose_name_plural = _("Household adjustments")

    def __str__(self):
        return f"{self.household} — {format_money(self.amount)} ({self.reason})"


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
        return f"{self.person} — {format_money(self.amount)} ({self.date})"


def household_groups(school_year):
    """Group the year's billed members into households, eldest first.

    Returns a list of dicts in a stable order::

        {"household": Household | None, "name": str, "members": [Person, ...]}

    ``household`` is None for a group inferred from the postal address.
    An explicit :class:`Household` membership wins outright: a member named in a
    household is grouped there and is *never* folded back into the address
    group, which is what makes splitting one child out of a family a single
    membership edit rather than a special case threaded through the billing.

    ``members`` is ordered by birthday ascending because that is the order
    :func:`calculate_balances` assigns sibling ranks in — the eldest is rank 1
    and pays the full fee wherever they live.
    """
    members = (
        Person.objects.filter(
            primary_role__short__in=["e", "a", "ar"],
            status="a",
            enrollment__school_year=school_year,
        )
        .select_related("primary_role")
        .prefetch_related("households")
        .distinct()
        .order_by("birthday")
    )

    explicit = {}  # household pk -> (Household, [Person])
    inferred = {}  # address -> (None, [Person])

    for member in members:
        household = next(iter(member.households.all()), None)
        if household is not None:
            bucket = explicit.setdefault(household.pk, (household, []))
        else:
            bucket = inferred.setdefault(member.address or "", (None, []))
        bucket[1].append(member)

    groups = [
        {"household": household, "name": household.name, "members": group}
        for household, group in explicit.values()
    ] + [
        {"household": None, "name": address, "members": group}
        for address, (_none, group) in inferred.items()
    ]
    groups.sort(key=lambda g: (g["name"].casefold(), g["household"] is None))
    return groups


def household_index(school_year):
    """``{person_id: household group}`` for the year's billed members.

    The one lookup a member page needs: it answers "which household is this
    person billed in, and who else is in it" without the caller re-deriving the
    grouping. A person missing from the index is simply not billed this year.
    """
    return {
        member.pk: group
        for group in household_groups(school_year)
        for member in group["members"]
    }


def _adjustment_totals(school_year):
    """Net manual adjustment per household id for a school year."""
    totals = {}
    for row in HouseholdAdjustment.objects.filter(school_year=school_year).values(
        "household_id", "amount"
    ):
        totals[row["household_id"]] = (
            totals.get(row["household_id"], Decimal("0")) + row["amount"]
        )
    return totals


def _apply_adjustments(totals, groups, dues):
    """Fold each household's adjustments into one member's dues.

    An adjustment is a single figure for a whole household while a balance is
    per person, so the net amount is placed on the household's first enrolled
    *child* — the line whose fee already anchors the family, and the one the
    reminder tool chases, so a write-off actually reaches the parent who owes
    it. A household with no child enrolled this year (animators only) falls
    back to its eldest member.

    Returns ``{person_id: Decimal}`` for the members carrying an amount.
    """
    applied = {}
    for group in groups:
        household = group["household"]
        if household is None or not group["members"]:
            continue
        total = totals.get(household.pk)
        if not total:
            continue
        anchor = next(
            (m for m in group["members"] if m.primary_role.short == "e"),
            group["members"][0],
        )
        dues[anchor.pk] += total
        applied[anchor.pk] = total
    return applied


def household_summaries(school_year, balances=None):
    """Per-household totals for the year, in :func:`household_groups` order.

    Unlike the per-person balances, the ``adjustment`` here is the household's
    net adjustment straight from the database. It is shown even when the group
    has no enrolled member to carry it, so a line that is quietly not being
    applied is visible rather than absent.
    """
    if balances is None:
        balances = calculate_balances(school_year)
    by_person = {b["person_id"]: b for b in balances}
    totals = _adjustment_totals(school_year)

    summaries = []
    for group in household_groups(school_year):
        rows = [by_person[m.pk] for m in group["members"] if m.pk in by_person]
        adjustment = (
            totals.get(group["household"].pk, Decimal("0"))
            if group["household"]
            else Decimal("0")
        )
        summaries.append({
            "household": group["household"],
            "name": group["name"],
            "members": group["members"],
            "rows": rows,
            "base_due": sum(
                (r["amount_due"] - r["adjustment"] for r in rows), Decimal("0")
            ),
            "adjustment": adjustment,
            "due": sum((r["amount_due"] for r in rows), Decimal("0")),
            "paid": sum((r["amount_paid"] for r in rows), Decimal("0")),
            "balance": sum((r["balance"] for r in rows), Decimal("0")),
        })
    return summaries


def calculate_balances(school_year):
    """Calculate what each person owes for a school year.

    Returns a list of dicts::

        {person_id, amount_due, amount_paid, balance, is_late,
         adjustment, household, household_name}

    ``amount_due`` is the fee for the member's rank in their household plus the
    household's manual adjustment (see :func:`_apply_adjustments`), so callers
    that only care about the money need no extra step. ``adjustment`` is that
    same share broken out for display, and is zero for everyone else.
    """
    config = CotisationConfig.get_for_year(school_year)
    groups = household_groups(school_year)

    member_ids = [m.pk for g in groups for m in g["members"]]
    branch_by_person = {}
    for enr in (
        Enrollment.objects.filter(school_year=school_year, user__in=member_ids)
        .select_related("section__branch")
    ):
        if enr.user_id not in branch_by_person and enr.section_id:
            branch_by_person[enr.user_id] = enr.section.branch

    dues = {}  # person_id -> Decimal amount due
    group_by_person = {}

    for group in groups:
        for i, member in enumerate(group["members"]):
            rank = 1 if i == 0 else (2 if i == 1 else 3)
            is_animator = member.primary_role.short in ["a", "ar"]
            member_type = (
                FeeRule.MemberType.ANIMATOR if is_animator else FeeRule.MemberType.CHILD
            )
            branch = None if is_animator else branch_by_person.get(member.pk)
            dues[member.pk] = FeeRule.get_fee(school_year, member_type, rank, branch)
            group_by_person[member.pk] = group

    now = timezone.now().date()
    is_late = config.late_deadline and now > config.late_deadline
    if is_late:
        factor = Decimal("1") + config.late_penalty_percent / Decimal("100")
        for pk in dues:
            dues[pk] = (dues[pk] * factor).quantize(Decimal("0.01"))

    # After the penalty, not before: an adjustment corrects what the household
    # owes, it is not another price to be surcharged.
    adjustments = _apply_adjustments(_adjustment_totals(school_year), groups, dues)

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
        group = group_by_person[person_id]
        results.append({
            "person_id": person_id,
            "amount_due": amount_due,
            "amount_paid": amount_paid,
            "balance": balance,
            "is_late": is_late and balance > 0,
            "adjustment": adjustments.get(person_id, Decimal("0")),
            "household": group["household"],
            "household_name": group["name"],
        })

    return results


def get_adults_with_balance(school_year):
    """Get all adults (parents of enrolled children) who have an unpaid balance.

    Returns list of dicts: {person, email, children_names, balance}

    The balance is the *net* over the parent's children, credits included. With
    a household adjustment in play a sibling can be in credit while another
    still owes, and a household written off in full must stop being chased for
    the share that was waived — counting only the positive rows would keep the
    reminder coming.
    """
    balances = calculate_balances(school_year)
    balance_by_person = {b["person_id"]: b["balance"] for b in balances}

    # No child can be in credit (net) if none is owed for.
    if not any(balance > 0 for balance in balance_by_person.values()):
        return []

    # Only children are chased for; an animateur is billed but has no parent to
    # write to.
    child_ids = list(
        Person.objects.filter(
            pk__in=balance_by_person.keys(), primary_role__short="e"
        ).values_list("pk", flat=True)
    )

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

        parent_children = Person.objects.filter(
            as_child__parent=parent,
            pk__in=child_ids,
        )
        total_balance = sum(
            (balance_by_person[c.pk] for c in parent_children), Decimal("0")
        )

        if total_balance > 0:
            results.append({
                "person": parent,
                "email": parent.account.email,
                "children_names": ", ".join(str(c) for c in parent_children),
                "balance": total_balance,
            })

    return results
