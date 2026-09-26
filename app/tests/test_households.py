"""Explicit households: the override over address inference, and its adjustments.

``test_finance.py`` covers billing as it is *inferred* — the household is the
postal address and the ranks fall out of the birthdays. This module covers what
happens when that guess is overridden: a named household takes its members out
of the address grouping (so the override wins outright, including for the
sibling ranks of the siblings left behind), and a household carries manual
adjustment lines that land in the balances, the payment history and the
reminder amounts.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from finance.models import (
    Household,
    HouseholdAdjustment,
    HouseholdMember,
    calculate_balances,
    get_adults_with_balance,
    household_groups,
    household_summaries,
)
from members.models import SchoolYear, TroopSettings
from tests.base import TroopSettingsTestCase
from tests.test_finance import FinanceTestBase


def due_of(balances, person):
    """The amount due for one person in a ``calculate_balances`` result."""
    return next(b for b in balances if b["person_id"] == person.pk)["amount_due"]


def row_of(balances, person):
    """The whole balance row for one person."""
    return next(b for b in balances if b["person_id"] == person.pk)


class HouseholdOverrideTest(FinanceTestBase):
    """An explicit household wins over the address, ranks included.

    The fixture's family is two children at ``Rue des Fleurs 10`` (Charlie, 8,
    and Diana, 6) billed 80.00 and 60.00, plus Eve at another address billed
    80.00 on her own.
    """

    def _household(self, name, *persons):
        household = Household.objects.create(name=name)
        for person in persons:
            HouseholdMember.objects.create(household=household, person=person)
        return household

    def test_inference_is_the_default(self):
        balances = calculate_balances(self.current_year)
        self.assertEqual(due_of(balances, self.child_eldest), Decimal("80.00"))
        self.assertEqual(due_of(balances, self.child_youngest), Decimal("60.00"))

    def test_split_takes_a_member_out_of_the_address_group(self):
        """Charlie moved out, so Diana becomes her address group's first member."""
        self._household("Charlie seul", self.child_eldest)

        balances = calculate_balances(self.current_year)

        # Charlie keeps the full fee, now as the head of his own household.
        self.assertEqual(due_of(balances, self.child_eldest), Decimal("80.00"))
        # And Diana is billed as a first member rather than a second: the
        # override removed Charlie from the address group instead of only
        # labelling him.
        self.assertEqual(due_of(balances, self.child_youngest), Decimal("80.00"))

    def test_merge_bills_members_at_different_addresses_together(self):
        """Charlie and Eve live apart but are one household: Eve gets rank 2."""
        before = calculate_balances(self.current_year)
        self.assertEqual(due_of(before, self.child_other), Decimal("80.00"))

        self._household("Famille recomposée", self.child_eldest, self.child_other)

        balances = calculate_balances(self.current_year)
        self.assertEqual(due_of(balances, self.child_eldest), Decimal("80.00"))
        self.assertEqual(due_of(balances, self.child_other), Decimal("60.00"))

    def test_sibling_rank_under_a_household_follows_birthdays(self):
        """Ranks are by age, not by the order the members were added."""
        # Youngest added first: if ranks followed insertion order this would
        # pay the younger child's fee to the elder.
        self._household("Ordre inversé", self.child_youngest, self.child_eldest)

        balances = calculate_balances(self.current_year)
        self.assertEqual(due_of(balances, self.child_eldest), Decimal("80.00"))
        self.assertEqual(due_of(balances, self.child_youngest), Decimal("60.00"))

    def test_third_member_gets_the_third_rank_price(self):
        self._household(
            "Fratrie de trois",
            self.child_eldest,
            self.child_other,
            self.child_youngest,
        )

        balances = calculate_balances(self.current_year)
        self.assertEqual(due_of(balances, self.child_eldest), Decimal("80.00"))
        self.assertEqual(due_of(balances, self.child_other), Decimal("60.00"))
        self.assertEqual(due_of(balances, self.child_youngest), Decimal("50.00"))

    def test_a_member_moves_rather_than_multiplies(self):
        """Adding someone already housed reassigns them: never two households."""
        first = self._household("Premier", self.child_eldest)
        second = self._household("Second", self.child_youngest)

        HouseholdMember.objects.update_or_create(
            person=self.child_eldest, defaults={"household": second}
        )

        self.assertEqual(self.child_eldest.households.get(), second)
        self.assertEqual(HouseholdMember.objects.filter(person=self.child_eldest).count(), 1)
        self.assertEqual(first.members.count(), 0)

    def test_groups_are_reported_with_their_household(self):
        household = self._household("Charlie seul", self.child_eldest)

        groups = {g["name"]: g for g in household_groups(self.current_year)}

        self.assertEqual(groups["Charlie seul"]["household"], household)
        self.assertEqual(
            [m.pk for m in groups["Charlie seul"]["members"]], [self.child_eldest.pk]
        )
        # Diana is now alone under the address, which is what "split" means.
        self.assertIsNone(groups["Rue des Fleurs 10, 1300 Limal"]["household"])
        self.assertEqual(
            [m.pk for m in groups["Rue des Fleurs 10, 1300 Limal"]["members"]],
            [self.child_youngest.pk],
        )

    def test_a_member_outside_the_address_inference_is_not_billed_twice(self):
        """A household member appears in exactly one group."""
        self._household("Charlie seul", self.child_eldest)

        seen = [
            m.pk for g in household_groups(self.current_year) for m in g["members"]
        ]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertIn(self.child_eldest.pk, seen)


