"""View-level tests for the attestation wizard, steps 3 to 5.

``test_attestations.py`` covers the PDF services plus steps 1-2. This module
covers the rest: teaching the anchor, uploading the signature, and the send
step — which has the most branches, because an operator can skip an item,
re-point it at a different person, or leave it with no resolvable recipients,
and each has to leave a different status behind.

Uploaded files go to a throwaway MEDIA_ROOT so the tests never write into the
repo's media directory.
"""

import tempfile
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from post_office.models import Email

from attestations.models import AttestationCampaign, AttestationItem
from attestations.views import _resolve_placeholders
from members.models import Account, Role
from members.permissions import can_manage_unit
from tests.test_attestations import AttestationDbTestBase, _blank_pdf


class AttestationViewTestBase(AttestationDbTestBase):
    """AttestationDbTestBase, logged in as an 'animateur responsable'."""

    def setUp(self):
        super().setUp()
        media = override_settings(MEDIA_ROOT=tempfile.mkdtemp())
        media.enable()
        self.addCleanup(media.disable)

        self.animateur.roles.add(Role.objects.get(short="ar"))
        self.client.login(email="frank@test.com", password="testpass")

    def make_campaign(self, **kwargs):
        defaults = {
            "title": "Attestations",
            "created_by": self.animateur,
            "page_range_start": 1,
            "page_range_end": 1,
            "name_page": 1,
        }
        defaults.update(kwargs)
        campaign = AttestationCampaign.objects.create(**defaults)
        if campaign.documents is None or not campaign.documents.name:
            campaign.documents.save("docs.pdf", ContentFile(_blank_pdf(2)))
        return campaign

    def make_item(self, campaign, **kwargs):
        defaults = {
            "campaign": campaign,
            "page_start": 0,
            "page_end": 0,
            "extracted_name": "Charlie Dupont",
            "matched_person": self.child,
            "recipients": ["alice@test.com"],
            "status": AttestationItem.Status.READY,
        }
        defaults.update(kwargs)
        return AttestationItem.objects.create(**defaults)


class WizardAccessTest(AttestationViewTestBase):
    """Every wizard step is closed to ordinary parents."""

    def setUp(self):
        super().setUp()
        campaign = self.make_campaign(step=3)
        self.item = self.make_item(campaign)
        self.campaign = campaign
        self.client.logout()
        self.client.login(email="alice@test.com", password="testpass")

    def test_index_forbidden(self):
        self.assertEqual(self.client.get(reverse("attestations:index")).status_code, 404)

    def test_create_forbidden(self):
        self.assertEqual(
            self.client.post(reverse("attestations:create"), {"title": "x"}).status_code,
            404,
        )

    def test_step2_forbidden(self):
        self.assertEqual(
            self.client.get(
                reverse("attestations:step2", args=[self.campaign.pk])
            ).status_code,
            404,
        )

    def test_step3_forbidden(self):
        self.assertEqual(
            self.client.get(
                reverse("attestations:step3", args=[self.campaign.pk])
            ).status_code,
            404,
        )

    def test_step4_forbidden(self):
        self.assertEqual(
            self.client.get(
                reverse("attestations:step4", args=[self.campaign.pk])
            ).status_code,
            404,
        )

    def test_review_forbidden(self):
        self.assertEqual(
            self.client.get(
                reverse("attestations:review", args=[self.campaign.pk])
            ).status_code,
            404,
        )

    def test_send_forbidden(self):
        self.assertEqual(
            self.client.post(
                reverse("attestations:send", args=[self.campaign.pk]),
                {"subject": "s", "body": "b"},
            ).status_code,
            404,
        )

    def test_unknown_campaign_is_404_for_a_manager(self):
        self.client.logout()
        self.client.login(email="frank@test.com", password="testpass")
        self.assertEqual(
            self.client.get(reverse("attestations:step3", args=[999999])).status_code,
            404,
        )


