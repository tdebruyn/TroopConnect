"""The member import and export, and the column format the two share.

The format's own tests come first — a file the export writes has to be a file
the import reads, so both halves of every convention are checked against each
other rather than against a hand-written expectation. The round trip at the end
is the same idea said once, over a troop that uses every column.
"""

import datetime
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse
from post_office.models import Email

from members.importexport import columns as cols
from members.importexport import exporter
from members.importexport.files import FileError, read_table, write_csv, write_xlsx
from members.importexport.importer import apply_plan, build_plan
from members.models import (
    Account,
    Branch,
    Enrollment,
    ParentChild,
    Person,
    Role,
    SchoolYear,
    Section,
)
from tests.base import TroopSettingsTestCase


def csv_bytes(header, *rows):
    """A file whose headers are the internal keys, which need no translation."""
    lines = [";".join(header)] + [";".join(row) for row in rows]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8-sig")


def member_table(header, *rows):
    return read_table(
        "members.csv", csv_bytes(header, *rows), column_set=cols.MEMBER_COLUMNS
    )


# --- The format --------------------------------------------------------------


class ColumnFormatTest(SimpleTestCase):
    def test_every_language_header_names_its_column(self):
        index = cols.header_index()
        for header in ("Prénom", "Voornaam", "First name", "first_name"):
            with self.subTest(header=header):
                self.assertEqual(index[cols.fold_header(header)], "first_name")

    def test_a_header_is_matched_through_case_accents_and_spaces(self):
        index = cols.header_index()
        for header in ("  PRENOM ", "prenom", "Prénom"):
            with self.subTest(header=header):
                self.assertEqual(index[cols.fold_header(header)], "first_name")

    def test_a_date_is_written_iso_and_read_from_either_order(self):
        self.assertEqual(cols.parse_date("2020-05-04"), datetime.date(2020, 5, 4))
        self.assertEqual(cols.parse_date("04/05/2020"), datetime.date(2020, 5, 4))
        self.assertEqual(cols.parse_date("4-5-2020"), datetime.date(2020, 5, 4))
        self.assertEqual(cols.format_date(datetime.date(2020, 5, 4)), "2020-05-04")
        self.assertEqual(cols.format_date(None), "")
        with self.assertRaises(ValueError):
            cols.parse_date("not a date")

    def test_a_decimal_is_read_with_either_decimal_separator(self):
        for text in ("12.50", "12,50"):
            with self.subTest(text=text):
                self.assertEqual(cols.parse_decimal(text), Decimal("12.50"))
        # A number carrying both separators: whichever comes last is the decimal
        # one, so the European and the English spellings both read as 1234.56.
        for text in ("1.234,56", "1,234.56"):
            with self.subTest(text=text):
                self.assertEqual(cols.parse_decimal(text), Decimal("1234.56"))
        with self.assertRaises(ValueError):
            cols.parse_decimal("twelve")

    def test_a_boolean_accepts_the_words_a_person_writes(self):
        for text in ("yes", "YES", "true", "1", "ja", "oui"):
            with self.subTest(text=text):
                self.assertIs(cols.parse_bool(text), True)
        for text in ("no", "false", "0", "nee", "non"):
            with self.subTest(text=text):
                self.assertIs(cols.parse_bool(text), False)
        self.assertIsNone(cols.parse_bool(""))
        with self.assertRaises(ValueError):
            cols.parse_bool("perhaps")

    def test_a_sex_is_one_of_the_two_codes(self):
        self.assertEqual(cols.parse_sex("m"), "M")
        self.assertEqual(cols.parse_sex("F"), "F")
        self.assertIsNone(cols.parse_sex(""))
        with self.assertRaises(ValueError):
            cols.parse_sex("X")

    def test_a_section_cell_takes_a_name_or_a_branch_qualified_one(self):
        keys = {"louveteaux"}
        self.assertEqual(cols.split_section_ref("Meute 1", keys), (None, "Meute 1"))
        self.assertEqual(
            cols.split_section_ref("louveteaux:Meute 1", keys), ("louveteaux", "Meute 1")
        )
        # A colon that is not a branch key belongs to the name.
        self.assertEqual(
            cols.split_section_ref("Troupe: les aînés", keys),
            (None, "Troupe: les aînés"),
        )

    def test_a_section_is_qualified_only_where_the_name_is_shared(self):
        self.assertEqual(cols.format_section_ref("Meute", "louveteaux", False), "Meute")
        self.assertEqual(
            cols.format_section_ref("Meute", "louveteaux", True), "louveteaux:Meute"
        )
        # Nothing to qualify with: the bare name goes out.
        self.assertEqual(cols.format_section_ref("Meute", "", True), "Meute")


