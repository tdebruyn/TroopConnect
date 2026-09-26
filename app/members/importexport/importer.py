"""The uploaded rows turned into a plan, and the plan into records.

Importing is two steps on purpose. :func:`build_plan` reads the file and works
out what it *would* do — how many members it would create, which rows it cannot
read at all, which ones need a look — and :func:`apply_plan` does it, in one
transaction, so a failure halfway leaves nothing behind. The two are separate
calls because "is this file right?" is the whole point of showing a preview,
and because the confirmed import applies the very plan the preview showed, so
the two cannot disagree about what the file means.

A row with an error is refused and nothing is written at all: a file that is
half-readable is a file to fix first. A warning is not a refusal — the row is
imported and the remark is there to be read.

**No mail is sent.** A row carrying an email address gets an ``Account``,
created directly and with an unusable password. That is the path that does not
go through ``ResetPasswordForm``, which is what sends the "choose your
password" message everywhere else in this project — a troop importing three
hundred members must not mail three hundred families. The account is left
without an allauth ``EmailAddress`` row as well: nothing here is evidence that
the address belongs to that person, so nothing here claims it is verified.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from types import SimpleNamespace

import phonenumbers
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils.translation import gettext as _

from members.models import (
    Account,
    Enrollment,
    ParentChild,
    Person,
    PersonRole,
    Role,
    SchoolYear,
    Section,
    TroopSettings,
)

from . import columns as cols
from .files import LINE_KEY, FileError

#: What a row will do to the database.
ACTION_CREATE = "create"
ACTION_UPDATE = "update"

#: The columns a file cannot do without: every row is a person, and a person
#: without a name is not one.
REQUIRED_KEYS = ("first_name", "last_name")

#: What a member the file says nothing about becomes. An import is a troop
#: bringing in people it already has, not a batch of registration requests.
DEFAULT_STATUS = "a"


@dataclass
class Row:
    """One line of the file, and what the import makes of it."""

    line: int
    cells: dict
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    action: str = ACTION_CREATE
    #: The member this row writes to: an existing person, or ``None`` to create.
    person: object = None
    #: The parsed values, keyed by column key. A column the file did not carry
    #: has no entry here, which is what keeps an absent column from clearing
    #: what is already stored.
    values: dict = field(default_factory=dict)

    @property
    def ok(self):
        return not self.errors

    @property
    def name(self):
        return " ".join(
            part
            for part in (self.values.get("first_name"), self.values.get("last_name"))
            if part
        )


@dataclass
class Plan:
    """What an import would do, in full, before it does any of it."""

    members: list = field(default_factory=list)
    payments: list = field(default_factory=list)
    file_warnings: list = field(default_factory=list)
    #: Things the plan will have to create, so the preview can say so.
    new_households: list = field(default_factory=list)
    new_school_years: list = field(default_factory=list)

    @property
    def has_errors(self):
        return any(not row.ok for row in self.members + self.payments)

    def counts(self):
        """How many of each thing the plan does, for the preview's summary."""
        return {
            "members_created": sum(
                1 for row in self.members if row.ok and row.action == ACTION_CREATE
            ),
            "members_updated": sum(
                1 for row in self.members if row.ok and row.action == ACTION_UPDATE
            ),
            "members_rejected": sum(1 for row in self.members if not row.ok),
            "payments_created": sum(1 for row in self.payments if row.ok),
            "payments_rejected": sum(1 for row in self.payments if not row.ok),
            "households_created": len(self.new_households),
            "school_years_created": len(self.new_school_years),
            "warnings": len(self.file_warnings)
            + sum(len(row.warnings) for row in self.members + self.payments),
        }


# --- Lookups -----------------------------------------------------------------