class HouseholdAdjustmentTest(FinanceTestBase):
    """Manual adjustment lines, from the line to the balance it lands on."""

    def setUp(self):
        super().setUp()
        # One household over the two brothers, so ranks and the anchor are
        # unambiguous: Charlie is the eldest child of the household.
        self.household = Household.objects.create(name="Famille Dupont")
        for person in (self.child_eldest, self.child_youngest):
            HouseholdMember.objects.create(household=self.household, person=person)

        self.author = self.parent1

    def _adjust(self, amount, *, reason="Geste commercial", year=None):
        return HouseholdAdjustment.objects.create(
            household=self.household,
            school_year=year or self.current_year,
            amount=Decimal(amount),
            reason=reason,
            author=self.author,
        )

    def test_no_adjustment_leaves_the_fee_alone(self):
        balances = calculate_balances(self.current_year)
        self.assertEqual(due_of(balances, self.child_eldest), Decimal("80.00"))
        self.assertEqual(row_of(balances, self.child_eldest)["adjustment"], Decimal("0"))

    def test_negative_adjustment_reduces_the_amount_due(self):
        self._adjust("-20.00")

        balances = calculate_balances(self.current_year)

        self.assertEqual(due_of(balances, self.child_eldest), Decimal("60.00"))
        self.assertEqual(row_of(balances, self.child_eldest)["adjustment"], Decimal("-20.00"))

    def test_positive_adjustment_increases_the_amount_due(self):
        self._adjust("15.00")

        balances = calculate_balances(self.current_year)

        self.assertEqual(due_of(balances, self.child_eldest), Decimal("95.00"))

    def test_adjustment_lands_on_the_eldest_child_only(self):
        self._adjust("-20.00")

        balances = calculate_balances(self.current_year)

        self.assertEqual(row_of(balances, self.child_eldest)["adjustment"], Decimal("-20.00"))
        self.assertEqual(row_of(balances, self.child_youngest)["adjustment"], Decimal("0"))
        # The household total moves by exactly the adjustment, no more.
        self.assertEqual(due_of(balances, self.child_youngest), Decimal("60.00"))

    def test_adjustments_are_summed(self):
        self._adjust("-20.00", reason="Geste commercial")
        self._adjust("-5.50", reason="Correction")

        balances = calculate_balances(self.current_year)

        self.assertEqual(due_of(balances, self.child_eldest), Decimal("54.50"))

    def test_adjustment_is_added_after_the_late_penalty(self):
        """A correction applies to the total, it is not itself surcharged."""
        self.config.late_deadline = timezone.now().date() - timedelta(days=1)
        self.config.save(update_fields=["late_deadline"])
        self._adjust("-20.00")

        balances = calculate_balances(self.current_year)

        # 80.00 + 10% = 88.00, then -20.00.
        self.assertEqual(due_of(balances, self.child_eldest), Decimal("68.00"))

    def test_only_the_school_year_adjustments_apply(self):
        next_name = SchoolYear.objects.order_by("-name").first().name + 1
        other_year = SchoolYear.objects.create(
            name=next_name,
            start_date=date(next_name, 8, 1),
            end_date=date(next_name + 1, 7, 31),
            range=f"{next_name}-{next_name + 1}",
        )
        self._adjust("-20.00")
        self._adjust("-99.00", year=other_year)

        balances = calculate_balances(self.current_year)

        self.assertEqual(due_of(balances, self.child_eldest), Decimal("60.00"))

    def test_adjustment_reaches_the_reminder_amount(self):
        self._adjust("-20.00")

        adults = get_adults_with_balance(self.current_year)
        alice = next(a for a in adults if a["person"] == self.parent1)

        # Alice's children: Charlie 60.00 (80 − 20), Diana 60.00, and Eve
        # 80.00 in her own household at the other address.
        self.assertEqual(alice["balance"], Decimal("200.00"))

    def test_a_write_off_can_clear_the_household(self):
        """A full waiver nets to zero instead of leaving the sibling chased."""
        self._adjust("-140.00")

        balances = calculate_balances(self.current_year)
        household_total = (
            row_of(balances, self.child_eldest)["balance"]
            + row_of(balances, self.child_youngest)["balance"]
        )
        self.assertEqual(household_total, Decimal("0"))

        # Alice is still reminded about Eve, but nothing for the waived family.
        alice = next(
            a
            for a in get_adults_with_balance(self.current_year)
            if a["person"] == self.parent1
        )
        self.assertEqual(alice["balance"], Decimal("80.00"))

    def test_adjustment_on_a_household_outside_the_address_group_still_applies(self):
        """The household is what carries the line, not the address."""
        household = Household.objects.create(name="Charlie seul")
        HouseholdMember.objects.update_or_create(
            person=self.child_eldest, defaults={"household": household}
        )
        HouseholdAdjustment.objects.create(
            household=household,
            school_year=self.current_year,
            amount=Decimal("-10.00"),
            reason="Geste",
        )

        balances = calculate_balances(self.current_year)

        self.assertEqual(due_of(balances, self.child_eldest), Decimal("70.00"))

    def test_adjustment_with_nobody_enrolled_reaches_no_balance(self):
        """A household with no enrolled member has no balance to carry it."""
        household = Household.objects.create(name="Anciens")
        HouseholdMember.objects.create(household=household, person=self.parent2)
        HouseholdAdjustment.objects.create(
            household=household,
            school_year=self.current_year,
            amount=Decimal("-30.00"),
            reason="Remboursement",
        )

        balances = calculate_balances(self.current_year)
        self.assertNotIn(self.parent2.pk, [b["person_id"] for b in balances])
        # And every balance is exactly what it was before the line existed.
        self.assertEqual(due_of(balances, self.child_eldest), Decimal("80.00"))
        self.assertEqual(due_of(balances, self.child_youngest), Decimal("60.00"))

    def test_summary_separates_fees_from_the_adjustment(self):
        self._adjust("-20.00")

        summary = next(
            s
            for s in household_summaries(self.current_year)
            if s["household"] and s["household"].pk == self.household.pk
        )

        self.assertEqual(summary["base_due"], Decimal("140.00"))
        self.assertEqual(summary["adjustment"], Decimal("-20.00"))
        self.assertEqual(summary["due"], Decimal("120.00"))
        self.assertEqual(summary["balance"], Decimal("120.00"))


