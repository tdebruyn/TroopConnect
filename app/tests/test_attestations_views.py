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
from django.utils.translation import gettext
from post_office.models import Email

from attestations.models import AttestationCampaign, AttestationItem, NameAlias
from attestations.services import match_person
from attestations.views import _anchor_text, _resolve_placeholders
from members.models import Account, Person, Role
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


class ReopenStepTest(AttestationViewTestBase):
    """A finished campaign can be walked back into and its steps changed."""

    def _finished(self, **kwargs):
        defaults = {"step": 5, "status": AttestationCampaign.Status.READY}
        defaults.update(kwargs)
        campaign = self.make_campaign(**defaults)
        campaign.signature.save("sig.pdf", ContentFile(_blank_pdf(1)))
        campaign.name_anchor = [40, 780, 200, 800]
        campaign.save()
        return campaign

    def _step_urls(self, campaign):
        return [
            reverse(f"attestations:{name}", args=[campaign.pk])
            for name in ("step1", "step2", "step3", "step4")
        ]

    def test_review_links_back_to_every_reached_step(self):
        campaign = self._finished()

        response = self.client.get(reverse("attestations:review", args=[campaign.pk]))

        for url in self._step_urls(campaign):
            self.assertContains(response, f'href="{url}"')

    def test_a_sent_campaign_offers_no_step_links(self):
        campaign = self._finished(status=AttestationCampaign.Status.SENT)

        response = self.client.get(reverse("attestations:review", args=[campaign.pk]))

        for url in self._step_urls(campaign):
            self.assertNotContains(response, f'href="{url}"')

    def test_every_step_refuses_a_sent_campaign(self):
        campaign = self._finished(status=AttestationCampaign.Status.SENT)

        for name in ("step1", "step2", "step3", "step4"):
            with self.subTest(step=name):
                response = self.client.get(reverse(f"attestations:{name}",
                                                   args=[campaign.pk]))
                self.assertRedirects(
                    response, reverse("attestations:review", args=[campaign.pk])
                )

    def test_step1_renames_an_existing_campaign(self):
        campaign = self._finished()

        response = self.client.post(
            reverse("attestations:step1", args=[campaign.pk]),
            {"title": "Attestations 2026"},
        )

        campaign.refresh_from_db()
        self.assertEqual(campaign.title, "Attestations 2026")
        # Renaming invalidates nothing, so the campaign stays where it was.
        self.assertEqual(campaign.step, 5)
        self.assertEqual(campaign.status, AttestationCampaign.Status.READY)
        self.assertRedirects(
            response, reverse("attestations:review", args=[campaign.pk])
        )

    def test_step1_edit_form_shows_the_current_title(self):
        campaign = self._finished(title="Attestations 2025")

        response = self.client.get(reverse("attestations:step1", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attestations 2025")

    def test_editing_step2_recedes_the_wizard_and_the_status(self):
        campaign = self._finished()

        self.client.post(
            reverse("attestations:step2", args=[campaign.pk]),
            {
                "documents": ContentFile(_blank_pdf(2), name="docs.pdf"),
                "name_page": 1,
                "page_range_start": 1,
                "page_range_end": 1,
            },
        )

        campaign.refresh_from_db()
        self.assertEqual(campaign.step, 3)
        self.assertEqual(campaign.status, AttestationCampaign.Status.DRAFT)

    def test_step3_offers_the_name_it_already_found(self):
        campaign = self._finished()
        update = _anchor_text(
            campaign,
            [{"text": "Dupont Jean", "x0": 40, "y0": 780, "x1": 200, "y1": 800}],
        )

        self.assertEqual(update, {"name_value": "Dupont Jean"})

    def test_step3_offers_nothing_before_an_anchor_exists(self):
        campaign = self.make_campaign(step=3)

        self.assertEqual(_anchor_text(campaign, []), {})
class SuggestionDecisionTest(AttestationViewTestBase):
    """Accepting or rejecting a probable match from the review table.

    Both actions answer with the re-rendered row, so the test asserts on the
    response body as well as on what was stored.
    """

    def setUp(self):
        super().setUp()
        self.campaign = self.make_campaign(
            step=5, status=AttestationCampaign.Status.READY
        )
        self.item = self.make_item(
            self.campaign,
            extracted_name="Charlle Dupnot",
            matched_person=None,
            recipients=[],
            status=AttestationItem.Status.PENDING,
            suggested_person=self.child,
            match_score=0.85,
        )
        self.accept_url = reverse(
            "attestations:accept_suggestion", args=[self.campaign.pk, self.item.pk]
        )
        self.dismiss_url = reverse(
            "attestations:dismiss_suggestion", args=[self.campaign.pk, self.item.pk]
        )

    def test_accepting_makes_the_probable_match_the_recipient(self):
        response = self.client.post(self.accept_url)

        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.matched_person, self.child)
        self.assertEqual(self.item.recipients, ["alice@test.com", "bob@test.com"])
        self.assertEqual(self.item.status, AttestationItem.Status.READY)
        # The row comes back resolved: the picker holds the person, the addresses
        # are filled in, and the proposal is gone.
        self.assertContains(response, f'value="{self.child.pk}" selected')
        self.assertContains(response, "alice@test.com")
        self.assertNotContains(response, gettext("Probable match"))

    def test_accepting_without_any_recipients_leaves_the_item_pending(self):
        loner = Person.objects.create(
            first_name="Solo", last_name="Enfant", primary_role=self.role_child, status="a"
        )
        self.item.suggested_person = loner
        self.item.save(update_fields=["suggested_person"])

        response = self.client.post(self.accept_url)

        self.item.refresh_from_db()
        self.assertEqual(self.item.matched_person, loner)
        self.assertEqual(self.item.recipients, [])
        self.assertEqual(self.item.status, AttestationItem.Status.PENDING)
        self.assertContains(response, gettext("No recipient"))

    def test_dismissing_falls_back_to_the_plain_not_found_row(self):
        response = self.client.post(self.dismiss_url)

        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.suggestion_dismissed)
        self.assertIsNone(self.item.matched_person)
        self.assertNotContains(response, gettext("Probable match"))
        self.assertContains(response, gettext("Not found"))
        self.assertContains(response, "table-warning")

    def test_dismissing_keeps_the_suggestion_for_the_record(self):
        self.client.post(self.dismiss_url)
        self.item.refresh_from_db()
        self.assertEqual(self.item.suggested_person, self.child)
        self.assertEqual(self.item.match_score, 0.85)
        self.assertFalse(self.item.has_suggestion)

    def test_a_dismissed_suggestion_is_not_offered_again(self):
        self.client.post(self.dismiss_url)
        response = self.client.get(
            reverse("attestations:review", args=[self.campaign.pk]),
            {"filter": "suggested"},
        )
        self.assertEqual(len(response.context["items"]), 0)

    def test_the_decision_has_to_be_posted(self):
        self.assertEqual(self.client.get(self.accept_url).status_code, 405)
        self.assertEqual(self.client.get(self.dismiss_url).status_code, 405)

    def test_an_item_of_another_campaign_is_not_reachable(self):
        other = self.make_campaign(step=5)
        url = reverse("attestations:accept_suggestion", args=[other.pk, self.item.pk])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_a_parent_cannot_decide(self):
        self.client.logout()
        self.client.login(email="alice@test.com", password="testpass")
        self.assertEqual(self.client.post(self.accept_url).status_code, 404)
        self.assertEqual(self.client.post(self.dismiss_url).status_code, 404)


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


