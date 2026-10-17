import json
import re
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
from django.views import View
from django.views.generic import TemplateView

from homepage.models import ImageAsset, SiteContent
from homepage.timeline import timeline_for
from members import modules
from members.models import (
    Absence,
    Branch,
    Enrollment,
    Person,
    SchoolYear,
    SectionEvent,
    TroopSettings,
)
from members.modules import module_enabled
from members.permissions import (
    ANIMATEUR_ROLES,
    PARENT,
    can_access_finance,
    can_access_messaging,
    can_edit_section_agenda,
    can_manage_unit,
    get_person,
    has_primary_role,
    visible_sections,
)

# Languages offered in the editor's language tabs (modeltranslation languages).
EDITOR_LANGUAGES = settings.MODELTRANSLATION_LANGUAGES

# Default markup seeded into the editor when a page/language was never edited,
# so first-time editing starts from the current look.
EDITOR_SEED_TEMPLATES = {
    SiteContent.Page.HOME: "homepage/snippets/home_default.html",
    SiteContent.Page.FAQ: "homepage/snippets/faq_default.html",
}

# GrapesJS exports its canvas wrapper as a literal <body> element. Injected
# mid-page, the browser merges that tag's attributes onto the real <body>,
# so wrapper styling (padding, background…) shifts the whole page chrome.
# The attribute part is quote-aware so a ">" inside an attribute cannot end
# the tag early.
_TAG_ATTRS = r"(?:\"[^\"]*\"|'[^']*'|[^>])"
_WRAPPER_OPEN_RE = re.compile(
    rf"^\s*(?:<html{_TAG_ATTRS}*>\s*)?<body{_TAG_ATTRS}*>", re.IGNORECASE
)
_WRAPPER_CLOSE_RE = re.compile(r"</body>\s*(?:</html>\s*)?$", re.IGNORECASE)
# CSS selectors that target the page itself rather than editor content.
_WRAPPER_SELECTORS = {"", "html", "body", "*"}


# The FAQ page renders a fixed hat banner above the edited content (like the
# other pages), so a `<header class="masthead">` card inside saved content
# duplicates the title. Stripped at both render and save; the Home page keeps
# its card (it is real content there, and "masthead" carries no styling of its
# own).
_FAQ_EMPTIED_CONTAINER_RE = re.compile(r"<div class=\"container row\">\s*</div>")


# These markers are matched with `str.find` rather than a regex to keep the pass
# linear. An unanchored `<header class="masthead">.*?</header>` walks to the end
# of the document from every position where the opening tag matches, so content
# that repeats that tag without ever closing it costs a scan per repetition.
# A cursor that only ever moves forward costs one pass whatever the input.
_MASTHEAD_OPEN = '<header class="masthead">'
_MASTHEAD_CLOSE = "</header>"
_HERO_ROW_OPEN = '<div class="container row">'
_HERO_ROW_CLOSE = "</div>"


def _cut_mastheads(html):
    """Drop every `<header class="masthead">…</header>` element from `html`."""
    pieces = []
    pos = 0
    while True:
        start = html.find(_MASTHEAD_OPEN, pos)
        if start == -1:
            break
        end = html.find(_MASTHEAD_CLOSE, start + len(_MASTHEAD_OPEN))
        if end == -1:
            # No close tag left in the document, so no later element has one
            # either — the same would-be match is not worth looking for again.
            break
        pieces.append(html[pos:start])
        pos = end + len(_MASTHEAD_CLOSE)
    pieces.append(html[pos:])
    return "".join(pieces)


def _split_hero(html):
    """The page's opening ``<header class="masthead">`` on its own, and the rest.

    The band is the unit introducing itself, so it stays above everything the
    homepage adds — the enrolment desk included — while remaining inside the
    content the editor owns and locks. Splitting it here is what lets the desk
    sit under the unit's own opening without the editor losing the hero.

    The band's own heading is promoted to the page's ``h1``, because a heading
    above the desk's question would otherwise leave the outline starting at
    level two. It keeps the ``h2`` class, so it still looks exactly as the
    troop's page drew it — only the level changes.

    Whether that promotion actually happened comes back with the markup. The
    band is the troop's to edit now, so it can arrive with its heading
    deleted, and the desk has to know: with no heading up there its question
    is the page's ``h1`` rather than a subheading.
    """
    if not html:
        return "", html, False
    start = html.find(_MASTHEAD_OPEN)
    if start == -1:
        return "", html, False
    close = html.find(_MASTHEAD_CLOSE, start + len(_MASTHEAD_OPEN))
    if close == -1:
        return "", html, False
    end = close + len(_MASTHEAD_CLOSE)
    hero, promoted = _promote_heading(html[start:end])
    return hero, (html[:start] + html[end:]).strip(), promoted


# The empty div the hero carries where the year-line goes. It is matched by its
# data attribute rather than by class order so an editor save that rearranges
# attributes cannot silently stop the line being drawn.
_TIMELINE_SLOT_RE = re.compile(
    r"<div\b[^>]*\bdata-home-timeline\b[^>]*>\s*</div>", re.IGNORECASE
)


