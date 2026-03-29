from decimal import Decimal
from datetime import timedelta

from django.test import TestCase, Client
from django.utils import timezone

from members.models import (
    Account, Person, Role, SchoolYear, Section, Branch, Enrollment, ParentChild,
)
from post_office.models import EmailTemplate
from finance.models import CotisationConfig, Payment, calculate_balances, get_adults_with_balance


class FinanceTestBase(TestCase):
    """Shared setup for finance tests."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )

    def setUp(self):
        self.current_year = SchoolYear.current()
        self.role_parent = Role.objects.get(short="p")
        self.role_anime = Role.objects.get(short="e")
        self.role_animateur = Role.objects.get(short="a")

        # Create a branch and section
        self.branch = Branch.objects.create(name="Baladins", min_age_dec_31=6, max_age_dec_31=9)
        self.section = Section.objects.create(name="Louveteaux", branch=self.branch)

        # Create two parents in same household (same address)
        self.parent1 = Person.objects.create(
            first_name="Alice", last_name="Dupont",
            primary_role=self.role_parent, status="a",
            address="Rue des Fleurs 10, 1300 Limal",
        )
        self.parent1_account = Account.objects.create_user(
            email="alice@test.com", password="testpass", person=self.parent1,
        )

        self.parent2 = Person.objects.create(
            first_name="Bob", last_name="Dupont",
            primary_role=self.role_parent, status="a",
            address="Rue des Fleurs 10, 1300 Limal",
        )
        self.parent2_account = Account.objects.create_user(
            email="bob@test.com", password="testpass", person=self.parent2,
        )

        # Create two children in same household (same address), different ages
        self.child_eldest = Person.objects.create(
            first_name="Charlie", last_name="Dupont",
            primary_role=self.role_anime, status="a",
            birthday=timezone.now().date() - timedelta(days=365 * 8),
            address="Rue des Fleurs 10, 1300 Limal",
        )
        self.child_youngest = Person.objects.create(
            first_name="Diana", last_name="Dupont",
            primary_role=self.role_anime, status="a",
            birthday=timezone.now().date() - timedelta(days=365 * 6),
            address="Rue des Fleurs 10, 1300 Limal",
        )

        # A child in a different household
        self.child_other = Person.objects.create(
            first_name="Eve", last_name="Martin",
            primary_role=self.role_anime, status="a",
            birthday=timezone.now().date() - timedelta(days=365 * 7),
            address="Avenue Louise 50, 1050 Bruxelles",
        )

        # An animateur
        self.animateur = Person.objects.create(
            first_name="Frank", last_name="Leader",
            primary_role=self.role_animateur, status="a",
        )
        self.anim_account = Account.objects.create_user(
            email="frank@test.com", password="testpass", person=self.animateur,
        )

        # Link parents to children
        ParentChild.objects.create(parent=self.parent1, child=self.child_eldest, primary_contact=True)
        ParentChild.objects.create(parent=self.parent1, child=self.child_youngest)
        ParentChild.objects.create(parent=self.parent2, child=self.child_eldest)
        ParentChild.objects.create(parent=self.parent1, child=self.child_other)

        # Enroll children and animateur
        Enrollment.objects.create(user=self.child_eldest, section=self.section, school_year=self.current_year)
        Enrollment.objects.create(user=self.child_youngest, section=self.section, school_year=self.current_year)
        Enrollment.objects.create(user=self.child_other, section=self.section, school_year=self.current_year)
        Enrollment.objects.create(user=self.animateur, section=self.section, school_year=self.current_year)

        # Create cotisation config
        self.config = CotisationConfig.objects.create(
            school_year=self.current_year,
            full_fee=Decimal("80.00"),
            sibling_discount=Decimal("20.00"),
            animateur_fee=Decimal("30.00"),
            late_penalty_percent=Decimal("10.00"),
        )

    def _login_tresorier(self):
        """Create and login a Trésorier user."""
        tresorier_role = Role.objects.get(short="t")
        self.tresorier = Person.objects.create(
            first_name="Tres", last_name="Or",
            primary_role=self.role_parent, status="a",
        )
        self.tresorier.roles.add(tresorier_role)
        self.tresorier_account = Account.objects.create_user(
            email="tres@test.com", password="testpass", person=self.tresorier,
        )
        self.client.login(email="tres@test.com", password="testpass")


class HouseholdGroupingTest(FinanceTestBase):
    """Tests for household grouping by address."""

    def test_children_grouped_by_address(self):
        balances = calculate_balances(self.current_year)
        child_balances = [
            b for b in balances
            if b["person_id"] in [self.child_eldest.pk, self.child_youngest.pk, self.child_other.pk]
        ]
        # Charlie + Diana in same household = 2 children
        # Eve alone = 1 child
        self.assertEqual(len(child_balances), 3)

    def test_eldest_gets_full_fee(self):
        balances = calculate_balances(self.current_year)
        eldest_balance = next(
            b for b in balances if b["person_id"] == self.child_eldest.pk
        )
        self.assertEqual(eldest_balance["amount_due"], Decimal("80.00"))

    def test_sibling_gets_discount(self):
        balances = calculate_balances(self.current_year)
        youngest_balance = next(
            b for b in balances if b["person_id"] == self.child_youngest.pk
        )
        self.assertEqual(youngest_balance["amount_due"], Decimal("60.00"))

    def test_lone_child_gets_full_fee(self):
        balances = calculate_balances(self.current_year)
        other_balance = next(
            b for b in balances if b["person_id"] == self.child_other.pk
        )
        self.assertEqual(other_balance["amount_due"], Decimal("80.00"))


class AnimateurFlatRateTest(FinanceTestBase):
    """Tests for animateur flat rate."""

    def test_animateur_gets_flat_rate(self):
        balances = calculate_balances(self.current_year)
        anim_balance = next(
            b for b in balances if b["person_id"] == self.animateur.pk
        )
        self.assertEqual(anim_balance["amount_due"], Decimal("30.00"))

    def test_animateur_no_sibling_discount(self):
        """Animateur fee is independent of sibling discount logic."""
        balances = calculate_balances(self.current_year)
        anim_balance = next(
            b for b in balances if b["person_id"] == self.animateur.pk
        )
        self.assertEqual(anim_balance["amount_due"], Decimal("30.00"))
        self.assertNotEqual(anim_balance["amount_due"], self.config.full_fee - self.config.sibling_discount)


class LatePenaltyTest(FinanceTestBase):
    """Tests for late payment penalty."""

    def test_no_penalty_before_deadline(self):
        self.config.late_deadline = timezone.now().date() + timedelta(days=30)
        self.config.save()
        balances = calculate_balances(self.current_year)
        child_balance = next(
            b for b in balances if b["person_id"] == self.child_eldest.pk
        )
        self.assertEqual(child_balance["amount_due"], Decimal("80.00"))
        self.assertFalse(child_balance["is_late"])

    def test_penalty_after_deadline(self):
        self.config.late_deadline = timezone.now().date() - timedelta(days=1)
        self.config.save()
        balances = calculate_balances(self.current_year)
        child_balance = next(
            b for b in balances if b["person_id"] == self.child_eldest.pk
        )
        # 80 * 1.10 = 88.00
        self.assertEqual(child_balance["amount_due"], Decimal("88.00"))
        self.assertTrue(child_balance["is_late"])

    def test_no_penalty_without_deadline(self):
        self.config.late_deadline = None
        self.config.save()
        balances = calculate_balances(self.current_year)
        child_balance = next(
            b for b in balances if b["person_id"] == self.child_eldest.pk
        )
        self.assertFalse(child_balance["is_late"])


class PaymentTest(FinanceTestBase):
    """Tests for payment recording."""

    def test_payment_reduces_balance(self):
        Payment.objects.create(
            person=self.child_eldest,
            school_year=self.current_year,
            amount=Decimal("40.00"),
        )
        balances = calculate_balances(self.current_year)
        child_balance = next(
            b for b in balances if b["person_id"] == self.child_eldest.pk
        )
        self.assertEqual(child_balance["amount_paid"], Decimal("40.00"))
        self.assertEqual(child_balance["balance"], Decimal("40.00"))

    def test_full_payment_zeroes_balance(self):
        Payment.objects.create(
            person=self.child_eldest,
            school_year=self.current_year,
            amount=Decimal("80.00"),
        )
        balances = calculate_balances(self.current_year)
        child_balance = next(
            b for b in balances if b["person_id"] == self.child_eldest.pk
        )
        self.assertEqual(child_balance["balance"], Decimal("0.00"))

    def test_multiple_payments_summed(self):
        Payment.objects.create(
            person=self.child_eldest,
            school_year=self.current_year,
            amount=Decimal("30.00"),
        )
        Payment.objects.create(
            person=self.child_eldest,
            school_year=self.current_year,
            amount=Decimal("20.00"),
        )
        balances = calculate_balances(self.current_year)
        child_balance = next(
            b for b in balances if b["person_id"] == self.child_eldest.pk
        )
        self.assertEqual(child_balance["amount_paid"], Decimal("50.00"))


class BulkReminderTest(FinanceTestBase):
    """Tests for bulk reminder emails."""

    def test_adults_with_balance_returns_parents(self):
        adults = get_adults_with_balance(self.current_year)
        parent_emails = {a["email"] for a in adults}
        # parent1 is linked to all 3 children, parent2 to child_eldest
        self.assertIn("alice@test.com", parent_emails)

    def test_fully_paid_excluded_from_reminders(self):
        Payment.objects.create(
            person=self.child_eldest,
            school_year=self.current_year,
            amount=Decimal("80.00"),
        )
        Payment.objects.create(
            person=self.child_youngest,
            school_year=self.current_year,
            amount=Decimal("60.00"),
        )
        Payment.objects.create(
            person=self.child_other,
            school_year=self.current_year,
            amount=Decimal("80.00"),
        )
        adults = get_adults_with_balance(self.current_year)
        self.assertEqual(len(adults), 0)


class FinanceAppImportTest(TestCase):
    """Tests that the finance app loads correctly."""

    def test_finance_models_import(self):
        from finance.models import CotisationConfig, Payment
        self.assertTrue(CotisationConfig)
        self.assertTrue(Payment)

    def test_finance_forms_instantiate(self):
        from finance.forms import PaymentForm, ReminderForm
        form1 = PaymentForm()
        form2 = ReminderForm()
        self.assertIn("amount", form1.fields)
        self.assertIn("subject", form2.fields)
        self.assertIn("body", form2.fields)

    def test_finance_urls_resolve(self):
        from django.urls import reverse
        self.assertEqual(reverse("finance:billing"), "/finance/")
        self.assertEqual(reverse("finance:record_payment"), "/finance/payment/")
        self.assertEqual(reverse("finance:reminders"), "/finance/reminders/")


class BillingViewAccessTest(FinanceTestBase):
    """Tests for Trésorier access to billing views."""

    def test_tresorier_can_access_billing(self):
        self._login_tresorier()
        response = self.client.get("/finance/")
        self.assertEqual(response.status_code, 200)

    def test_staff_can_access_billing(self):
        self.parent1_account.is_staff = True
        self.parent1_account.save()
        self.client.login(email="alice@test.com", password="testpass")
        response = self.client.get("/finance/")
        self.assertEqual(response.status_code, 200)

    def test_plain_parent_cannot_access_billing(self):
        self.client.login(email="alice@test.com", password="testpass")
        response = self.client.get("/finance/")
        self.assertEqual(response.status_code, 404)

    def test_tresorier_can_access_payment_form(self):
        self._login_tresorier()
        response = self.client.get("/finance/payment/")
        self.assertEqual(response.status_code, 200)

    def test_tresorier_can_access_reminders(self):
        self._login_tresorier()
        response = self.client.get("/finance/reminders/")
        self.assertEqual(response.status_code, 200)

    def test_plain_parent_cannot_record_payment(self):
        self.client.login(email="alice@test.com", password="testpass")
        response = self.client.get("/finance/payment/")
        self.assertEqual(response.status_code, 404)

    def test_tresorier_sees_cotisations_nav_link(self):
        self._login_tresorier()
        response = self.client.get("/")
        self.assertContains(response, "Cotisations")

    def test_plain_parent_does_not_see_cotisations_nav_link(self):
        self.client.login(email="alice@test.com", password="testpass")
        response = self.client.get("/")
        self.assertNotContains(response, "Cotisations")
