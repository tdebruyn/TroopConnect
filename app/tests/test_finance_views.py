"""View-level tests for the finance app.

``test_finance.py`` covers the pricing/balance model layer; this module covers
the views the trésorier actually drives — recording a payment, reading a
household's payment history, and firing the bulk reminder run. The reminder
tests pin the outcome-counting rule: the success message must report emails
that were actually queued, not attempts.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from post_office import mail as post_office_mail
from post_office.models import Email

from finance.models import Payment, get_adults_with_balance
from finance.views import _is_tresorier
from members.models import Account, Person, Role, SchoolYear
from tests.mail import MailTestCase
from tests.test_finance import FinanceTestBase


class FinanceMailTestBase(MailTestCase, FinanceTestBase):
    """FinanceTestBase plus the dummy backend, for views that send mail.

    MailTestCase must come first in the MRO: ``FinanceTestBase.setUp`` does not
    call ``super().setUp()``, so putting it first would silently skip
    MailTestCase's setUp and leave the real Celery broker in the path — every
    ``mail.send`` would then raise on the ``email_queued`` signal *after* the
    Email row was already created, making sends look like they worked.
    """


class RecordPaymentTest(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self._login_tresorier()
        self.url = reverse("finance:record_payment")

    def _post(self, **overrides):
        data = {
            "person_id": str(self.child_eldest.pk),
            "amount": "40.00",
            "date": "2026-09-01",
            "note": "espèces",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_records_a_payment_and_redirects(self):
        response = self._post()
        self.assertRedirects(response, reverse("finance:billing"))

        payment = Payment.objects.get()
        self.assertEqual(payment.person, self.child_eldest)
        self.assertEqual(payment.amount, Decimal("40.00"))
        self.assertEqual(payment.date.isoformat(), "2026-09-01")
        self.assertEqual(payment.note, "espèces")
        self.assertEqual(payment.school_year, self.current_year)

    def test_records_who_took_the_payment(self):
        self._post()
        self.assertEqual(Payment.objects.get().recorded_by, self.tresorier)

    def test_htmx_post_returns_hx_redirect(self):
        response = self.client.post(
            self.url,
            {
                "person_id": str(self.child_eldest.pk),
                "amount": "40.00",
                "date": "2026-09-01",
                "note": "",
            },
            headers={"hx-request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Redirect"], reverse("finance:billing"))
        self.assertTrue(Payment.objects.exists())

    def test_unknown_person_is_rejected(self):
        response = self._post(person_id="00000000-0000-0000-0000-000000000001")
        self.assertRedirects(response, reverse("finance:billing"))
        self.assertFalse(Payment.objects.exists())

    def test_unknown_person_via_htmx_returns_empty(self):
        response = self.client.post(
            self.url,
            {
                "person_id": "00000000-0000-0000-0000-000000000001",
                "amount": "40.00",
                "date": "2026-09-01",
                "note": "",
            },
            headers={"hx-request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertFalse(Payment.objects.exists())

    def test_invalid_amount_redisplays_form_without_saving(self):
        response = self._post(amount="0.00")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Payment.objects.exists())

    def test_get_prefills_person_id_from_query_string(self):
        response = self.client.get(f"{self.url}?person_id={self.child_eldest.pk}")
        self.assertEqual(
            response.context["form"].initial["person_id"], str(self.child_eldest.pk)
        )

    def test_get_prefills_todays_date(self):
        response = self.client.get(self.url)
        self.assertEqual(
            response.context["form"].initial["date"], timezone.now().date()
        )

    def test_htmx_get_renders_the_modal_partial(self):
        response = self.client.get(self.url, headers={"hx-request": "true"})
        self.assertTemplateUsed(response, "finance/record_payment_modal.html")

    def test_plain_parent_cannot_record_a_payment(self):
        self.client.logout()
        self.client.login(email="alice@test.com", password="testpass")
        response = self._post()
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Payment.objects.exists())


class PaymentHistoryTest(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self._login_tresorier()
        self.url = reverse("finance:payment_history", args=[self.child_eldest.pk])

    def test_lists_this_years_payments_for_the_person(self):
        Payment.objects.create(
            person=self.child_eldest,
            school_year=self.current_year,
            amount=Decimal("40.00"),
            date=timezone.now().date(),
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["payments"]), list(Payment.objects.all()))

    def test_other_years_are_excluded(self):
        other_year = SchoolYear.objects.create(
            name=self.current_year.name + 5,
            start_date=self.current_year.start_date.replace(year=self.current_year.start_date.year + 5),
            end_date=self.current_year.end_date.replace(year=self.current_year.end_date.year + 5),
            range="other",
        )
        Payment.objects.create(
            person=self.child_eldest,
            school_year=other_year,
            amount=Decimal("40.00"),
            date=timezone.now().date(),
        )
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["payments"]), 0)

    def test_unknown_person_returns_empty_response(self):
        response = self.client.get(
            reverse(
                "finance:payment_history",
                args=["00000000-0000-0000-0000-000000000001"],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_plain_parent_gets_404(self):
        self.client.logout()
        self.client.login(email="alice@test.com", password="testpass")
        self.assertEqual(self.client.get(self.url).status_code, 404)


class SendRemindersTest(FinanceMailTestBase):
    def setUp(self):
        super().setUp()
        self._login_tresorier()
        self.url = reverse("finance:reminders")

    def _post(self, **overrides):
        data = {
            "subject": "Rappel de cotisation",
            "body": "Bonjour {prenom}, votre solde est de {solde}€.",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_tresorier_can_open_the_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("adults", response.context)

    def test_plain_parent_gets_404(self):
        self.client.logout()
        self.client.login(email="alice@test.com", password="testpass")
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_sends_one_email_per_adult_with_balance(self):
        adults = get_adults_with_balance(self.current_year)
        self.assertTrue(adults)

        response = self._post()

        self.assertRedirects(response, reverse("finance:billing"))
        self.assertEqual(Email.objects.count(), len(adults))

    def test_placeholders_are_substituted_per_recipient(self):
        adults = get_adults_with_balance(self.current_year)
        self._post()

        emails = list(Email.objects.all())
        for adult in adults:
            matching = [e for e in emails if adult["email"] in e.to]
            self.assertEqual(
                len(matching), 1, f"expected one email for {adult['email']}"
            )
            body = matching[0].message
            self.assertIn(adult["person"].first_name, body)
            self.assertIn(str(adult["balance"]), body)
            self.assertNotIn("{prenom}", body)
            self.assertNotIn("{solde}", body)

    def test_failed_send_is_reported_and_not_counted_as_sent(self):
        """The trésorier must not be told a household was chased if it wasn't."""
        adults = get_adults_with_balance(self.current_year)
        self.assertTrue(adults)

        with patch("finance.views.mail.send", side_effect=RuntimeError("smtp down")):
            response = self._post()

        self.assertRedirects(response, reverse("finance:billing"))
        self.assertEqual(Email.objects.count(), 0)

        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        # Expected wording is resolved here rather than hardcoded so the
        # assertion stays valid under the French default locale.
        self.assertIn(
            _("Reminders sent to %(count)s adult(s).") % {"count": 0}, msgs
        )
        self.assertIn(
            _("%(count)s reminder(s) could not be sent.")
            % {"count": len(adults)},
            msgs,
        )

    def test_partial_failure_counts_only_the_successes(self):
        adults = get_adults_with_balance(self.current_year)
        self.assertGreater(len(adults), 1, "fixture needs 2+ adults")

        calls = {"n": 0}
        # Grab the real function before patching: finance.views.mail *is* the
        # post_office.mail module, so patching its `send` rebinds it globally
        # and calling post_office_mail.send here would re-enter the mock.
        real_send = post_office_mail.send

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("first one fails")
            return real_send(*args, **kwargs)

        with patch("finance.views.mail.send", side_effect=flaky):
            response = self._post()

        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn(
            _("Reminders sent to %(count)s adult(s).") % {"count": len(adults) - 1},
            msgs,
        )

    def test_invalid_form_does_not_send(self):
        response = self._post(subject="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Email.objects.exists())


class MissingSchoolYearTest(TestCase):
    """Views that need a current school year must redirect instead of crashing."""

    def setUp(self):
        self.tresorier = Person.objects.create(
            first_name="Tres",
            last_name="Or",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        self.tresorier.roles.add(Role.objects.get(short="t"))
        self.account = Account.objects.create_user(
            email="tres@test.com", password="testpass", person=self.tresorier
        )
        self.client.force_login(self.account)
        SchoolYear.objects.all().delete()

    def test_billing_overview_redirects(self):
        response = self.client.get(reverse("finance:billing"))
        self.assertRedirects(response, reverse("homepage"))

    def test_price_grid_redirects(self):
        response = self.client.get(reverse("finance:prices"))
        self.assertRedirects(response, reverse("homepage"))

    def test_record_payment_redirects(self):
        response = self.client.get(reverse("finance:record_payment"))
        self.assertRedirects(response, reverse("homepage"))

    def test_record_payment_htmx_returns_empty(self):
        response = self.client.get(
            reverse("finance:record_payment"), headers={"hx-request": "true"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")


class PriceGridYearSelectionTest(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self._login_tresorier()
        self.url = reverse("finance:prices")

    def test_unknown_year_falls_back_to_the_current_year(self):
        response = self.client.get(f"{self.url}?year=999999")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_year"], self.current_year)

    def test_explicit_year_is_honoured(self):
        older = SchoolYear.objects.create(
            name=self.current_year.name - 1,
            start_date=self.current_year.start_date.replace(
                year=self.current_year.start_date.year - 1
            ),
            end_date=self.current_year.end_date.replace(
                year=self.current_year.end_date.year - 1
            ),
            range="older",
        )
        response = self.client.get(f"{self.url}?year={older.pk}")
        self.assertEqual(response.context["selected_year"], older)


class TresorierHelperTest(TestCase):
    def test_account_without_a_person_is_not_a_tresorier(self):
        """Defensive guard — an unsaved Account has no Person yet.

        ``Account.save()`` creates a Person whenever ``person_id`` is empty, so
        a persisted Account can never reach this branch; it exists only to keep
        ``_is_tresorier`` safe for callers holding an unsaved instance.
        """
        self.assertFalse(_is_tresorier(Account(email="orphan@test.com")))