class Step3AnchorTest(AttestationViewTestBase):
    def setUp(self):
        super().setUp()
        self.campaign = self.make_campaign(step=3)
        self.url = reverse("attestations:step3", args=[self.campaign.pk])

    def test_get_shows_the_page_text(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("page_text", response.context)

    def test_matching_name_stores_the_anchor_and_advances(self):
        anchor = [40.0, 760.0, 120.0, 780.0]
        with patch("attestations.services.locate_anchor", return_value=anchor):
            response = self.client.post(self.url, {"name_value": "Dupont Jean"})

        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.name_anchor, anchor)
        self.assertEqual(self.campaign.step, 4)
        self.assertRedirects(
            response, reverse("attestations:step4", args=[self.campaign.pk])
        )

    def test_name_not_on_the_page_redisplays_the_form(self):
        with patch("attestations.services.locate_anchor", return_value=None):
            response = self.client.post(self.url, {"name_value": "Personne Absente"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.name_anchor)
        self.assertEqual(self.campaign.step, 3)


class Step4SignatureTest(AttestationViewTestBase):
    def setUp(self):
        super().setUp()
        self.campaign = self.make_campaign(step=4)
        self.url = reverse("attestations:step4", args=[self.campaign.pk])

    def _post(self, **overrides):
        data = {
            "signature": ContentFile(_blank_pdf(1), name="sig.pdf"),
            "signature_page": 1,
            "signature_offset_x": "0",
            "signature_offset_y": "0",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_upload_advances_and_builds_the_items(self):
        response = self._post()

        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.step, 5)
        self.assertEqual(self.campaign.status, AttestationCampaign.Status.READY)
        self.assertTrue(self.campaign.signature.name)
        self.assertRedirects(
            response, reverse("attestations:review", args=[self.campaign.pk])
        )
        # 2-page PDF, one page per person -> two items.
        self.assertEqual(self.campaign.items.count(), 2)

    def test_signature_page_beyond_the_document_is_rejected(self):
        """pages_per_item is 1 here, so page 2 cannot be signed."""
        response = self._post(signature_page=2)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.step, 4)

    def test_missing_signature_is_rejected(self):
        data = {
            "signature": "",
            "signature_page": 1,
            "signature_offset_x": "0",
            "signature_offset_y": "0",
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)


class ReviewTest(AttestationViewTestBase):
    def test_review_lists_items_and_persons(self):
        campaign = self.make_campaign(step=5, status=AttestationCampaign.Status.READY)
        self.make_item(campaign)

        response = self.client.get(reverse("attestations:review", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["items"]), list(campaign.items.all()))
        self.assertIn(self.child, response.context["persons"])


class SendBranchingTest(AttestationViewTestBase):
    def setUp(self):
        super().setUp()
        self.campaign = self.make_campaign(
            step=5, status=AttestationCampaign.Status.READY
        )
        self.campaign.signature.save("sig.pdf", ContentFile(_blank_pdf(1)))
        self.url = reverse("attestations:send", args=[self.campaign.pk])

    def _post(self, **extra):
        data = {"subject": "Attestation {prenom} {nom}", "body": "Bonjour {prenom}"}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_sends_and_marks_the_item_sent(self):
        item = self.make_item(self.campaign)
        self._post()
        item.refresh_from_db()
        self.assertEqual(item.status, AttestationItem.Status.SENT)
        self.assertTrue(item.generated_pdf.name)
        self.assertEqual(Email.objects.count(), 1)

    def test_skipped_item_is_marked_skipped(self):
        item = self.make_item(self.campaign)
        self._post(**{f"skip_{item.pk}": "on"})
        item.refresh_from_db()
        self.assertEqual(item.status, AttestationItem.Status.SKIPPED)
        self.assertFalse(Email.objects.exists())

    def test_item_without_recipients_stays_pending(self):
        item = self.make_item(
            self.campaign,
            extracted_name="Zoe Inconnue",
            matched_person=None,
            recipients=[],
        )
        self._post()
        item.refresh_from_db()
        self.assertEqual(item.status, AttestationItem.Status.PENDING)
        self.assertFalse(Email.objects.exists())

    def test_item_can_be_repointed_at_another_person(self):
        item = self.make_item(
            self.campaign,
            extracted_name="Zoe Inconnue",
            matched_person=None,
            recipients=[],
        )
        self._post(**{f"person_{item.pk}": str(self.animateur.pk)})

        item.refresh_from_db()
        self.assertEqual(item.matched_person, self.animateur)
        self.assertEqual(item.recipients, ["frank@test.com"])
        self.assertEqual(item.status, AttestationItem.Status.SENT)
        self.assertEqual(Email.objects.get().to, ["frank@test.com"])

    def test_existing_match_is_kept_when_the_same_person_is_resubmitted(self):
        item = self.make_item(self.campaign)
        self._post(**{f"person_{item.pk}": str(self.child.pk)})
        item.refresh_from_db()
        self.assertEqual(item.matched_person, self.child)
        self.assertEqual(item.status, AttestationItem.Status.SENT)

    def test_send_failure_marks_the_item_failed(self):
        item = self.make_item(self.campaign)
        with patch(
            "attestations.views.mail.send", side_effect=RuntimeError("smtp down")
        ):
            self._post()

        item.refresh_from_db()
        self.assertEqual(item.status, AttestationItem.Status.FAILED)
        self.assertFalse(Email.objects.exists())

    def test_invalid_form_redisplays_the_review(self):
        self.make_item(self.campaign)
        response = self._post(subject="")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "attestations/review.html")
        self.assertFalse(Email.objects.exists())

    def test_placeholders_are_resolved_in_subject_and_body(self):
        self.make_item(self.campaign)
        self._post(subject="Attestation {prenom} {nom}", body="Cher {prenom} {nom}")
        email = Email.objects.get()
        self.assertEqual(email.subject, "Attestation Charlie Dupont")
        self.assertEqual(email.message, "Cher Charlie Dupont")

    def test_campaign_is_marked_sent_even_when_nothing_was_sent(self):
        """Current behaviour: the campaign closes regardless of item outcomes.

        Worth flagging — a campaign where every item stayed PENDING or FAILED
        is still stamped SENT, so the index cannot distinguish "all delivered"
        from "nothing delivered". Pinned here so a change is deliberate.
        """
        self.make_item(
            self.campaign,
            extracted_name="Zoe Inconnue",
            matched_person=None,
            recipients=[],
        )
        self._post()
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, AttestationCampaign.Status.SENT)
        self.assertFalse(Email.objects.exists())


