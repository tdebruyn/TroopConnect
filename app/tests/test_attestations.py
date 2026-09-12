from io import BytesIO

from django.core.files.base import ContentFile
from django.test import SimpleTestCase
from django.urls import reverse
from post_office.models import Email
from pypdf import PdfReader, PdfWriter

from attestations.models import AttestationCampaign, AttestationItem
from attestations.services import (
    build_signed_pdf,
    extract_field,
    item_ranges,
    locate_anchor,
    match_person,
    resolve_recipients,
)
from members.models import Account, ParentChild, Person, Role
from tests.mail import MailTestCase


def _blank_pdf(num_pages=1):
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=595, height=842)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _lines(texts):
    """Synthetic extraction lines stacked top-to-bottom, each 20pt tall."""
    lines = []
    y_top = 800
    for text in texts:
        lines.append(
            {
                "text": text,
                "x0": 40,
                "y0": y_top - 20,
                "x1": 40 + len(text) * 6,
                "y1": y_top,
            }
        )
        y_top -= 20
    return lines


class AnchorTest(SimpleTestCase):
    def test_locate_single_line(self):
        lines = _lines(["Aux parents de", "Dupont Jean", "Rue des Fleurs 10"])
        anchor = locate_anchor("Dupont Jean", lines)
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor[0], 40)  # left margin
        self.assertEqual(anchor[1], 760)  # bottom of the name line
        self.assertEqual(anchor[3], 780)  # top of the name line

    def test_locate_smallest_window_across_two_lines(self):
        lines = _lines(["Aux parents de", "Jean", "Dupont", "Rue des Fleurs"])
        anchor = locate_anchor("Jean Dupont", lines)
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor[1], 740)  # bottom spans down to the "Dupont" line
        self.assertEqual(anchor[3], 780)  # top is the "Jean" line

    def test_locate_missing_value_returns_none(self):
        lines = _lines(["Aux parents de", "Dupont Jean"])
        self.assertIsNone(locate_anchor("Marie Martin", lines))

    def test_extract_field_reads_anchor_region(self):
        lines = _lines(["Aux parents de", "Dupont Jean", "Rue des Fleurs 10"])
        anchor = locate_anchor("Dupont Jean", lines)
        self.assertEqual(extract_field(lines, anchor), "Dupont Jean")


class ItemRangesTest(SimpleTestCase):
    def test_fixed_length_windows(self):
        # 6 pages, each document spans pages 1..3 (3 pages) -> two items.
        self.assertEqual(item_ranges(6, 1, 3), [(0, 2), (3, 5)])

    def test_single_page_per_document(self):
        self.assertEqual(item_ranges(3, 1, 1), [(0, 0), (1, 1), (2, 2)])

    def test_offset_start(self):
        # First document starts on page 2 (1-based) and spans two pages.
        self.assertEqual(item_ranges(5, 2, 3), [(1, 2), (3, 4)])

    def test_partial_last_window(self):
        self.assertEqual(item_ranges(5, 1, 3), [(0, 2), (3, 4)])

    def test_empty(self):
        self.assertEqual(item_ranges(0, 1, 3), [])


class BuildSignedPdfTest(SimpleTestCase):
    def test_page_count(self):
        pages = list(PdfReader(BytesIO(_blank_pdf(3))).pages)
        out = build_signed_pdf(BytesIO(_blank_pdf(1)), pages, signature_page=1)
        self.assertEqual(len(PdfReader(BytesIO(out)).pages), 3)

    def test_signature_on_chosen_page(self):
        pages = list(PdfReader(BytesIO(_blank_pdf(3))).pages)
        out = build_signed_pdf(
            BytesIO(_blank_pdf(1)),
            pages,
            offset_x=10,
            offset_y=-20,
            signature_page=3,
        )
        self.assertEqual(len(PdfReader(BytesIO(out)).pages), 3)