class Lookups:
    """Everything the file's text is resolved against, read once.

    Loading the roles, sections, members and accounts up front is what lets a
    plan be built without a query per row; ``pending_external_ids`` is what lets
    one row refer to a member an earlier row in the same file is about to
    create.
    """

    def __init__(self):
        from finance.models import Household

        self.troop = TroopSettings.get_settings()

        self.roles_by_text = {}
        for role in Role.objects.all():
            self.roles_by_text.setdefault(role.short.casefold(), role)
            for language in settings.MODELTRANSLATION_LANGUAGES:
                name = getattr(role, f"name_{language}", "")
                if name:
                    self.roles_by_text.setdefault(cols.fold_header(name), role)

        self.sections_by_name = {}
        self.sections_by_branch_name = {}
        self.branch_keys = set()
        for section in Section.objects.select_related("branch"):
            folded = cols.fold_header(section.name or "")
            self.sections_by_name.setdefault(folded, []).append(section)
            if section.branch and section.branch.key:
                self.branch_keys.add(section.branch.key)
                self.sections_by_branch_name[(section.branch.key, folded)] = section

        self.by_external_id = {
            person.external_id: person
            for person in Person.objects.exclude(external_id="")
        }
        self.pending_external_ids = set()
        self.accounts_by_email = {
            account.email.strip().casefold(): account
            for account in Account.objects.select_related("person")
        }
        self.taken_names = Counter(
            cols.fold_header(f"{first} {last}")
            for first, last in Person.objects.values_list("first_name", "last_name")
        )

        self.school_years = {year.name: year for year in SchoolYear.objects.all()}
        self.new_school_years = []
        self.households = set(Household.objects.values_list("name", flat=True))
        self.new_households = []

    def role(self, text):
        """The role a cell names, by its short code or by any of its names."""
        return self.roles_by_text.get(cols.fold_header(text)) if text else None

    def section(self, value):
        """``(section, warning)`` for a section cell.

        A bare name is ambiguous as soon as two sections share one, which is
        what the ``branchkey:name`` spelling is for. Resolving it to either of
        them would be a coin toss, so it is refused and said out loud.
        """
        branch_key, name = cols.split_section_ref(value, self.branch_keys)
        if not name:
            return None, ""
        folded = cols.fold_header(name)
        if branch_key:
            found = self.sections_by_branch_name.get((branch_key, folded))
            if found is None:
                return None, _(
                    "No section named “%(name)s” in the “%(branch)s” branch."
                ) % {"name": name, "branch": branch_key}
            return found, ""
        matches = self.sections_by_name.get(folded, [])
        if not matches:
            return None, _("No section named “%(name)s”.") % {"name": name}
        if len(matches) > 1:
            return None, _(
                "“%(name)s” is the name of %(count)s sections; write it as "
                "branch:name to say which one."
            ) % {"name": name, "count": len(matches)}
        return matches[0], ""

    def school_year(self, value):
        """A school year by its number; ``None`` when the cell is not one.

        A year this instance has never seen is remembered for creation. Only
        the payments file asks for that: a payment belongs to the year it was
        recorded in, and a troop importing its history has years this instance
        has never seen. An enrolment never creates one — the current and next
        school years are the instance's own calendar, not the file's.
        """
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        existing = self.school_years.get(number)
        if existing is not None:
            return existing
        for pending in self.new_school_years:
            if pending.name == number:
                return pending
        pending = SimpleNamespace(name=number, start_date=None, pk=None)
        self.new_school_years.append(pending)
        return pending

    def person_for(self, external_id, email, match_email=True):
        """``(person, error)`` — the member a row writes to, or ``None``.

        The external id first and the email second, in that order: an address
        is something a family changes, and matching on it alone is how a troop
        ends up with the same child twice. A file with no email column is not
        allowed to match on one it never mentions.
        """
        by_external = self.by_external_id.get(external_id) if external_id else None
        by_email = None
        if email and match_email:
            account = self.accounts_by_email.get(email.strip().casefold())
            if account is not None:
                by_email = account.person
        if by_external is not None and by_email is not None:
            if by_external.pk != by_email.pk:
                return None, _(
                    "External ID “%(external)s” and email “%(email)s” belong to "
                    "two different members."
                ) % {"external": external_id, "email": email}
        return by_external or by_email, ""


