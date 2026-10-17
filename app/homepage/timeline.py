"""The public year-line: the September-July axis and the activities on it.

The axis is a real calendar, not eleven equal cells: the month ticks sit at
their months' actual midpoints and an activity sits at its start date's day
fraction, so a date in the second half of a month reads as one. A multi-day
activity is a bar from its first day to its last, inclusive.
"""

from datetime import date, timedelta

from django.utils.translation import get_language

#: The axis runs from September 1 to August 1, exclusive, which is the eleven
#: months the band's design has room for. The year in a school year's name is
#: the September the axis starts in.
AXIS_START_MONTH = 9
AXIS_END_MONTH = 8

#: A label's estimated width, as a percentage of the axis, is this much per
#: character. It is measured at the narrowest card (390px) and deliberately
#: over-estimates at wider sizes: a label that *might* touch its neighbour is
#: moved to the other side of the line rather than left to overlap.
LABEL_PERCENT_PER_CHAR = 2.0
LABEL_GAP = 1.5
LABEL_MAX_PERCENT = 47.0

#: Lowercase, short and language-native. The axis is a caption, not a table of
#: months; Django's date formats fall back to English abbreviations here, so
#: the three languages the product ships are written out.
_MONTHS = {
    "fr": (
        ("janv", "janvier"), ("févr", "février"), ("mars", "mars"),
        ("avr", "avril"), ("mai", "mai"), ("juin", "juin"),
        ("juil", "juillet"), ("août", "août"), ("sept", "septembre"),
        ("oct", "octobre"), ("nov", "novembre"), ("déc", "décembre"),
    ),
    "nl": (
        ("jan", "januari"), ("feb", "februari"), ("mrt", "maart"),
        ("apr", "april"), ("mei", "mei"), ("jun", "juni"),
        ("jul", "juli"), ("aug", "augustus"), ("sep", "september"),
        ("okt", "oktober"), ("nov", "november"), ("dec", "december"),
    ),
    "en": (
        ("jan", "January"), ("feb", "February"), ("mar", "March"),
        ("apr", "April"), ("may", "May"), ("jun", "June"),
        ("jul", "July"), ("aug", "August"), ("sep", "September"),
        ("oct", "October"), ("nov", "November"), ("dec", "December"),
    ),
}


def _language():
    code = (get_language() or "fr").split("-")[0]
    return code if code in _MONTHS else "fr"


def _month(month):
    short, full = _MONTHS[_language()][month - 1]
    return short, full


def axis_for(value):
    """The ``(September 1, August 1)`` axis a date belongs on."""
    start_year = value.year if value.month >= AXIS_START_MONTH else value.year - 1
    return date(start_year, AXIS_START_MONTH, 1), date(start_year + 1, AXIS_END_MONTH, 1)


def _axis(school_year):
    start_year = school_year.name
    start = date(start_year, AXIS_START_MONTH, 1)
    end = date(start_year + 1, AXIS_END_MONTH, 1)
    return start, end, (end - start).days


def _months(start, end, total_days):
    """One tick per month, placed at the month's true midpoint."""
    months = []
    cursor = start
    while cursor < end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        middle = (cursor - start).days + (next_month - cursor).days / 2
        months.append({"label": _month(cursor.month)[0],
                       "at": round(middle / total_days * 100, 3)})
        cursor = next_month
    return months


def _label_side(at, width, index, last_end):
    """Above or below, whichever side has room for the label's estimated span.

    The first activity goes above and the order then alternates, which is what
    keeps the September pair apart; a side that is still occupied is skipped.
    The two last-end cursors are enough because labels are visited by start.
    """
    end_aligned = at + width > 100
    span = (at - width, at) if end_aligned else (at, at + width)
    preferred = "above" if index % 2 == 0 else "below"
    other = "below" if preferred == "above" else "above"
    if span[0] >= last_end[preferred] + LABEL_GAP:
        side = preferred
    elif span[0] >= last_end[other] + LABEL_GAP:
        side = other
    else:
        side = preferred if last_end[preferred] <= last_end[other] else other
    last_end[side] = span[1]
    return side, end_aligned


def timeline_for(school_year):
    """The months and activities the homepage draws, or ``None`` for no year.

    Only the current school year's activities are returned: a troop may enter
    next year's dates, and they must not appear before their year begins.
    """
    if school_year is None:
        return None

    from homepage.models import TimelineActivity

    start, end, total_days = _axis(school_year)
    activities = TimelineActivity.objects.filter(
        start_date__gte=start, start_date__lt=end
    ).order_by("start_date", "id")

    events = []
    last_end = {"above": -100.0, "below": -100.0}
    for index, activity in enumerate(activities):
        name = activity.name
        at = (activity.start_date - start).days / total_days * 100
        last_day = activity.end_date or activity.start_date
        is_range = last_day > activity.start_date
        width = None
        if is_range:
            # Dates are inclusive: a camp from the 18th to the 25th covers
            # eight days, and its bar ends at the start of the 26th.
            span_end = min(last_day + timedelta(days=1), end)
            width = (span_end - activity.start_date).days / total_days * 100
        estimate = min(
            len(name) * LABEL_PERCENT_PER_CHAR + 1.0, LABEL_MAX_PERCENT
        )
        side, end_aligned = _label_side(at, estimate, index, last_end)
        events.append(
            {
                "name": name,
                "at": round(at, 3),
                "width": round(width, 3) if width is not None else None,
                "is_range": is_range,
                "side": side,
                "end_aligned": end_aligned,
                "month": _month(activity.start_date.month)[1],
            }
        )

    if not events:
        return None
    return {
        "months": _months(start, end, total_days),
        "events": events,
        # A label longer than this wraps on a phone; the chart takes the taller
        # axis step so the second line has somewhere to go.
        "tall": any(len(event["name"]) > 20 for event in events),
    }
