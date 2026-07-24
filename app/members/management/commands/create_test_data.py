from datetime import date

from allauth.account.models import EmailAddress
from django.core.management.base import BaseCommand
from django.db.models.signals import post_save

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
from members.signals import notify_admins_on_profile_save


class Command(BaseCommand):
    help = "Creates test users and data for Playwright E2E tests"

    def handle(self, *args, **options):
        password = "Test1234!"

        # Seeding test data shouldn't fire the "notify registration admins"
        # email, so disconnect that signal for this run only.
        post_save.disconnect(
            notify_admins_on_profile_save, sender=Person
        )

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

        # Child for parent1. Children must have a birthday and sex — enforced
        # by Person.clean() (run via _set_primary_role). Birth years are offset
        # from the current school year so the children always fit the Baladins
        # age band (8-10 on Dec 31), however many years pass.
        baladins_birth = school_year.name - 9
        child = None
        if parent1.person.as_parent.exists():
            child = parent1.person.as_parent.first().child
        if child is None:
            child = Person(
                first_name="Child", last_name="One",
                birthday=date(baladins_birth, 6, 15), sex=Person.Sex.MALE,
            )
            self._set_primary_role(child, role_child)
            ParentChild.objects.create(parent=parent1.person, child=child)
        elif not child.birthday or not child.sex:
            # Backfill a pre-existing child so the seed never leaves one
            # without birthday/sex.
            child.birthday = child.birthday or date(baladins_birth, 6, 15)
            child.sex = child.sex or Person.Sex.MALE
            self._set_primary_role(child, role_child)
        Enrollment.objects.get_or_create(
            user=child, section=section, school_year=school_year
        )

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
        Enrollment.objects.get_or_create(
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

        # --- Child user (Animé) — has a login, enrolled in a section ---
        child_user = self._create_account(
            email="child1@test.be",
            password=password,
            first_name="Child",
            last_name="User",
            is_staff=False,
            birthday=date(school_year.name - 8, 3, 20),
            sex=Person.Sex.FEMALE,
        )
        self._set_primary_role(child_user.person, role_child)
        Enrollment.objects.get_or_create(
            user=child_user.person,
            section=section,
            school_year=school_year,
        )

        # --- Superuser (is_staff + is_superuser) — can reach /admin/ ---
        superadmin = self._create_account(
            email="superadmin@test.be",
            password=password,
            first_name="Super",
            last_name="Admin",
            is_staff=True,
            is_superuser=True,
        )
        self._set_primary_role(superadmin.person, role_parent)

        self.stdout.write(self.style.SUCCESS("Test data created successfully."))
        self.stdout.write(f"  parent1@test.be / {password} (parent with child)")
        self.stdout.write(f"  parent2@test.be / {password} (parent + ar secondary)")
        self.stdout.write(f"  anim1@test.be / {password} (animateur)")
        self.stdout.write(f"  staff1@test.be / {password} (staff)")
        self.stdout.write(f"  child1@test.be / {password} (child / animé)")
        self.stdout.write(f"  superadmin@test.be / {password} (superuser)")

    def _create_account(
        self,
        email,
        password,
        first_name,
        last_name,
        is_staff=False,
        is_superuser=False,
        birthday=None,
        sex=None,
    ):
        account, created = Account.objects.get_or_create(
            email=email,
            defaults={
                "is_staff": is_staff,
                "is_superuser": is_superuser,
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

        # Mark the person as active so OnboardingMiddleware doesn't bounce the
        # non-staff users (parents, animateur, child) to the onboarding page,
        # and apply optional demographics (idempotent on re-runs).
        person = account.person
        changed = False
        if person.status != "a":
            person.status = "a"
            changed = True
        if birthday is not None and person.birthday != birthday:
            person.birthday = birthday
            changed = True
        if sex is not None and person.sex != sex:
            person.sex = sex
            changed = True
        if changed:
            person.save()

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
        # Validate before persisting so the seed can never create a Person that
        # violates model invariants (e.g. a child missing birthday/sex).
        person.full_clean()
        person.save()