def _with_timeline(hero):
    """Fill the authored year-line slot with the current school year's line.

    The hero is the troop's markup and the dates are configuration, so the
    slot stays empty in the editor and is filled here. A page that predates the
    slot is left alone rather than being given a second copy of the line, and a
    year with no activities removes the slot rather than leaving a gap.
    """
    timeline = timeline_for(SchoolYear.current())
    html = (
        render_to_string("homepage/snippets/timeline.html", {"timeline": timeline})
        if timeline
        else ""
    )
    return _TIMELINE_SLOT_RE.sub(lambda match: html, hero, count=1)


# A heading element, its attributes (quote-aware so `>` inside one cannot end
# the tag early) and its content, back-referenced so the pair matches.
_HEADING_RE = re.compile(
    r"<h([1-6])((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>(.*?)</h\1>",
    re.IGNORECASE | re.DOTALL,
)


def _promote_heading(html):
    """Rewrite the first heading in `html` as an ``h1``, style untouched.

    Returns the markup and whether there was a heading to promote — a hero
    the troop has stripped its heading from must not leave the page without
    one. Only the first heading is promoted, so a second one stays at its own
    level rather than competing for the outline's top.
    """
    promoted = []

    def swap(match):
        attrs = match.group(2)
        if "class=" not in attrs:
            attrs = ' class="h2"' + attrs
        promoted.append(True)
        return f"<h1{attrs}>{match.group(3)}</h1>"

    return _HEADING_RE.sub(swap, html, count=1), bool(promoted)


def _back_over_blanks(html, pos):
    """The index where the run of blanks ending at `pos` begins."""
    while pos > 0 and html[pos - 1].isspace():
        pos -= 1
    return pos


def _forward_over_blanks(html, pos):
    """The first index at or after `pos` holding something other than a blank."""
    while pos < len(html) and html[pos].isspace():
        pos += 1
    return pos


def _unwrap_legacy_hero(html):
    """Lift the hero out of the grid div the old home snippet wrapped it in.

    The hero is an ordinary block now; left inside that div the full-bleed photo
    would be inset by the grid's gutters and the card laid out as a flex item.
    Pages saved before the change are unwrapped at render and at save, the way
    the FAQ masthead is — so they look right before anyone edits them again.
    Only a div holding the hero and nothing else is removed, which is what the
    old snippet produced. Anything else is left alone.
    """
    if not html:
        return html
    pieces = []
    # Two cursors: `search` skips past a hero that turns out not to be wrapped,
    # while `copied` only advances once the text before it has been kept.
    copied = 0
    search = 0
    while True:
        start = html.find(_MASTHEAD_OPEN, search)
        if start == -1:
            break
        end = html.find(_MASTHEAD_CLOSE, start + len(_MASTHEAD_OPEN))
        if end == -1:
            break  # no close tag left, so no later element is closed either
        end += len(_MASTHEAD_CLOSE)
        search = end
        row_end = _back_over_blanks(html, start)
        row_start = row_end - len(_HERO_ROW_OPEN)
        if row_start < copied or not html.startswith(_HERO_ROW_OPEN, row_start):
            continue
        row_close = _forward_over_blanks(html, end)
        if not html.startswith(_HERO_ROW_CLOSE, row_close):
            continue
        pieces.append(html[copied:row_start])
        pieces.append(html[start:end])
        copied = row_close + len(_HERO_ROW_CLOSE)
        search = copied
    pieces.append(html[copied:])
    return "".join(pieces)


def _strip_legacy_faq_header(html):
    """Drop the pre-banner masthead card (and its emptied wrapper) from FAQ HTML."""
    if not html:
        return html
    html = _cut_mastheads(html)
    html = _FAQ_EMPTIED_CONTAINER_RE.sub("", html)
    return html.strip()


def _sanitize_html(html):
    """Unwrap the GrapesJS <body> wrapper from saved editor HTML."""
    if not html:
        return html
    html = _WRAPPER_OPEN_RE.sub("", html)
    html = _WRAPPER_CLOSE_RE.sub("", html)
    return html.strip()


def _page_has_content(page):
    """Whether one saved GrapesJS page holds components.

    GrapesJS 0.23 keeps a page's component tree on its frame — the saved
    project looks like ``{"pages": [{"frames": [{"component": {...}}]}]}``.
    Reading ``page["components"]`` instead, as this used to, finds nothing on
    real project data: every saved page was treated as empty, so the editor
    quietly threw away what had been saved and re-seeded the default look —
    and the next save then wrote that default back over the stored content.
    """
    if not isinstance(page, dict):
        return False
    if page.get("component"):
        return True  # project data that carries the tree on the page itself
    frames = page.get("frames")
    return isinstance(frames, list) and any(
        isinstance(frame, dict) and frame.get("component") for frame in frames
    )


