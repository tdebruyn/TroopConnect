"""PDF splitting, field extraction, name matching and signing for attestations.

Pure functions so they can be unit-tested without a full request cycle. Text is
extracted with bounding boxes (pdfminer.six) so that an anchor — a small region
taught on one page — can be read back on the first page of every document of a
template-generated PDF. Pages are split and merged with pypdf.
"""

import re
from io import BytesIO

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

# A token shorter than this is too easy to confuse with another name, so it has
# to match exactly; and a name may differ from the database one by at most this
# many letter-level mistakes in total.
_TYPO_MIN_LEN = 4
_MAX_TYPOS = 1


def _is_one_typo_apart(a, b):
    """True when ``a`` and ``b`` differ by a single letter-level mistake.

    Covers the mistakes that actually show up in a scanned document: a wrong
    letter, a swapped pair of letters, or a missing/extra letter.
    """
    if a == b:
        return True
    if min(len(a), len(b)) < _TYPO_MIN_LEN:
        return False
    if abs(len(a) - len(b)) > 1:
        return False

    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        # Adjacent transposition, e.g. "Dupnot" for "Dupont".
        return (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and a[diffs[0]] == b[diffs[1]]
            and a[diffs[1]] == b[diffs[0]]
        )

    # Lengths differ by one: one insertion or deletion.
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1 :]


def _all_tokens_found(source, target, max_typos=_MAX_TYPOS):
    """True when every token of ``source`` also occurs in ``target``.

    Exact matches are tried first so that the typo budget is only spent when it
    is actually needed. ``max_typos`` is the total across the whole name.
    """
    remaining = list(target)
    typos = 0
    for token in source:
        if token in remaining:
            remaining.remove(token)
            continue
        close = next((t for t in remaining if _is_one_typo_apart(token, t)), None)
        if close is None or typos >= max_typos:
            return False
        remaining.remove(close)
        typos += 1
    return True


def _names_match(name_tokens, person_tokens):
    """Whether an extracted name and a person's name refer to the same name.

    Order-insensitive and tolerant of case, accents (both handled upstream by
    ``_name_tokens``) and a single typo. Either name may carry extra tokens —
    a document often spells out a middle name the database does not hold, and
    the reverse happens too — so a match in either direction counts.
    """
    if not name_tokens or not person_tokens:
        return False
    return _all_tokens_found(name_tokens, person_tokens) or _all_tokens_found(
        person_tokens, name_tokens
    )


class PersonMatcher:
    """Fuzzy name → Person lookup, built once and reused across a campaign.

    Names are matched in Python rather than with an ``icontains`` query: SQL
    cannot express "one letter off", and an accented database column does not
    match the accent-stripped, typo-tolerant tokens we compare against. The unit
    has a few hundred members, so scanning them is cheap.
    """

    def __init__(self, persons=None):
        if persons is None:
            persons = Person.objects.filter(status="a")
        self._entries = [
            (person, _name_tokens(f"{person.first_name} {person.last_name}"))
            for person in persons
        ]

    def candidates(self, name):
        """Every person whose name matches the extracted one."""
        tokens = _name_tokens(name)
        if not tokens:
            return []
        return [
            person
            for person, person_tokens in self._entries
            if _names_match(tokens, person_tokens)
        ]

    def match(self, name, address=None):
        """The unique matching Person, else None.

        When several people share a name, the (normalised) address breaks the
        tie. If it still cannot be disambiguated, None is returned and the
        operator decides during review.
        """
        candidates = self.candidates(name)
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


def candidate_persons(name):
    """The persons matching ``name``; kept for callers needing the raw list."""
    return PersonMatcher().candidates(name)


def match_person(name, address=None, matcher=None):
    """Return the unique Person matching ``name``, else None."""
    if matcher is None:
        matcher = PersonMatcher()
    return matcher.match(name, address)


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
    matcher = PersonMatcher()

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
        person = matcher.match(name, address)
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