class HouseholdStaffTest(FinanceTestBase):
    """A trésorier who is also Django staff.

    The member screens are ``is_staff``-gated while the household screens are
    treasurer-or-staff, so only a user holding both can drive the feature end to
    end — which is who these tests are about.
    """

    def setUp(self):
        super().setUp()
        self._login_tresorier()
        self.tresorier_account.is_staff = True
        self.tresorier_account.save(update_fields=["is_staff"])


class HouseholdViewTest(HouseholdStaffTest):
    """The treasurer's household screens."""

    def setUp(self):
        super().setUp()
        self.household = Household.objects.create(name="Famille Dupont")
        HouseholdMember.objects.create(household=self.household, person=self.child_eldest)

    def test_list_is_reachable(self):
        response = self.client.get(reverse("finance:households"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Famille Dupont")

    def test_plain_parent_cannot_reach_it(self):
        self.client.logout()
        self.client.login(email="alice@test.com", password="testpass")
        self.assertEqual(
            self.client.get(reverse("finance:households")).status_code, 404
        )

    def test_create_a_household(self):
        response = self.client.post(reverse("finance:households"), {"name": "Martin"})

        household = Household.objects.get(name="Martin")
        self.assertRedirects(
            response, reverse("finance:household_detail", kwargs={"pk": household.pk})
        )

    def test_detail_shows_the_rank_the_member_is_billed_at(self):
        """Asserted on the context: the rendered rank label is translated."""
        response = self.client.get(
            reverse("finance:household_detail", kwargs={"pk": self.household.pk})
        )
        rows = response.context["member_rows"]
        self.assertEqual([r["rank"] for r in rows], [1])
        self.assertEqual(rows[0]["person"], self.child_eldest)

    def test_list_keeps_a_household_nobody_enrolled_in(self):
        """It still has to be listed, or it could never be cleaned up."""
        empty = Household.objects.create(name="Anciens")
        HouseholdMember.objects.create(household=empty, person=self.parent2)

        response = self.client.get(reverse("finance:households"))

        self.assertContains(response, "Anciens")

    def test_detail_warns_when_an_adjustment_cannot_be_applied(self):
        household = Household.objects.create(name="Anciens")
        HouseholdMember.objects.create(household=household, person=self.parent2)
        HouseholdAdjustment.objects.create(
            household=household,
            school_year=self.current_year,
            amount=Decimal("-30.00"),
            reason="Remboursement",
        )

        response = self.client.get(
            reverse("finance:household_detail", kwargs={"pk": household.pk})
        )

        self.assertEqual(response.context["unapplied"], Decimal("-30.00"))
        self.assertEqual(response.context["member_rows"][0]["rank"], None)

    def test_detail_does_not_warn_when_the_adjustment_is_applied(self):
        HouseholdAdjustment.objects.create(
            household=self.household,
            school_year=self.current_year,
            amount=Decimal("-30.00"),
            reason="Remboursement",
        )

        response = self.client.get(
            reverse("finance:household_detail", kwargs={"pk": self.household.pk})
        )

        self.assertIsNone(response.context["unapplied"])

    def test_adding_a_member_reassigns_them(self):
        self.client.post(
            reverse("finance:household_detail", kwargs={"pk": self.household.pk}),
            {"action": "add_member", "person": self.child_other.pk},
        )
        self.assertEqual(self.child_other.households.get(), self.household)

    def test_assigning_from_the_member_page_clears_the_override(self):
        response = self.client.post(
            reverse("finance:assign_household"),
            {
                "person_id": self.child_eldest.pk,
                "household": "",
                "next": reverse(
                    "members:admin_update", kwargs={"pk": self.child_eldest.pk}
                ),
            },
        )

        self.assertFalse(HouseholdMember.objects.filter(person=self.child_eldest).exists())
        self.assertRedirects(
            response,
            reverse("members:admin_update", kwargs={"pk": self.child_eldest.pk}),
        )

    def test_assigning_refuses_an_off_site_redirect(self):
        response = self.client.post(
            reverse("finance:assign_household"),
            {
                "person_id": self.child_youngest.pk,
                "household": self.household.pk,
                "next": "https://evil.example/",
            },
        )
        self.assertRedirects(response, reverse("members:admin_list"))

    def test_added_adjustment_records_its_author(self):
        self.client.post(
            reverse("finance:household_detail", kwargs={"pk": self.household.pk}),
            {
                "action": "add_adjustment",
                "school_year": self.current_year.pk,
                "amount": "-25.00",
                "reason": "Geste commercial",
            },
        )

        adjustment = HouseholdAdjustment.objects.get()
        self.assertEqual(adjustment.household, self.household)
        self.assertEqual(adjustment.amount, Decimal("-25.00"))
        self.assertEqual(adjustment.reason, "Geste commercial")
        self.assertEqual(adjustment.author, self.tresorier)

    def test_zero_adjustment_is_refused(self):
        self.client.post(
            reverse("finance:household_detail", kwargs={"pk": self.household.pk}),
            {
                "action": "add_adjustment",
                "school_year": self.current_year.pk,
                "amount": "0.00",
                "reason": "Rien",
            },
        )
        self.assertFalse(HouseholdAdjustment.objects.exists())

    def test_adjustment_can_be_deleted(self):
        adjustment = HouseholdAdjustment.objects.create(
            household=self.household,
            school_year=self.current_year,
            amount=Decimal("-25.00"),
            reason="Erreur",
        )

        self.client.post(
            reverse(
                "finance:adjustment_delete",
                kwargs={
                    "pk": self.household.pk,
                    "adjustment_pk": adjustment.pk,
                },
            )
        )
        self.assertFalse(HouseholdAdjustment.objects.exists())

    def test_deleting_a_household_frees_its_members(self):
        self.client.post(
            reverse("finance:household_delete", kwargs={"pk": self.household.pk})
        )
        self.assertFalse(Household.objects.filter(pk=self.household.pk).exists())
        self.assertFalse(HouseholdMember.objects.exists())
        # And the member is billed by address again.
        self.assertEqual(
            due_of(calculate_balances(self.current_year), self.child_eldest),
            Decimal("80.00"),
        )

    def test_billing_overview_shows_the_household_and_its_adjustment(self):
        HouseholdAdjustment.objects.create(
            household=self.household,
            school_year=self.current_year,
            amount=Decimal("-20.00"),
            reason="Geste commercial",
        )

        response = self.client.get(reverse("finance:billing"))

        # Charlie alone in the household: 80.00 of fees, 20.00 written off.
        summary = next(
            s for s in response.context["household_rows"] if s["household"] == self.household
        )
        self.assertEqual(summary["base_due"], Decimal("80.00"))
        self.assertEqual(summary["adjustment"], Decimal("-20.00"))
        self.assertEqual(summary["due"], Decimal("60.00"))

        self.assertContains(response, "Famille Dupont")

    def test_payment_history_lists_the_household_adjustments(self):
        HouseholdAdjustment.objects.create(
            household=self.household,
            school_year=self.current_year,
            amount=Decimal("-20.00"),
            reason="Geste commercial",
            author=self.tresorier,
        )

        response = self.client.get(
            reverse(
                "finance:payment_history", kwargs={"person_id": self.child_eldest.pk}
            )
        )

        self.assertContains(response, "Geste commercial")
        self.assertContains(response, "Famille Dupont")


class HouseholdMemberPageTest(HouseholdStaffTest):
    """What the member screens show about the household."""

    def setUp(self):
        super().setUp()
        self.list_url = reverse("members:admin_list")
        self.edit_url = reverse("members:admin_update", kwargs={"pk": self.child_eldest.pk})

    def test_member_list_falls_back_to_the_address(self):
        response = self.client.get(self.list_url)
        self.assertContains(response, "Rue des Fleurs 10, 1300 Limal")

    def test_member_list_prefers_the_explicit_household(self):
        household = Household.objects.create(name="Famille recomposée")
        HouseholdMember.objects.create(household=household, person=self.child_eldest)

        response = self.client.get(self.list_url)
        self.assertContains(response, "Famille recomposée")

    def test_member_page_shows_the_inferred_household_members(self):
        response = self.client.get(self.edit_url)
        # Diana shares the address, so she is billed with Charlie today.
        self.assertContains(response, "Diana Dupont")

    def test_member_page_shows_the_chosen_household(self):
        household = Household.objects.create(name="Famille recomposée")
        HouseholdMember.objects.create(household=household, person=self.child_eldest)

        response = self.client.get(self.edit_url)
        self.assertContains(response, "Famille recomposée")

    def test_member_page_assigns_a_household(self):
        household = Household.objects.create(name="Famille recomposée")

        response = self.client.post(
            reverse("finance:assign_household"),
            {
                "person_id": self.child_eldest.pk,
                "household": household.pk,
                "next": self.edit_url,
            },
        )

        self.assertRedirects(response, self.edit_url)
        self.assertEqual(self.child_eldest.households.get(), household)

    def test_the_household_panel_is_a_form_of_its_own(self):
        """Saving the member form must not be able to wipe the household.

        The panel is a second <form> on the page posting to its own endpoint,
        so the member form — which rewrites Person, roles and enrolments — is
        not in the path that assigns households at all.
        """
        response = self.client.get(self.edit_url)
        assign_url = reverse("finance:assign_household")
        self.assertContains(response, f'action="{assign_url}"')


class HouseholdModuleFlagTest(TroopSettingsTestCase, FinanceTestBase):
    """The household feature follows `fees_enabled`, like the rest of the module.

    ``TroopSettingsTestCase`` comes first in the MRO so its ``clear_cache``
    runs and chains into ``FinanceTestBase.setUp`` — which does not call
    ``super().setUp()``, exactly as in ``test_finance_views``.
    """

    def setUp(self):
        super().setUp()
        self._login_tresorier()
        self.tresorier_account.is_staff = True
        self.tresorier_account.save(update_fields=["is_staff"])
        self.household = Household.objects.create(name="Famille Dupont")

    def _disable_fees(self):
        troop = TroopSettings.get_settings()
        troop.fees_enabled = False
        troop.save(update_fields=["fees_enabled"])

    def test_households_page_404s_when_fees_are_off(self):
        self._disable_fees()
        self.assertEqual(self.client.get(reverse("finance:households")).status_code, 404)

    def test_assigning_404s_when_fees_are_off(self):
        self._disable_fees()
        response = self.client.post(
            reverse("finance:assign_household"),
            {"person_id": self.child_eldest.pk, "household": self.household.pk},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(HouseholdMember.objects.exists())

    def test_member_page_hides_the_panel_when_fees_are_off(self):
        self._disable_fees()
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": self.child_eldest.pk})
        )
        self.assertFalse(response.context["household_enabled"])
        self.assertNotContains(response, reverse("finance:assign_household"))

    def test_member_page_shows_the_panel_when_fees_are_on(self):
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": self.child_eldest.pk})
        )
        self.assertTrue(response.context["household_enabled"])
        self.assertContains(response, reverse("finance:assign_household"))

    def test_member_list_has_no_household_column_when_fees_are_off(self):
        self._disable_fees()
        response = self.client.get(reverse("members:admin_list"))
        self.assertNotIn("household", dict(response.context["fields_map"]))

    def test_member_list_has_the_household_column_when_fees_are_on(self):
        response = self.client.get(reverse("members:admin_list"))
        self.assertIn("household", dict(response.context["fields_map"]))
