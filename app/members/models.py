from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from phonenumber_field.modelfields import PhoneNumberField
from django.db.models import Q, Count
from datetime import datetime, date
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords
import uuid

# class CustomAccountManager(BaseUserManager):
#     def create_user(
#         self,
#         is_staff=False,
#         is_superuser=False,
#         email=None,
#         password=None,
#     ):
#         normalized_email = self.normalize_email(email) if email else None
#         user = self.model(
#             email=normalized_email,
#             is_staff=is_staff,
#             is_superuser=is_superuser,
#         )
#         if password:
#             user.set_password(password)
#         else:
#             user.set_unusable_password()
#         user.save(using=self._db)
#         return user

#     def create_superuser(
#         self, first_name, last_name, email=None, birthday=None, password=None
#     ):

#         return self.create_user(
#             is_staff=True,
#             is_superuser=True,
#             email=email,
#             password=password
#         )


def default_role():
    return Role.objects.get(short="n")


class Person(models.Model):
    """
    Represents any person in the system (parents, children, leaders, ...).  Only those who need a login get an Account.
    """

    class Sex(models.TextChoices):
        MALE = "M", "Garçon"
        FEMALE = "F", "Fille"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    birthday = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, null=True, blank=True)
    address = models.CharField(max_length=200, null=True, blank=True)
    phone = PhoneNumberField(region="BE", null=True, blank=True)
    totem = models.CharField(max_length=60, null=True, blank=True)
    photo_consent = models.BooleanField(default=False)
    note = models.TextField(max_length=500, blank=True)
    primary_role = models.ForeignKey(
        "Role",
        on_delete=models.PROTECT,
        limit_choices_to={"is_primary": True},
        related_name="primary_persons",
        default=default_role,
    )
    status = models.CharField(
        max_length=2,
        choices=[
            ("a", "Active"),
            ("ar", "Archived"),
            ("r", "Requested"),
        ],
        default="r",
    )

    roles = models.ManyToManyField(
        "Role",
        through="PersonRole",
        related_name="people",
        blank=True,
    )

    parents = models.ManyToManyField(
        "self",
        through="ParentChild",
        through_fields=("child", "parent"),
        symmetrical=False,
        related_name="children",
        blank=True,
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def needs_membership(self) -> bool:
        # membership app can check this
        role_names = {r.name for r in self.roles.all()}
        return bool(role_names & {"Leader", "Child"})

    @property
    def has_account(self) -> bool:
        return hasattr(self, "account")

    def is_adult(self):
        if self.birthday:
            birthday_int = self.birthday_to_int()
            current_date_int = self.current_date_to_int()
            return (current_date_int - birthday_int) > 180000
        return True

    def get_section(self):
        # Returns the current section enrollment for the person.
        # If no enrollment exists for the current year, returns next year's enrollment with the year between parentheses.
        # If no enrollment exists for the next year, returns None.

        current_year = SchoolYear.current()
        enrollment = self.enrollment_set.filter(school_year=current_year).first()
        if enrollment:
            return enrollment.section
        else:
            next_year = SchoolYear.next_school_year()
            enrollment = self.enrollment_set.filter(school_year=next_year).first()
            if enrollment:
                return f"{enrollment.section} ({next_year.range})"

        return {"name": "En attente"}


class Role(models.Model):
    short = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=30, unique=True)
    description = models.TextField()
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class PersonRole(models.Model):
    """
    Assigns a Role to a Person, with optional metadata (e.g. date_promoted).
    """

    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    date_assigned = models.DateField(default=timezone.now)

    class Meta:
        unique_together = ("person", "role")


class ParentChild(models.Model):
    """
    Links children to their parents.  You can mark one as “primary_contact”.
    """

    parent = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="as_parent"
    )
    child = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="as_child")
    primary_contact = models.BooleanField(default=False)

    class Meta:
        unique_together = ("parent", "child")


class AccountManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email address is required")
        email = self.normalize_email(email)

        # Extract person from extra_fields
        person = extra_fields.pop("person", None)

        # If no person provided, create one from extra_fields
        if not person:
            person_fields = {}
            for field in [
                "first_name",
                "last_name",
                "birthday",
                "sex",
                "address",
                "phone",
                "photo_consent",
                "note",
            ]:
                if field in extra_fields:
                    person_fields[field] = extra_fields.pop(field)

            # Ensure required fields are present
            if "first_name" not in person_fields or "last_name" not in person_fields:
                raise ValueError(
                    "First name and last name are required to create a Person"
                )

            person = Person.objects.create(**person_fields)

        # Create the account linked to the person
        user = self.model(email=email, person=person, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        # Ensure first_name and last_name are provided for Person creation
        if "first_name" not in extra_fields:
            extra_fields["first_name"] = "Admin"
        if "last_name" not in extra_fields:
            extra_fields["last_name"] = "User"

        return self.create_user(email, password, **extra_fields)


class Account(AbstractBaseUser, PermissionsMixin):
    """
    Only people who need a login get an Account.
    An Account must always be linked to a Person.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.OneToOneField(Person, on_delete=models.CASCADE)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = AccountManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        # Ensure person is set
        if not self.person_id:
            person = Person.objects.create()
            person.primary_role = default_role()
            self.person = person
        super().save(*args, **kwargs)

        # class CustomUser(AbstractBaseUser, PermissionsMixin):
        #     class Sex(models.TextChoices):
        #         MALE = "m", _("Male")
        #         FEMALE = "f", _("Female")
        #     class Status(models.TextChoices):
        #         ACTIVE = "a", _("Active")
        #         ARCHIVED = "ar", _("Archived")
        #         REQUESTED = "r", _("Requested")
        #     class Type(models.TextChoices):
        #         CHILD = "c", _("Child")
        #         LEADER = "l", _("Leader")
        #         PARENT = "p", _("Parent")
        #         ACTIVE_PARENT = "a", _("Active Parent")
        #     email = models.EmailField(unique=True, null=True, blank=True)
        #     username = models.CharField(primary_key=True, max_length=30, unique=True)
        #     password = models.CharField(max_length=128, null=True, blank=True)
        #     birthday = models.DateField(
        #         null=True, blank=True, help_text=_("Required only for childrens")
        #     )
        #     secret_key = models.CharField(max_length=30, null=True, blank=True)
        #     address = models.CharField(max_length=200, null=True, blank=True)
        #     phone = PhoneNumberField(region="BE", null=True, blank=True)
        #     first_name = models.CharField(max_length=150, null=True, blank=True)
        #     last_name = models.CharField(max_length=150, null=True, blank=True)
        #     sex = models.CharField(max_length=1, choices=Sex.choices, null=True, blank=True)
        #     status = models.CharField(max_length=2, choices=Status.choices, default=Status.REQUESTED)
        #     totem = models.CharField(max_length=60, null=True, blank=True)
        #     is_active = models.BooleanField(default=True)
        #     is_staff = models.BooleanField(default=False)
        #     date_joined = models.DateTimeField(default=timezone.now)
        #     parents = models.ManyToManyField("CustomUser", blank=True, related_name="children")
        #     photo_consent = models.BooleanField(
        #         default=False, help_text=_("I give my consent to use my photo")
        #     )
        #     note = models.TextField(max_length=500, null=True, blank=True)
        #     history = HistoricalRecords(m2m_fields=[PermissionsMixin.groups.field])
        #     objects = CustomUserManager()

        #     USERNAME_FIELD = "username"
        #     REQUIRED_FIELDS = ["first_name", "last_name", "birthday", "email"]

        #     class Meta:
        #         verbose_name = _("user")
        #         verbose_name_plural = _("users")

        #     def __str__(self) -> str:
        #         """Return the full name of the user."""
        #         return f"{self.first_name} {self.last_name}"

        #     def save(self, *args, **kwargs):
        #         if not self.password:
        #             self.set_unusable_password()
        #         super().save(*args, **kwargs)

        #     # def get_group_from_type(self, type):
        #     #     """
        #     #     The roles of the users is determined by the groups they belong to.
        #     #     Groups have different purposes, like permissions, age group, ...
        #     #     The purpose of the groups is defined by the group's parent.  Like, "baladin"'s parent is "section"

        #     #     This method returns, for this user instance, the group it belongs to, based on the parent group.
        #     #     For example, get_group_from_parent("Parents") will return "Parent Actif" or "Parent Passif"
        #     #     """
        #     #     groups = CustomGroup.objects.filter(
        #     #         Q(parents__name=type) | Q(parents__parents__name=type)
        #     #     ).filter(id__in=self.groups.all())
        #     #     return groups if groups.exists() else None

        #     # def get_adult(self):
        #     #     adult = self.get_group_from_type("Adulte")
        #     #     if adult is None:
        #     #         return _("Enfant")
        #     #     else:
        #     #         return adult.first()

        #     def get_section(self):
        #         sections = self.get_group_from_type("Section")
        #         if sections is None:
        #             return None
        #         for section in sections:
        #             if section.year == SchoolYear.current():
        #                 return section
        #         for section in sections:
        #             if section.year is None:
        #                 return section
        #             if section.year.name > SchoolYear.current().name:
        #                 return section
        #         return None

        #     def get_section_year(self, year):
        #         if year is None or year == "":
        #             return self.get_section()
        #         sections = self.get_group_from_type("Section")
        #         if sections is None:
        #             return None
        #         for section in sections:
        #             if section.year and section.year.pk == int(year):
        #                 return section
        #         return self.get_section()

        #     def birthday_to_int(self):
        #         if self.birthday:
        #             return int(self.birthday.strftime("%Y%m%d"))
        #         return None

        #     def current_date_to_int(self):
        #         today = datetime.now().date()
        #         return int(today.strftime("%Y%m%d"))


# class CustomGroup(Group):
#     group_name = models.CharField(_("name"), max_length=150, default="changeme")
#     year = models.ForeignKey(
#         "SchoolYear", null=True, blank=True, on_delete=models.CASCADE
#     )
#     description = models.CharField(max_length=200, null=True, blank=True)
#     parents = models.ForeignKey(
#         "self",
#         null=True,
#         blank=True,
#         related_name="children",
#         on_delete=models.CASCADE,
#     )

#     @classmethod
#     def get_children(cls, top_name):
#         """Get all children of a given group."""
#         return cls.objects.filter(parents__name=top_name)


#     @classmethod
#     def get_leaf_nodes(cls, top_name):
#         """Get all leaf nodes under a top-level group without a loop."""
#         try:
#             # Fetch the top node by name
#             top = cls.objects.get(name=top_name)

#             # Find all descendants of the top node
#             descendants = cls.objects.filter(parents__in=top.get_descendants(include_self=True))

#             # Filter to keep only leaf nodes (nodes with no children)
#             leaf_nodes = descendants.filter(children__isnull=True)

#             return leaf_nodes
#         except cls.DoesNotExist:
#             return cls.objects.none()
#     # @classmethod
#     # def get_leaf_nodes(cls, top_name):
#     #     """Get all leaf nodes under a top-level group."""
#     #     try:
#     #         top = cls.objects.get(name=top_name)
#     #         work_qs = top.children.all()
#     #         result_qs = work_qs
#     #         for item in work_qs:
#     #             if item.children.exists():
#     #                 result_qs = result_qs | item.children.all()
#     #                 result_qs = result_qs.exclude(pk=item.pk)  # Exclude the non-leaf node itself

#     #         return result_qs
#     #     except cls.DoesNotExist:
#     #         return cls.objects.none()

#     @classmethod
#     def get_all_leaf_nodes(cls):
#         """Get all groups with no children."""
#         return cls.objects.annotate(child_count=Count("children")).filter(child_count=0)

#     def is_base(self):
#         """Check if this group has no parents (top-level group)."""
#         return self.parents is None

#     def is_adult(self):
#         """Check if this group has 'Adulte' as a top-level parent."""
#         return self.has_top_parent("Adulte")

#     def has_top_parent(self, top_parent):
#         """Check if this group has the specified group as any ancestor."""
#         return CustomGroup.objects.filter(
#             Q(parents__name=top_parent) | Q(parents__parents__name=top_parent)
#         ).exists()

#     def save(self, *args, **kwargs):
#         """Auto-set name based on group_name and year, and enforce constraints."""
#         if self.group_name and self.year:
#             self.name = f"{self.group_name} {self.year.name}"
#         elif self.group_name:
#             self.name = self.group_name
#         else:
#             raise ValidationError("group_name cannot be null.")
#         super().save(*args, **kwargs)

#     class Meta:
#         verbose_name = _("group")
#         verbose_name_plural = _("groups")


class SchoolYearManager(models.Manager):
    def create_year(self, year):
        start_date = date(year, 8, 1)
        end_date = date(year + 1, 7, 31)
        range_str = f"{year}-{year + 1}"
        school_year = self.create(
            name=year, start_date=start_date, end_date=end_date, range=range_str
        )
        return school_year


class SchoolYear(models.Model):
    name = models.IntegerField(
        unique=True,
        help_text=_("Calendar year from the start of the time period"),
    )
    start_date = models.DateField()
    end_date = models.DateField()
    range = models.CharField(max_length=12, null=True)
    objects = SchoolYearManager()

    def __str__(self):
        return _(f"{self.name} --> du {self.start_date}, au {self.end_date}")

    def current():
        current_time = datetime.now().date()
        return SchoolYear.objects.filter(
            start_date__lte=current_time, end_date__gte=current_time
        ).first()

    @staticmethod
    def next_school_year():
        current_year = SchoolYear.current()
        if not current_year:
            return None
        return (
            SchoolYear.objects.filter(start_date__gt=current_year.start_date)
            .order_by("start_date")
            .first()
        )

    # def birth_year_range():
    #     """
    #     Generates a dict like this: {2016: {"name": "baladin}, {"color": "ls-baladin"}, 2017...}
    #     """
    #     ages = Age.objects.all().order_by("start_age")
    #     current_year = int(SchoolYear.current().name)
    #     year_range = {}
    #     year_choice = []
    #     for current_age, next_age in zip(ages, ages[1:]):
    #         for year in range(
    #             current_year - current_age.start_age,
    #             current_year - next_age.start_age,
    #             -1,
    #         ):
    #             year_range[year] = {
    #                 "name": current_age.name,
    #                 "color": current_age.color,
    #             }
    #     for year in year_range.keys():
    #         year_choice.append((year, f"{year} - {year_range[year]['name']}"))
    #     return year_range, tuple(year_choice)

    @classmethod
    def create(cls, year):
        year = cls()


class Branch(models.Model):
    name = models.CharField(max_length=30, null=True, blank=True)
    min_age_dec_31 = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Age des membres les plus jeunes de la section au 31 décembre de l'année scolaire"
        ),
    )
    max_age_dec_31 = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Age des membres les plus âgés de la section au 31 décembre de l'année scolaire"
        ),
    )

    def __str__(self):
        return f"{self.name} ({self.min_age_dec_31}-{self.max_age_dec_31} ans)"