class FileFormatTest(SimpleTestCase):
    def test_a_csv_survives_being_written_and_read(self):
        records = [
            {"first_name": "Élise", "last_name": "Van der Berghe"},
            {"first_name": "Jean;Paul", "last_name": "Dupont"},
        ]
        data = write_csv(cols.MEMBER_COLUMNS, records)
        table = read_table("members.csv", data, column_set=cols.MEMBER_COLUMNS)

        self.assertEqual(table.rows[0]["first_name"], "Élise")
        self.assertEqual(table.rows[0]["last_name"], "Van der Berghe")
        self.assertEqual(table.rows[1]["first_name"], "Jean;Paul")

    def test_an_xlsx_survives_being_written_and_read(self):
        records = [
            {
                "first_name": "Élise",
                "birthdate": datetime.date(2015, 5, 4),
                "photo_consent": True,
            }
        ]
        data = write_xlsx(cols.MEMBER_COLUMNS, records, title="Members")
        table = read_table("members.xlsx", data, column_set=cols.MEMBER_COLUMNS)

        self.assertEqual(table.rows[0]["first_name"], "Élise")
        # A spreadsheet cell is a datetime; the format reads it as a date.
        self.assertEqual(
            cols.parse_date(table.rows[0]["birthdate"]), datetime.date(2015, 5, 4)
        )

    def test_a_comma_separated_file_is_read_as_well_as_the_export_s_own(self):
        data = b"first_name,last_name\r\nJean,Dupont\r\n"
        table = read_table("members.csv", data, column_set=cols.MEMBER_COLUMNS)

        self.assertEqual(table.rows[0]["first_name"], "Jean")

    def test_columns_the_format_does_not_know_are_reported_not_refused(self):
        table = member_table(("first_name", "last_name", "Favourite colour"), ("A", "B", "red"))

        self.assertEqual(table.unknown_headers, ["Favourite colour"])
        self.assertEqual(table.rows[0]["first_name"], "A")

    def test_columns_the_file_leaves_out_are_reported(self):
        table = member_table(("first_name", "last_name"), ("A", "B"))

        self.assertIn("birthdate", table.missing_headers)
        self.assertNotIn("first_name", table.missing_headers)

    def test_a_file_with_no_recognisable_header_is_refused(self):
        with self.assertRaises(FileError):
            read_table("members.csv", b"a;b;c\r\n1;2;3\r\n")

    def test_a_blank_line_is_not_a_row(self):
        table = member_table(
            ("first_name", "last_name"), ("A", "B"), ("", ""), ("C", "D")
        )

        self.assertEqual([row["first_name"] for row in table.rows], ["A", "C"])
        self.assertEqual(table.rows[1]["_line"], 4)


# --- Export ------------------------------------------------------------------


