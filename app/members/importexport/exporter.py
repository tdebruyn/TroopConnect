"""The database read out into the shared column format.

Two tables come out of this module: one row per person, and — while the fees
module is on — one row per recorded payment, plus the year's balances appended
to the member rows.

The records this builds are what :mod:`members.importexport.importer` reads
back, so a value written here has to be a value the importer accepts. They are
ordered by their own contents rather than by anything the database assigns,
which is what makes exporting, importing and exporting again produce the same
file: a primary key is not the same in the second database, but a last name is.
"""

from members.models import Enrollment, Person, SchoolYear


def _external_id(person):
    """A person's identifier in the file.

    A member nobody has given an external id to falls back to their own UUID.
    That is what lets a re-import of an export recognise them: matched by name
    alone they would be created a second time, and matched by email a member
    who has none, or who has changed address, would be too.
    """
    return person.external_id or str(person.pk)


def _section_ref(section, name_counts):
    """A section as the format writes it — see ``columns.format_section_ref``."""
    from .columns import format_section_ref

    if section is None:
        return ""
    key = section.branch.key if section.branch else ""
    return format_section_ref(section.name or "", key, name_counts.get(section.name, 0) > 1)


def _sections_for_people(people, current_year, next_year):
    """``{person id: (current year's section, next year's section)}``."""
    wanted = {year.pk: position for position, year in enumerate((current_year, next_year)) if year}
    found = {}
    if not wanted:
        return found
    enrollments = (
        Enrollment.objects.filter(user__in=people, school_year__in=wanted)
        .select_related("section__branch")
    )
    for enrollment in enrollments:
        slot = found.setdefault(enrollment.user_id, [None, None])
        position = wanted[enrollment.school_year_id]
        if slot[position] is None:
            slot[position] = enrollment.section
    return {person_id: tuple(slots) for person_id, slots in found.items()}


def member_records(include_balances=False):
    """Every person in the troop as a row of the shared format."""
    from django.db.models import Count

    from members.models import Section

    name_counts = {
        row["name"]: row["count"]
        for row in Section.objects.values("name").annotate(count=Count("pk"))
    }

    current_year = SchoolYear.current()
    next_year = SchoolYear.next_school_year()
    sections = _sections_for_people(Person.objects.all(), current_year, next_year)

    balances = {}
    if include_balances:
        from finance.models import calculate_balances

        if current_year is not None:
            balances = {
                row["person_id"]: row for row in calculate_balances(current_year)
            }

    people = (
        Person.objects.select_related("primary_role", "account")
        .prefetch_related("roles", "parents", "households")
        .order_by("last_name", "first_name")
    )

    records = []
    for person in people:
        account = getattr(person, "account", None)
        current_section, next_section = sections.get(person.pk, (None, None))
        balance = balances.get(person.pk)
        record = {
            "external_id": _external_id(person),
            "first_name": person.first_name,
            "last_name": person.last_name,
            "birthdate": person.birthday,
            "sex": person.sex or "",
            "email": account.email if account else "",
            "phone": str(person.phone) if person.phone else "",
            "address": person.address or "",
            "primary_role": person.primary_role.short if person.primary_role else "",
            "secondary_roles": sorted(role.short for role in person.roles.all()),
            "parent_external_ids": [_external_id(parent) for parent in person.parents.all()],
            "section_current_year": _section_ref(current_section, name_counts),
            "section_next_year": _section_ref(next_section, name_counts),
            "household": next(iter(person.households.all()), None),
            "photo_consent": person.photo_consent,
            "notes": person.note,
            "status": person.status,
        }
        if record["household"] is not None:
            record["household"] = record["household"].name
        if include_balances:
            record["amount_due"] = balance["amount_due"] if balance else None
            record["amount_paid"] = balance["amount_paid"] if balance else None
            record["balance"] = balance["balance"] if balance else None
        records.append(record)

    # Sorted on the exported values, not on the model's: `external_id` is never
    # empty in a record (see `_external_id`), so this order is total and the
    # same in whichever database the export is taken from.
    records.sort(
        key=lambda record: (
            record["last_name"] or "",
            record["first_name"] or "",
            record["birthdate"] or "",
            record["external_id"],
        )
    )
    return records


def payment_records():
    """Every recorded payment as a row of the payments file."""
    from finance.models import Payment

    records = [
        {
            "external_id": _external_id(payment.person),
            "school_year": payment.school_year.name,
            "amount": payment.amount,
            "date": payment.date,
            "note": payment.note,
        }
        for payment in Payment.objects.select_related("person", "school_year").order_by(
            "school_year__name", "date", "amount"
        )
    ]
    records.sort(
        key=lambda record: (
            record["school_year"],
            record["date"] or "",
            record["external_id"],
            record["amount"] or "",
            record["note"] or "",
        )
    )
    return records
