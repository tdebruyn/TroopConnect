from datetime import datetime

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


# Passage runs for the upcoming school year on the day the troop configured
# (TroopSettings.passage_month/day — May 1 by default). The task is scheduled
# DAILY (not once a year): Celery beat's catch-up is unreliable for yearly
# tasks, and a worker/beat outage on the trigger day would otherwise skip the
# passage for a full year. Daily scheduling is safe because run_passage
# self-guards with a date gate + an idempotency marker, so it only actually
# promotes children once per target school year — and if the trigger day was
# missed, it performs the passage at the next Celery start instead. Setting
# passage_mode to "manual" switches the automatic run off entirely; staff then
# run the same code on demand from the passage page.


def _today():
    """Current date, wrapped so tests can patch it deterministically."""
    return datetime.now().date()


@shared_task(name="create_year_task")
def create_year_task():
    """Ensure the current school year and the one following it exist.

    A SchoolYear is named by its start calendar year (e.g. name=2026 →
    "2026-2027", Aug 2026–Jul 2027). The "current" school year is the one whose
    configured range contains today — see ``TroopSettings.school_year_for``.

    Computing it from the date (rather than relying on SchoolYear.current())
    means we create the current year even when no rows exist yet — and the next
    year is ``current_start + 1``, NOT ``calendar_year + 1``: from January
    through July the calendar year is already the next school year's start
    year, so using the raw calendar year is off by one (it created "2027-2028"
    on 2026-07-23 instead of "2026-2027").

    The work itself is in ``members.setup.ensure_school_years``, which
    ``manage.py setup`` calls on a fresh database too — the nightly task and a
    first run have to agree about where the year boundary is, and the only way
    to guarantee that is to run the same code.
    """
    from .setup import ensure_school_years

    ensure_school_years(_today())


def _place(child, school_year, section):
    """Enrol the child in ``section`` for ``school_year``.

    Also forgets the two things that belonged to an earlier decision: the
    "needs review" flag and the manual override that has now been applied.
    """
    from .models import Enrollment

    Enrollment.objects.update_or_create(
        user=child,
        school_year=school_year,
        defaults={"section": section},
    )
    child.next_section = None
    child.passage_review = ""
    child.save(update_fields=["next_section", "passage_review"])


def _flag(child, reason):
    """Mark the child as needing a human decision, leaving them where they are."""
    child.passage_review = reason
    child.save(update_fields=["passage_review"])


@shared_task(name="run_passage")
def run_passage(force=False):
    """
    Passage task — moves active Animé (children) into their next section for
    the upcoming school year.

    Scheduled DAILY (not once a year). Celery beat's catch-up is unreliable for
    yearly tasks, and a worker outage on the trigger day would otherwise skip
    the passage for a whole year, so this task runs every day and decides
    itself whether work is due via two guards:

      1. Date gate — only act on/after the troop's passage day (May 1 by
         default) for the target school year — see
         ``TroopSettings.passage_datetime``, which reads that day from the
         settings — so the daily run doesn't promote children the moment the
         next SchoolYear is created.
      2. Marker gate — TroopSettings.last_passage_school_year records the target
         year already processed; once set the task is a no-op. This is what
         guarantees "run at next start if the trigger day was missed": when
         Celery comes back, the daily tick sees the marker unset for the
         current target year and performs the passage exactly once.

    A troop that would rather move children up by hand sets ``passage_mode`` to
    ``manual``, which switches the automatic run off entirely; staff then run
    the same code on demand from the passage page, which passes ``force``.

    ``force=True`` skips the three automatic guards below. They exist to stop
    the *daily* task acting too early or twice, not to overrule someone who has
    just pressed the button. The marker is still written, so forcing a run does
    not make the nightly one repeat it.

    Where each member goes:
      - ``Person.next_section`` wins: that is the troop's own decision for that
        member, and it is consumed as it is applied.
      - Otherwise the current branch decides. While the member still fits it —
        within its ``max_age_dec_31`` on the troop's age reference day — they
        stay in their section. A branch that sets no maximum age keeps them.
      - When they have outgrown it, the branch's ``promotes_to`` names where
        they go. That link is data, so branches may be renamed, reordered or
        given a shape that is not a single age ladder without touching this
        code.
      - A branch with no ``promotes_to``: the top of the ladder (``is_top``)
        graduates its members out of the sections — to animators, unless the
        troop asked to review them — while any other branch cannot be followed
        at all, so its members are flagged for review rather than moved
        somewhere arbitrary.
      - The section found in the target branch has to suit the member: a
        section declaring a sex takes only members of that sex, and a member
        whose own sex is unknown is only placed in a mixed section.

    Anything the task cannot decide sets ``Person.passage_review`` with the
    reason and leaves the member alone. Flagged members are listed on the staff
    passage page, and the next run reconsiders them — as does a
    ``next_section`` override set by hand in the meantime.
    """
    from .models import (
        PASSAGE_MODE_MANUAL,
        Enrollment,
        ParentChild,
        Person,
        Role,
        SchoolYear,
        TroopSettings,
    )

    troop = TroopSettings.get_settings()

    # --- Guards 0-2: what keeps the *daily* run in check -------------------
    if not force:
        if troop.passage_mode == PASSAGE_MODE_MANUAL:
            logger.info("Passage mode is manual; the task leaves the passage alone")
            return

    target_year = SchoolYear.next_school_year()
    if not target_year:
        logger.error("No next school year found. Create it first.")
        return

    if not force:
        # Guard 1: date gate. Only run on/after the configured passage day for
        # the target year; the gate is day-granular, and the helper is what
        # knows the passage day is the one in that year's start calendar year.
        today = _today()
        trigger = troop.passage_datetime(target_year).date()
        if today < trigger:
            logger.info(
                f"Passage not due yet (today {today} < {trigger} for "
                f"school year {target_year.name}); skipping"
            )
            return

        # Guard 2: marker gate (idempotency / catch-up).
        if troop.last_passage_school_year == target_year.name:
            logger.info(
                f"Passage already applied for school year {target_year.name}; skipping"
            )
            return

    current_year = SchoolYear.current()

    role_anime = Role.objects.get(short="e")
    role_animateur = Role.objects.get(short="a")

    children = Person.objects.filter(
        primary_role=role_anime, status="a"
    ).select_related("primary_role")

    promoted = 0
    aged_out = 0
    flagged = 0

    for child in children:
        if not child.birthday:
            logger.warning(f"Skipping {child}: no birthday set")
            continue

        # --- The troop's own decision for this member, if there is one -----
        if child.next_section:
            _place(child, target_year, child.next_section)
            promoted += 1
            continue

        current_enrollment = Enrollment.objects.filter(
            user=child,
            school_year=current_year,
        ).select_related("section__branch").first()

        if not current_enrollment or not current_enrollment.section.branch:
            logger.warning(f"Skipping {child}: no branch enrolled for the current year")
            continue

        current_branch = current_enrollment.section.branch
        age_at_reference = troop.age_at_reference(child, target_year)

        # Still within the branch's age range → they stay where they are. A
        # branch that declares no maximum age has not said they outgrew it.
        if (
            current_branch.max_age_dec_31 is None
            or age_at_reference <= current_branch.max_age_dec_31
        ):
            _place(child, target_year, current_enrollment.section)
            continue

        next_branch = current_branch.promotes_to
        if next_branch is None:
            if not current_branch.is_top:
                _flag(child, Person.PassageReview.NO_NEXT_BRANCH)
                flagged += 1
                logger.warning(f"{child}: {current_branch} has no next branch")
                continue

            if not troop.top_branch_graduates_become_leaders:
                _flag(child, Person.PassageReview.GRADUATION)
                flagged += 1
                logger.info(f"{child} graduated from {current_branch}; flagged")
                continue

            # Out of the ladder for good: animators are no longer billed as
            # part of a household, so the parent links go too.
            child.primary_role = role_animateur
            child.save(update_fields=["primary_role"])
            ParentChild.objects.filter(child=child).delete()
            aged_out += 1
            logger.info(f"{child} graduated → Animateur")
            continue

        target_section = next_branch.section_for(child.sex)
        if target_section is None:
            _flag(child, Person.PassageReview.NO_SECTION)
            flagged += 1
            logger.warning(f"{child}: no {next_branch} section suits them")
            continue

        _place(child, target_year, target_section)
        promoted += 1
        logger.info(f"{child} → {target_section}")

    # --- Record the marker so passage runs at most once per target year ----
    troop.last_passage_school_year = target_year.name
    troop.save(update_fields=["last_passage_school_year"])

    logger.info(
        f"Passage complete: {promoted} promoted, {aged_out} graduated, "
        f"{flagged} flagged for review"
    )
    return {"promoted": promoted, "aged_out": aged_out, "flagged": flagged}