def _has_content(project_json):
    """Whether a saved project actually holds editable content.

    An empty project ({"pages": []}, or pages whose frames carry nothing —
    e.g. from an abandoned editor session) must seed the canvas with the
    current page look instead of loading a blank project.
    """
    if not project_json:
        return False
    try:
        project = json.loads(project_json)
    except (TypeError, json.JSONDecodeError):
        return False
    pages = project.get("pages") if isinstance(project, dict) else None
    if not isinstance(pages, list):
        return False
    return any(_page_has_content(page) for page in pages)


def _sanitize_css(css):
    """Drop wrapper-targeting (html/body/*) rules from saved editor CSS.

    Scans rule by rule (brace-matching) so dropped rules cannot swallow the
    next one, and recurses into at-rule blocks (@media…) to catch responsive
    wrapper styling.
    """
    if not css:
        return css
    kept = []
    pos = 0
    while True:
        brace = css.find("{", pos)
        if brace == -1:
            kept.append(css[pos:])
            break
        selector = css[pos:brace]
        # Find the matching close brace, counting nested braces (@media…).
        depth = 1
        end = brace + 1
        while end < len(css) and depth:
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        selectors = [part.strip() for part in selector.split(",")]
        if selectors and all(part in _WRAPPER_SELECTORS for part in selectors):
            pass  # wrapper rule: drop selector + block entirely
        elif selector.strip().startswith("@"):
            kept.append(selector + "{" + _sanitize_css(css[brace + 1 : end - 1]) + "}")
        else:
            kept.append(selector + css[brace:end])
        pos = end
    return "".join(kept).strip()


def _edited_context(page):
    """Context entries for rendering a page's edited content (if any)."""
    content = SiteContent.get_content(page)
    if content is None:
        return {"page_html": None, "page_css": None}
    # modeltranslation resolves the active language, falling back to French
    # when the current language was never edited. Sanitizing at render as well
    # as at save, so already-stored content is corrected at display time too.
    html = _sanitize_html(content.html)
    html = _unwrap_legacy_hero(html)
    if page == SiteContent.Page.FAQ:
        html = _strip_legacy_faq_header(html)
    return {
        "page_html": html,
        "page_css": _sanitize_css(content.css),
    }


#: The federation's colour per branch, taken from the theme's own charter
#: (`.bg-ls-*` / `--bs-ls-*`). Keyed by ``Branch.key`` — the preset slug, which
#: the preset schema requires — and not by name, because a troop renames its
#: branches and the colour belongs to the branch the federation prints, not to
#: whatever the troop calls it.
#:
#: A branch with no key is one no preset made. It gets *no* colour rather than
#: a fallback: the rule beside the answer exists to say which branch, and a
#: rule in the page's own ink says nothing while looking like it does.
BRANCH_COLOURS = {
    "baladins": "#00a0de",
    "louveteaux": "#296f52",
    "eclaireurs": "#004f9f",
    "pionniers": "#d51317",
}

#: The same colour per branch written as *text*: the branch's own hue darkened
#: — in its own hue, never toward the charter blue, which drags Louveteaux's
#: green into a teal — until it is legible both as words on the desk's tint and
#: as the ground a white chip is read on. Measured, not chosen, and not the same
#: value as `BRANCH_COLOURS` for three of the four.
#:
#: Baladins is why this exists at all: #00a0de is a *light* blue, and light blues
#: cannot be small text on a pale ground however they are set. Left alone it
#: measures 2.4:1 as a branch name and 2.9:1 on a white chip — two failures thin
#: enough to ship. Every value here clears 4.9:1 on the tint it is written on and
#: carries white at 4.9:1 or better when it is a fill, which is what lets the
#: chosen year be a solid chip in the branch's colour rather than a ring around
#: one. Pionniers keeps 85% of itself, Louveteaux 90%, Éclaireurs all of it.
BRANCH_INKS = {
    "baladins": "#006085",
    "louveteaux": "#246248",
    "eclaireurs": "#004f9f",
    "pionniers": "#aa0f12",
}

#: The federation's own topping for each branch, in the branch's colour. The
#: theme's `.bg-topping-*` classes only reach the white cut; the answer sheet
#: wants the coloured 100px tile, which is shipped beside it in the vendored
#: theme. The tile is repeated behind the sentence at a strength that reads as
#: paper, not as a picture. Same keys and the same rule as the colours above:
#: a branch no preset made has no topping to wear, and borrowing another
#: branch's mark would name a branch it is not.
BRANCH_TOPPING_IMAGES = {
    "baladins": "vendor/template-unite/images/toppings/topping_Baladins_bleu_100.png",
    "louveteaux": "vendor/template-unite/images/toppings/topping_Louveteaux_vert_100.png",
    "eclaireurs": "vendor/template-unite/images/toppings/topping_Eclaireurs_bleu_100.png",
    "pionniers": "vendor/template-unite/images/toppings/topping_Pionniers_rouge_100.png",
}


