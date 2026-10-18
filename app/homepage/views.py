from collections import namedtuple
from decimal import Decimal

from django.db.models import Count
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from homepage.timeline import timeline_for
from members import modules
from members.models import (
    Absence,
    Branch,
    Enrollment,
    ImportantDocument,
    Person,
    Role,
    SchoolYear,
    SectionEvent,
    TroopSettings,
)
from members.modules import module_enabled
from members.permissions import (
    ANIMATEUR_ROLES,
    ANIME,
    NOUVEAU,
    PARENT,
    can_access_finance,
    can_access_messaging,
    can_edit_section_agenda,
    can_manage_members,
    can_manage_unit,
    get_person,
    has_primary_role,
    visible_sections,
)

# A tile in the tools board. `details` are the lines under its title that say
# what is behind the tile — the next activities, the documents — with the
# first read as the headline fact and the rest dimmed by the template.
# `alert` marks the one tile that reports work rather than offering a tool;
# it carries its own treatment instead of borrowing the page's single dark
# note, which belongs to whichever group leads. `quiet` marks a door the
# reader normally does not open — the Django admin — so it sits in the mosaic
# without competing with the unit's daily work.
Tool = namedtuple(
    "Tool", "label url icon modal details alert quiet",
    defaults=((), False, False),
)


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

