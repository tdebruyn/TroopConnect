"""Telling a section that one of its children will not be coming.

An absence is recorded in the agenda, but its whole point is the email it
produces: the people running the activity read the section's mailbox, not the
site. That hand-off lives here, apart from the view, so the recipient, the
fallback and the shape of the notice are in one readable place.
"""

from django.utils import formats, translation
from django.utils.translation import gettext_lazy as _

from .mail import absolute_url, resolve_language, send_templated
from .models import TroopSettings


def section_recipients(section):
    """The addresses a notice for ``section`` goes to; empty when there are none.

    The section's own address comes first — a section mailbox outlives the
    leader who happens to run the section this year. It falls back exactly as
    that field's own help text says it does: an empty section address leaves
    the troop's reply-to address in charge, so a troop that configured nothing
    per section still hears about the absences of its children. With neither
    set, the absence is still recorded — it simply does not travel.
    """
    if section is not None and section.email:
        return [section.email]

    reply_to = TroopSettings.get_settings().reply_to_email
    return [reply_to] if reply_to else []


def activity_when(event, language):
    """The activity's day — or day range — written out in ``language``.

    Rendered here rather than left to the template because post_office renders
    the template in the *recipient's* language while a context value is already
    a string: left to the template, the date would come out in whatever
    language the reporting parent happened to be reading the site in.
    """
    with translation.override(language):
        when = formats.date_format(event.start_date, "DATE_FORMAT")
        if event.is_multi_day:
            last = formats.date_format(event.last_date, "DATE_FORMAT")
            when = f"{when} – {last}"

    if event.time_range:
        when = f"{when} · {event.time_range}"
    return when


def notify_section(absence, url):
    """Send the notice for ``absence``; returns the queued row, or None.

    None means the troop has no address to send it to — the absence itself is
    unaffected either way, so a caller has nothing to undo.
    """
    event = absence.event
    recipients = section_recipients(event.section)
    if not recipients:
        return None

    language = resolve_language(None)
    return send_templated(
        template="absence_reported",
        recipients=recipients,
        language=language,
        context={
            "child_name": str(absence.child),
            "activity_title": event.title,
            "activity_date": activity_when(event, language),
            "section_name": event.section.name,
            "reason": absence.reason,
            "reporter_name": str(absence.reported_by or _("A parent")),
            "url": absolute_url(url),
        },
    )