def _desk_rows(school_year):
    """``(birth_year, branch)`` for every year some branch accepts, ascending.

    A child born in year Y is ``reference_year - Y`` on the troop's age
    reference day — the arithmetic :meth:`TroopSettings.age_at_reference` does
    from a birthday, read backwards. Where two branches claim the same age the
    first one in the editor's order wins, so the desk and the branch list can
    never name different sections for the same child.
    """
    reference_year = TroopSettings.get_settings().age_reference_date(school_year).year
    branches = Branch.objects.filter(
        min_age_dec_31__isnull=False, max_age_dec_31__isnull=False
    ).order_by("min_age_dec_31", "name")

    # Both bounds are ages a member can have: a branch holds
    # [min_age_dec_31, max_age_dec_31]. That is how `Person.age_fits_branch`
    # and the passage task read them, so the desk cannot disagree with the
    # enrolment logic about where a child belongs.
    #
    # It is also why the ranges a troop configures have to be the *effective*
    # ones — 6-7, 8-11, 12-15, 16-17 for the federation's four — rather than
    # the ages they are advertised as. A troop whose Baladins say 6-8 gives an
    # eight-year-old to Baladins and, if its Louveteaux start at 8, to
    # Louveteaux as well.
    by_year = {}
    for branch in branches:
        for year in range(
            reference_year - branch.max_age_dec_31,
            reference_year - branch.min_age_dec_31 + 1,
        ):
            by_year.setdefault(year, branch)
    return sorted(by_year.items())


def _desk_groups(rows):
    """The desk's rows, grouped under the branch each birth year lands in.

    A parent knows their child's age and mostly does not know which branch a
    name refers to, so the branch is the heading and its age range is the way
    in: four segments to scan rather than twelve bare years differing only in
    their last digit.

    Youngest branch first, and the youngest year first inside it — the order
    the branch list is itself read in. Across the whole rail that makes one run
    from the youngest child to the oldest, rather than a run that restarts at
    every segment.
    """
    groups = {}
    for year, branch in rows:
        groups.setdefault(
            branch.pk,
            {
                "branch": branch,
                "years": [],
                # The rail above the desk draws each branch as a segment as
                # long as the branch is: the span is its own age range, so a
                # troop that re-ages or drops a branch reshapes that rail
                # without anyone editing it.
                "span": branch.max_age_dec_31 - branch.min_age_dec_31 + 1,
                # Through the same map the answer band reads, so a branch can
                # never be one colour in the rail and another one below it.
                "colour": BRANCH_COLOURS.get(branch.key),
                # The same colour as words. A branch with no colour has no ink
                # either, and its name and years fall back to the page's own.
                "ink": BRANCH_INKS.get(branch.key),
            },
        )["years"].append(year)
    # `_desk_rows` hands the years over ascending. The rail draws a branch's
    # years the same way it draws the branches — youngest first — so the line
    # reads as one journey instead of restarting at every segment.
    for group in groups.values():
        group["years"].reverse()
    return sorted(
        groups.values(),
        key=lambda group: (group["branch"].min_age_dec_31 or 0, group["branch"].name),
    )


def _school_year_label(start_year):
    """``2026-2027``, the way a SchoolYear names its own range."""
    return f"{start_year}-{start_year + 1}"


def _desk_requested(value):
    """The birth year asked for, when it is one at all.

    Empty for anything that is not a run of digits, so a hand-edited query
    string lands on the unanswered desk rather than being quoted back at the
    visitor as though it were a birth year.
    """
    value = value or ""
    return value if value.isdigit() else ""


def _desk_answer(rows, requested, school_year):
    """The branch a birth year lands in, or None when it lands in no branch.

    Carries the scout years the child would spend there: a branch holds ages
    [min, max] inclusive, and the age is the one they have on the troop's
    reference day, so in the year starting ``Y`` it is ``Y - birth_year`` and
    they are in the branch while ``birth_year + min <= Y <= birth_year + max``.
    Years already behind us are cut, because a parent is asking where to
    register, not where the child would have been.
    """
    if not requested or not requested.isdigit():
        return None
    year = int(requested)
    for row_year, branch in rows:
        if row_year != year:
            continue
        first = max(school_year.name, year + branch.min_age_dec_31)
        last = year + branch.max_age_dec_31
        return {
            "year": year,
            "branch": branch,
            # The name carries its own span because it is the one word in the
            # sentence written in the branch's ink. Passing it in already
            # marked up keeps the tag out of the translated msgid: the catalogs
            # hold the sentence with a plain %(branch)s, so a translator reads
            # words and never HTML.
            "branch_html": format_html(
                '<span class="desk-answer-name">{}</span>', branch.name
            ),
            "min_age": branch.min_age_dec_31,
            "max_age": branch.max_age_dec_31,
            "colour": BRANCH_COLOURS.get(branch.key),
            "ink": BRANCH_INKS.get(branch.key),
            "topping_image": BRANCH_TOPPING_IMAGES.get(branch.key),
            "first_year": _school_year_label(first),
            "last_year": _school_year_label(last),
            "is_final_year": first == last,
        }
    return None


