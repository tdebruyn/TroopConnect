"""Import data from the legacy djangoCMS-era SQLite database.

The legacy schema (db21sv_20240520.sqlite) is organised around a ``famille``
(household) entity that no longer exists in TroopConnect.  This command reads
the SQLite file directly and rebuilds the data into the current models:

    auth_user + accounts_myprofile + accounts_parent  ->  Account + Person (Parent)
    accounts_anime                                    ->  Person (Animé / Animateur)
    accounts_famille + accounts_liendeparente         ->  ParentChild
    inscriptions_section                              ->  Section (+ Branch)
    inscriptions_inscription                          ->  Enrollment (current year only)
    cotisations_cotisationrule                        ->  FeeRule + CotisationConfig
    cotisations_cotisationpayement                    ->  Payment (attributed to a payer)
    inscriptions_evenement                            ->  homepage.Event
    auth_user_groups                                  ->  PersonRole (secondary roles)

Usage:
    manage.py import_legacy /path/to/db21sv_20240520.sqlite

Designed for a freshly-migrated database (roles/branches/school years from
migrations are reused via get_or_create).  The whole import runs inside a
single transaction and is aborted (rolled back) on the first error.
"""

import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime

import phonenumbers
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from finance.models import CotisationConfig, FeeRule, Payment
from homepage.models import Event
from members.models import (
    Account,
    Branch,
    Enrollment,
    ParentChild,
    Person,
    PersonRole,
    Role,
    SchoolYear,
    Section,
)

# --- Static mapping tables (edit these to adjust the import) -----------------

# Scout age branches.  min/max are ages on 31 Dec of the school year.
# Route has no real upper bound; we cap it so the passage task can still
# "age out" members who grow past the oldest branch.
BRANCHES = [
    ("Baladins", 6, 8),
    ("Louveteaux", 8, 12),
    ("Éclaireurs", 12, 16),
    ("Pionniers", 16, 18),
    ("Route", 18, 25),
]

# Legacy section code -> (branch name, sex).  `None` marks the pseudo-sections
# "Toutes" and "Conseil d'Unité" that staff are enrolled in but which have no
# age branch.
SECTION_MAP = {
    "bal1": ("Baladins", "B"),
    "bal2": ("Baladins", "B"),
    "lou1": ("Louveteaux", "M"),
    "lou2": ("Louveteaux", "B"),
    "lou3": ("Louveteaux", "F"),
    "ecl1": ("Éclaireurs", "F"),
    "ecl2": ("Éclaireurs", "M"),
    "pio1": ("Pionniers", "B"),
    "pio2": ("Pionniers", "B"),
    "route": ("Route", "B"),
    "all": (None, None),
    "cu": (None, None),
}

# Legacy `inscriptions_inscription.qualite` -> TroopConnect primary Role short.
QUALITE_TO_ROLE = {
    "anime": "e",  # Animé (child)
    "staff": "a",  # Animateur
    "chefdu": "a",  # Animateur (chef d'unité)
    "intendant": "a",  # Animateur (intendant)
    "ancien": "a",  # Former staff -> Animateur
}

# Legacy auth_group name -> secondary Role short.
GROUP_TO_ROLE = {
    "chefs_unite": "ar",
    "cotisation_managers": "t",
    "inscription_managers": "ri",
    "webmasters": "ad",
    "user_managers": "ad",
}

# Legacy `cotisations_cotisationrule` "MM-DD" penalty date -> (month, day).
# Only used for the late_deadline; the flat penalty amount is not converted.


