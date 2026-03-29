from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime

logger = get_task_logger(__name__)


@shared_task(name="create_year_task")
def create_year_task():
    from .models import SchoolYear

    current_year = datetime.now().year
    # Check if the next school year exists; if not, create it
    if not SchoolYear.objects.filter(name=current_year + 1).exists():
        SchoolYear.objects.create_year(current_year + 1)
        logger.info(f"Created school year {current_year + 1}")
    else:
        logger.info(f"School year {current_year + 1} already exists")


@shared_task(name="run_passage")
def run_passage():
    """
    Automated Passage task — runs on May 1st.

    For each active Animé (child) member:
    1. If Person.next_section is set, use that override.
    2. Otherwise, calculate based on age on Dec 31 of the next school year:
       - If child exceeds current Branch max_age, move to next Branch
         (ordered by min_age_dec_31). If multiple sections in that branch,
         assign to the alphabetically first section.
    3. If child exceeds the oldest Branch, change role to Animateur and
       remove ParentChild links (remove from household billing).
    """
    from .models import (
        Branch,
        Enrollment,
        ParentChild,
        Person,
        Role,
        SchoolYear,
        Section,
    )

    next_year = SchoolYear.next_school_year()
    if not next_year:
        logger.error("No next school year found. Create it first.")
        return

    # Dec 31 of the next school year
    dec_31 = datetime(next_year.name + 1, 12, 31).date()

    role_anime = Role.objects.get(short="e")
    role_animateur = Role.objects.get(short="a")

    children = Person.objects.filter(
        primary_role=role_anime, status="a"
    ).select_related("primary_role")

    branches = list(Branch.objects.order_by("min_age_dec_31"))
    if not branches:
        logger.warning("No branches defined. Passage skipped.")
        return

    oldest_branch = branches[-1]

    promoted = 0
    aged_out = 0

    for child in children:
        if not child.birthday:
            logger.warning(f"Skipping {child}: no birthday set")
            continue

        age_on_dec_31 = (dec_31 - child.birthday).days // 365

        # Check for manual override
        if child.next_section:
            Enrollment.objects.update_or_create(
                user=child,
                school_year=next_year,
                defaults={"section": child.next_section},
            )
            child.next_section = None
            child.save(update_fields=["next_section"])
            promoted += 1
            continue

        # Find current enrollment
        current_enrollment = Enrollment.objects.filter(
            user=child,
            school_year=SchoolYear.current(),
        ).select_related("section__branch").first()

        if not current_enrollment:
            logger.warning(f"Skipping {child}: no enrollment for current year")
            continue

        current_branch = current_enrollment.section.branch

        # Check if child still fits in current branch
        if current_branch.max_age_dec_31 is not None and age_on_dec_31 <= current_branch.max_age_dec_31:
            # Stay in same section
            Enrollment.objects.update_or_create(
                user=child,
                school_year=next_year,
                defaults={"section": current_enrollment.section},
            )
            continue

        # Find next branch by age
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

        # Assign alphabetically first section in target branch
        target_section = Section.objects.filter(branch=target_branch).order_by("name").first()
        if not target_section:
            logger.warning(f"No section found for branch {target_branch}")
            continue

        Enrollment.objects.update_or_create(
            user=child,
            school_year=next_year,
            defaults={"section": target_section},
        )
        promoted += 1
        logger.info(f"{child} → {target_section}")

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

        from post_office import mail

        for email in recipients:
            mail.send(
                recipients=[email],
                template="archive_deletion_warning",
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