# --- Planning ----------------------------------------------------------------


def build_plan(member_table, payment_table=None):
    """Read both files and work out what importing them would do."""
    for key in REQUIRED_KEYS:
        if key in member_table.missing_headers:
            raise FileError(
                _("The file has no %(column)s column.")
                % {"column": cols.column_for(key).heading()}
            )
    if payment_table is not None:
        for key in ("external_id", "school_year", "amount"):
            if key in payment_table.missing_headers:
                raise FileError(
                    _("The payments file has no %(column)s column.")
                    % {"column": cols.column_for(key).heading()}
                )

    lookups = Lookups()
    plan = Plan()
    plan.file_warnings.extend(_unknown_column_warnings(member_table))
    if payment_table is not None:
        plan.file_warnings.extend(_unknown_column_warnings(payment_table))

    _plan_members(member_table, lookups, plan)
    if payment_table is not None:
        _plan_payments(payment_table, lookups, plan)

    plan.new_households = list(lookups.new_households)
    plan.new_school_years = [year.name for year in lookups.new_school_years]
    return plan


def _unknown_column_warnings(table):
    """A column nothing in the format reads is a warning, not a failure.

    A troop's own export may carry a column this version does not know, and a
    hand-made file may have a note in column Z. Neither is a reason to refuse
    the rows that are readable.
    """
    return [
        _("Column “%(name)s” is not part of the format and is ignored.")
        % {"name": name}
        for name in table.unknown_headers
        if name
    ]


def _plan_members(table, lookups, plan):
    """Pass one parses every row; pass two applies the rules that need them all."""
    rows = []
    external_ids = Counter()
    names = Counter()
    display_names = {}

    for cells in table.rows:
        row = Row(line=cells.get(LINE_KEY, 0), cells=cells)
        _values(row, lookups)
        if "household" in cells and row.values.get("household"):
            if row.values["household"] not in lookups.households:
                lookups.households.add(row.values["household"])
                lookups.new_households.append(row.values["household"])
        if row.values.get("external_id"):
            external_ids[row.values["external_id"]] += 1
        if row.values.get("name_key"):
            names[row.values["name_key"]] += 1
            display_names.setdefault(row.values["name_key"], row.name)
        person, conflict = lookups.person_for(
            row.values.get("external_id"),
            row.values.get("email"),
            match_email="email" not in table.missing_headers,
        )
        if conflict:
            row.errors.append(conflict)
        row.person = person
        row.action = ACTION_UPDATE if person is not None else ACTION_CREATE
        if row.action == ACTION_CREATE and row.values.get("external_id"):
            # A later row — a payment, or a child naming this parent — may refer
            # to this member by their external id.
            lookups.pending_external_ids.add(row.values["external_id"])
        rows.append(row)

    for row in rows:
        _check_row(row, lookups, external_ids, names)
    plan.members = rows

    plan.file_warnings.extend(
        _("Two rows name “%(name)s”. Check whether they are the same person.")
        % {"name": display}
        for key, count in names.items()
        if count > 1
        for display in [display_names.get(key, key)]
    )