class Command(BaseCommand):
    help = "Import the legacy SQLite database into TroopConnect."

    def add_arguments(self, parser):
        parser.add_argument("sqlite_path", help="Path to the legacy .sqlite file.")

    @transaction.atomic
    def handle(self, *args, **options):
        path = options["sqlite_path"]
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            self._import(conn)
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _rows(self, conn, sql):
        return conn.execute(sql).fetchall()

    def _lookup(self, conn, table):
        return {row["id"]: row for row in self._rows(conn, f"SELECT * FROM {table}")}

    def _normalize_phone(self, raw):
        """Return an E.164 string, or None when the number can't be parsed."""
        if not raw:
            return None
        digits = re.sub(r"\D", "", raw)
        if not digits:
            return None
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("0") and len(digits) == 10:
            digits = "32" + digits[1:]  # Belgian mobile/landline without country code
        if not digits.startswith("+"):
            digits = "+" + digits
        try:
            parsed = phonenumbers.parse(digits, None)
            if not phonenumbers.is_valid_number(parsed):
                return None
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            return None

    def _merge_address(self, adresse, code_postal, localite):
        parts = []
        if adresse:
            parts.append(adresse.strip().strip(","))
        if code_postal and code_postal != "0000":
            city = f"{code_postal} {localite}".strip() if localite else code_postal
            parts.append(city)
        return ", ".join(parts) or None

    def _map_sex(self, genre):
        return {"m": Person.Sex.MALE, "f": Person.Sex.FEMALE}.get(
            (genre or "").lower()
        )

    def _parse_datetime(self, value):
        """Parse a naive legacy datetime string into an aware datetime."""
        if not value:
            return timezone.now()
        parsed = datetime.fromisoformat(str(value))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        return parsed

    # ------------------------------------------------------------------ #
    # Import
    # ------------------------------------------------------------------ #
    def _import(self, conn):
        stats = defaultdict(int)
        warnings = []

        # --- Static reference data ------------------------------------ #
        roles = {r.short: r for r in Role.objects.all()}
        branches = self._ensure_branches()
        school_years = self._ensure_school_years(conn)
        sections = self._ensure_sections(conn, branches)
        current_year = self._current_school_year(conn, school_years)

        # --- Source rows ----------------------------------------------- #
        auth_users = self._lookup(conn, "auth_user")
        profiles = self._lookup(conn, "accounts_myprofile")
        parents = self._lookup(conn, "accounts_parent")
        animes = self._lookup(conn, "accounts_anime")
        liens = self._rows(conn, "SELECT * FROM accounts_liendeparente")
        inscriptions = {
            row["anime_id"]: row
            for row in self._rows(conn, "SELECT * FROM inscriptions_inscription")
        }
        group_rows = self._rows(
            conn,
            "SELECT user_id, group_id FROM auth_user_groups",
        )
        group_names = {
            row["id"]: row["name"]
            for row in self._rows(conn, "SELECT * FROM auth_group")
        }

        # --- People: one Person per login (myprofile), plus animés
        #     without a login.  The 24 people who are both parent and
        #     animé share one myprofile and therefore collapse into a
        #     single Person. -------------------------------------------- #
        person_by_profile = {}  # myprofile id -> Person
        person_by_anime = {}  # accounts_anime id -> Person
        person_by_parent = {}  # accounts_parent id -> Person

        for prof in profiles.values():
            user = auth_users.get(prof["user_id"])
            if user is None or not user["email"]:
                continue  # AnonymousUser and any profile without an email

            anime = self._find_anime_by_login(animes, prof["id"])
            qualite = inscriptions[anime["id"]]["qualite"] if anime and anime["id"] in inscriptions else None
            role_short = QUALITE_TO_ROLE.get(qualite, "p") if anime else ("p" if prof["is_parent"] else "p")

            if anime:
                first_name = anime["prenom"] or user["first_name"]
                last_name = anime["nom"] or user["last_name"]
                birthday = anime["date_de_naissance"]
                sex = self._map_sex(anime["genre"])
                totem = anime["totem"]
                note = anime["notes"]
            else:
                first_name = user["first_name"]
                last_name = user["last_name"]
                birthday = None
                sex = None
                totem = None
                note = None

            person = self._create_person(
                roles, role_short, first_name, last_name, birthday, sex,
                self._merge_address(prof["adresse"], prof["code_postal"], prof["localite"]),
                self._normalize_phone(prof["telephone"]), totem, note,
            )
            self._create_account(user, person)
            person_by_profile[prof["id"]] = person
            if anime:
                person_by_anime[anime["id"]] = person
            stats["accounts"] += 1
            if not first_name:
                warnings.append(f"Empty first name: {user['email']}")
            if role_short == "e" and (sex is None or birthday is None):
                stats["children_incomplete"] += 1

        # Animés without a login (children whose parents hold the account).
        for anime in animes.values():
            if anime["login_id"] is not None:
                continue
            insc = inscriptions.get(anime["id"])
            qualite = insc["qualite"] if insc else "anime"
            role_short = QUALITE_TO_ROLE.get(qualite, "e")
            person = self._create_person(
                roles, role_short, anime["prenom"], anime["nom"],
                anime["date_de_naissance"], self._map_sex(anime["genre"]),
                None, None, anime["totem"], anime["notes"],
            )
            person_by_anime[anime["id"]] = person
            stats["people_no_login"] += 1
            if role_short == "e" and (person.sex is None or person.birthday is None):
                stats["children_incomplete"] += 1

        # Map parents (accounts_parent.login_id -> myprofile) to Persons.
        for parent in parents.values():
            person = person_by_profile.get(parent["login_id"])
            if person is not None:
                person_by_parent[parent["id"]] = person

        # --- ParentChild links (through famille) ----------------------- #
        self._import_parent_child(conn, animes, inscriptions, liens, person_by_parent, person_by_anime, stats)

        # --- Enrollments (current year only) ---------------------------- #
        self._import_enrollments(inscriptions, person_by_anime, sections, current_year, stats)

        # --- Finance ----------------------------------------------------- #
        self._import_finance(conn, school_years, person_by_parent, person_by_anime, stats, warnings)

        # --- Events ------------------------------------------------------ #
        self._import_events(conn, sections, stats)

        # --- Secondary roles from groups -------------------------------- #
        self._import_secondary_roles(auth_users, profiles, group_rows, group_names, person_by_profile, roles, stats)

        # --- Summary ----------------------------------------------------- #
        self.stdout.write(self.style.SUCCESS("Import complete."))
        for key in sorted(stats):
            self.stdout.write(f"  {key}: {stats[key]}")
        for w in warnings:
            self.stdout.write(self.style.WARNING(f"  ! {w}"))

    # ------------------------------------------------------------------ #
    # Static data
    # ------------------------------------------------------------------ #
    def _ensure_branches(self):
        branches = {}
        for name, min_age, max_age in BRANCHES:
            branch, _ = Branch.objects.get_or_create(
                name=name, defaults={"min_age_dec_31": min_age, "max_age_dec_31": max_age}
            )
            branches[name] = branch
        return branches

    def _ensure_school_years(self, conn):
        years = set()
        for row in self._rows(conn, "SELECT DISTINCT annee FROM cotisations_cotisation"):
            years.add(row["annee"])
        for row in self._rows(conn, "SELECT DISTINCT annee FROM inscriptions_historyinscription"):
            years.add(row["annee"])
        result = {}
        for year in sorted(years):
            school_year, _ = SchoolYear.objects.get_or_create(
                name=year,
                defaults={
                    "start_date": date(year, 8, 1),
                    "end_date": date(year + 1, 7, 31),
                    "range": f"{year}-{year + 1}",
                },
            )
            result[year] = school_year
        return result

    def _current_school_year(self, conn, school_years):
        """The school year that the legacy `inscription` rows represent.

        The dump is dated 2024-05-20, so its "current" school year is 2023-2024.
        We take the latest year recorded in the enrollment history.
        """
        years = [
            row["annee"]
            for row in self._rows(conn, "SELECT DISTINCT annee FROM inscriptions_historyinscription")
        ]
        if not years:
            years = sorted(school_years)
        return school_years[max(years)]

    def _ensure_sections(self, conn, branches):
        """Create target Sections, keyed by legacy section id.

        Branch/sex come from SECTION_MAP (by legacy code); the human-readable
        name comes straight from the source.
        """
        sections = {}
        for row in self._rows(conn, "SELECT * FROM inscriptions_section"):
            branch_name, sex = SECTION_MAP.get(row["code"], (None, None))
            branch = branches.get(branch_name) if branch_name else None
            section, _ = Section.objects.get_or_create(
                name=row["nom"],
                defaults={"branch": branch, "sex": sex},
            )
            sections[row["id"]] = section
        return sections

    # ------------------------------------------------------------------ #
    # People
    # ------------------------------------------------------------------ #
    def _find_anime_by_login(self, animes, profile_id):
        for anime in animes.values():
            if anime["login_id"] == profile_id:
                return anime
        return None

    def _create_person(self, roles, role_short, first_name, last_name, birthday, sex, address, phone, totem, note):
        person = Person(
            first_name=first_name or "",
            last_name=last_name or "",
            birthday=birthday,
            sex=sex,
            address=address,
            phone=phone,
            totem=totem,
            note=note or "",
            primary_role=roles[role_short],
            status="a",
        )
        person.save()  # Person.save() fills secret_key
        return person

    def _create_account(self, user, person):
        Account.objects.get_or_create(
            email=user["email"],
            defaults={
                "person": person,
                "password": user["password"] or None,
                "is_staff": bool(user["is_staff"]),
                "is_superuser": bool(user["is_superuser"]),
                "is_active": bool(user["is_active"]),
                "date_joined": self._parse_datetime(user["date_joined"]),
            },
        )

    # ------------------------------------------------------------------ #
    # Relations / enrollments
    # ------------------------------------------------------------------ #
    def _import_parent_child(self, conn, animes, inscriptions, liens, person_by_parent, person_by_anime, stats):
        # children by family
        children_by_family = defaultdict(list)
        for anime in animes.values():
            if anime["famille_id"] is None:
                continue
            insc = inscriptions.get(anime["id"])
            if insc and insc["qualite"] == "anime":  # only actual children, not staff
                children_by_family[anime["famille_id"]].append(anime["id"])

        parents_by_family = defaultdict(list)
        for lien in liens:
            parents_by_family[lien["famille_id"]].append(lien["parent_id"])

        for famille_id, child_ids in children_by_family.items():
            parent_ids = parents_by_family.get(famille_id, [])
            if not parent_ids:
                continue
            primary = min(parent_ids)
            for parent_id in parent_ids:
                parent = person_by_parent.get(parent_id)
                if parent is None:
                    continue
                for child_id in child_ids:
                    child = person_by_anime.get(child_id)
                    if child is None:
                        continue
                    ParentChild.objects.get_or_create(
                        parent=parent,
                        child=child,
                        defaults={"primary_contact": parent_id == primary},
                    )
                    stats["parent_child"] += 1

    def _import_enrollments(self, inscriptions, person_by_anime, sections, current_year, stats):
        for anime_id, insc in inscriptions.items():
            person = person_by_anime.get(anime_id)
            section = sections.get(insc["section_id"])
            if person is None or section is None:
                continue
            Enrollment.objects.get_or_create(
                user=person, section=section, school_year=current_year
            )
            stats["enrollments"] += 1

    # ------------------------------------------------------------------ #
    # Finance
    # ------------------------------------------------------------------ #
    def _import_finance(self, conn, school_years, person_by_parent, person_by_anime, stats, warnings):
        cotisations = {
            row["id"]: row for row in self._rows(conn, "SELECT * FROM cotisations_cotisation")
        }
        parents_by_family = defaultdict(list)
        for lien in self._rows(conn, "SELECT * FROM accounts_liendeparente"):
            parents_by_family[lien["famille_id"]].append(lien["parent_id"])
        animes_by_family = defaultdict(list)
        for anime in self._rows(conn, "SELECT * FROM accounts_anime"):
            if anime["famille_id"] is not None:
                animes_by_family[anime["famille_id"]].append(anime["id"])

        # Fee rules + configs, one year at a time.
        for rule in self._rows(conn, "SELECT * FROM cotisations_cotisationrule"):
            school_year = school_years.get(rule["annee"])
            if school_year is None:
                continue
            self._import_fee_rules(school_year, rule)
            self._import_cotisation_config(school_year, rule)
            stats["fee_rules"] += 6  # 3 child ranks + 3 animator ranks
            stats["cotisation_configs"] += 1

        # Payments: attribute each family cotisation's payments to a payer.
        for pay in self._rows(conn, "SELECT * FROM cotisations_cotisationpayement"):
            cotisation = cotisations.get(pay["cotisation_id"])
            if cotisation is None:
                continue
            school_year = school_years.get(cotisation["annee"])
            if school_year is None:
                continue
            payer = self._family_payer(
                cotisation["famille_id"], parents_by_family, animes_by_family,
                person_by_parent, person_by_anime,
            )
            if payer is None:
                warnings.append(f"Payment {pay['id']}: no payer for famille {cotisation['famille_id']}")
                continue
            amount = pay["montant_paye"]
            if amount is None:
                warnings.append(f"Payment {pay['id']}: null amount, skipped")
                continue
            Payment.objects.create(
                person=payer,
                school_year=school_year,
                amount=amount,
                date=pay["date_payement"] or school_year.start_date,
                note=pay["commentaire"] or "",
            )
            stats["payments"] += 1

    def _family_payer(self, famille_id, parents_by_family, animes_by_family, person_by_parent, person_by_anime):
        parent_ids = parents_by_family.get(famille_id, [])
        if parent_ids:
            return person_by_parent.get(min(parent_ids))
        anime_ids = animes_by_family.get(famille_id, [])
        if anime_ids:
            return person_by_anime.get(min(anime_ids))
        return None

    def _import_fee_rules(self, school_year, rule):
        amounts = {
            1: rule["montant_a"],
            2: rule["montant_b"],
            3: rule["montant_c"],
        }
        for rank, amount in amounts.items():
            FeeRule.objects.get_or_create(
                school_year=school_year, branch=None, rank=rank,
                member_type=FeeRule.MemberType.CHILD,
                defaults={"amount": amount or 0},
            )
            FeeRule.objects.get_or_create(
                school_year=school_year, branch=None, rank=rank,
                member_type=FeeRule.MemberType.ANIMATOR,
                # Animators pay the "2nd member" price (montant_b).
                defaults={"amount": rule["montant_b"] or 0},
            )

    def _import_cotisation_config(self, school_year, rule):
        deadline = self._parse_penalty_date(school_year.name, rule["date_penalite"])
        CotisationConfig.objects.get_or_create(
            school_year=school_year,
            defaults={
                "late_penalty_percent": 0,  # flat € penalty has no percent equivalent
                "late_deadline": deadline,
            },
        )

    def _parse_penalty_date(self, year, mm_dd):
        if not mm_dd:
            return None
        m = re.match(r"^(\d{2})-(\d{2})$", mm_dd)
        if not m:
            return None
        month, day = int(m.group(1)), int(m.group(2))
        try:
            return date(year, month, day)
        except ValueError:
            return None

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #
    def _import_events(self, conn, sections, stats):
        for ev in self._rows(conn, "SELECT * FROM inscriptions_evenement"):
            if ev["date_event"] is None or ev["titre"] is None:
                continue
            section = sections.get(ev["section_id"])
            Event.objects.create(
                title=ev["titre"],
                description=ev["contenu"] or "",
                date=ev["date_event"].split(" ")[0],  # drop the time component
                section=section,
            )
            stats["events"] += 1

    # ------------------------------------------------------------------ #
    # Secondary roles
    # ------------------------------------------------------------------ #
    def _import_secondary_roles(self, auth_users, profiles, group_rows, group_names, person_by_profile, roles, stats):
        profile_by_user = {p["user_id"]: p for p in profiles.values()}
        for row in group_rows:
            group_name = group_names.get(row["group_id"])
            role_short = GROUP_TO_ROLE.get(group_name)
            if role_short is None:
                continue
            profile = profile_by_user.get(row["user_id"])
            person = person_by_profile.get(profile["id"]) if profile else None
            if person is None:
                continue
            _, created = PersonRole.objects.get_or_create(person=person, role=roles[role_short])
            if created:
                stats["secondary_roles"] += 1