class ImportExportTestBase(TroopSettingsTestCase):
    """A branch, a section, a school year and one family, for both directions."""

    @classmethod
    def setUpTestData(cls):
        cls.role_parent = Role.objects.get(short="p")
        cls.role_child = Role.objects.get(short="e")
        cls.role_animator = Role.objects.get(short="a")
        cls.role_treasurer = Role.objects.get(short="t")

    def setUp(self):
        super().setUp()
        self.branch = Branch.objects.create(
            name="Louveteaux", key="louveteaux", min_age_dec_31=8, max_age_dec_31=12
        )
        self.section = Section.objects.create(
            name="Meute 1", branch=self.branch, sex=Section.Sex.BOTH
        )
        self.other_section = Section.objects.create(
            name="Meute 2", branch=self.branch, sex=Section.Sex.BOTH
        )
        self.current_year = SchoolYear.current()

    def make_child(self, **fields):
        fields.setdefault("birthday", self.child_birthday())
        fields.setdefault("sex", "M")
        fields.setdefault("primary_role", self.role_child)
        fields.setdefault("first_name", "Charlie")
        fields.setdefault("last_name", "Dupont")
        return Person.objects.create(status="a", **fields)

    def child_birthday(self):
        """An age that fits the branch in the current school year."""
        year = SchoolYear.current().name
        return datetime.date(year - 9, 1, 1)

    def make_parent(self, person=None, email=""):
        person = person or Person.objects.create(
            first_name="Alice",
            last_name="Dupont",
            primary_role=self.role_parent,
            status="a",
        )
        if email:
            Account.objects.create_user(
                email=email, password="testpass", person=person
            )
        return person


class ExporterTest(ImportExportTestBase):
    def test_a_member_is_written_with_their_section_roles_and_household(self):
        from finance.models import Household, HouseholdMember

        child = self.make_child(external_id="X1", address="Rue des Fleurs 10")
        parent = self.make_parent(email="alice@test.be")
        ParentChild.objects.create(parent=parent, child=child, primary_contact=True)
        Enrollment.objects.create(
            user=child, section=self.section, school_year=self.current_year
        )
        household = Household.objects.create(name="Famille Dupont")
        HouseholdMember.objects.create(household=household, person=child)

        record = next(
            row for row in exporter.member_records() if row["external_id"] == "X1"
        )

        self.assertEqual(record["first_name"], "Charlie")
        self.assertEqual(record["section_current_year"], "Meute 1")
        self.assertEqual(record["household"], "Famille Dupont")
        self.assertEqual(record["parent_external_ids"], [str(parent.pk)])
        self.assertEqual(record["primary_role"], "e")

    def test_a_shared_section_name_is_written_with_its_branch_key(self):
        other = Branch.objects.create(name="Éclaireurs", key="eclaireurs")
        Section.objects.create(name="Troupe", branch=self.branch)
        Section.objects.create(name="Troupe", branch=other)
        child = self.make_child(external_id="X1")
        Enrollment.objects.create(
            user=child, section=Section.objects.get(branch=other, name="Troupe"),
            school_year=self.current_year,
        )

        record = next(
            row for row in exporter.member_records() if row["external_id"] == "X1"
        )

        self.assertEqual(record["section_current_year"], "eclaireurs:Troupe")

    def test_a_member_without_an_external_id_is_written_with_their_uuid(self):
        child = self.make_child()

        record = next(
            row
            for row in exporter.member_records()
            if row["external_id"] == str(child.pk)
        )

        self.assertEqual(record["last_name"], "Dupont")


# --- Import ------------------------------------------------------------------