class PlaceholderResolutionTest(AttestationViewTestBase):
    """``_resolve_placeholders`` falls back to the extracted name when unmatched."""

    def _campaign(self):
        return AttestationCampaign.objects.create(
            title="tmp", created_by=self.animateur
        )

    def test_uses_the_person_when_matched(self):
        item = self.make_item(self._campaign(), extracted_name="ignored")
        self.assertEqual(
            _resolve_placeholders("{prenom} {nom}", self.child, item),
            "Charlie Dupont",
        )

    def test_falls_back_to_the_extracted_name(self):
        """Defensive: the send view never calls this with person=None, because
        a person-less item has no recipients and is skipped before this point.

        The first token becomes {prenom} and the remainder {nom} — which
        assumes first-name-first, while the step-3 form's help text suggests
        typing names last-name-first ("Dupont Jean"). Harmless only because
        this branch is unreachable from the send view.
        """
        item = self.make_item(self._campaign(), extracted_name="Jean Dupont")
        self.assertEqual(
            _resolve_placeholders("{prenom} {nom}", None, item), "Jean Dupont"
        )

    def test_falls_back_to_a_single_token_extracted_name(self):
        item = self.make_item(self._campaign(), extracted_name="Cher")
        self.assertEqual(_resolve_placeholders("{prenom}-{nom}", None, item), "Cher-")

    def test_empty_extracted_name_leaves_placeholders_empty(self):
        item = self.make_item(self._campaign(), extracted_name="")
        self.assertEqual(_resolve_placeholders("{prenom}{nom}", None, item), "")


class CanManageTest(AttestationDbTestBase):
    def test_unsaved_account_is_not_a_manager(self):
        """Defensive guard — Account.save() always attaches a Person."""
        self.assertFalse(can_manage_unit(Account(email="orphan@test.com")))

    def test_staff_is_a_manager(self):
        self.parent1_account.is_staff = True
        self.assertTrue(can_manage_unit(self.parent1_account))

    def test_plain_parent_is_not_a_manager(self):
        self.assertFalse(can_manage_unit(self.parent1_account))

    def test_admin_secondary_role_is_a_manager(self):
        self.animateur.roles.add(Role.objects.get(short="ad"))
        self.animateur_account.refresh_from_db()
        self.assertTrue(can_manage_unit(self.animateur_account))

    def test_animateur_without_secondary_role_is_not_a_manager(self):
        self.assertFalse(can_manage_unit(self.animateur_account))