def _upcoming_events(sections):
    """The next activity of each of ``sections``, keyed by section id."""
    today = timezone.localdate()
    events = {}
    for section in sections:
        event = (
            SectionEvent.objects.filter(section=section, start_date__gte=today)
            .order_by("start_date", "start_time")
            .first()
        )
        if event is not None:
            events[section.pk] = event
    return events


def _absence_counts(events):
    """How many children are reported absent, per event id."""
    counts = {}
    for row in Absence.objects.filter(event_id__in=[e.pk for e in events]).values(
        "event_id"
    ):
        counts[row["event_id"]] = counts.get(row["event_id"], 0) + 1
    return counts


def _household_dues(children, school_year):
    """What the households these children belong to still owe this year.

    Fees are billed per *household*, not per child — the eldest pays in full
    and siblings are discounted — so this sums whole households rather than the
    children's own shares, which is the amount a parent is actually asked for.

    The grouping comes from :func:`finance.models.household_index` rather than
    from each balance row's ``household``, because that field is ``None`` for a
    household inferred from the postal address — which is most troops most of
    the time. Reading it directly would quietly report nothing owed to every
    family the unit never split out by hand.
    """
    from finance.models import CotisationConfig, calculate_balances, household_index

    index = household_index(school_year)
    billed = set()
    for child in children:
        group = index.get(child.pk)
        if group is not None:
            billed.update(member.pk for member in group["members"])
    if not billed:
        return None

    rows = [row for row in calculate_balances(school_year) if row["person_id"] in billed]
    owed = sum((row["balance"] for row in rows), Decimal("0"))
    if owed <= 0:
        return None
    return {
        "owed": owed,
        "late": any(row["is_late"] for row in rows),
        # What the parent is being asked for, and by when. A balance with no
        # deadline is the normal case, so the date is only shown when set.
        "deadline": CotisationConfig.get_for_year(school_year).late_deadline,
        "discounted": _siblings_are_discounted(school_year),
    }


def _siblings_are_discounted(school_year):
    """Whether this troop actually bills a second child less.

    Not assumed: a troop may set every rank the same price, in which case
    telling a parent that siblings get a discount would be a claim their own
    fee table contradicts.
    """
    from finance.models import FeeRule

    by_branch = {}
    for rule in FeeRule.objects.filter(
        school_year=school_year, member_type=FeeRule.MemberType.CHILD
    ):
        # `rank` is an integer field, so these keys are ints. `is not None`
        # rather than a truth test: a rank priced at zero is still a price.
        by_branch.setdefault(rule.branch_id, {})[rule.rank] = rule.amount
    return any(
        ranks.get(1) is not None
        and ranks.get(2) is not None
        and ranks[1] != ranks[2]
        for ranks in by_branch.values()
    )


