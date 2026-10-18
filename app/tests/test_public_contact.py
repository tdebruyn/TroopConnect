"""The contact form on the public site.

A visitor has no login, so the form carries ALTCHA's proof-of-work challenge
and never names the person behind the role. These tests pin the challenge, the
footer split between visitors and signed-in readers, and the email that leaves
with the visitor's address as its Reply-To.
"""

import base64
import json
from unittest import mock

from altcha import solve_challenge_v1
from django.urls import reverse
from post_office.models import Email

from members.models import Account, Person, PersonRole, Role, TroopSettings

from .mail import MailTestCase

VERIFY = "members.public_views.verify_solution_v1"


class PublicContactTestBase(MailTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lead = Person.objects.create(
            first_name="Ada",
            last_name="Lead",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        PersonRole.objects.create(
            person=cls.lead, role=Role.objects.get(short="ar")
        )
        Account.objects.create_user(
            email="lead@test.be", password="testpass", person=cls.lead
        )

        cls.staff = Person.objects.create(
            first_name="Sam",
            last_name="Staff",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        Account.objects.create_user(
            email="staff@test.be",
            password="testpass",
            person=cls.staff,
            is_staff=True,
        )

        cls.parent = Person.objects.create(
            first_name="Paul",
            last_name="Parent",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        cls.parent_account = Account.objects.create_user(
            email="parent@test.be", password="testpass", person=cls.parent
        )

    def setUp(self):
        super().setUp()
        TroopSettings.clear_cache()
        self.addCleanup(TroopSettings.clear_cache)
        settings_row = TroopSettings.get_settings()
        settings_row.contact_email = "unit@test.be"
        settings_row.contact_phone = "010 00 00 00"
        settings_row.save()

    def verification(self, verified=True):
        return mock.patch(
            VERIFY, return_value=(verified, None if verified else "invalid")
        )

    def credentials(self, **overrides):
        data = {
            "name": "Visitor",
            "email": "visitor@test.be",
            "message": "We would like to register our child.",
            "altcha": "test-payload",
        }
        data.update(overrides)
        return data

    def post(self, **overrides):
        return self.client.post(
            reverse("public_contact"), self.credentials(**overrides)
        )


class PublicFooterTest(PublicContactTestBase):
    def test_a_visitor_gets_a_contact_form_instead_of_the_addresses(self):
        response = self.client.get("/")
        self.assertNotContains(response, "unit@test.be")
        self.assertNotContains(response, "010 00 00 00")
        self.assertContains(response, reverse("public_contact"))
        self.assertContains(response, "Nous contacter")

    def test_a_signed_in_reader_keeps_the_unit_s_addresses(self):
        self.client.force_login(self.parent_account)
        response = self.client.get("/")
        self.assertContains(response, "unit@test.be")
        self.assertContains(response, "010 00 00 00")
        self.assertNotContains(response, 'hx-get="/contact/"')


class PublicContactViewTest(PublicContactTestBase):
    def test_the_page_never_names_the_recipient(self):
        response = self.client.get(reverse("public_contact"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "animateur responsable")
        self.assertNotContains(response, "Ada Lead")
        self.assertContains(response, reverse("public_contact_challenge"))
        self.assertContains(response, "Vérification anti-spam")

    def test_the_dialog_is_a_fragment(self):
        response = self.client.get(
            reverse("public_contact"), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="modal-content"')
        self.assertNotContains(response, "<!DOCTYPE html>")

    def test_the_challenge_endpoint_returns_a_signed_challenge(self):
        response = self.client.get(reverse("public_contact_challenge"))
        self.assertEqual(response.status_code, 200)
        challenge = response.json()
        self.assertEqual(challenge["algorithm"], "SHA-256")
        self.assertIn("challenge", challenge)
        self.assertIn("salt", challenge)
        self.assertIn("signature", challenge)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_a_valid_message_reaches_the_unit_lead(self):
        with self.verification():
            response = self.post()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("public_contact_sent"))

        message = Email.objects.get()
        self.assertEqual(message.to, ["lead@test.be"])
        self.assertEqual(message.headers["Reply-To"], "visitor@test.be")
        self.assertIn("Visitor", message.subject)
        self.assertIn("We would like to register our child.", message.message)
        self.assertIn("visitor@test.be", message.message)

    def test_the_altcha_payload_is_verified_with_the_site_secret(self):
        """One test goes through the real library, not the patched verifier."""
        data = self.client.get(reverse("public_contact_challenge")).json()
        solution = solve_challenge_v1(
            data["challenge"],
            salt=data["salt"],
            algorithm=data["algorithm"],
            max_number=data["maxNumber"],
        )
        self.assertIsNotNone(solution)
        payload = base64.b64encode(
            json.dumps(
                {**data, "number": solution.number, "took": solution.took}
            ).encode()
        ).decode()

        response = self.post(altcha=payload)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Email.objects.exists())

    def test_the_site_staff_are_the_fallback_when_no_unit_lead_is_named(self):
        PersonRole.objects.filter(person=self.lead, role__short="ar").delete()
        with self.verification():
            self.post()
        self.assertEqual(Email.objects.get().to, ["staff@test.be"])

    def test_a_failed_anti_spam_check_sends_nothing(self):
        with self.verification(verified=False):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Email.objects.exists())
        self.assertContains(response, "La vérification anti-spam")

    def test_a_missing_anti_spam_check_sends_nothing(self):
        response = self.post(altcha="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Email.objects.exists())
        self.assertContains(response, "Veuillez compléter")

    def test_the_honeypot_sends_nothing(self):
        with self.verification():
            response = self.post(website="https://spam.example")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Email.objects.exists())

    def test_a_line_break_in_the_name_is_refused(self):
        with self.verification():
            response = self.post(name="Visitor\nBcc: someone@test.be")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Email.objects.exists())

    def test_the_dialog_toasts_on_success(self):
        with self.verification():
            response = self.client.post(
                reverse("public_contact"),
                self.credentials(),
                HTTP_HX_REQUEST="true",
            )
        self.assertEqual(response.status_code, 204)
        self.assertIn("showMessage", response.headers["HX-Trigger"])
        self.assertTrue(Email.objects.exists())

    def test_the_confirmation_page_states_the_answer_by_email(self):
        response = self.client.get(reverse("public_contact_sent"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Votre message a bien été envoyé. L'animateur responsable de "
            "l'équipe d'unité vous répondra par e-mail.",
        )