class Section(models.Model):
    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        BOTH = "B", "Both"

    name = models.CharField(max_length=30, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.branch})"


class Enrollment(models.Model):
    user = models.ForeignKey(Person, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "section", "school_year")

    def __str__(self):
        return f"{self.user.first_name} - {self.section.name} ({self.school_year.year})"


def get_registration_admins():
    # Get the list of Person who's roles includes "Responsable inscriptions"
    # and return a list of their emails address found in the Account corresponding to the Person
    admins = Person.objects.filter(roles__name="Responsable inscriptions")
    admins_accounts = Account.objects.filter(person__in=admins)
    return [admin.email for admin in admins_accounts]


class SiteSettings(models.Model):
    """Model to store site-wide settings that can be changed by admins."""

    # Site information
    site_name = models.CharField(max_length=100, default="Scouts de Limal")
    site_description = models.TextField(
        default="Site officiel des scouts de Limal, présentant notre unité et permettant d'inscrire les enfants."
    )
    site_keywords = models.CharField(
        max_length=255,
        default="scouts limal wavre brabant-wallon wallonie belgique baden-powel",
    )

    # Contact information
    contact_email = models.EmailField(default="info@scouts-limal.be")
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_address = models.TextField(blank=True)

    # Social media
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)

    # Email signatures
    email_signature = models.TextField(
        default="Salutations cordiales,\nLe staff d'unité"
    )

    # Registration settings
    registration_open = models.BooleanField(default=True)
    registration_message = models.TextField(
        default="Les inscriptions sont ouvertes pour l'année scoute."
    )

    # Singleton pattern
    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    @classmethod
    def get_settings(cls):
        """Get the site settings, creating them if they don't exist."""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
