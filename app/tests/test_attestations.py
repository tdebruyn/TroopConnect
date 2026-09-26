import tempfile
from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext
from post_office.models import Email
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from attestations import services
from attestations.models import AttestationCampaign, AttestationItem, NameAlias
from attestations.services import (
    PersonMatcher,
    build_signed_pdf,
    extract_field,
    item_ranges,
    locate_anchor,
    match_person,
    page_lines,
    process_campaign,
    remember_alias,
    resolve_recipients,
    suggest_person,
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


def _text_pdf(text, num_pages=1):
    """A PDF whose first page draws ``text`` in Helvetica, so it reads back.

    The attestation documents are template-generated with real text, so the
    extraction path is only exercised by a PDF that carries some.
    """
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for index in range(num_pages):
        page = writer.add_blank_page(width=595, height=842)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(
            f"BT /F1 12 Tf 40 800 Td ({text}) Tj ET".encode() if index == 0 else b""
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _signature_pdf(content):
    """A one-page A4 signature whose only content stream is ``content``."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    stream = DecodedStreamObject()
    stream.set_data(content)
    page[NameObject("/Contents")] = writer._add_object(stream)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


# A mark, and the same mark on paper: what an already-transparent signature
# looks like versus one scanned or exported onto white.
TRANSPARENT_SIGNATURE = b"0 g\n100 100 50 50 re f\n"
WHITE_SIGNATURE = b"1 g\n0 0 595 842 re f\n" + TRANSPARENT_SIGNATURE


def _resource(page, kind):
    """``page``'s ``kind`` resource dictionary, empty when the page has none."""
    resources = page.get("/Resources")
    entries = resources.get_object().get(kind) if resources is not None else None
    return entries.get_object() if entries is not None else {}


def _stamp_soft_mask(page):
    """The soft mask the stamp added to ``page``, or None."""
    for ref in _resource(page, "/ExtGState").values():
        smask = ref.get_object().get("/SMask")
        if smask is not None:
            return smask.get_object()
    return None


def _form_xobjects(page):
    """Every form XObject on ``page``, by resource name."""
    return {
        str(name): ref.get_object()
        for name, ref in _resource(page, "/XObject").items()
        if ref.get_object().get("/Subtype") == "/Form"
    }


def _assert_mask_paints_paper(case, mask_data, signature):
    """The mask must lay a white page box down first, then the signature."""
    white_fill, _, stamped = mask_data.partition(b" re f\n")
    case.assertRegex(white_fill, rb"^1 g\n[-\d. ]+$")
    case.assertEqual(stamped, signature)


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
    def _stamp(self, signature, num_pages=1, **kwargs):
        """Stamp ``signature`` onto a blank document, return the output page."""
        pages = list(PdfReader(BytesIO(_blank_pdf(num_pages))).pages)
        out = build_signed_pdf(
            BytesIO(signature), pages, signature_page=kwargs.pop("signature_page", 1),
            **kwargs,
        )
        reader = PdfReader(BytesIO(out))
        self.assertEqual(len(reader.pages), num_pages)
        return reader.pages[0]

    def test_page_count(self):
        pages = list(PdfReader(BytesIO(_blank_pdf(3))).pages)
        out = build_signed_pdf(BytesIO(_blank_pdf(1)), pages, signature_page=1)
        self.assertEqual(len(PdfReader(BytesIO(out)).pages), 3)

    def test_page_without_the_signature_is_untouched(self):
        page = self._stamp(_signature_pdf(WHITE_SIGNATURE), num_pages=3, signature_page=3)
        self.assertIsNone(_stamp_soft_mask(page))
        self.assertEqual(_form_xobjects(page), {})

    def test_white_background_is_stamped_as_transparent(self):
        """A scanned signature must not paint its paper over the attestation."""
        page = self._stamp(_signature_pdf(WHITE_SIGNATURE))

        smask = _stamp_soft_mask(page)
        self.assertIsNotNone(smask, "the stamp must be drawn through a soft mask")
        self.assertEqual(smask.get("/S"), "/Luminosity")

        # The mask's luminance is inverted, so white paper lands on alpha 0...
        transfer = smask.get("/TR")
        self.assertEqual(list(transfer.get("/C0")), [1])
        self.assertEqual(list(transfer.get("/C1")), [0])

        # ...and it reads that luminance off the signature painted onto paper.
        _assert_mask_paints_paper(
            self, smask.get("/G").get_object().get_data(), WHITE_SIGNATURE
        )

        # The stamp itself is the signature alone, with no paper of its own.
        self.assertIn(
            WHITE_SIGNATURE, [f.get_data() for f in _form_xobjects(page).values()]
        )

    def test_already_transparent_signature_is_masked_the_same_way(self):
        """The transparent case keeps working, through the same code path."""
        page = self._stamp(_signature_pdf(TRANSPARENT_SIGNATURE))

        smask = _stamp_soft_mask(page)
        self.assertIsNotNone(smask)
        self.assertEqual(smask.get("/S"), "/Luminosity")
        self.assertEqual(list(smask.get("/TR").get("/C0")), [1])

        # The paper is painted by the mask only, never by the stamp.
        _assert_mask_paints_paper(
            self, smask.get("/G").get_object().get_data(), TRANSPARENT_SIGNATURE
        )
        self.assertIn(
            TRANSPARENT_SIGNATURE,
            [f.get_data() for f in _form_xobjects(page).values()],
        )

    def test_blank_signature_leaves_the_document_alone(self):
        page = self._stamp(_blank_pdf(1))
        self.assertIsNone(_stamp_soft_mask(page))

    def test_signature_page_beyond_the_document_is_ignored(self):
        page = self._stamp(_signature_pdf(WHITE_SIGNATURE), signature_page=9)
        self.assertIsNone(_stamp_soft_mask(page))


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

    def test_matches_when_document_is_all_caps(self):
        self.assertEqual(match_person("CHARLIE DUPONT"), self.child)

    def test_matches_when_name_order_is_reversed(self):
        self.assertEqual(match_person("Dupont Charlie"), self.child)

    def test_matches_accented_database_name_without_accent_in_document(self):
        # Both tokens are accented in the database, so the old SQL prefilter
        # (an icontains on the raw column) could never find this person.
        Person.objects.create(
            first_name="Hélène", last_name="Lefèvre", primary_role=self.role_child, status="a"
        )
        person = match_person("Helene Lefevre")
        self.assertIsNotNone(person)
        self.assertEqual(person.first_name, "Hélène")

    def test_matches_single_letter_substitution(self):
        self.assertEqual(match_person("Charlle Dupont"), self.child)

    def test_matches_transposed_letters(self):
        self.assertEqual(match_person("Charlie Dupnot"), self.child)

    def test_matches_missing_letter(self):
        self.assertEqual(match_person("Charlie Dupot"), self.child)

    def test_matches_extra_letter(self):
        self.assertEqual(match_person("Charlie Dupondt"), self.child)

    def test_matches_extra_token_in_document(self):
        self.assertEqual(match_person("Charlie Jean Dupont"), self.child)

    def test_two_typos_do_not_match(self):
        self.assertIsNone(match_person("Charlle Dupnot"))

    def test_typo_in_short_token_does_not_match(self):
        # Below the typo threshold a token must match exactly, otherwise short
        # names would start colliding with each other.
        Person.objects.create(
            first_name="Luc", last_name="Martin", primary_role=self.role_child, status="a"
        )
        self.assertIsNone(match_person("Lux Martin"))

    def test_typo_does_not_match_unrelated_name(self):
        self.assertIsNone(match_person("Charlie Durand"))

    def test_unknown_name_returns_none(self):
        self.assertIsNone(match_person("Zoe Inconnue"))

    def test_ambiguous_name_returns_none(self):
        Person.objects.create(
            first_name="Charlie", last_name="Dupont", primary_role=self.role_child, status="a"
        )
        self.assertIsNone(match_person("Charlie Dupont"))

    def test_ambiguous_typo_match_returns_none(self):
        # A typo that fits two people is not a match — the operator decides.
        Person.objects.create(
            first_name="Charlle", last_name="Dupont", primary_role=self.role_child, status="a"
        )
        self.assertIsNone(match_person("Charlie Dupont"))


class SuggestPersonTest(AttestationDbTestBase):
    """The third outcome: close enough to propose, not close enough to match."""

    def test_suggests_the_person_behind_two_typos(self):
        # Two mistakes is one too many for a match, but the name is still
        # obviously "Charlie Dupont".
        person, score = suggest_person("Charlle Dupnot")
        self.assertEqual(person, self.child)
        # The score is what separates a suggestion from a match. The lower
        # bound is implied by the matcher (it returns None below 0.8), so
        # assert the upper one: a two-typo name must not read as a match.
        self.assertLess(score, 1.0)

    def test_suggests_the_person_behind_a_single_letter_miss(self):
        person, _ = suggest_person("Charlie Dupondt")
        self.assertEqual(person, self.child)

    def test_no_suggestion_for_an_unrelated_name(self):
        self.assertIsNone(suggest_person("Zoe Inconnue"))

    def test_no_suggestion_when_one_name_only_is_shared(self):
        # "Charlie Durand" shares a first name with the child and nothing else;
        # a shared first name is not a probable match.
        self.assertIsNone(suggest_person("Charlie Durand"))

    def test_no_suggestion_between_similar_first_names(self):
        Person.objects.create(
            first_name="Marc", last_name="Dupont", primary_role=self.role_child, status="a"
        )
        self.assertIsNone(suggest_person("Marie Dupont"))

    def test_no_suggestion_for_a_single_token_name(self):
        # "Dupont" alone would point at every Dupont in the unit.
        self.assertIsNone(suggest_person("Dupont"))

    def test_no_suggestion_when_the_two_candidates_are_too_close(self):
        # Two people the name fits almost equally well: picking either would be
        # a coin flip, so the operator searches instead.
        Person.objects.create(
            first_name="Charlle", last_name="Dupont", primary_role=self.role_child, status="a"
        )
        self.assertIsNone(suggest_person("Charlie Dupont"))

    def test_a_clear_winner_is_still_suggested(self):
        # ...but a close runner-up that is clearly worse does not block one.
        Person.objects.create(
            first_name="Charlotte", last_name="Dupont", primary_role=self.role_child, status="a"
        )
        person, _ = suggest_person("Chalrie Dupnot")
        self.assertEqual(person, self.child)

    def test_archived_people_are_not_candidates(self):
        # Were they active, this name would score a perfect 1.0 — archived
        # members are never proposed (nor matched), only current ones.
        Person.objects.create(
            first_name="Zoe",
            last_name="Inconnue",
            primary_role=self.role_child,
            status="ar",
        )
        self.assertIsNone(suggest_person("Zoe Inconnue"))


class ProcessCampaignSuggestionTest(AttestationDbTestBase):
    """Splitting a campaign keeps a near-miss as a proposal, not a match."""

    def _process(self, extracted_name):
        campaign = AttestationCampaign.objects.create(
            title="Test",
            name_anchor=[0.0, 0.0, 1.0, 1.0],
            page_range_start=1,
            page_range_end=1,
        )
        campaign.documents.save("docs.pdf", ContentFile(_blank_pdf(1)))
        with patch("attestations.services.extract_field", return_value=extracted_name):
            services.process_campaign(campaign)
        return campaign.items.get()

    def test_a_near_miss_is_stored_as_a_suggestion(self):
        item = self._process("Charlle Dupnot")
        self.assertIsNone(item.matched_person)
        self.assertEqual(item.suggested_person, self.child)
        # Stored as a near-miss, not as a match (>= 0.8 is implied: the
        # matcher returns None below that).
        self.assertLess(item.match_score, 1.0)
        # Nothing is sent on the strength of a suggestion, so the item is left
        # with no recipients and stays pending.
        self.assertEqual(item.recipients, [])
        self.assertEqual(item.status, AttestationItem.Status.PENDING)

    def test_a_name_nobody_resembles_is_left_alone(self):
        item = self._process("Zoe Inconnue")
        self.assertIsNone(item.matched_person)
        self.assertIsNone(item.suggested_person)
        self.assertIsNone(item.match_score)

    def test_an_exact_match_is_not_also_offered_as_a_suggestion(self):
        item = self._process("Charlie Dupont")
        self.assertEqual(item.matched_person, self.child)
        self.assertIsNone(item.suggested_person)


class NameAliasTest(AttestationDbTestBase):
    """Correspondences an operator saved by hand, and when they are honoured."""

    def make_vandenberghe(self):
        return Person.objects.create(
            first_name="Jan",
            last_name="Vandenberghe",
            primary_role=self.role_child,
            status="a",
        )

    def test_a_remembered_name_resolves_a_spelling_the_matcher_cannot(self):
        # Split in two, so no amount of typo tolerance bridges it.
        person = self.make_vandenberghe()
        remember_alias("Van den Berg Jan", person)

        self.assertEqual(match_person("Van den Berg Jan"), person)

    def test_a_remembered_name_ignores_case_accents_and_word_order(self):
        person = self.make_vandenberghe()
        remember_alias("Van den Berg Jan", person)

        self.assertEqual(match_person("JAN VAN DEN BERG"), person)

    def test_a_remembered_name_wins_over_the_fuzzy_match(self):
        # "Charlle Dupont" is one letter off the child, so the fuzzy matcher
        # claims it (see test_matches_single_letter_substitution); the
        # operator's decision has to override that.
        remember_alias("Charlle Dupont", self.animateur)

        self.assertEqual(match_person("Charlle Dupont"), self.animateur)

    def test_a_remembered_name_is_left_alone_when_two_members_share_it(self):
        # Otherwise every document spelled that way would go to whoever was
        # picked last time, namesake or not.
        Person.objects.create(
            first_name="Charlie",
            last_name="Dupont",
            primary_role=self.role_child,
            status="a",
        )
        remember_alias("Charlie Dupont", self.child)

        self.assertIsNone(match_person("Charlie Dupont"))

    def test_a_remembered_name_for_an_archived_member_is_ignored(self):
        person = self.make_vandenberghe()
        remember_alias("Van den Berg Jan", person)
        person.status = "ar"
        person.save()

        self.assertIsNone(match_person("Van den Berg Jan"))

    def test_remembering_the_same_spelling_again_moves_it(self):
        person = self.make_vandenberghe()
        remember_alias("Van den Berg Jan", self.child)
        remember_alias("van den  berg  jan", person)

        alias = NameAlias.objects.get()
        self.assertEqual(alias.person, person)
        self.assertEqual(alias.name, "van den berg jan")
        self.assertEqual(alias.match_key, "berg den jan van")
        self.assertEqual(match_person("Van den Berg Jan"), person)

    def test_remembering_needs_a_name_and_a_person(self):
        self.assertIsNone(remember_alias("   ", self.child))
        self.assertIsNone(remember_alias("Zoe Inconnue", None))
        self.assertFalse(NameAlias.objects.exists())

    def test_lookup_reports_whether_a_remembered_name_decided(self):
        person = self.make_vandenberghe()
        remember_alias("Van den Berg Jan", person)
        matcher = PersonMatcher()

        self.assertEqual(matcher.lookup("Van den Berg Jan"), (person, True))
        self.assertEqual(matcher.lookup("Charlie Dupont"), (self.child, False))


class ProcessCampaignTest(AttestationDbTestBase):
    """Splitting a campaign's PDF into items, including remembered names."""

    def setUp(self):
        super().setUp()
        media = override_settings(MEDIA_ROOT=tempfile.mkdtemp())
        media.enable()
        self.addCleanup(media.disable)

    def make_campaign_for(self, name):
        campaign = AttestationCampaign.objects.create(
            title="Attestations",
            created_by=self.animateur,
            name_page=1,
            page_range_start=1,
            page_range_end=2,
        )
        campaign.documents.save("docs.pdf", ContentFile(_text_pdf(name, num_pages=2)))
        campaign.name_anchor = locate_anchor(
            name, page_lines(campaign.documents.path, 0)
        )
        campaign.save()
        return campaign

    def test_an_item_resolved_by_a_remembered_name_is_flagged(self):
        person = Person.objects.create(
            first_name="Jan",
            last_name="Vandenberghe",
            primary_role=self.role_child,
            status="a",
        )
        remember_alias("Van den Berg Jan", person)

        campaign = self.make_campaign_for("Van den Berg Jan")
        process_campaign(campaign)

        item = campaign.items.get()
        self.assertEqual(item.extracted_name, "Van den Berg Jan")
        self.assertEqual(item.matched_person, person)
        self.assertTrue(item.matched_by_alias)

    def test_an_item_resolved_by_its_own_name_is_not_flagged(self):
        campaign = self.make_campaign_for("Charlie Dupont")
        process_campaign(campaign)

        item = campaign.items.get()
        self.assertEqual(item.matched_person, self.child)
        self.assertFalse(item.matched_by_alias)


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


class ProcessCampaignCarryOverTest(AttestationDbTestBase):
    """Re-running the split must not throw away the operator's review work."""

    def _campaign(self, num_pages=1, **kwargs):
        defaults = {
            "title": "Test",
            "step": 5,
            "created_by": self.animateur,
            "name_page": 1,
            "page_range_start": 1,
            "page_range_end": 1,
        }
        defaults.update(kwargs)
        campaign = AttestationCampaign.objects.create(**defaults)
        campaign.documents.save("docs.pdf", ContentFile(_blank_pdf(num_pages)))
        return campaign

    def _choose_recipient(self, campaign, **ranges):
        """Stand in for the operator picking a recipient on the review screen."""
        item = campaign.items.get(**ranges)
        item.matched_person = self.child
        item.recipients = ["alice@test.com"]
        item.status = AttestationItem.Status.READY
        item.save()
        return item

    def test_unchanged_document_keeps_the_chosen_recipient(self):
        campaign = self._campaign()
        services.process_campaign(campaign)
        self._choose_recipient(campaign, page_start=0, page_end=0)

        services.process_campaign(campaign)

        item = campaign.items.get()
        self.assertEqual(item.matched_person, self.child)
        self.assertEqual(item.recipients, ["alice@test.com"])
        self.assertEqual(item.status, AttestationItem.Status.READY)

    def test_unchanged_document_keeps_what_was_decided_about_a_suggestion(self):
        campaign = self._campaign()
        services.process_campaign(campaign)
        item = campaign.items.get()
        item.suggested_person = self.child
        item.match_score = 0.85
        item.suggestion_dismissed = True
        item.save()

        services.process_campaign(campaign)

        item = campaign.items.get()
        self.assertEqual(item.suggested_person, self.child)
        self.assertEqual(item.match_score, 0.85)
        # A rejection the operator already made must not come back to life.
        self.assertTrue(item.suggestion_dismissed)
        self.assertFalse(item.has_suggestion)

    def test_resplit_document_is_matched_afresh(self):
        campaign = self._campaign(num_pages=2)
        services.process_campaign(campaign)
        self._choose_recipient(campaign, page_start=0, page_end=0)

        # One document per page becomes one document for the whole file, so
        # nothing carries over and the (blank) page yields no match.
        campaign.page_range_end = 2
        campaign.save()
        services.process_campaign(campaign)

        item = campaign.items.get()
        self.assertEqual((item.page_start, item.page_end), (0, 1))
        self.assertIsNone(item.matched_person)
        self.assertEqual(item.recipients, [])
        self.assertEqual(item.status, AttestationItem.Status.PENDING)


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


class ReviewFilterTest(AttestationDbTestBase):
    """The step-5 filters: everything, to confirm, or recipient not found."""

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
        self.matched = AttestationItem.objects.create(
            campaign=self.campaign,
            page_start=0,
            page_end=0,
            extracted_name="Charlie Dupont",
            matched_person=self.child,
            recipients=["alice@test.com", "bob@test.com"],
            status=AttestationItem.Status.READY,
        )
        self.unmatched = AttestationItem.objects.create(
            campaign=self.campaign,
            page_start=1,
            page_end=1,
            extracted_name="Zoe Inconnue",
            status=AttestationItem.Status.PENDING,
        )
        # A third document whose name is close to a person's but not close
        # enough to be called a match — the suggestion tier.
        self.suggested = AttestationItem.objects.create(
            campaign=self.campaign,
            page_start=2,
            page_end=2,
            extracted_name="Charlle Dupnot",
            suggested_person=self.child,
            match_score=0.85,
            status=AttestationItem.Status.PENDING,
        )

    def _review(self, **params):
        return self.client.get(
            reverse("attestations:review", args=[self.campaign.pk]), params
        )

    def test_review_lists_every_item_by_default(self):
        response = self._review()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["items"]), 3)
        self.assertEqual(response.context["filter_name"], "all")
        self.assertEqual(response.context["total_count"], 3)
        self.assertEqual(response.context["suggested_count"], 1)
        self.assertEqual(response.context["unmatched_count"], 1)
        # The recipient pickers are wired for the type-to-filter combobox, which
        # enhances the <select> in place (the select still posts the person pk).
        self.assertContains(response, "person-select")
        # The combobox script, not just its stylesheet: the <link> alone
        # satisfied the previous bare "tom-select" match with the JS removed.
        self.assertRegex(
            response.content.decode(),
            r'<script[^>]*src="[^"]*tom-select[^"]*\.js"',
        )

    def test_filter_shows_every_count(self):
        # Compare against the translated labels: the app renders in the visitor's
        # language (French by default), not in the English source strings.
        response = self._review()
        self.assertContains(response, gettext("All (%(count)s)") % {"count": 3})
        self.assertContains(response, gettext("To confirm (%(count)s)") % {"count": 1})
        self.assertContains(response, gettext("Not found (%(count)s)") % {"count": 1})

    def test_suggested_filter_shows_just_the_probable_match(self):
        response = self._review(filter="suggested")
        items = list(response.context["items"])
        self.assertEqual([item.pk for item in items], [self.suggested.pk])
        self.assertEqual(response.context["filter_name"], "suggested")

    def test_unmatched_filter_shows_just_the_not_found_item(self):
        # The suggested document has a proposal to decide on, so it is not
        # "not found" — it is listed under its own filter.
        response = self._review(filter="unmatched")
        items = list(response.context["items"])
        self.assertEqual([item.pk for item in items], [self.unmatched.pk])
        self.assertEqual(response.context["filter_name"], "unmatched")

    def test_unknown_filter_falls_back_to_everything(self):
        response = self._review(filter="nonsense")
        self.assertEqual(response.context["filter_name"], "all")
        self.assertEqual(len(response.context["items"]), 3)

    def test_dismissed_suggestion_moves_to_the_not_found_filter(self):
        self.suggested.suggestion_dismissed = True
        self.suggested.save(update_fields=["suggestion_dismissed"])

        suggested = self._review(filter="suggested")
        self.assertEqual(len(suggested.context["items"]), 0)

        unmatched = self._review(filter="unmatched")
        self.assertEqual(
            [item.pk for item in unmatched.context["items"]],
            [self.unmatched.pk, self.suggested.pk],
        )

    def test_probable_match_row_offers_both_ways_out(self):
        response = self._review(filter="suggested")
        self.assertContains(response, gettext("Probable match"))
        self.assertContains(
            response,
            reverse(
                "attestations:accept_suggestion",
                args=[self.campaign.pk, self.suggested.pk],
            ),
        )
        self.assertContains(
            response,
            reverse(
                "attestations:dismiss_suggestion",
                args=[self.campaign.pk, self.suggested.pk],
            ),
        )
        # 0.85 renders as a percentage, and the addresses confirming it would
        # send to are shown before the operator commits to anything.
        self.assertContains(response, "85 %")
        self.assertContains(response, "alice@test.com")
        # Flagged apart from both the matched and the not-found rows.
        self.assertContains(response, "table-info")
        # Both buttons post through htmx, which needs the CSRF token in a header
        # — the row is inside the send form, not a form of its own.
        self.assertContains(response, "hx-post")
        self.assertContains(response, "X-CSRFToken")

    def test_a_confirmed_match_is_no_longer_offered_as_a_suggestion(self):
        self.suggested.matched_person = self.child
        self.suggested.save(update_fields=["matched_person"])
        response = self._review(filter="suggested")
        self.assertEqual(len(response.context["items"]), 0)

    def test_unmatched_filter_survives_an_invalid_send(self):
        response = self.client.post(
            reverse("attestations:send", args=[self.campaign.pk]),
            {"subject": "", "body": "", "filter": "unmatched"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filter_name"], "unmatched")
        self.assertEqual(len(response.context["items"]), 1)

    def test_filtered_out_items_are_still_sent_with_their_stored_match(self):
        # Hiding the matched rows must not drop them from the send.
        self.client.post(
            reverse("attestations:send", args=[self.campaign.pk]),
            {"subject": "s", "body": "b", "filter": "unmatched"},
        )
        self.matched.refresh_from_db()
        self.assertEqual(self.matched.status, AttestationItem.Status.SENT)
        self.unmatched.refresh_from_db()
        self.assertEqual(self.unmatched.status, AttestationItem.Status.PENDING)
        self.suggested.refresh_from_db()
        self.assertEqual(self.suggested.status, AttestationItem.Status.PENDING)