#: The federation's own mark for each branch, shipped in the vendored theme.
#: Same keys and the same rule as the colours: a branch no preset made has no
#: mark, because borrowing another branch's would name a branch it is not.
BRANCH_LOGOS = {
    "baladins": "vendor/template-unite/images/logos/logo_Baladins.png",
    "louveteaux": "vendor/template-unite/images/logos/logo_Louveteaux.png",
    "eclaireurs": "vendor/template-unite/images/logos/logo_Eclaireurs.png",
    "pionniers": "vendor/template-unite/images/logos/logo_Pionniers.png",
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
                "logo": BRANCH_LOGOS.get(branch.key),
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
            "logo": BRANCH_LOGOS.get(branch.key),
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


def _next_events(section, limit=2):
    """The next ``limit`` activities of ``section``, in reading order."""
    if section is None:
        return []
    return list(
        SectionEvent.objects.filter(
            section=section, start_date__gte=timezone.localdate()
        ).order_by("start_date", "start_time", "title")[:limit]
    )


def _event_lines(events):
    """Activities as a tile's detail lines: when, then what.

    The date leads because it is the fact the reader opens the agenda for; the
    title alone would say what happens without saying when.
    """
    if not events:
        return (_("Nothing scheduled"),)
    return tuple(
        f"{date_format(event.start_date, 'D j N')} · {event.title}"
        for event in events
    )


def _document_lines():
    """The newest documents as a tile's detail lines, or the empty-state line."""
    titles = tuple(ImportantDocument.objects.values_list("title", flat=True)[:2])
    return titles or (_("No documents available."),)


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


def _member_tools(
    user, person, sections, children, leads, own_section=None, own_events=None
):
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
    if (
        user.is_staff
        or can_manage_unit(user)
        or can_manage_members(user)
        or can_access_finance(user)
    ):
        leading = "unit"
    elif leads:
        leading = "sections"
    else:
        leading = "children"

    def priority(kind):
        if kind == leading:
            return 0
        return 2 if kind in ("account", "site") else 1

    # The two add tools render modal fragments, so the tile opens the system's
    # one dialog rather than navigating to a page that is only the inside of
    # one. The fourth item is that flag; the fifth is the detail lines under
    # the title.
    #
    # The key tool names the situation, not the key: a second parent recognises
    # "already registered" where "link with a key" only states the mechanism.
    # The detail says who did the registering, which the label cannot.
    add_items = [
        Tool(_("Add a child"), reverse("members:add_new_child"), "person-plus", True),
        Tool(
            _("Add an already registered child"),
            reverse("members:add_key_child"),
            "person-down",
            True,
            (_("by the other parent or a relative"),),
        ),
    ]
    agenda_items = (
        [Tool(_("Agenda"), reverse("members:agenda"), "calendar3", False)]
        if module_enabled(modules.AGENDA)
        else []
    )
    # A calendar with nobody on it is not the reader's work: until a child is
    # on the page the group leads with the two ways to add one, and the page's
    # one dark note goes to the first of them rather than to the agenda.
    no_children = not children
    parent_items = (
        add_items + agenda_items if no_children else agenda_items + add_items
    )
    # No entry for the children list itself: `members:child_list` renders an
    # HTMX fragment and answers 400 to a plain request, and the panels above
    # are that list anyway.
    if person is not None and (children or has_primary_role(user, (PARENT,))):
        groups.append(
            {
                "title": _("Your children"),
                "items": parent_items,
                "priority": priority("children"),
                "kind": "children",
                "no_children": no_children,
            }
        )

    # A unit admin's section tools are unit-wide work: the same three doors
    # reach every section, so they belong with the unit's tools rather than in
    # a "Your sections" group that implies the reader leads them. A section's
    # own animateur keeps the group, because for them it is their own work.
    admin_section_items = []
    if sections:
        section_items = []
        if can_access_messaging(user):
            section_items += [
                Tool(_("Send a message"), reverse("messaging:compose"), "send", False),
                Tool(
                    _("Message history"),
                    reverse("messaging:animateur_history"),
                    "chat-left-text",
                    False,
                ),
            ]
        if module_enabled(modules.AGENDA):
            section_items.append(
                Tool(
                    _("Section agendas"),
                    reverse("members:agenda"),
                    "calendar-week",
                    False,
                )
            )
        if section_items:
            if can_manage_unit(user):
                admin_section_items = section_items
            else:
                groups.append(
                    {
                        # An animateur's page is their one section; the group
                        # is their own work, not the unit's.
                        "title": _("Your section"),
                        "items": section_items,
                        "priority": priority("sections"),
                        "kind": "sections",
                    }
                )

    unit_items = []
    if can_manage_members(user):
        # A person created without a role — every child a parent registers —
        # starts as "Nouveau" (`Person.primary_role`'s default). Staff clear
        # that state by classifying the member on the edit page, so the count
        # is the same query the member list's role filter runs.
        nouveau_role = Role.objects.filter(short=NOUVEAU).first()
        nouveau_count = (
            Person.objects.filter(primary_role=nouveau_role).count()
            if nouveau_role
            else 0
        )
        if nouveau_count:
            unit_items.append(
                Tool(
                    _("New members"),
                    f"{reverse('members:admin_list')}?role={nouveau_role.pk}",
                    "person-exclamation",
                    False,
                    (_("%(count)s awaiting processing") % {"count": nouveau_count},),
                    True,
                )
            )
        unit_items.append(
            Tool(
                _("Member management"),
                reverse("members:admin_list"),
                "people",
                False,
            )
        )
    # The section tools moved here for a unit admin; they follow the member
    # list because writing to a section is the unit team's next most common
    # act.
    unit_items += admin_section_items
    if can_manage_unit(user):
        unit_items += [
            Tool(
                _("Section passage"),
                reverse("members:passage"),
                "arrow-left-right",
                False,
            ),
            Tool(
                _("Sections"),
                reverse("members:sections"),
                "diagram-3",
                False,
            ),
        ]
    if can_manage_members(user):
        unit_items.append(
            Tool(
                _("Import and export"),
                reverse("members:member_import"),
                "arrow-down-up",
                False,
            )
        )
    if user.is_staff:
        unit_items.append(
            Tool(
                _("Settings"),
                reverse("members:troop_settings"),
                "sliders2",
                False,
            )
        )
    # The two module tools sit together on the second-to-last line; the
    # advanced door and the email queue close the list, the queue last of all
    # because it is read when something has failed, not as a destination.
    if can_manage_unit(user) and module_enabled(modules.SIGNING):
        unit_items.append(
            Tool(
                _("Attestations"),
                reverse("attestations:index"),
                "file-earmark-check",
                False,
            )
        )
    if can_access_finance(user) and module_enabled(modules.FEES):
        unit_items.append(
            Tool(_("Membership fees"), reverse("finance:billing"), "cash-coin", False)
        )
    # The account menu is the way out alone, so the board carries the admin;
    # without this tile a superuser has no way to reach it. It is named for
    # what it holds rather than for where it comes from, and drawn quiet: it
    # is the door to advanced settings, not one of the unit's daily tools.
    if user.is_superuser:
        unit_items.append(
            Tool(
                _("Advanced settings"),
                reverse("admin:index"),
                "gear",
                False,
                (_("Technical settings, rarely needed"),),
                False,
                True,
            )
        )
    # Last of all: a queue is read when something failed, not a destination.
    if user.is_staff:
        unit_items.append(
            Tool(
                _("Email queue"),
                reverse("members:mail_queue"),
                "envelope",
                False,
            )
        )
    if unit_items:
        groups.append(
            {
                "title": _("The unit"),
                "items": unit_items,
                "priority": priority("unit"),
                "kind": "unit",
            }
        )

    account_items = [
        Tool(
            _("My profile"),
            reverse("members:profile", kwargs={"pk": user.pk}),
            "person-circle",
            False,
        ),
        Tool(
            _("My documents"),
            reverse("members:documents"),
            "folder2-open",
            False,
            _document_lines(),
        ),
    ]
    # A participant's page has no "Your children" group to carry the agenda,
    # so it joins their account tools. It takes the wide row under the profile
    # and documents: an activity line is longer than a document's name, and
    # the list of next activities is what most needs the room.
    if own_section is not None and module_enabled(modules.AGENDA):
        account_items.append(
            Tool(
                _("Agenda"),
                f"{reverse('members:agenda')}?section={own_section.pk}",
                "calendar3",
                False,
                _event_lines(own_events),
            )
        )
    groups.append(
        {
            "priority": priority("account"),
            "title": _("Your account"),
            "kind": "account",
            "items": account_items,
            # A participant's group pairs profile and documents rather than
            # giving the first tile the group's full width; the agenda takes
            # the wide row beneath them.
            "pair_first": own_section is not None,
        }
    )
    groups.append(
        {
            "priority": priority("site"),
            "title": _("The unit's page"),
            "kind": "site",
            "items": [
                Tool(_("Our unit"), reverse("unit_page"), "house-door", False),
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
            "member_is_child": False,
        }

    children = list(Person.objects.filter(as_child__parent=person))
    # A participant answers for themselves, so their page has no child or
    # section panels. Their own section still matters: it is where the
    # agenda lives, and the heading has to name it rather than a family.
    is_child = has_primary_role(user, (ANIME,))
    own_sections = list(visible_sections(user)) if is_child else []
    own_section = own_sections[0] if own_sections else None
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

    subjects = [
        child.get_section() for child in children if child.get_section()
    ] + led
    if own_section is not None:
        subjects.append(own_section)
    events = _upcoming_events(subjects)
    own_events = _next_events(own_section) if own_section is not None else []
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
                "branch_logo": (
                    BRANCH_LOGOS.get(section.branch.key)
                    if section and section.branch
                    else None
                ),
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
                    "branch_logo": (
                        BRANCH_LOGOS.get(section.branch.key)
                        if section.branch
                        else None
                    ),
                }
            )

    return {
        "member_panels": panels,
        "member_tools": _member_tools(
            user,
            person,
            readable,
            children,
            leads,
            own_section,
            own_events,
        ),
        # A reader who leads gets the unit's heading whether or not they also
        # have children: "Your children" over a section tile would be a lie,
        # and a leader with no section yet is still a leader. A participant
        # answers for no one, so the page names their own section instead of
        # asking them to look after children they do not have.
        "member_heading": (
            _("Your section")
            if own_section is not None
            else _("Your unit")
            if leads or is_child
            else _("Your children")
        ),
        # The greeting is the reader's own name, not a label over the heading:
        # the head reads "Vos enfants" then "Bonjour Marc. 3 enfants…" because
        # the page is a tool that knows who is holding it, and a page opener
        # that says so costs one line it already has room for.
        "member_first_name": person.first_name,
        "member_children": sum(1 for panel in panels if panel["kind"] == "child"),
        "member_is_child": is_child,
        # The empty state explains an empty account to a family. A reader whose
        # page is their tools is not missing anything, so it is not shown to
        # them — it would tell an administrator their unit is not attached.
        # A participant is not missing children either; only one without a
        # section has something to be told, and the template says it in the
        # agenda's own words instead of talking about a family.
        "member_show_empty": (
            not panels
            and not children
            and (
                (is_child and own_section is None)
                or not (
                    is_child
                    or user.is_staff
                    or can_manage_unit(user)
                    or can_manage_members(user)
                    or can_access_finance(user)
                )
            )
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
    the unit's own page; anyone signed in gets the tool. Members reach the
    unit's page at ``/unite/``.
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context.update(_member_context(self.request.user))
        else:
            school_year = SchoolYear.current()
            context["timeline"] = timeline_for(school_year)
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

    A member's ``/`` is the tool; this is the unit's own page, on a route
    that does not change shape with who is looking at it.
    """

    template_name = "homepage/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["timeline"] = timeline_for(SchoolYear.current())
        return context