class ImporterTest(ImportExportTestBase):
    def plan(self, header, *rows, payments=None):
        table = member_table(header, *rows)
        payment_table = (
            read_table(
                "payments.csv",
                csv_bytes(*payments),
                column_set=cols.PAYMENT_COLUMNS,
            )
            if payments
            else None
        )
        return build_plan(table, payment_table)

    def test_a_row_creates_a_member_with_an_account_and_no_password(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name", "birthdate", "sex", "email"),
            ("X1", "Jean", "Dupont", "2015-05-04", "M", "jean@test.be"),
        )
        self.assertFalse(plan.has_errors)

        apply_plan(plan)

        person = Person.objects.get(external_id="X1")
        self.assertEqual(person.first_name, "Jean")
        self.assertEqual(person.birthday, datetime.date(2015, 5, 4))
        self.assertEqual(person.sex, "M")
        self.assertEqual(person.status, "a")
        self.assertEqual(person.account.email, "jean@test.be")
        self.assertFalse(person.account.has_usable_password())

    def test_importing_sends_no_mail(self):
        plan = self.plan(
            ("first_name", "last_name", "email"),
            ("Jean", "Dupont", "jean@test.be"),
        )

        apply_plan(plan)

        self.assertTrue(Account.objects.filter(email="jean@test.be").exists())
        self.assertFalse(Email.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_a_member_is_matched_by_external_id_before_email(self):
        existing = self.make_parent(email="alice@test.be")
        existing.external_id = "X1"
        existing.save(update_fields=["external_id"])

        plan = self.plan(
            ("external_id", "first_name", "last_name", "email"),
            ("X1", "Alicia", "Dupont", "alice@test.be"),
        )
        apply_plan(plan)

        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(Person.objects.get().first_name, "Alicia")

    def test_a_member_is_matched_by_email_when_the_row_has_no_external_id(self):
        self.make_parent(email="alice@test.be")

        plan = self.plan(
            ("first_name", "last_name", "email"), ("Alicia", "Dupont", "alice@test.be")
        )
        apply_plan(plan)

        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(Person.objects.get().first_name, "Alicia")

    def test_an_external_id_and_an_email_naming_two_members_is_an_error(self):
        self.make_parent(email="alice@test.be")
        second = self.make_parent(email="bob@test.be")
        second.external_id = "X2"
        second.save(update_fields=["external_id"])

        plan = self.plan(
            ("external_id", "first_name", "last_name", "email"),
            ("X2", "Bob", "Dupont", "alice@test.be"),
        )

        self.assertTrue(plan.has_errors)
        self.assertIsNone(plan.members[0].person)
        self.assertEqual(Person.objects.count(), 2)

    def test_a_column_the_file_leaves_out_is_not_cleared(self):
        child = self.make_child(note="allergic to nuts")
        child.external_id = "X1"
        child.save(update_fields=["external_id"])

        plan = self.plan(("external_id", "first_name", "last_name"), ("X1", "Charlie", "Dupont"))
        apply_plan(plan)

        child.refresh_from_db()
        self.assertEqual(child.note, "allergic to nuts")

    def test_a_section_column_creates_the_enrolment(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name", "birthdate", "sex", "section_current_year"),
            ("X1", "Charlie", "Dupont", self.child_birthday().isoformat(), "M", "louveteaux:Meute 1"),
        )
        apply_plan(plan)

        child = Person.objects.get(external_id="X1")
        enrollment = Enrollment.objects.get(user=child)
        self.assertEqual(enrollment.section, self.section)
        self.assertEqual(enrollment.school_year, self.current_year)

    def test_a_household_column_puts_the_member_in_a_new_household(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name", "household"),
            ("X1", "Charlie", "Dupont", "Famille Dupont"),
        )
        apply_plan(plan)

        child = Person.objects.get(external_id="X1")
        self.assertEqual(child.households.get().name, "Famille Dupont")

    def test_a_parent_column_links_a_member_to_their_parent(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name", "primary_role", "birthdate", "sex", "parent_external_ids"),
            ("ADULT", "Alice", "Dupont", "p", "", "", ""),
            ("X1", "Charlie", "Dupont", "e", self.child_birthday().isoformat(), "M", "ADULT"),
        )
        apply_plan(plan)

        child = Person.objects.get(external_id="X1")
        parent = Person.objects.get(external_id="ADULT")
        self.assertEqual(list(child.parents.all()), [parent])

    def test_a_role_is_read_from_its_name_as_well_as_its_code(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name", "primary_role", "birthdate", "sex"),
            ("X1", "Charlie", "Dupont", "Participant", self.child_birthday().isoformat(), "F"),
        )
        apply_plan(plan)

        self.assertEqual(
            Person.objects.get(external_id="X1").primary_role, self.role_child
        )

    def test_secondary_roles_are_replaced_by_what_the_file_says(self):
        person = self.make_parent(email="alice@test.be")
        person.external_id = "X1"
        person.roles.add(self.role_treasurer)
        person.save(update_fields=["external_id"])

        plan = self.plan(
            ("external_id", "first_name", "last_name", "secondary_roles"),
            ("X1", "Alice", "Dupont", "ri"),
        )
        apply_plan(plan)

        self.assertEqual(
            list(person.roles.values_list("short", flat=True)),
            ["ri"],
        )

    # -- warnings ------------------------------------------------------------

    def test_an_unknown_section_is_a_warning_and_the_member_is_still_imported(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name", "section_current_year"),
            ("X1", "Charlie", "Dupont", "Nowhere"),
        )

        self.assertFalse(plan.has_errors)
        self.assertTrue(plan.members[0].warnings)

        apply_plan(plan)

        self.assertTrue(Person.objects.filter(external_id="X1").exists())
        self.assertFalse(Enrollment.objects.exists())

    def test_an_age_outside_the_branch_is_a_warning(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name", "birthdate", "sex", "section_current_year"),
            ("X1", "Charlie", "Dupont", "1990-01-01", "M", "Meute 1"),
        )

        self.assertFalse(plan.has_errors)
        self.assertTrue(
            any("branch" in warning for warning in plan.members[0].warnings),
            plan.members[0].warnings,
        )

    def test_a_section_for_another_sex_is_a_warning(self):
        girls = Section.objects.create(
            name="Meute des filles", branch=self.branch, sex=Section.Sex.FEMALE
        )
        plan = self.plan(
            ("external_id", "first_name", "last_name", "birthdate", "sex", "section_current_year"),
            ("X1", "Charlie", "Dupont", self.child_birthday().isoformat(), "M", girls.name),
        )

        self.assertFalse(plan.has_errors)
        self.assertTrue(plan.members[0].warnings)

    def test_a_name_a_member_already_wears_is_a_warning(self):
        self.make_child(external_id="X0")
        plan = self.plan(
            ("external_id", "first_name", "last_name", "birthdate", "sex"),
            ("X1", "Charlie", "Dupont", self.child_birthday().isoformat(), "M"),
        )

        self.assertFalse(plan.has_errors)
        self.assertTrue(plan.members[0].warnings)

    def test_two_rows_wearing_the_same_name_are_reported_once(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name", "birthdate", "sex"),
            ("X1", "Charlie", "Dupont", self.child_birthday().isoformat(), "M"),
            ("X2", "Charlie", "Dupont", self.child_birthday().isoformat(), "M"),
        )

        self.assertFalse(plan.has_errors)
        self.assertEqual(len(plan.file_warnings), 1)

    # -- errors --------------------------------------------------------------

    def test_a_row_without_a_name_is_an_error(self):
        plan = self.plan(("first_name", "last_name"), ("", "Dupont"))

        self.assertTrue(plan.has_errors)

    def test_a_birthdate_that_is_not_a_date_is_an_error(self):
        plan = self.plan(("first_name", "last_name", "birthdate"), ("Jean", "Dupont", "hier"))

        self.assertTrue(plan.has_errors)

    def test_an_external_id_twice_in_one_file_is_an_error(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name"),
            ("X1", "Jean", "Dupont"),
            ("X1", "Jeanne", "Dupont"),
        )

        self.assertTrue(plan.has_errors)

    def test_an_unknown_role_is_an_error(self):
        plan = self.plan(
            ("first_name", "last_name", "primary_role"), ("Jean", "Dupont", "Wizard")
        )

        self.assertTrue(plan.has_errors)

    def test_a_participant_without_a_birthday_is_an_error(self):
        plan = self.plan(
            ("first_name", "last_name", "primary_role", "sex"),
            ("Jean", "Dupont", "e", "M"),
        )

        self.assertTrue(plan.has_errors)

    def test_an_error_stops_the_whole_file_from_being_written(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name"),
            ("X1", "Jean", "Dupont"),
            ("X2", "", "Dupont"),
        )

        with self.assertRaises(ValueError):
            apply_plan(plan)
        self.assertFalse(Person.objects.filter(external_id="X1").exists())

    # -- payments ------------------------------------------------------------

    def test_a_payment_is_recorded_against_the_member_it_names(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name"),
            ("X1", "Jean", "Dupont"),
            payments=(
                ("external_id", "school_year", "amount", "date", "note"),
                ("X1", str(self.current_year.name), "40.00", "2025-10-01", "espèces"),
            ),
        )
        apply_plan(plan)

        from finance.models import Payment

        payment = Payment.objects.get()
        self.assertEqual(payment.person.external_id, "X1")
        self.assertEqual(payment.amount, Decimal("40.00"))
        self.assertEqual(payment.date, datetime.date(2025, 10, 1))
        self.assertEqual(payment.note, "espèces")

    def test_a_school_year_the_instance_has_never_seen_is_created(self):
        from finance.models import Payment

        plan = self.plan(
            ("external_id", "first_name", "last_name"),
            ("X1", "Jean", "Dupont"),
            payments=(
                ("external_id", "school_year", "amount"),
                ("X1", "2019", "40.00"),
            ),
        )

        self.assertEqual(plan.new_school_years, [2019])
        apply_plan(plan)

        self.assertTrue(SchoolYear.objects.filter(name=2019).exists())
        self.assertEqual(Payment.objects.get().school_year.name, 2019)

    def test_a_payment_already_recorded_is_not_recorded_twice(self):
        from finance.models import Payment

        rows = (
            ("external_id", "school_year", "amount", "date"),
            ("X1", str(self.current_year.name), "40.00", "2025-10-01"),
        )
        members = (("external_id", "first_name", "last_name"), ("X1", "Jean", "Dupont"))
        apply_plan(self.plan(*members, payments=rows))
        apply_plan(self.plan(*members, payments=rows))

        self.assertEqual(Payment.objects.count(), 1)

    def test_a_payment_for_an_unknown_member_is_an_error(self):
        plan = self.plan(
            ("external_id", "first_name", "last_name"),
            ("X1", "Jean", "Dupont"),
            payments=(
                ("external_id", "school_year", "amount"),
                ("X9", str(self.current_year.name), "40.00"),
            ),
        )

        self.assertTrue(plan.has_errors)


# --- The round trip ----------------------------------------------------------


class RoundTripTest(ImportExportTestBase):
    """Export, wipe, import, export again: the same file, byte for byte."""

    def build_troop(self):
        from finance.models import Household, HouseholdMember, Payment

        child = self.make_child(
            external_id="CHILD-1",
            address="Rue des Fleurs 10, 1300 Limal",
            photo_consent=True,
            note="Allergic to nuts",
        )
        child.roles.add(self.role_treasurer)
        sibling = self.make_child(
            external_id="CHILD-2",
            first_name="Camille",
            sex="F",
            birthday=datetime.date(self.current_year.name - 11, 3, 2),
            address="Rue des Fleurs 10, 1300 Limal",
        )
        parent = self.make_parent(email="alice@test.be", person=Person.objects.create(
            first_name="Alice",
            last_name="Dupont",
            primary_role=self.role_parent,
            status="a",
            external_id="PARENT-1",
            address="Rue des Fleurs 10, 1300 Limal",
            phone="+32475123456",
        ))
        ParentChild.objects.create(parent=parent, child=child, primary_contact=True)
        ParentChild.objects.create(parent=parent, child=sibling)

        animator = Person.objects.create(
            first_name="Léa",
            last_name="Martin",
            primary_role=self.role_animator,
            status="a",
            external_id="ANIM-1",
            birthday=datetime.date(1995, 6, 1),
        )
        Enrollment.objects.create(
            user=child, section=self.section, school_year=self.current_year
        )
        Enrollment.objects.create(
            user=sibling, section=self.other_section, school_year=self.current_year
        )
        next_year = SchoolYear.next_school_year()
        if next_year is not None:
            Enrollment.objects.create(
                user=child, section=self.other_section, school_year=next_year
            )

        household = Household.objects.create(name="Famille Dupont")
        HouseholdMember.objects.create(household=household, person=child)
        Payment.objects.create(
            person=child,
            school_year=self.current_year,
            amount=Decimal("40.00"),
            date=datetime.date(self.current_year.name, 10, 1),
            note="virement",
        )
        return animator

    def test_the_two_files_survive_a_round_trip(self):
        self.build_troop()
        members_before = exporter.member_records(include_balances=True)
        payments_before = exporter.payment_records()
        self.assertTrue(members_before)

        Person.objects.all().delete()
        from finance.models import Payment

        Payment.objects.all().delete()

        member_table = read_table(
            "members.csv",
            write_csv(cols.member_columns(include_balances=True), members_before),
            column_set=cols.member_columns(include_balances=True),
        )
        payment_table = read_table(
            "payments.csv",
            write_csv(cols.PAYMENT_COLUMNS, payments_before),
            column_set=cols.PAYMENT_COLUMNS,
        )
        plan = build_plan(member_table, payment_table)
        self.assertFalse(plan.has_errors, [row.errors for row in plan.members])
        apply_plan(plan)

        self.assertEqual(
            write_csv(cols.member_columns(include_balances=True), exporter.member_records(include_balances=True)),
            write_csv(cols.member_columns(include_balances=True), members_before),
        )
        self.assertEqual(
            write_csv(cols.PAYMENT_COLUMNS, exporter.payment_records()),
            write_csv(cols.PAYMENT_COLUMNS, payments_before),
        )

    def test_an_xlsx_round_trip_carries_the_same_data(self):
        self.build_troop()
        before = exporter.member_records()

        Person.objects.all().delete()

        table = read_table(
            "members.xlsx",
            write_xlsx(cols.member_columns(), before, title="Members"),
            column_set=cols.member_columns(),
        )
        apply_plan(build_plan(table))

        after = exporter.member_records()
        self.assertEqual(len(after), len(before))
        for written, original in zip(after, before, strict=True):
            for column in cols.member_columns():
                with self.subTest(column=column.key, name=original["first_name"]):
                    self.assertEqual(
                        cols.to_cell(written.get(column.key), column),
                        cols.to_cell(original.get(column.key), column),
                    )

    def test_the_parent_link_survives_the_round_trip(self):
        self.build_troop()
        before = exporter.member_records()

        Person.objects.all().delete()
        table = read_table(
            "members.csv",
            write_csv(cols.member_columns(), before),
            column_set=cols.member_columns(),
        )
        apply_plan(build_plan(table))

        child = Person.objects.get(external_id="CHILD-1")
        self.assertEqual(
            list(child.parents.values_list("external_id", flat=True)), ["PARENT-1"]
        )
        self.assertEqual(ParentChild.objects.count(), 2)


# --- The page ----------------------------------------------------------------


class ImportExportViewsTest(ImportExportTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("members:member_import")
        self.staff_person = Person.objects.create(
            first_name="Ada",
            last_name="Staff",
            primary_role=self.role_parent,
            status="a",
        )
        self.staff = Account.objects.create_user(
            email="staff@test.be", password="testpass", person=self.staff_person, is_staff=True
        )

    def login(self):
        self.client.force_login(self.staff)

    def upload(self, data, action="preview", name="members.csv"):
        return self.client.post(
            self.url,
            {
                "action": action,
                "members": SimpleUploadedFile(name, data, content_type="text/csv"),
            },
        )

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        response = self.client.get(self.url)

        self.assertRedirects(response, f"{reverse('account_login')}?next={self.url}")

    def test_a_member_of_staff_gets_the_page(self):
        self.login()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("members:import_template", args=["csv"]))

    def test_a_signed_in_member_who_is_not_staff_is_refused(self):
        other = Person.objects.create(
            first_name="No", last_name="Staff", primary_role=self.role_parent, status="a"
        )
        self.client.force_login(
            Account.objects.create_user(email="no@test.be", password="pw", person=other)
        )

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_the_staff_menu_offers_the_page(self):
        self.login()

        response = self.client.get(reverse("homepage"))

        self.assertContains(response, self.url)

    def test_a_member_download_carries_the_export_s_headers(self):
        self.login()

        response = self.client.get(
            reverse("members:export_download", args=["members", "csv"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".csv", response["Content-Disposition"])

    def test_the_payments_download_is_closed_while_the_fees_module_is_off(self):
        from members.models import TroopSettings

        self.login()
        troop = TroopSettings.get_settings()
        troop.fees_enabled = False
        troop.save()

        response = self.client.get(
            reverse("members:export_download", args=["payments", "csv"])
        )

        self.assertEqual(response.status_code, 404)

    def test_an_upload_shows_a_preview_and_writes_nothing(self):
        self.login()

        response = self.upload(
            csv_bytes(
                ("external_id", "first_name", "last_name"), ("X1", "Jean", "Dupont")
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["counts"]["members_created"], 1)
        self.assertFalse(Person.objects.filter(external_id="X1").exists())

    def test_an_exported_file_imports_without_a_complaint_about_its_own_columns(self):
        from members.models import TroopSettings

        self.make_child(external_id="X1")
        troop = TroopSettings.get_settings()
        troop.fees_enabled = True
        troop.save()
        exported = write_csv(
            cols.member_columns(include_balances=True),
            exporter.member_records(include_balances=True),
        )
        self.login()

        response = self.upload(exported)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["plan"].file_warnings, [])

    def test_confirming_the_preview_writes_the_file(self):
        self.login()
        self.upload(
            csv_bytes(
                ("external_id", "first_name", "last_name"), ("X1", "Jean", "Dupont")
            )
        )

        response = self.client.post(self.url, {"action": "apply"})

        self.assertRedirects(response, self.url)
        self.assertTrue(Person.objects.filter(external_id="X1").exists())

    def test_cancelling_the_preview_keeps_the_file_out_of_the_database(self):
        self.login()
        self.upload(
            csv_bytes(
                ("external_id", "first_name", "last_name"), ("X1", "Jean", "Dupont")
            )
        )

        response = self.client.post(self.url, {"action": "cancel"})

        self.assertRedirects(response, self.url)
        self.assertFalse(Person.objects.filter(external_id="X1").exists())

    def test_a_file_with_errors_is_shown_and_not_applied(self):
        self.login()
        self.upload(csv_bytes(("first_name", "last_name"), ("", "Dupont")))

        response = self.client.post(self.url, {"action": "apply"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["plan"].has_errors)
        # Only the staff member who is looking at the page.
        self.assertEqual(Person.objects.count(), 1)

    def test_an_unreadable_file_is_reported_instead_of_crashing(self):
        self.login()

        response = self.upload(b"a;b;c\r\n1;2;3\r\n")

        self.assertRedirects(response, self.url)
        self.assertEqual(Person.objects.count(), 1)

    def test_the_preview_survives_a_change_of_language(self):
        self.login()
        self.upload(
            csv_bytes(("first_name", "last_name"), ("Jean", "Dupont")),
        )

        response = self.client.post(self.url, {"action": "apply"}, headers={"accept-language": "nl"})

        self.assertRedirects(response, self.url)
        self.assertTrue(Person.objects.filter(first_name="Jean").exists())

    def test_importing_from_the_page_sends_no_mail(self):
        self.login()
        self.upload(
            csv_bytes(
                ("first_name", "last_name", "email"), ("Jean", "Dupont", "jean@test.be")
            )
        )

        self.client.post(self.url, {"action": "apply"})

        self.assertTrue(Account.objects.filter(email="jean@test.be").exists())
        self.assertFalse(Email.objects.exists())
        self.assertEqual(mail.outbox, [])
