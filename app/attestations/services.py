"""PDF splitting, field extraction, name matching and signing for attestations.

Pure functions so they can be unit-tested without a full request cycle. Text is
extracted with bounding boxes (pdfminer.six) so that an anchor — a small region
taught on one page — can be read back on the first page of every document of a
template-generated PDF. Pages are split and merged with pypdf, and the signature
is stamped through a soft mask that drops its white paper (see
``build_signed_pdf``).
"""

import difflib
from collections import Counter
from io import BytesIO

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine
from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

from members.models import Account, Person

from .models import AttestationItem, NameAlias
from .normalization import name_key, name_tokens, normalize, token_key

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
    needle = normalize(value)
    if not needle:
        return None
    for window_size in range(1, 7):
        for start in range(len(lines) - window_size + 1):
            window = lines[start : start + window_size]
            combined = normalize(" ".join(line["text"] for line in window))
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


def _similarity(a, b):
    """How alike two tokens are, 0..1 (``difflib`` ratio, order-sensitive)."""
    return difflib.SequenceMatcher(None, a, b).ratio()


# A suggestion is a near-miss of the exact rule above: every token of one name
# must have a counterpart in the other at least this similar, and the names as
# a whole must score at least that well. Looser than this and the operator
# would be confirming noise rather than being saved a search.
_FUZZY_MIN_PAIR = 0.75
_FUZZY_MIN_SCORE = 0.8
# ...and the runner-up has to be clearly worse, so that a coin flip between two
# similar people is never presented as a likely match.
_FUZZY_MIN_MARGIN = 0.1


def _covered_by(source, target):
    """Average similarity of the pairs covering ``source``, else ``None``.

    Each source token is paired with the most similar unused target token;
    ``None`` is returned as soon as one of them has no counterpart close
    enough, since two names sharing only one of their words are not the same
    person.
    """
    remaining = list(target)
    ratios = []
    for token in source:
        if not remaining:
            return None
        best = max(remaining, key=lambda other: _similarity(token, other))
        ratio = _similarity(token, best)
        if ratio < _FUZZY_MIN_PAIR:
            return None
        remaining.remove(best)
        ratios.append(ratio)
    return sum(ratios) / len(ratios)


def _fuzzy_score(name_tokens, person_tokens):
    """How close two names are, or ``None`` when they are not close enough.

    As in the exact rule either name may carry extra tokens — a document often
    spells out a middle name the database does not hold — so a full cover in
    either direction counts, and the score is the average similarity of the
    pairs that cover it. A one-token name is never scored: "Dupont" alone would
    otherwise point at every Dupont in the unit.
    """
    if len(name_tokens) < 2 or not person_tokens:
        return None
    covers = [
        cover
        for cover in (
            _covered_by(name_tokens, person_tokens),
            _covered_by(person_tokens, name_tokens),
        )
        if cover is not None
    ]
    if not covers:
        return None
    score = max(covers)
    return score if score >= _FUZZY_MIN_SCORE else None