def _member_tools(user, person, sections, children, leads):
    """The groups of links the reader's own tools are made of.

    Built here rather than in the template, because every entry is a promise
    that the page it points at will answer: each is gated on the same predicate
    its view enforces. Three dead links have shipped from this file already —
    the Pay button, "Add an activity", and both of them for the same reason —
    so the rule is that a link and its gate live in one place.

    This is why the header no longer carries a menu for a signed-in reader: the
    page is the menu, and a link that appears in both would be two places to
    keep honest.
    """
    groups = []

    # Which group leads. A reader's page should open on their own work: a staff
    # page that starts with "Your children" makes an administrator scroll past
    # a group that is not their job, and the header no longer offers a way
    # around it.
    if user.is_staff or can_manage_unit(user):
        leading = "unit"
    elif leads:
        leading = "sections"
    else:
        leading = "children"

    def priority(kind):
        if kind == leading:
            return 0
        return 2 if kind in ("account", "site") else 1

    parent_items = []
    if module_enabled(modules.AGENDA):
        parent_items.append(
            (_("Agenda"), reverse("members:agenda"), "calendar3", False)
        )
    # No entry for the children list itself: `members:child_list` renders an
    # HTMX fragment and answers 400 to a plain request, and the panels above
    # are that list anyway.
    #
    # The two add tools render modal fragments too, so the tile opens the
    # system's one dialog rather than navigating to a page that is only the
    # inside of one. The fourth item is that flag; a fixed-length tuple keeps
    # the template's unpacking simple.
    parent_items += [
        (
            _("Add a child"),
            reverse("members:add_new_child"),
            "person-plus",
            True,
        ),
        (
            _("Link a child with a key"),
            reverse("members:add_key_child"),
            "key",
            True,
        ),
    ]
    if person is not None and (children or has_primary_role(user, (PARENT,))):
        groups.append(
            {
                "title": _("Your children"),
                "items": parent_items,
                "priority": priority("children"),
                "kind": "children",
            }
        )

    if sections:
        section_items = []
        if can_access_messaging(user):
            section_items += [
                (_("Send a message"), reverse("messaging:compose"), "send", False),
                (
                    _("Message history"),
                    reverse("messaging:animateur_history"),
                    "chat-left-text",
                    False,
                ),
            ]
        if module_enabled(modules.AGENDA):
            section_items.append(
                (
                    _("Section agendas"),
                    reverse("members:agenda"),
                    "calendar-week",
                    False,
                )
            )
        if section_items:
            groups.append(
                {
                    # An animateur's page is their one section; staff may hold
                    # several. The title follows the role rather than the list
                    # length, because the list is only ever longer by mistake.
                    "title": (
                        _("Your section")
                        if has_primary_role(user, ANIMATEUR_ROLES)
                        else _("Your sections")
                    ),
                    "items": section_items,
                    "priority": priority("sections"),
                    "kind": "sections",
                }
            )

    unit_items = []
    if user.is_staff:
        unit_items += [
            (
                _("Member management"),
                reverse("members:admin_list"),
                "people",
                False,
            ),
            (
                _("Section passage"),
                reverse("members:passage"),
                "arrow-left-right",
                False,
            ),
            (
                _("Import and export"),
                reverse("members:member_import"),
                "arrow-down-up",
                False,
            ),
            (
                _("Settings"),
                reverse("members:troop_settings"),
                "sliders2",
                False,
            ),
            (
                _("Email queue"),
                reverse("members:mail_queue"),
                "envelope",
                False,
            ),
        ]
    if can_access_finance(user) and module_enabled(modules.FEES):
        unit_items.append(
            (_("Membership fees"), reverse("finance:billing"), "cash-coin", False)
        )
    if can_manage_unit(user) and module_enabled(modules.SIGNING):
        unit_items.append(
            (
                _("Attestations"),
                reverse("attestations:index"),
                "file-earmark-check",
                False,
            )
        )
    # The account menu is the way out alone, so the board carries the editor
    # and the admin; without these tiles a superuser has no link to either.
    if user.is_superuser:
        unit_items += [
            (
                _("Edit homepage"),
                reverse("homepage_editor"),
                "pencil-square",
                False,
            ),
            (
                _("Site administration"),
                reverse("admin:index"),
                "gear",
                False,
            ),
        ]
    if unit_items:
        groups.append(
            {
                "title": _("The unit"),
                "items": unit_items,
                "priority": priority("unit"),
                "kind": "unit",
            }
        )

    groups.append(
        {
            "priority": priority("account"),
            "title": _("Your account"),
            "kind": "account",
            "items": [
                (
                    _("My profile"),
                    reverse("members:profile", kwargs={"pk": user.pk}),
                    "person-circle",
                    False,
                ),
                (
                    _("My documents"),
                    reverse("members:documents"),
                    "folder2-open",
                    False,
                ),
            ],
        }
    )
    groups.append(
        {
            "priority": priority("site"),
            "title": _("The unit's page"),
            "kind": "site",
            "items": [
                (_("Our unit"), reverse("unit_page"), "house-door", False),
                (_("FAQ"), reverse("faq"), "question-circle", False),
            ],
        }
    )
    # A stable sort: groups of equal standing keep the order they are built in.
    groups.sort(key=lambda group: group["priority"])
    # The wide cluster and the dark tile go to the group with the most to offer,
    # not blindly to the first: a leader who also holds the attestations role
    # had a one-link "unit" group take the page's loudest tile while their
    # three-link sections group squeezed into a corner.
    featured = max(groups, key=lambda group: len(group["items"]))
    for group in groups:
        group["featured"] = group is featured
    return groups


