from datetime import date, datetime

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


# Passage is intended to run on May 1 each year, for the upcoming school year.
# The task is scheduled DAILY (not once a year): Celery beat's catch-up is
# unreliable for yearly tasks, and a worker/beat outage on the trigger day
# would otherwise skip the passage for a full year. Daily scheduling is safe
# because run_passage self-guards with a date gate + an idempotency marker, so
# it only actually promotes children once per target school year — and if May 1
# was missed, it performs the passage at the next Celery start instead.
PASSAGE_TRIGGER_MONTH = 5
PASSAGE_TRIGGER_DAY = 1


def _today():
    """Current date, wrapped so tests can patch it deterministically."""
    return datetime.now().date()


@shared_task(name="create_year_task")
def create_year_task():
    """Ensure the current school year and the one following it exist.

    A SchoolYear is named by its start calendar year (e.g. name=2026 →
    "2026-2027", Aug 2026–Jul 2027). The "current" school year is the one whose
    [start_date, end_date] range contains today; its start year is the calendar
    year if today is on/after Aug 1, otherwise the previous calendar year.

    Computing it from the date (rather than relying on SchoolYear.current())
    means we create the current year even when no rows exist yet — and the next
    year is ``current_start + 1``, NOT ``calendar_year + 1``: from January
    through July the calendar year is already the next school year's start
    year, so using the raw calendar year is off by one (it created "2027-2028"
    on 2026-07-23 instead of "2026-2027").
    """
    from .models import SchoolYear

    today = _today()
    # School year containing today (Aug 1 → Jul 31).
    current_start = today.year if today >= date(today.year, 8, 1) else today.year - 1

    # Ensure the current school year exists.
    if not SchoolYear.objects.filter(name=current_start).exists():
        SchoolYear.objects.create_year(current_start)
        logger.info(f"Created current school year {current_start}")
    else:
        logger.info(f"Current school year {current_start} already exists")

    # Ensure the next school year exists too.
    next_start_year = current_start + 1
    if not SchoolYear.objects.filter(name=next_start_year).exists():
        SchoolYear.objects.create_year(next_start_year)
        logger.info(f"Created school year {next_start_year}")
    else:
        logger.info(f"School year {next_start_year} already exists")