def _values(row, lookups):
    """Every column of one row, parsed. A bad cell records an error and is dropped."""
    cells = row.cells
    values = row.values

    def parse(key, function):
        if key not in cells:
            return None
        try:
            return function(cells.get(key))
        except ValueError as error:
            row.errors.append(f"{cols.column_for(key).heading()}: {error}")
            return None

    values["external_id"] = str(cells.get("external_id") or "").strip()
    values["email"] = str(cells.get("email") or "").strip()
    values["address"] = str(cells.get("address") or "").strip()
    values["notes"] = str(cells.get("notes") or "").strip()
    values["household"] = str(cells.get("household") or "").strip()

    for key in ("first_name", "last_name"):
        text = str(cells.get(key) or "").strip()
        values[key] = text
        if key not in cells:
            continue
        if not text:
            row.errors.append(
                _("%(column)s is required.") % {"column": cols.column_for(key).heading()}
            )
        elif len(text) > cols.NAME_MAX_LENGTH:
            row.errors.append(_too_long(key))
    if len(values["address"]) > cols.ADDRESS_MAX_LENGTH:
        row.errors.append(_too_long("address"))

    values["birthdate"] = parse("birthdate", cols.parse_date)
    values["sex"] = parse("sex", cols.parse_sex)
    values["photo_consent"] = parse("photo_consent", cols.parse_bool)
    values["status"] = parse("status", cols.parse_status)

    if values["email"]:
        try:
            validate_email(values["email"])
        except ValidationError:
            row.errors.append(
                _("%(column)s: “%(value)s” is not an email address.")
                % {"column": cols.column_for("email").heading(), "value": values["email"]}
            )

    values["phone"] = None
    if "phone" in cells and str(cells.get("phone") or "").strip():
        values["phone"] = _parse_phone(cells.get("phone"))
        if values["phone"] is None:
            row.errors.append(
                _("%(column)s: “%(value)s” is not a phone number.")
                % {
                    "column": cols.column_for("phone").heading(),
                    "value": str(cells.get("phone")).strip(),
                }
            )

    if "primary_role" in cells:
        text = str(cells.get("primary_role") or "").strip()
        if text:
            role = lookups.role(text)
            if role is None:
                row.errors.append(_unknown_role("primary_role", text))
            else:
                values["primary_role"] = role

    if "secondary_roles" in cells:
        roles = []
        for text in cols.parse_list(cells.get("secondary_roles")):
            role = lookups.role(text)
            if role is None:
                row.errors.append(_unknown_role("secondary_roles", text))
            else:
                roles.append(role)
        values["secondary_roles"] = roles

    if "parent_external_ids" in cells:
        values["parent_external_ids"] = cols.parse_list(cells.get("parent_external_ids"))

    for key in ("section_current_year", "section_next_year"):
        if key in cells:
            section, warning = lookups.section(cells.get(key))
            if warning:
                row.warnings.append(f"{cols.column_for(key).heading()}: {warning}")
            values[key] = section

    name = f"{values.get('first_name', '')} {values.get('last_name', '')}".strip()
    values["name_key"] = cols.fold_header(name) if name else ""


def _too_long(key):
    return _("%(column)s is longer than %(limit)s characters.") % {
        "column": cols.column_for(key).heading(),
        "limit": (
            cols.ADDRESS_MAX_LENGTH if key == "address" else cols.NAME_MAX_LENGTH
        ),
    }


def _unknown_role(key, value):
    return _("%(column)s: no role named “%(value)s”.") % {
        "column": cols.column_for(key).heading(),
        "value": value,
    }


def _check_row(row, lookups, external_ids, names):
    """The rules that need more than one row, or the database, to decide."""
    values = row.values

    if values.get("external_id") and external_ids[values["external_id"]] > 1:
        row.errors.append(
            _("External ID “%(value)s” appears on more than one row.")
            % {"value": values["external_id"]}
        )

    if names.get(values.get("name_key"), 0) == 1:
        # Only warn about a name that collides outside the file: two rows with
        # the same name are already reported once, as a file warning.
        others = lookups.taken_names.get(values["name_key"], 0)
        if row.person is not None:
            others -= 1  # this row's own member is not somebody else
        if others > 0:
            row.warnings.append(
                _("Another member is already called “%(name)s”.") % {"name": row.name}
            )

    if "parent_external_ids" in row.cells:
        for parent_id in values.get("parent_external_ids", []):
            if parent_id == values.get("external_id"):
                row.errors.append(
                    _("%(column)s: a member cannot be their own parent.")
                    % {"column": cols.column_for("parent_external_ids").heading()}
                )
            elif (
                parent_id not in lookups.by_external_id
                and parent_id not in lookups.pending_external_ids
            ):
                row.warnings.append(
                    _("%(column)s: no member with external ID “%(value)s”.")
                    % {
                        "column": cols.column_for("parent_external_ids").heading(),
                        "value": parent_id,
                    }
                )

    _check_participant(row)
    _check_sections(row, lookups)