def _member_context(user):
    """What a signed-in reader sees on ``/``, by role.

    The panel's subject follows the reader — a parent's children, a leader's own
    section — while the panel itself stays the same shape, so the page is
    predictable whatever the role. A leader has exactly one section; the query
    below takes the first even if bad data holds a second, because the page
    composes that section as a hero rather than a list. A reader who is both a
    parent and a leader gets both subjects, children first, rather than one
    silently winning.

    A panel is a thing the reader *answers for*, not a thing they may read. That
    is why the unit's staff get no section panels: they can read every agenda,
    but leading none of them made their page a wall of sections that said
    nothing about their work. Their page is their tools.
    """
    person = get_person(user)
    school_year = SchoolYear.current()
    if person is None or school_year is None:
        return {
            "member_panels": [],
            "member_heading": _("Your unit"),
            "member_first_name": "",
        }

    children = list(Person.objects.filter(as_child__parent=person))
    # An animateur's role is a *primary* one, which is the predicate the nav and
    # the messaging app already use. A plain parent is enrolled nowhere, so
    # reading visible_sections for them would hand back their children's
    # sections and give every parent a leader's panels.
    leads = can_manage_unit(user) or has_primary_role(user, ANIMATEUR_ROLES)
    readable = list(visible_sections(user)) if leads else []
    # An animateur leads exactly one section; the model can hold more only
    # through bad data, and the member homepage composes a leader's section as
    # a single hero tile rather than a list. Taking the first keeps the page
    # honest instead of growing a second panel from a state that cannot happen.
    # The agenda tools still reach every section the reader may read.
    led = [
        section
        for section in readable
        if can_edit_section_agenda(user, section)
    ][:1]

    events = _upcoming_events(
        [child.get_section() for child in children if child.get_section()] + led
    )
    absences = _absence_counts(list(events.values()))

    panels = []
    for child in children:
        section = child.get_section()
        event = events.get(section.pk) if section else None
        panels.append(
            {
                "kind": "child",
                "person": child,
                "section": section,
                "event": event,
                "absences": absences.get(event.pk, 0) if event else 0,
            }
        )

    if led:
        sizes = {
            row["section_id"]: row["n"]
            for row in Enrollment.objects.filter(
                school_year=school_year, section__in=led
            )
            .values("section_id")
            .annotate(n=Count("id"))
        }
        for section in led:
            event = events.get(section.pk)
            panels.append(
                {
                    "kind": "section",
                    "section": section,
                    "event": event,
                    "absences": absences.get(event.pk, 0) if event else 0,
                    "members": sizes.get(section.pk, 0),
                }
            )

    return {
        "member_panels": panels,
        "member_tools": _member_tools(user, person, readable, children, leads),
        # A reader who leads gets the unit's heading whether or not they also
        # have children: "Your children" over a section tile would be a lie,
        # and a leader with no section yet is still a leader.
        "member_heading": _("Your unit") if leads else _("Your children"),
        # The greeting is the reader's own name, not a label over the heading:
        # the head reads "Vos enfants" then "Bonjour Marc. 3 enfants…" because
        # the page is a tool that knows who is holding it, and a page opener
        # that says so costs one line it already has room for.
        "member_first_name": person.first_name,
        "member_children": sum(1 for panel in panels if panel["kind"] == "child"),
        # The empty state explains an empty account to a family. A reader whose
        # page is their tools is not missing anything, so it is not shown to
        # them — it would tell an administrator their unit is not attached.
        "member_show_empty": (
            not panels and not children and not (user.is_staff or can_manage_unit(user))
        ),
        # The treasurer's screens 404 for everyone else, so a parent who is not
        # one must not be handed a Pay button that dead-ends.
        "member_can_pay": can_access_finance(user),
        # Only a parent is asked for money, and only where the troop runs fees.
        "member_dues": (
            _household_dues(children, school_year)
            if children and module_enabled(modules.FEES)
            else None
        ),
    }


