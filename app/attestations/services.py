"""PDF splitting, field extraction, name matching and signing for attestations.

Pure functions so they can be unit-tested without a full request cycle. Text is
extracted with bounding boxes (pdfminer.six) so that an anchor — a small region
taught on one page — can be read back on the first page of every document of a
template-generated PDF. Pages are split and merged with pypdf.
"""

import re
from io import BytesIO

from django.db.models import Q
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine
from pypdf import PdfReader, PdfWriter, Transformation
from unidecode import unidecode

from members.models import Account, Person

from .models import AttestationItem

# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalize(text):
    """Lowercase, strip accents, collapse whitespace."""
    return re.sub(r"\s+", " ", unidecode(text or "").lower()).strip()


def _name_tokens(text):
    """Split a name into its significant word tokens (accent- and case-free)."""
    return [t for t in re.findall(r"[a-z]+", _normalize(text)) if len(t) > 1]


# ---------------------------------------------------------------------------
# PDF text extraction (with bounding boxes)
# ---------------------------------------------------------------------------

def _iter_lines(obj):
    if isinstance(obj, LTTextLine):
        yield obj
    elif isinstance(obj, LTTextContainer):
        for child in obj:
            yield from _iter_lines(child)


def _collect_lines(page):
    lines = []
    for child in page:
        for line in _iter_lines(child):
            text = line.get_text().strip()
            if not text:
                continue
            x0, y0, x1, y1 = line.bbox
            lines.append({"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    # Reading order: top-to-bottom, then left-to-right.
    lines.sort(key=lambda line: (-line["y1"], line["x0"]))
    return lines


def page_lines_map(path):
    """Extract {page_index: [line dicts]} for every page of a PDF."""
    result = {}
    for idx, page in enumerate(extract_pages(path)):
        result[idx] = _collect_lines(page)
    return result


def page_lines(path, page_index):
    """Extract the line dicts for a single page."""
    return page_lines_map(path).get(page_index, [])


# ---------------------------------------------------------------------------
# Anchor location and field extraction
# ---------------------------------------------------------------------------

def _union_bbox(lines):
    x0 = min(line["x0"] for line in lines)
    y0 = min(line["y0"] for line in lines)
    x1 = max(line["x1"] for line in lines)
    y1 = max(line["y1"] for line in lines)
    return [x0, y0, x1, y1]


def locate_anchor(value, lines):
    """Return the bounding box [x0, y0, x1, y1] of ``value`` in ``lines``.

    The smallest contiguous run of lines whose combined text contains the
    (normalised) value wins, so a single-line name resolves to that line rather
    than a larger block that happens to also contain the name.
    """
    needle = _normalize(value)
    if not needle:
        return None
    for window_size in range(1, 7):
        for start in range(len(lines) - window_size + 1):
            window = lines[start : start + window_size]
            combined = _normalize(" ".join(line["text"] for line in window))
            if needle in combined:
                return _union_bbox(window)
    return None


def extract_field(lines, anchor, tol=3.0):
    """Return the text of the lines intersecting ``anchor`` (a small tolerance).

    Lines are matched by their vertical *centre* falling within the anchor's
    vertical band (rather than raw bbox intersection), so an adjacent line that
    merely shares an edge with the anchor is not pulled in.
    """
    if not anchor:
        return ""
    ax0, ay0, ax1, ay1 = anchor
    selected = [
        line
        for line in lines
        if ay0 - tol <= (line["y0"] + line["y1"]) / 2 <= ay1 + tol
        and line["x0"] <= ax1 + tol
        and line["x1"] >= ax0 - tol
    ]
    selected.sort(key=lambda line: (-line["y1"], line["x0"]))
    return " ".join(line["text"] for line in selected).strip()


# ---------------------------------------------------------------------------
# Name matching and recipient resolution
# ---------------------------------------------------------------------------

def candidate_persons(name):
    """Person objects whose first+last name tokens contain the extracted name's."""
    tokens = _name_tokens(name)
    if not tokens:
        return Person.objects.none()

    query = Q()
    for token in tokens:
        query |= Q(first_name__icontains=token) | Q(last_name__icontains=token)
    candidates = Person.objects.filter(status="a").filter(query).distinct()

    matches = []
    for person in candidates:
        person_tokens = _name_tokens(f"{person.first_name} {person.last_name}")
        if not person_tokens:
            continue
        common = set(tokens) & set(person_tokens)
        if len(tokens) == 1:
            # A single token must equal the person's full name exactly.
            if common == set(tokens) == set(person_tokens):
                matches.append(person)
        elif common == set(tokens) or common == set(person_tokens):
            matches.append(person)
    return matches


def match_person(name, address=None):
    """Return the unique Person matching ``name``, else None.

    When several people share a name, the (normalised) address breaks the tie.
    If it still cannot be disambiguated, None is returned and the operator must
    decide during review.
    """
    candidates = list(candidate_persons(name))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if address:
        norm_address = _normalize(address)
        address_matches = [
            person
            for person in candidates
            if person.address and _normalize(person.address) == norm_address
        ]
        if len(address_matches) == 1:
            return address_matches[0]
    return None


def resolve_recipients(person):
    """Deduped email addresses for a matched person.

    Covers both scripts' behaviour at once: the person's own account (adults /
    animateurs) plus the accounts of their parents (children).
    """
    if person is None:
        return []
    emails = set()
    account = Account.objects.filter(person=person).first()
    if account and account.email:
        emails.add(account.email.lower())
    parent_ids = person.parents.values_list("pk", flat=True)
    for account in Account.objects.filter(person_id__in=parent_ids):
        if account.email:
            emails.add(account.email.lower())
    return sorted(emails)


# ---------------------------------------------------------------------------
# Page splitting and signing
# ---------------------------------------------------------------------------

def item_ranges(page_count, page_range_start, page_range_end):
    """Return inclusive [start, end] 0-indexed page ranges, one per document.

    ``page_range_start`` / ``page_range_end`` are 1-based and inclusive, and
    describe the first document's span. Every following document spans the same
    number of pages, so the whole PDF is split into fixed-length windows.
    """
    if page_count == 0:
        return []
    per_item = max(1, page_range_end - page_range_start + 1)
    ranges = []
    start = page_range_start - 1
    while start < page_count:
        end = min(start + per_item - 1, page_count - 1)
        ranges.append((start, end))
        start += per_item
    return ranges


def build_signed_pdf(
    signature, pages, offset_x=0.0, offset_y=0.0, signature_page=1
):
    """Overlay ``signature`` (a path or file-like) onto ``pages`` and return bytes.

    ``signature_page`` is the 1-based page (within ``pages``) that receives the
    stamp; every other page is copied through untouched.
    """
    signature_reader = PdfReader(signature)
    signature_leaf = signature_reader.pages[0]

    writer = PdfWriter()
    for idx, page in enumerate(pages):
        if idx + 1 != signature_page:
            writer.add_page(page)
            continue
        page.merge_transformed_page(
            signature_leaf, Transformation().translate(offset_x, offset_y)
        )
        writer.add_page(page)

    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def process_campaign(campaign):
    """Split a campaign's PDF into AttestationItems (name/address/match/recipients).

    Replaces any existing items for the campaign.
    """
    AttestationItem.objects.filter(campaign=campaign).delete()

    reader = PdfReader(campaign.documents.path)
    ranges = item_ranges(
        len(reader.pages), campaign.page_range_start, campaign.page_range_end
    )
    lines_by_page = page_lines_map(campaign.documents.path)

    items = []
    for start, end in ranges:
        lines = lines_by_page.get(start, [])
        name = (
            extract_field(lines, campaign.name_anchor) if campaign.name_anchor else ""
        )
        address = (
            extract_field(lines, campaign.address_anchor)
            if campaign.address_anchor
            else ""
        )
        person = match_person(name, address)
        recipients = resolve_recipients(person)
        items.append(
            AttestationItem(
                campaign=campaign,
                page_start=start,
                page_end=end,
                extracted_name=name,
                extracted_address=address,
                matched_person=person,
                recipients=recipients,
                status=(
                    AttestationItem.Status.READY
                    if recipients
                    else AttestationItem.Status.PENDING
                ),
            )
        )
    AttestationItem.objects.bulk_create(items)
    return items
