from datetime import date

from allauth.account.models import EmailAddress
from django.core.management.base import BaseCommand

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


class Command(BaseCommand):
    help = "Creates test users and data for Playwright E2E tests"

    def handle(self, *args, **options):
        password = "Test1234!"

        # Ensure school year exists covering today
        today = date.today()
        year = today.year
        school_year = SchoolYear.objects.filter(
            start_date__lte=today, end_date__gte=today
        ).first()
        if not school_year:
            school_year, created = SchoolYear.objects.get_or_create(
                name=year,
                defaults={
                    "start_date": date(year, 9, 1),
                    "end_date": date(year + 1, 8, 31),
                    "range": f"{year}-{year + 1}",
                },
            )
            if created:
                self.stdout.write(f"Created school year: {school_year}")

        # Ensure branch and section exist
        branch, _ = Branch.objects.get_or_create(
            name="Baladins", defaults={"min_age_dec_31": 8, "max_age_dec_31": 10}
        )
        section, _ = Section.objects.get_or_create(
            name="Baladins", defaults={"branch": branch, "sex": "B"}
        )

        # Get roles
        role_parent = Role.objects.get(short="p")
        role_animateur = Role.objects.get(short="a")
        role_child = Role.objects.get(short="e")
        role_ar = Role.objects.get(short="ar")

        # --- Parent 1 (has a child enrolled in section) ---
        parent1 = self._create_account(
            email="parent1@test.be",
            password=password,
            first_name="Parent",
            last_name="One",
            is_staff=False,
        )
        self._set_primary_role(parent1.person, role_parent)

        # Create child
        child = Person.objects.create(
            first_name="Child", last_name="One", primary_role=role_child
        )
        ParentChild.objects.create(parent=parent1.person, child=child)
        Enrollment.objects.create(user=child, section=section, school_year=school_year)

        # --- Parent 2 (parent with ar secondary role — can send-all) ---
        parent2 = self._create_account(
            email="parent2@test.be",
            password=password,
            first_name="Parent",
            last_name="Two",
            is_staff=False,
        )
        self._set_primary_role(parent2.person, role_parent)
        PersonRole.objects.get_or_create(person=parent2.person, role=role_ar)

        # --- Animateur (primary role animateur, enrolled in section) ---
        anim = self._create_account(
            email="anim1@test.be",
            password=password,
            first_name="Anim",
            last_name="One",
            is_staff=False,
        )
        self._set_primary_role(anim.person, role_animateur)
        Enrollment.objects.create(
            user=anim.person, section=section, school_year=school_year
        )

        # --- Staff user ---
        staff = self._create_account(
            email="staff1@test.be",
            password=password,
            first_name="Staff",
            last_name="One",
            is_staff=True,
        )
        self._set_primary_role(staff.person, role_parent)

        self.stdout.write(self.style.SUCCESS("Test data created successfully."))
        self.stdout.write(f"  parent1@test.be / {password} (parent with child)")
        self.stdout.write(f"  parent2@test.be / {password} (parent + ar secondary)")
        self.stdout.write(f"  anim1@test.be / {password} (animateur)")
        self.stdout.write(f"  staff1@test.be / {password} (staff)")

    def _create_account(self, email, password, first_name, last_name, is_staff=False):
        account, created = Account.objects.get_or_create(
            email=email,
            defaults={
                "is_staff": is_staff,
                "is_active": True,
            },
        )
        if created:
            account.person.first_name = first_name
            account.person.last_name = last_name
            account.person.save()
            account.set_password(password)
            account.save()
            self.stdout.write(f"  Created account: {email}")
        else:
            self.stdout.write(f"  Account already exists: {email}")

        # Mark email as verified so allauth lets users log in
        ea, _ = EmailAddress.objects.get_or_create(
            email=email,
            defaults={"user": account, "verified": True, "primary": True},
        )
        if not ea.verified or not ea.primary:
            ea.verified = True
            ea.primary = True
            ea.save()

        return account

    def _set_primary_role(self, person, role):
        person.primary_role = role
        person.save()