def _names_match(document_tokens, person_tokens):
    """Whether an extracted name and a person's name refer to the same name.

    Order-insensitive and tolerant of case, accents (both handled upstream by
    ``name_tokens``) and a single typo. Either name may carry extra tokens —
    a document often spells out a middle name the database does not hold, and
    the reverse happens too — so a match in either direction counts.
    """
    if not document_tokens or not person_tokens:
        return False
    return _all_tokens_found(document_tokens, person_tokens) or _all_tokens_found(
        person_tokens, document_tokens
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
            (person, name_tokens(f"{person.first_name} {person.last_name}"))
            for person in persons
        ]
        # How many members answer to each full name, to tell a name that
        # identifies one person from one that identifies several.
        self._namesakes = Counter(token_key(tokens) for _, tokens in self._entries)
        self._aliases = {
            alias.match_key: alias.person
            for alias in NameAlias.objects.filter(person__status="a").select_related(
                "person"
            )
        }

    def candidates(self, name):
        """Every person whose name matches the extracted one."""
        tokens = name_tokens(name)
        if not tokens:
            return []
        return [
            person
            for person, person_tokens in self._entries
            if _names_match(tokens, person_tokens)
        ]

    def alias_match(self, name):
        """The person remembered for this exact spelling, when it is safe to use.

        A stored correspondence is only reused while the name identifies a
        single member: with two members sharing a full name, honouring it would
        quietly send every document spelled that way to whoever was picked last
        time. So an ambiguous name falls through to the fuzzy matcher, which
        returns None and leaves the row to the operator.
        """
        key = name_key(name)
        if not key or self._namesakes.get(key, 0) > 1:
            return None
        return self._aliases.get(key)

    def match(self, name, address=None):
        """The unique matching Person, else None."""
        return self.lookup(name, address)[0]

    def lookup(self, name, address=None):
        """The matching Person plus whether a remembered correspondence found it.

        A stored alias is consulted first: it records what an operator decided
        for this very spelling, whereas the typo tolerance below is exactly what
        would otherwise pull the name back to the person they rejected.
        """
        alias = self.alias_match(name)
        if alias is not None:
            return alias, True
        return self._fuzzy_match(name, address), False

    def _fuzzy_match(self, name, address=None):
        """A match on the names themselves, tolerant of one typo.

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
            norm_address = normalize(address)
            address_matches = [
                person
                for person in candidates
                if person.address and normalize(person.address) == norm_address
            ]
            if len(address_matches) == 1:
                return address_matches[0]
        return None

    def suggest(self, name):
        """The most likely Person for a name the exact rule could not resolve.

        Returns ``(person, score)``, the score being 0..1, or ``None`` when no
        name is close enough — or when the two best candidates are too close to
        each other to choose between, which is left to the operator. A
        suggestion is only ever a proposal: nothing is sent on its strength
        until someone confirms it during review.
        """
        tokens = name_tokens(name)
        scored = [
            (person, score)
            for person, person_tokens in self._entries
            if (score := _fuzzy_score(tokens, person_tokens)) is not None
        ]
        if not scored:
            return None
        scored.sort(key=lambda pair: -pair[1])
        best_person, best_score = scored[0]
        if len(scored) > 1 and best_score - scored[1][1] < _FUZZY_MIN_MARGIN:
            return None
        return best_person, best_score


def remember_alias(name, person, created_by=None):
    """Store the operator's manual name → person correspondence.

    Keyed on the normalised name, so a later campaign whose PDF spells the name
    the same way (any case, order or accents) resolves it without asking. The
    latest decision wins: pointing the same spelling at somebody else replaces
    the correspondence instead of piling up a second one.
    """
    key = name_key(name)
    if not key or person is None:
        return None
    alias, _created = NameAlias.objects.update_or_create(
        match_key=key,
        defaults={
            # Kept as spelled, so the admin shows what the PDF actually said.
            "name": " ".join(name.split())[:300],
            "person": person,
            "created_by": created_by,
        },
    )
    return alias


def candidate_persons(name):
    """The persons matching ``name``; kept for callers needing the raw list."""
    return PersonMatcher().candidates(name)


def match_person(name, address=None, matcher=None):
    """Return the unique Person matching ``name``, else None."""
    if matcher is None:
        matcher = PersonMatcher()
    return matcher.match(name, address)


def suggest_person(name, matcher=None):
    """Return ``(person, score)`` for a likely, but unconfirmed, match."""
    if matcher is None:
        matcher = PersonMatcher()
    return matcher.suggest(name)


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


def _pt(value):
    """A PDF real, rounded so the content streams we emit stay readable."""
    return FloatObject(round(float(value), 4))


def _page_box(page):
    """The page's media box as ``[x0, y0, x1, y1]``."""
    box = page.mediabox
    return [float(box.left), float(box.bottom), float(box.right), float(box.top)]


def _white_paper_rect(box):
    """Paint the whole page box white."""
    x0, y0, x1, y1 = box
    return f"{_pt(x0)} {_pt(y0)} {_pt(x1 - x0)} {_pt(y1 - y0)} re f\n".encode()


def _inverted_luminosity_transfer():
    """``y = 1 - x``, so white paper (luminance 1) becomes alpha 0.

    A linear fall-off rather than a hard cut-off: paper that is only *nearly*
    white — a scan, or a JPEG of one — then fades out in proportion instead of
    leaving a contour wherever the threshold happens to fall.
    """
    return DictionaryObject(
        {
            NameObject("/FunctionType"): NumberObject(2),
            NameObject("/Domain"): ArrayObject([_pt(0), _pt(1)]),
            NameObject("/C0"): ArrayObject([_pt(1)]),
            NameObject("/C1"): ArrayObject([_pt(0)]),
            NameObject("/N"): NumberObject(1),
        }
    )


def _form_xobject(writer, content, box, resources, group=None):
    form = DecodedStreamObject()
    form.set_data(content)
    form[NameObject("/Type")] = NameObject("/XObject")
    form[NameObject("/Subtype")] = NameObject("/Form")
    form[NameObject("/FormType")] = NumberObject(1)
    form[NameObject("/BBox")] = ArrayObject([_pt(v) for v in box])
    if resources is not None:
        form[NameObject("/Resources")] = resources
    if group is not None:
        form[NameObject("/Group")] = group
    return writer._add_object(form)