@shared_task(name="notify_upcoming_deletion")
def notify_upcoming_deletion():
    """
    Send notification emails to users who will be deleted in 1 month
    (archived one month short of the troop's retention period).

    The retention period is TroopSettings.archive_retention_years, 5 by
    default. Runs daily via Celery beat.
    """
    from django.utils import timezone as tz

    from .models import Account, Person, TroopSettings

    troop = TroopSettings.get_settings()
    today = tz.now().date()
    # Only notify those whose warning day is today: the helper places it
    # ARCHIVE_WARNING_DAYS before the retention cut-off.
    to_notify = Person.objects.filter(
        status="ar",
        archived_date=troop.archive_warning_cutoff(today),
    )

    notified = 0
    for person in to_notify:
        # Try to find linked parent(s) with accounts first
        parent_accounts = Account.objects.filter(
            person__in=person.parents.all(),
        )
        recipients = list(parent_accounts.values_list("email", flat=True))

        # Fallback: notify the person's own account if they have one
        if not recipients and hasattr(person, "account"):
            recipients = [person.account.email]

        if not recipients:
            logger.warning(f"No email recipient for archived {person}")
            continue

        from django.conf import settings

        from .mail import send_templated
        from .models import Account

        for email in recipients:
            acct = Account.objects.filter(email=email).first()
            send_templated(
                recipients=[email],
                template="archive_deletion_warning",
                language=acct.preferred_language if acct else settings.LANGUAGE_CODE,
                context={
                    "person_name": str(person),
                    "deletion_date": troop.archive_purge_date(
                        person.archived_date
                    ).isoformat(),
                },
            )
            notified += 1

    logger.info(f"Sent {notified} deletion warnings")
    return notified


@shared_task(name="delete_archived_users")
def delete_archived_users():
    """
    Permanently delete users archived for at least the troop's retention
    period (TroopSettings.archive_retention_years, 5 by default).
    Runs daily via Celery beat.
    """
    from django.utils import timezone as tz

    from .models import Person, TroopSettings

    troop = TroopSettings.get_settings()
    today = tz.now().date()
    cutoff = troop.archive_purge_cutoff(today)
    to_delete = Person.objects.filter(
        status="ar",
        archived_date__lte=cutoff,
    )

    count = to_delete.count()
    if count:
        to_delete.delete()
        logger.info(
            f"Deleted {count} users archived for "
            f"{troop.archive_retention_years}+ years"
        )
    else:
        logger.info("No archived users to delete")
    return count