@shared_task(name="run_passage")
def run_passage():
    """
    Automated Passage task — promotes active Animé (children) into their next
    section/branch for the upcoming school year.

    Scheduled DAILY (not once a year). Celery beat's catch-up is unreliable for
    yearly tasks, and a worker outage on the trigger day would otherwise skip
    the passage for a whole year, so this task runs every day and decides
    itself whether work is due via two guards:

      1. Date gate — only act on/after May 1 of the target school year's start
         calendar year, so the daily run doesn't promote children the moment
         the next SchoolYear is created.
      2. Marker gate — SiteSettings.last_passage_school_year records the target
         year already processed; once set the task is a no-op. This is what
         guarantees "run at next start if the trigger day was missed": when
         Celery comes back, the daily tick sees the marker unset for the
         current target year and performs the passage exactly once.

    Promotion logic per active child:
      - If Person.next_section is set, use that override (then clear it).
      - Otherwise compute the age on Dec 31 of the next school year:
        * exceeding the current Branch max age → next Branch (ordered by
          min_age_dec_31); with several sections, the alphabetically first.
        * exceeding the oldest Branch → switch role to Animateur and remove
          ParentChild links (out of household billing).
    """
    from .models import (
        Branch,
        Enrollment,
        ParentChild,
        Person,
        Role,
        SchoolYear,
        Section,
        SiteSettings,
    )

    target_year = SchoolYear.next_school_year()
    if not target_year:
        logger.error("No next school year found. Create it first.")
        return

    # --- Guard 1: date gate ------------------------------------------------
    # Only run on/after May 1 of the target year's start calendar year.
    today = _today()
    trigger = date(target_year.name, PASSAGE_TRIGGER_MONTH, PASSAGE_TRIGGER_DAY)
    if today < trigger:
        logger.info(
            f"Passage not due yet (today {today} < {trigger} for "
            f"school year {target_year.name}); skipping"
        )
        return

    # --- Guard 2: marker gate (idempotency / catch-up) ---------------------
    site_settings = SiteSettings.get_settings()
    if site_settings.last_passage_school_year == target_year.name:
        logger.info(
            f"Passage already applied for school year {target_year.name}; skipping"
        )
        return

    # Dec 31 of the next school year (starts Aug `name`, ends Jul `name + 1`)
    dec_31 = date(target_year.name + 1, 12, 31)
    current_year = SchoolYear.current()

    role_anime = Role.objects.get(short="e")
    role_animateur = Role.objects.get(short="a")

    children = Person.objects.filter(
        primary_role=role_anime, status="a"
    ).select_related("primary_role")

    branches = list(Branch.objects.order_by("min_age_dec_31"))
    if not branches:
        logger.warning("No branches defined. Passage skipped.")
        return

    promoted = 0
    aged_out = 0

    for child in children:
        if not child.birthday:
            logger.warning(f"Skipping {child}: no birthday set")
            continue

        age_on_dec_31 = (dec_31 - child.birthday).days // 365

        # Manual override
        if child.next_section:
            Enrollment.objects.update_or_create(
                user=child,
                school_year=target_year,
                defaults={"section": child.next_section},
            )
            child.next_section = None
            child.save(update_fields=["next_section"])
            promoted += 1
            continue

        current_enrollment = Enrollment.objects.filter(
            user=child,
            school_year=current_year,
        ).select_related("section__branch").first()

        if not current_enrollment:
            logger.warning(f"Skipping {child}: no enrollment for current year")
            continue

        current_branch = current_enrollment.section.branch

        # Child still fits in current branch → stay in the same section
        if (
            current_branch.max_age_dec_31 is not None
            and age_on_dec_31 <= current_branch.max_age_dec_31
        ):
            Enrollment.objects.update_or_create(
                user=child,
                school_year=target_year,
                defaults={"section": current_enrollment.section},
            )
            continue

        # Find the branch matching the child's age
        target_branch = None
        for branch in branches:
            if branch.min_age_dec_31 is not None and branch.max_age_dec_31 is not None:
                if branch.min_age_dec_31 <= age_on_dec_31 <= branch.max_age_dec_31:
                    target_branch = branch
                    break

        if target_branch is None:
            # Child exceeds all branches → age out to Animateur
            child.primary_role = role_animateur
            child.save(update_fields=["primary_role"])
            ParentChild.objects.filter(child=child).delete()
            aged_out += 1
            logger.info(f"{child} aged out → Animateur")
            continue

        # Assign the alphabetically first section in the target branch
        target_section = Section.objects.filter(branch=target_branch).order_by("name").first()
        if not target_section:
            logger.warning(f"No section found for branch {target_branch}")
            continue

        Enrollment.objects.update_or_create(
            user=child,
            school_year=target_year,
            defaults={"section": target_section},
        )
        promoted += 1
        logger.info(f"{child} → {target_section}")

    # --- Record the marker so passage runs at most once per target year ----
    site_settings.last_passage_school_year = target_year.name
    site_settings.save(update_fields=["last_passage_school_year"])

    logger.info(f"Passage complete: {promoted} promoted, {aged_out} aged out")
    return {"promoted": promoted, "aged_out": aged_out}


@shared_task(name="notify_upcoming_deletion")
def notify_upcoming_deletion():
    """
    Send notification emails to users who will be deleted in 1 month
    (archived for 4 years 11 months). Runs daily via Celery beat.
    """
    from datetime import timedelta

    from django.utils import timezone as tz

    from .models import Account, Person

    today = tz.now().date()
    # Users archived 4 years and 11 months ago (will hit 5 years in ~30 days)
    notify_threshold = today - timedelta(days=5 * 365 - 30)
    # Only notify those that haven't been notified yet (no account = skip)
    to_notify = Person.objects.filter(
        status="ar",
        archived_date=notify_threshold,
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
        from post_office import mail

        from .models import Account

        for email in recipients:
            acct = Account.objects.filter(email=email).first()
            mail.send(
                recipients=[email],
                template="archive_deletion_warning",
                language=(acct.preferred_language if acct else None) or settings.LANGUAGE_CODE,
                context={
                    "person_name": str(person),
                    "deletion_date": (person.archived_date + timedelta(days=5 * 365)).isoformat(),
                },
            )
            notified += 1

    logger.info(f"Sent {notified} deletion warnings")
    return notified


@shared_task(name="delete_archived_users")
def delete_archived_users():
    """
    Permanently delete users archived for 5+ consecutive years.
    Runs daily via Celery beat.
    """
    from datetime import timedelta

    from django.utils import timezone as tz

    from .models import Person

    today = tz.now().date()
    cutoff = today - timedelta(days=5 * 365)
    to_delete = Person.objects.filter(
        status="ar",
        archived_date__lte=cutoff,
    )

    count = to_delete.count()
    if count:
        to_delete.delete()
        logger.info(f"Deleted {count} users archived for 5+ years")
    else:
        logger.info("No archived users to delete")
    return count