def _stamp_white_keyed(writer, target, signature_leaf, offset_x, offset_y):
    """Stamp ``signature_leaf`` onto ``target``, treating its white as transparent.

    The stamp is drawn through a soft mask derived from the signature's own
    rendering: the mask paints white paper, draws the signature over it inside a
    DeviceGray transparency group, and the group's luminance is then inverted.
    Painted white paper and an absent (transparent) background both leave the
    mask at luminance 1, so both come out transparent while the ink stays
    opaque — one code path for either kind of signature. Only the mask is
    derived this way; the stamp is still the signature's own vector content, so
    nothing is rasterised and the ink keeps its colour.
    """
    contents = signature_leaf.get_contents()
    if contents is None:
        return
    content = contents.get_data()
    if not content.strip():
        return

    box = _page_box(signature_leaf)
    resources = signature_leaf.get("/Resources")
    if resources is not None:
        # The stamp re-uses the signature's content stream verbatim, so the
        # objects it refers to have to be carried into the output document.
        resources = resources.get_object().clone(writer, force_duplicate=True)

    mask = _form_xobject(
        writer,
        b"1 g\n" + _white_paper_rect(box) + content,
        box,
        resources,
        group=DictionaryObject(
            {
                NameObject("/S"): NameObject("/Transparency"),
                NameObject("/CS"): NameObject("/DeviceGray"),
                NameObject("/I"): BooleanObject(True),
                NameObject("/K"): BooleanObject(False),
            }
        ),
    )
    stamp = _form_xobject(writer, content, box, resources)
    graphics_state = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/ExtGState"),
                NameObject("/SMask"): DictionaryObject(
                    {
                        NameObject("/S"): NameObject("/Luminosity"),
                        NameObject("/G"): mask,
                        NameObject("/TR"): _inverted_luminosity_transfer(),
                    }
                ),
            }
        )
    )

    # The stamp goes onto the target through a throwaway single-page document,
    # so that pypdf does the resource merging and applies the offset. Building
    # the target's content stream by hand instead loses whatever the page
    # already carried.
    carrier = PageObject.create_blank_page(
        width=box[2] - box[0], height=box[3] - box[1]
    )
    carrier[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject({NameObject("/Sg"): stamp}),
            NameObject("/ExtGState"): DictionaryObject(
                {NameObject("/SgGs"): graphics_state}
            ),
        }
    )
    carrier_content = DecodedStreamObject()
    carrier_content.set_data(b"/SgGs gs\n/Sg Do")
    carrier[NameObject("/Contents")] = writer._add_object(carrier_content)
    writer._add_object(carrier)

    target.merge_transformed_page(
        carrier, Transformation().translate(offset_x, offset_y)
    )


def build_signed_pdf(
    signature, pages, offset_x=0.0, offset_y=0.0, signature_page=1
):
    """Overlay ``signature`` (a path or file-like) onto ``pages`` and return bytes.

    ``signature_page`` is the 1-based page (within ``pages``) that receives the
    stamp; every other page is copied through untouched. White in the signature
    is stamped as transparent, so a signature scanned or exported onto white
    paper works as well as one that was already transparent.
    """
    signature_reader = PdfReader(signature)
    signature_leaf = signature_reader.pages[0]

    writer = PdfWriter()
    for page in pages:
        writer.add_page(page)

    if 1 <= signature_page <= len(writer.pages):
        _stamp_white_keyed(
            writer,
            writer.pages[signature_page - 1],
            signature_leaf,
            offset_x,
            offset_y,
        )

    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def process_campaign(campaign):
    """Split a campaign's PDF into AttestationItems (name/address/match/recipients).

    Replaces any existing items for the campaign — but an operator who reopens
    an earlier step keeps the work they already did. An item whose page range
    survives the re-split carries over its matched person, recipients, status
    and whatever was decided about a suggestion; only documents that are new or
    re-ranged are matched afresh.
    """
    previous = {
        (item.page_start, item.page_end): item for item in campaign.items.all()
    }
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
        carried = previous.get((start, end))
        if carried is not None:
            matched_person = carried.matched_person
            suggested_person = carried.suggested_person
            match_score = carried.match_score
            suggestion_dismissed = carried.suggestion_dismissed
            matched_by_alias = carried.matched_by_alias
            recipients = carried.recipients
            status = carried.status
        else:
            matched_person, matched_by_alias = matcher.lookup(name, address)
            suggestion = matcher.suggest(name) if matched_person is None else None
            suggested_person = suggestion[0] if suggestion else None
            match_score = suggestion[1] if suggestion else None
            suggestion_dismissed = False
            recipients = resolve_recipients(matched_person)
            status = (
                AttestationItem.Status.READY
                if recipients
                else AttestationItem.Status.PENDING
            )
        items.append(
            AttestationItem(
                campaign=campaign,
                page_start=start,
                page_end=end,
                extracted_name=name,
                extracted_address=address,
                matched_person=matched_person,
                suggested_person=suggested_person,
                match_score=match_score,
                suggestion_dismissed=suggestion_dismissed,
                matched_by_alias=matched_by_alias,
                recipients=recipients,
                status=status,
            )
        )
    AttestationItem.objects.bulk_create(items)
    return items