def _check_participant(row):
    """A participant without a birthday or a sex is one the app refuses.

    ``Person.clean`` states the rule; this is that rule applied to what the row
    would leave *stored*, so a file that carries neither column for a child who
    already has both is fine, and one that empties them is not.
    """
    role = _effective(row, "primary_role", "primary_role")
    if role is None or role.short != Person.CHILD_ROLE_SHORT:
        return
    if _effective(row, "birthdate", "birthday") is None:
        row.errors.append(
            _("%(column)s is required for a participant.")
            % {"column": cols.column_for("birthdate").heading()}
        )
    if _effective(row, "sex", "sex") is None:
        row.errors.append(
            _("%(column)s is required for a participant.")
            % {"column": cols.column_for("sex").heading()}
        )


def _effective(row, column_key, attribute):
    """What a column would hold after this row: the file's value, or the stored one."""
    if row.person is None or column_key in row.cells:
        return row.values.get(column_key)
    return getattr(row.person, attribute)


def _check_sections(row, lookups):
    """Warn about an enrolment a row asks for that does not fit."""
    for key, year in (
        ("section_current_year", SchoolYear.current()),
        ("section_next_year", SchoolYear.next_school_year()),
    ):
        if key not in row.cells:
            continue
        section = row.values.get(key)
        if section is None:
            # An empty cell, or one `_values` has already complained about.
            continue
        if year is None:
            row.warnings.append(
                _(
                    "%(column)s: this instance has no such school year, so the "
                    "section cannot be recorded."
                )
                % {"column": cols.column_for(key).heading()}
            )
            continue

        sex = _effective(row, "sex", "sex")
        if sex and section.sex and section.sex not in (Section.Sex.BOTH, sex):
            row.warnings.append(
                _("%(section)s is a section for %(wanted)s, and this member is %(given)s.")
                % {
                    "section": section.name,
                    "wanted": section.get_sex_display(),
                    "given": dict(Person.Sex.choices).get(sex, sex),
                }
            )

        branch = section.branch
        birthday = _effective(row, "birthdate", "birthday")
        if not birthday or branch is None:
            continue
        age = lookups.troop.age_at_reference(SimpleNamespace(birthday=birthday), year)
        if (
            age is not None
            and branch.min_age_dec_31 is not None
            and branch.max_age_dec_31 is not None
            and not (branch.min_age_dec_31 <= age <= branch.max_age_dec_31)
        ):
            row.warnings.append(
                _("%(age)s years old — branch %(branch)s: %(min)s-%(max)s years old")
                % {
                    "age": age,
                    "branch": branch.name,
                    "min": branch.min_age_dec_31,
                    "max": branch.max_age_dec_31,
                }
            )


def _plan_payments(table, lookups, plan):
    """The payments file, resolved against the members the same run introduces."""
    rows = []
    for cells in table.rows:
        row = Row(line=cells.get(LINE_KEY, 0), cells=cells)
        values = row.values
        values["external_id"] = str(cells.get("external_id") or "").strip()

        person = lookups.by_external_id.get(values["external_id"])
        if person is None and values["external_id"] in lookups.pending_external_ids:
            pass  # a member an earlier row of this same run creates
        elif person is None:
            row.errors.append(
                _("%(column)s: no member with external ID “%(value)s”.")
                % {
                    "column": cols.column_for("external_id").heading(),
                    "value": values["external_id"],
                }
            )
        row.person = person

        year = lookups.school_year(cells.get("school_year"))
        if year is None:
            row.errors.append(
                _("%(column)s: “%(value)s” is not a school year.")
                % {
                    "column": cols.column_for("school_year").heading(),
                    "value": str(cells.get("school_year") or "").strip(),
                }
            )
        values["school_year"] = year

        amount = None
        if "amount" in cells:
            try:
                amount = cols.parse_decimal(cells.get("amount"))
            except ValueError as error:
                row.errors.append(f"{cols.column_for('amount').heading()}: {error}")
        if amount is None:
            row.errors.append(
                _("%(column)s is required.")
                % {"column": cols.column_for("amount").heading()}
            )
        values["amount"] = amount

        date = None
        if "date" in cells:
            try:
                date = cols.parse_date(cells.get("date"))
            except ValueError as error:
                row.errors.append(f"{cols.column_for('date').heading()}: {error}")
        values["date"] = date
        values["note"] = str(cells.get("note") or "").strip()
        rows.append(row)

    plan.payments = rows