class AttestationDbTestBase(MailTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_parent = Role.objects.get(short="p")
        cls.role_child = Role.objects.get(short="e")
        cls.role_animateur = Role.objects.get(short="a")

    def setUp(self):
        super().setUp()
        self.parent1 = Person.objects.create(
            first_name="Alice", last_name="Dupont", primary_role=self.role_parent, status="a"
        )
        self.parent1_account = Account.objects.create_user(
            email="alice@test.com", password="testpass", person=self.parent1
        )
        self.parent2 = Person.objects.create(
            first_name="Bob", last_name="Dupont", primary_role=self.role_parent, status="a"
        )
        self.parent2_account = Account.objects.create_user(
            email="bob@test.com", password="testpass", person=self.parent2
        )

        self.child = Person.objects.create(
            first_name="Charlie", last_name="Dupont", primary_role=self.role_child, status="a"
        )
        ParentChild.objects.create(parent=self.parent1, child=self.child)
        ParentChild.objects.create(parent=self.parent2, child=self.child)

        self.animateur = Person.objects.create(
            first_name="Frank", last_name="Leader", primary_role=self.role_animateur, status="a"
        )
        self.animateur_account = Account.objects.create_user(
            email="frank@test.com", password="testpass", person=self.animateur
        )


class MatchPersonTest(AttestationDbTestBase):
    def test_matches_child(self):
        self.assertEqual(match_person("Charlie Dupont"), self.child)

    def test_matches_accent_insensitive(self):
        Person.objects.create(
            first_name="Hélène", last_name="Loffet", primary_role=self.role_child, status="a"
        )
        person = match_person("Helene Loffet")
        self.assertIsNotNone(person)
        self.assertEqual(person.first_name, "Hélène")

    def test_unknown_name_returns_none(self):
        self.assertIsNone(match_person("Zoe Inconnue"))

    def test_ambiguous_name_returns_none(self):
        Person.objects.create(
            first_name="Charlie", last_name="Dupont", primary_role=self.role_child, status="a"
        )
        self.assertIsNone(match_person("Charlie Dupont"))


class ResolveRecipientsTest(AttestationDbTestBase):
    def test_child_resolves_to_parents(self):
        self.assertEqual(
            resolve_recipients(self.child),
            ["alice@test.com", "bob@test.com"],
        )

    def test_adult_resolves_to_self(self):
        self.assertEqual(resolve_recipients(self.animateur), ["frank@test.com"])

    def test_none_returns_empty(self):
        self.assertEqual(resolve_recipients(None), [])


class AccessControlTest(AttestationDbTestBase):
    def test_plain_parent_gets_404(self):
        self.client.login(email="alice@test.com", password="testpass")
        self.assertEqual(self.client.get(reverse("attestations:index")).status_code, 404)

    def test_staff_can_access(self):
        self.parent1_account.is_staff = True
        self.parent1_account.save()
        self.client.login(email="alice@test.com", password="testpass")
        self.assertEqual(self.client.get(reverse("attestations:index")).status_code, 200)

    def test_animateur_responsable_can_access(self):
        ar_role = Role.objects.get(short="ar")
        self.animateur.roles.add(ar_role)
        self.client.login(email="frank@test.com", password="testpass")
        self.assertEqual(self.client.get(reverse("attestations:index")).status_code, 200)


class WizardFlowTest(AttestationDbTestBase):
    def setUp(self):
        super().setUp()
        ar_role = Role.objects.get(short="ar")
        self.animateur.roles.add(ar_role)
        self.client.login(email="frank@test.com", password="testpass")

    def test_create_advances_to_step2(self):
        response = self.client.post(
            reverse("attestations:create"), {"title": "Attestations été"}
        )
        campaign = AttestationCampaign.objects.get()
        self.assertEqual(campaign.title, "Attestations été")
        self.assertEqual(campaign.step, 2)
        self.assertRedirects(
            response, reverse("attestations:step2", args=[campaign.pk])
        )

    def test_step2_upload_advances_to_step3(self):
        campaign = AttestationCampaign.objects.create(
            title="Test", step=2, created_by=self.animateur
        )
        response = self.client.post(
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
        self.assertTrue(campaign.documents.name)
        self.assertRedirects(
            response, reverse("attestations:step3", args=[campaign.pk])
        )


class SendFlowTest(AttestationDbTestBase):
    def setUp(self):
        super().setUp()
        ar_role = Role.objects.get(short="ar")
        self.animateur.roles.add(ar_role)
        self.client.login(email="frank@test.com", password="testpass")

        self.campaign = AttestationCampaign.objects.create(
            title="Test", status=AttestationCampaign.Status.READY, created_by=self.animateur
        )
        self.campaign.documents.save("docs.pdf", ContentFile(_blank_pdf(2)))
        self.campaign.signature.save("sig.pdf", ContentFile(_blank_pdf(1)))

        self.item = AttestationItem.objects.create(
            campaign=self.campaign,
            page_start=0,
            page_end=0,
            extracted_name="Charlie Dupont",
            matched_person=self.child,
            recipients=["alice@test.com", "bob@test.com"],
            status=AttestationItem.Status.READY,
        )

    def test_send_generates_pdf_and_queues_email(self):
        response = self.client.post(
            reverse("attestations:send", args=[self.campaign.pk]),
            {"subject": "Attestation {prenom} {nom}", "body": "Hello {prenom}"},
        )
        self.assertRedirects(response, reverse("attestations:index"))

        self.item.refresh_from_db()
        self.assertEqual(self.item.status, AttestationItem.Status.SENT)
        self.assertTrue(self.item.generated_pdf.name)

        email = Email.objects.get()
        self.assertIn("alice@test.com", email.to)
        self.assertEqual(email.subject, "Attestation Charlie Dupont")

    def test_skip_marks_item_skipped(self):
        self.client.post(
            reverse("attestations:send", args=[self.campaign.pk]),
            {"subject": "s", "body": "b", f"skip_{self.item.pk}": "on"},
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, AttestationItem.Status.SKIPPED)
        self.assertEqual(Email.objects.count(), 0)