class HomePage(TemplateView):
    """The unit's page to a visitor, this reader's people to a member.

    One route, two surfaces: an anonymous visitor gets the enrolment desk and
    the page the troop edits; anyone signed in gets the tool. Members reach the
    troop's own page at ``/unite/``.
    """

    template_name = "homepage/home.html"

    def get(self, request, *args, **kwargs):
        # The desk swaps only its answer. Without HTMX the same link reloads the
        # page and renders identical markup, so nothing here depends on the swap.
        if request.headers.get("HX-Request") and "annee" in request.GET:
            return self._desk_partial(request)
        return super().get(request, *args, **kwargs)

    def _desk_partial(self, request):
        school_year = SchoolYear.current()
        rows = _desk_rows(school_year) if school_year else []
        return render(
            request,
            "homepage/snippets/desk_answer.html",
            {
                "desk_answer": _desk_answer(
                    rows, request.GET.get("annee"), school_year
                ),
                # Carried so the fragment can tell "nothing picked yet" from
                # "picked a year no branch takes" — the two say different
                # things, and the fragment is the page's only renderer.
                "desk_requested": _desk_requested(request.GET.get("annee")),
            },
        )

    def get_template_names(self):
        if self.request.user.is_authenticated:
            return ["homepage/member.html"]
        return [self.template_name]

    def _troop_page(self):
        """The troop's page, its opening band separated from the rest.

        The default is rendered here rather than by an `{% include %}` in the
        template, because the hero has to be lifted out of whichever markup the
        page happens to have — saved or seeded — for the desk to sit under it.
        """
        content = _edited_context(SiteContent.Page.HOME)
        html = content["page_html"]
        if html is None:
            html = render_to_string(
                EDITOR_SEED_TEMPLATES[SiteContent.Page.HOME], request=self.request
            )
        hero, rest, promoted = _split_hero(html)
        hero = _with_timeline(hero)
        return {
            "hero_html": hero,
            "hero_heading": promoted,
            "page_html": rest,
            "page_css": content["page_css"],
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context.update(_member_context(self.request.user))
        else:
            context.update(self._troop_page())
            school_year = SchoolYear.current()
            rows = _desk_rows(school_year) if school_year else []
            context["desk_rows"] = rows
            context["desk_groups"] = _desk_groups(rows)
            context["desk_answer"] = _desk_answer(
                rows, self.request.GET.get("annee"), school_year
            )
            context["desk_requested"] = _desk_requested(self.request.GET.get("annee"))
            # An explicit flag, not `user.is_authenticated` in the template:
            # UnitPage renders the same template and a signed-out reader there
            # is just as anonymous, which would put the desk on the troop's own
            # page as well as on the homepage.
            context["show_desk"] = True
        return context


class UnitPage(TemplateView):
    """The troop's public page, at its own URL, for anyone who wants it.

    A member's ``/`` is the tool; this is the page the troop edits, on a route
    that does not change shape with who is looking at it.
    """

    template_name = "homepage/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        content = _edited_context(SiteContent.Page.HOME)
        html = content["page_html"]
        if html is None:
            html = render_to_string(
                EDITOR_SEED_TEMPLATES[SiteContent.Page.HOME], request=self.request
            )
        hero, rest, promoted = _split_hero(html)
        context["hero_html"] = _with_timeline(hero)
        context["hero_heading"] = promoted
        context["page_html"] = rest
        context["page_css"] = content["page_css"]
        return context


class FAQ(TemplateView):
    template_name = "homepage/faq.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_edited_context(SiteContent.Page.FAQ))
        return context


class HomePageEditorView(UserPassesTestMixin, TemplateView):
    """Full-page GrapesJS editor for the Home/FAQ content, superuser-only."""

    template_name = "homepage/editor.html"

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request, *args, **kwargs):
        # Validate page/lang from query params before rendering.
        try:
            kwargs["page"] = SiteContent.Page(request.GET.get("page", "home"))
        except ValueError:
            return HttpResponseBadRequest("Invalid page.")
        kwargs["lang"] = request.GET.get("lang", settings.LANGUAGE_CODE)
        if kwargs["lang"] not in EDITOR_LANGUAGES:
            return HttpResponseBadRequest("Invalid language.")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = kwargs["page"]
        lang = kwargs["lang"]

        content = SiteContent.get_content(page)
        with override(lang):
            project_json = content.project_json if content else None
            if _has_content(project_json):
                seed_html = None
                # Hand the template a parsed object: json_script encodes what it
                # is given, so passing the stored JSON *string* would ship a
                # JSON-encoded string to the editor, and GrapesJS treats a
                # string project as "load from that storage key" — it clears
                # the canvas and finds nothing, leaving a blank editor.
                project_json = json.loads(project_json)
            else:
                # Seed the canvas with the default look, translated for the
                # editor language.
                project_json = None
                seed_html = render_to_string(
                    EDITOR_SEED_TEMPLATES[page], context={"user": self.request.user}
                )

        context["page"] = page
        context["lang"] = lang
        context["project_json"] = project_json
        context["seed_html"] = seed_html
        context["assets"] = [
            {"src": asset.file.url, "name": asset.original_name}
            for asset in ImageAsset.objects.all()
        ]
        context["editor_strings"] = {
            "uploadFailed": str(_("Image upload failed.")),
            "saveFailed": str(_("Save failed.")),
            "catStructure": str(_("Structure")),
            "catBasic": str(_("Basic")),
            "blockSection": str(_("Section")),
            "blockColumns": str(_("2 columns")),
            "blockColumns3": str(_("3 columns")),
            "blockHeading": str(_("Heading")),
            "blockText": str(_("Text")),
            "blockTextContent": str(_("Your text here.")),
            "blockImage": str(_("Image")),
            "blockButton": str(_("Button")),
            "blockButtonContent": str(_("Click here")),
            "blockDivider": str(_("Divider")),
            "sectorDimension": str(_("Dimensions")),
            "sectorTypography": str(_("Typography")),
            "sectorDecorations": str(_("Decorations")),
            "sectorExtra": str(_("Extra")),
        }
        return context


class HomePageEditorSaveView(UserPassesTestMixin, View):
    """Persist editor output: {page, lang, project, html, css} JSON body."""

    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            page = SiteContent.Page(data["page"])
            lang = data["lang"]
        except (json.JSONDecodeError, KeyError, ValueError):
            return HttpResponseBadRequest("Invalid payload.")
        if lang not in EDITOR_LANGUAGES:
            return HttpResponseBadRequest("Invalid language.")

        # Empty string => None so a cleared language falls back to French.
        # The project arrives as a parsed JSON object; re-serialize it so the
        # TextField holds real JSON (str(dict) would store a Python repr).
        project = data.get("project")
        html = _sanitize_html(data.get("html"))
        html = _unwrap_legacy_hero(html)
        css = _sanitize_css(data.get("css"))
        if page == SiteContent.Page.FAQ:
            html = _strip_legacy_faq_header(html)
        with override(lang):
            content, _ = SiteContent.objects.get_or_create(page=page)
            content.project_json = (
                json.dumps(project, ensure_ascii=False) if project else None
            )
            content.html = html or None
            content.css = css or None
            content.save()
        return JsonResponse({"ok": True})


class HomePageEditorAssetsView(UserPassesTestMixin, View):
    """List uploaded images (GET) and store a new upload (POST, multipart)."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request, *args, **kwargs):
        assets = [
            {"src": asset.file.url, "name": asset.original_name}
            for asset in ImageAsset.objects.all()
        ]
        return JsonResponse({"assets": assets})

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            return HttpResponseBadRequest("Missing file.")
        asset = ImageAsset(file=upload, original_name=upload.name)
        try:
            asset.full_clean()
        except ValidationError:
            return HttpResponseBadRequest("Invalid file.")
        asset.save()
        return JsonResponse({"src": asset.file.url, "name": asset.original_name})