# --- Applying ----------------------------------------------------------------


def apply_plan(plan, actor=None):
    """Write the plan, in one transaction, and report what was written.

    Refuses to write anything while the plan holds an error — the preview has
    already shown them, and half a file is worse than none of it.
    """
    if plan.has_errors:
        raise ValueError("the plan has errors and cannot be applied")

    with transaction.atomic():
        years = _ensure_school_years(plan)
        _ensure_households(plan)
        for row in plan.members:
            _apply_member(row)
        _apply_parent_links(plan)
        written = _apply_payments(plan, years, actor)

    counts = plan.counts()
    counts["payments_created"] = written["created"]
    counts["payments_unchanged"] = written["unchanged"]
    return counts


def _ensure_school_years(plan):
    """Create the payments file's years that this instance has never seen."""
    years = {}
    for name in plan.new_school_years:
        years[name] = SchoolYear.objects.create_year(name)
    return years


def _ensure_households(plan):
    from finance.models import Household

    for name in plan.new_households:
        Household.objects.get_or_create(name=name)


def _apply_member(row):
    """Write one member row, column by column, and their account and sections."""
    person = row.person or Person()
    created = row.person is None
    cells = row.cells
    values = row.values

    for column_key, attribute in (
        ("first_name", "first_name"),
        ("last_name", "last_name"),
        ("birthdate", "birthday"),
        ("sex", "sex"),
        ("address", "address"),
        ("notes", "note"),
    ):
        if column_key in cells:
            setattr(person, attribute, values[column_key])
    if "phone" in cells:
        person.phone = values["phone"] or None
    if values.get("photo_consent") is not None:
        person.photo_consent = values["photo_consent"]
    if values.get("primary_role") is not None:
        person.primary_role = values["primary_role"]
    if values.get("status"):
        person.status = values["status"]
    elif created:
        person.status = DEFAULT_STATUS
    if values.get("external_id"):
        person.external_id = values["external_id"]

    person.save()

    if "secondary_roles" in cells:
        _apply_roles(person, values["secondary_roles"])
    _apply_account(row, person)
    _apply_household(row, person)
    _apply_enrollments(row, person)
    return person


def _apply_roles(person, roles):
    """Replace the member's secondary roles with the ones the file names.

    Only the secondary roles: the primary role is its own column, and the
    division is the one ``PersonRole`` is already built on.
    """
    PersonRole.objects.filter(person=person, role__is_primary=False).delete()
    for role in roles:
        PersonRole.objects.get_or_create(person=person, role=role)


def _apply_account(row, person):
    """Give the member the address the file carries, and no password.

    An empty cell changes nothing: clearing an email in a file would otherwise
    be a way to delete somebody's login, and the accounts this import does not
    create are not its to remove.
    """
    email = row.values.get("email") or ""
    if "email" not in row.cells or not email:
        return
    account = getattr(person, "account", None)
    if account is not None:
        if account.email != email:
            account.email = email
            account.save()
        return
    account = Account(person=person, email=email)
    account.set_unusable_password()
    account.save()