class RememberedNameTest(AttestationViewTestBase):
    """Step 5 keeps a manual recipient choice for the campaigns that follow."""

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

    def test_choosing_a_recipient_by_hand_is_remembered(self):
        item = self.make_item(
            self.campaign,
            extracted_name="Zoe Inconnue",
            matched_person=None,
            recipients=[],
        )
        self._post(**{f"person_{item.pk}": str(self.animateur.pk)})

        alias = NameAlias.objects.get()
        self.assertEqual(alias.person, self.animateur)
        self.assertEqual(alias.name, "Zoe Inconnue")
        self.assertEqual(alias.match_key, "inconnue zoe")
        self.assertEqual(alias.created_by, self.animateur)
        # The promise of the feature: the next campaign finds it on its own.
        self.assertEqual(match_person("Zoe Inconnue"), self.animateur)

    def test_a_match_left_as_it_was_is_not_remembered(self):
        item = self.make_item(self.campaign)
        self._post(**{f"person_{item.pk}": str(self.child.pk)})

        self.assertFalse(NameAlias.objects.exists())

    def test_a_skipped_row_is_not_remembered(self):
        item = self.make_item(
            self.campaign,
            extracted_name="Zoe Inconnue",
            matched_person=None,
            recipients=[],
        )
        self._post(**{f"skip_{item.pk}": "on", f"person_{item.pk}": str(self.animateur.pk)})

        self.assertFalse(NameAlias.objects.exists())

    def test_the_review_flags_a_remembered_match(self):
        self.make_item(self.campaign, matched_by_alias=True)

        response = self.client.get(
            reverse("attestations:review", args=[self.campaign.pk])
        )

        self.assertContains(response, gettext("Remembered"))

    def test_the_review_leaves_an_ordinary_match_unflagged(self):
        self.make_item(self.campaign)

        response = self.client.get(
            reverse("attestations:review", args=[self.campaign.pk])
        )

        self.assertNotContains(response, gettext("Remembered"))


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
