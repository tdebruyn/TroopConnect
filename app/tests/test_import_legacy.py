"""End-to-end tests for the legacy DB importer.

Each test builds a small SQLite file mimicking the legacy schema
(db21sv_20240520.sqlite), then runs ``import_legacy`` against it and asserts the
records that land in the target models.
"""

import os
import sqlite3
import tempfile

from django.core.management import call_command
from django.test import TestCase

from finance.models import CotisationConfig, FeeRule, Payment
from homepage.models import Event
from members.models import (
    Account,
    Enrollment,
    ParentChild,
    Person,
    PersonRole,
    Role,
    Section,
)


def _source_db():
    """Create a temporary legacy SQLite DB with a representative fixture."""
    handle, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(handle)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE auth_user (
            id INTEGER PRIMARY KEY, email TEXT, first_name TEXT, last_name TEXT,
            password TEXT, is_staff INTEGER, is_superuser INTEGER,
            is_active INTEGER, date_joined TEXT
        );
        CREATE TABLE accounts_myprofile (
            id INTEGER PRIMARY KEY, user_id INTEGER, telephone TEXT, adresse TEXT,
            code_postal TEXT, localite TEXT, is_parent INTEGER, is_anime INTEGER
        );
        CREATE TABLE accounts_parent (id INTEGER PRIMARY KEY, login_id INTEGER);
        CREATE TABLE accounts_anime (
            id INTEGER PRIMARY KEY, prenom TEXT, nom TEXT, date_de_naissance TEXT,
            totem TEXT, notes TEXT, famille_id INTEGER, login_id INTEGER, genre TEXT
        );
        CREATE TABLE accounts_famille (id INTEGER PRIMARY KEY, nom_de_famille TEXT);
        CREATE TABLE accounts_liendeparente (
            id INTEGER PRIMARY KEY, famille_id INTEGER, parent_id INTEGER
        );
        CREATE TABLE inscriptions_section (
            id INTEGER PRIMARY KEY, code TEXT, nom TEXT
        );
        CREATE TABLE inscriptions_inscription (
            id INTEGER PRIMARY KEY, anime_id INTEGER, section_id INTEGER, qualite TEXT
        );
        CREATE TABLE inscriptions_historyinscription (
            id INTEGER PRIMARY KEY, inscription_id INTEGER, annee INTEGER
        );
        CREATE TABLE cotisations_cotisationrule (
            id INTEGER PRIMARY KEY, annee INTEGER, montant_a REAL, montant_b REAL,
            montant_c REAL, montant_penalite REAL, date_penalite TEXT
        );
        CREATE TABLE cotisations_cotisation (
            id INTEGER PRIMARY KEY, annee INTEGER, famille_id INTEGER
        );
        CREATE TABLE cotisations_cotisationpayement (
            id INTEGER PRIMARY KEY, date_payement TEXT, montant_paye REAL,
            commentaire TEXT, cotisation_id INTEGER
        );
        CREATE TABLE inscriptions_evenement (
            id INTEGER PRIMARY KEY, date_event TEXT, titre TEXT, contenu TEXT,
            section_id INTEGER
        );
        CREATE TABLE auth_group (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE auth_user_groups (
            id INTEGER PRIMARY KEY, user_id INTEGER, group_id INTEGER
        );
        """
    )
    conn.executescript(
        """
        -- Login accounts: admin, a parent (empty first name), and a person who
        -- is both parent and staff (unit leader).
        INSERT INTO auth_user VALUES
            (1, 'admin@test.be', 'Admin', 'User', 'pbkdf2_hash_admin', 1, 1, 1, '2020-01-01'),
            (2, 'parent@test.be', '', 'Stassin', 'pbkdf2_hash_parent', 0, 0, 1, '2020-01-01'),
            (3, 'tom@test.be', 'Tom', 'Debruyne', 'pbkdf2_hash_tom', 0, 0, 1, '2020-01-01');
        INSERT INTO accounts_myprofile VALUES
            (1, 1, '', '', '', '', 0, 0),
            (2, 2, '0477/24.68.74', 'Rue Deladriere 36', '1300', 'Limal', 1, 0),
            (3, 3, '', 'Rue X 1', '1300', 'Limal', 1, 1);
        INSERT INTO accounts_parent VALUES (10, 2), (11, 3);
        INSERT INTO accounts_famille VALUES (1, 'Stassin'), (2, 'Debruyne');
        INSERT INTO accounts_liendeparente VALUES (1, 1, 10), (2, 2, 11);
        -- Child 20/21 belong to the Stassin family; 22 is the leader (both).
        INSERT INTO accounts_anime VALUES
            (20, 'Erin', 'Stassin', '2010-04-04', NULL, NULL, 1, NULL, 'f'),
            (21, 'Kieran', 'Stassin', '2012-06-19', NULL, NULL, 1, NULL, 'm'),
            (22, 'Tom', 'Debruyne', '1990-01-01', 'Totem', NULL, 2, 3, 'm');
        INSERT INTO inscriptions_section VALUES
            (1, 'bal1', 'Petit Bonheur'), (2, 'route', 'Route');
        INSERT INTO inscriptions_inscription VALUES
            (1, 20, 1, 'anime'), (2, 21, 1, 'anime'), (3, 22, 2, 'staff');
        INSERT INTO inscriptions_historyinscription VALUES (1, 3, 2023);
        INSERT INTO cotisations_cotisationrule VALUES
            (1, 2023, 70, 50, 50, 10, '11-01');
        INSERT INTO cotisations_cotisation VALUES (100, 2023, 1), (101, 2023, 2);
        INSERT INTO cotisations_cotisationpayement VALUES
            (1, '2023-09-15', 70, 'Erin', 100),
            (2, '2023-09-15', 50, '', 101);
        INSERT INTO inscriptions_evenement VALUES
            (1, '2023-09-01 19:00:00', 'Réunion', 'Contenu', 1);
        INSERT INTO auth_group VALUES (1, 'cotisation_managers');
        INSERT INTO auth_user_groups VALUES (1, 2, 1);
        """
    )
    conn.commit()
    conn.close()
    return path


class ImportLegacyTest(TestCase):
    def test_import(self):
        path = _source_db()
        try:
            call_command("import_legacy", path)
        finally:
            os.remove(path)

        # 3 login-derived people (admin, parent, both-parent-staff) + 2 children
        self.assertEqual(Person.objects.count(), 5)
        self.assertEqual(Account.objects.count(), 3)

        # The "both" person is a single Person with role Animateur.
        tom = Person.objects.get(first_name="Tom")
        self.assertEqual(tom.primary_role.short, "a")

        # Parent with an empty source first name is imported as-is.
        parent = Account.objects.get(email="parent@test.be").person
        self.assertEqual(parent.last_name, "Stassin")
        self.assertEqual(parent.first_name, "")
        self.assertEqual(str(parent.phone), "+32477246874")

        # ParentChild: Stassin parent -> two children.
        self.assertEqual(ParentChild.objects.count(), 2)
        erin = Person.objects.get(first_name="Erin")
        self.assertEqual(erin.as_child.filter(parent=parent).count(), 1)

        # Enrollments in the current school year (2023).
        self.assertEqual(Enrollment.objects.count(), 3)
        self.assertEqual(
            Enrollment.objects.filter(section__name="Petit Bonheur").count(), 2
        )
        self.assertTrue(
            Enrollment.objects.filter(user=tom, section__name="Route").exists()
        )

        # Finance: 6 fee rules, 1 config, 2 payments attributed to a payer.
        self.assertEqual(FeeRule.objects.count(), 6)
        self.assertEqual(CotisationConfig.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 2)
        stassin_payment = Payment.objects.get(note="Erin")
        self.assertEqual(stassin_payment.person, parent)

        # Leader's family (no parent-linked child) pays through the leader.
        tom_payment = Payment.objects.get(amount=50)
        self.assertEqual(tom_payment.person, tom)

        # Event imported minimally.
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.get().title, "Réunion")

        # Secondary role from the cotisation_managers group.
        treasurer = Role.objects.get(short="t")
        self.assertTrue(PersonRole.objects.filter(person=parent, role=treasurer).exists())

        # Section sex is inferred from the code.
        self.assertEqual(Section.objects.get(name="Petit Bonheur").sex, "B")
        self.assertEqual(Section.objects.get(name="Route").sex, "B")

    def test_dry_run_imports_nothing(self):
        path = _source_db()
        try:
            call_command("import_legacy", path, dry_run=True)
        finally:
            os.remove(path)

        # A dry run reports what it would do but persists nothing.
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Enrollment.objects.count(), 0)