def _apply_household(row, person):
    from finance.models import Household, HouseholdMember

    name = row.values.get("household") or ""
    if "household" not in row.cells:
        return
    if not name:
        HouseholdMember.objects.filter(person=person).delete()
        return
    household = Household.objects.filter(name=name).first()
    if household is None:
        return
    HouseholdMember.objects.update_or_create(
        person=person, defaults={"household": household}
    )


def _apply_enrollments(row, person):
    """The two section columns, as enrollments of the years they name.

    An empty cell removes that year's enrolment, which is what the member edit
    form does with an empty section field and what an export of a member with
    no section says. ``Person.next_section`` — the passage's own override — is
    deliberately not touched: it is bookkeeping the passage clears as it runs,
    not a statement about next year.
    """
    for key, year in (
        ("section_current_year", SchoolYear.current()),
        ("section_next_year", SchoolYear.next_school_year()),
    ):
        if key not in row.cells or year is None:
            continue
        section = row.values.get(key)
        existing = Enrollment.objects.filter(user=person, school_year=year).first()
        if section is None:
            if existing is not None:
                existing.delete()
            continue
        if existing is None:
            Enrollment.objects.create(user=person, school_year=year, section=section)
        elif existing.section_id != section.pk:
            existing.section = section
            existing.save(update_fields=["section"])
        if key == "section_next_year" and person.passage_review:
            # Choosing their section by hand is the decision the passage asked
            # for, exactly as it is on the member edit form.
            person.passage_review = ""
            person.save(update_fields=["passage_review"])


def _apply_parent_links(plan):
    """The parent links, after every member exists to link to."""
    wanted = {
        row.values["external_id"]: row.values.get("parent_external_ids", [])
        for row in plan.members
        if row.ok and "parent_external_ids" in row.cells
    }
    if not wanted:
        return
    by_external = {
        person.external_id: person
        for person in Person.objects.filter(external_id__in=set(wanted))
    }
    for external_id, parent_ids in wanted.items():
        child = by_external.get(external_id)
        if child is None:
            continue
        for parent_id in parent_ids:
            parent = by_external.get(parent_id)
            if parent is None or parent.pk == child.pk:
                continue
            ParentChild.objects.get_or_create(parent=parent, child=child)


def _apply_payments(plan, years, actor):
    """Record the year's payments, leaving an already-recorded one alone.

    Left alone rather than added again: a payment has no identifier of its own
    in the file, so a second import of the same file would otherwise double a
    family's recorded payments. The five fields the format carries are the
    whole of what a payment is, so two payments agreeing on all of them are
    the same payment.
    """
    from finance.models import Payment

    pending = {
        row.values["external_id"] for row in plan.payments if row.person is None
    }
    by_external = {
        person.external_id: person
        for person in Person.objects.filter(external_id__in=pending)
    } if pending else {}

    created = unchanged = 0
    for row in plan.payments:
        if not row.ok:
            continue
        person = row.person or by_external.get(row.values["external_id"])
        if person is None:
            continue
        year = row.values["school_year"]
        if getattr(year, "pk", None) is None:
            year = years.get(year.name)
        date = row.values["date"] or year.start_date
        fields = {
            "person": person,
            "school_year": year,
            "amount": row.values["amount"],
            "date": date,
            "note": row.values["note"],
        }
        if Payment.objects.filter(**fields).exists():
            unchanged += 1
            continue
        Payment.objects.create(recorded_by=actor, **fields)
        created += 1
    return {"created": created, "unchanged": unchanged}


# --- Field parsing -----------------------------------------------------------


def _parse_phone(value):
    """An E.164 number, or ``None`` when the cell is not a usable one.

    Parsed in the troop's own region, so a number written the way a member
    writes it down ("0475 12 34 56") is read as the troop's country means it.
    Stored as E.164 either way, which is what the export writes back, so a
    round trip through the file does not re-interpret a number.
    """
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"[^\d+]", "", text)
    try:
        parsed = phonenumbers.parse(text, TroopSettings.get_settings().phone_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
