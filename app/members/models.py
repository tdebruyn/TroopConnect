import calendar
import re
import uuid
from datetime import date, datetime, time, timedelta

import phonenumbers
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.contrib.postgres.fields import ArrayField
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.templatetags.static import static
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .constants import DEFAULT_LOGO
from .phone import TroopPhoneNumberField

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


# Languages available to users on the site. The superadmin chooses which subset
# is enabled via TroopSettings.enabled_languages.
AVAILABLE_LANGUAGE_CHOICES = [
    ("fr", "Français"),
    ("nl", "Nederlands"),
    ("en", "English"),
]


def default_enabled_languages():
    """Default enabled languages: French only (matches the pre-i18n site)."""
    return ["fr"]


# The historical name is kept as an alias: migration 0014 serialises this dotted
# path as the default of the `available_languages` column it adds, so the
# function has to stay importable under both names.
default_available_languages = default_enabled_languages

# How a child moves up a section at the end of the scout year.
PASSAGE_MODE_AUTO = "auto"
PASSAGE_MODE_MANUAL = "manual"
PASSAGE_MODE_CHOICES = [
    (PASSAGE_MODE_AUTO, _("Automatic")),
    (PASSAGE_MODE_MANUAL, _("Manual")),
]

# Every month/day pair below is stored as two small integers rather than a DateField:
# a calendar rule like "passage on 1 May" is a recurring day, not a single date,
# and a DateField would drag a meaningless year (and leap-year handling) behind it.
MONTH_VALIDATORS = [MinValueValidator(1), MaxValueValidator(12)]
DAY_VALIDATORS = [MinValueValidator(1), MaxValueValidator(31)]

# How long before an archived person is purged the warning email goes out. Used
# by TroopSettings.archive_warning_cutoff and the notify_upcoming_deletion task.
ARCHIVE_WARNING_DAYS = 30


def validate_phone_region(value):
    """Reject a region ``phonenumbers`` could never parse a number for."""
    if value and value.upper() not in phonenumbers.SUPPORTED_REGIONS:
        raise ValidationError(
            _("%(region)s is not a country code phone numbers can be parsed for."),
            params={"region": value},
        )


def validate_currency(value):
    """Reject anything that is not a bare three-letter ISO 4217 code."""
    if value and not re.fullmatch(r"[A-Z]{3}", value):
        raise ValidationError(
            _("Enter a three-letter currency code, e.g. EUR.")
        )


class Person(models.Model):
    """
    Represents any person in the system (parents, children, leaders, ...).  Only those who need a login get an Account.
    """

    class Sex(models.TextChoices):
        MALE = "M", _("Boy")
        FEMALE = "F", _("Girl")

    # Role short code identifying a child (Animé). Children always require a
    # birthday (passage/promotion relies on it) and a sex (section enrollment).
    CHILD_ROLE_SHORT = "e"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    secret_key = models.CharField(
        max_length=6,
        blank=True,
        help_text=_("First 6 characters of the UUID — key to link a parent to a child"),
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    birthday = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, null=True, blank=True)
    address = models.CharField(max_length=200, null=True, blank=True)
    phone = TroopPhoneNumberField(null=True, blank=True)
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
    archived_date = models.DateField(
        null=True,
        blank=True,
        help_text=_("Date on which the member was archived"),
    )

    roles = models.ManyToManyField(
        "Role",
        through="PersonRole",
        related_name="people",
        blank=True,
    )

    next_section = models.ForeignKey(
        "Section",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="next_persons",
        help_text=_("Manual override for passage: section assigned the following year"),
    )

    class PassageReview(models.TextChoices):
        """Why the passage could not place this member automatically."""

        NO_SECTION = "no_section", _("No section fits — choose one")
        NO_NEXT_BRANCH = "no_next_branch", _("The branch has no next branch set")
        GRADUATION = "graduation", _("Leaving the last branch — decide what comes next")

    passage_review = models.CharField(
        max_length=20,
        choices=PassageReview.choices,
        blank=True,
        default="",
        help_text=_(
            "Set by the passage when it cannot place a member on its own; "
            "cleared as soon as one is placed."
        ),
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

    def save(self, *args, **kwargs):
        if not self.secret_key:
            super().save(*args, **kwargs)
            self.secret_key = str(self.id)[:6]
            Person.objects.filter(pk=self.pk).update(secret_key=self.secret_key)
        else:
            super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        # Children (Animé) must always have a birthday and a sex: passage/
        # promotion relies on birthday, and section enrollment relies on sex.
        # Enforced via full_clean() (forms, admin, and the seed command) —
        # raw .create()/.save() bypass it, so creation paths must validate.
        if self.primary_role and self.primary_role.short == self.CHILD_ROLE_SHORT:
            errors = {}
            if not self.birthday:
                errors["birthday"] = _("Date of birth is required for a participant.")
            if not self.sex:
                errors["sex"] = _("Sex is required for a participant.")
            if errors:
                raise ValidationError(errors)

    @property
    def needs_membership(self) -> bool:
        # membership app can check this
        role_names = {r.name for r in self.roles.all()}
        return bool(role_names & {"Leader", "Child"})

    @property
    def has_account(self) -> bool:
        return hasattr(self, "account")

    def birthday_to_int(self):
        """Birthday as YYYYMMDD, so integer arithmetic can compare ages."""
        if self.birthday:
            return int(self.birthday.strftime("%Y%m%d"))
        return None

    def current_date_to_int(self):
        """Today as YYYYMMDD, matching ``birthday_to_int``."""
        return int(timezone.now().date().strftime("%Y%m%d"))

    def is_adult(self):
        if self.birthday:
            birthday_int = self.birthday_to_int()
            current_date_int = self.current_date_to_int()
            return (current_date_int - birthday_int) > 180000
        return True

    def get_section(self):
        """Return the person's current section, else next year's, else None.

        Templates render "Pending" themselves when this returns None.
        """
        current_year = SchoolYear.current()
        if current_year:
            enrollment = self.enrollment_set.filter(school_year=current_year).first()
            if enrollment:
                return enrollment.section
        next_year = SchoolYear.next_school_year()
        if next_year:
            enrollment = self.enrollment_set.filter(school_year=next_year).first()
            if enrollment:
                return enrollment.section
        return None

    @property
    def has_section(self) -> bool:
        """True when enrolled in the current or upcoming school year.

        Mirrors get_section(): a child whose Section column shows "Pending"
        has no section assigned and should be removed rather than deregistered.
        """
        current_year = SchoolYear.current()
        if current_year and self.enrollment_set.filter(
            school_year=current_year
        ).exists():
            return True
        next_year = SchoolYear.next_school_year()
        return bool(
            next_year and self.enrollment_set.filter(school_year=next_year).exists()
        )

    def has_role_dependencies(self):
        """Check if changing this person's primary role is blocked by existing data.

        Returns (False, "") if no dependencies, or (True, reason) if locked.
        """
        current_year = SchoolYear.current()
        if current_year and self.enrollment_set.filter(
            school_year=current_year
        ).exists():
            return True, _("linked sections")
        if self.as_parent.exists():
            return True, _("linked children")
        return False, ""

    def age_on_dec_31(self, school_year=None):
        """Whole-year age at the troop's age reference day, that school year.

        The name is historical: the reference day is
        ``TroopSettings.age_reference_month``/``_day`` (31 December by default),
        which is also the convention the ``Branch.min_age_dec_31`` and
        ``max_age_dec_31`` columns are named after. The computation itself lives
        in :meth:`TroopSettings.age_at_reference`, shared with the passage task
        and the member list's branch check.
        """
        return TroopSettings.get_settings().age_at_reference(self, school_year)

    def age_fits_branch(self, school_year=None):
        """True if this person is of an age that fits some Branch on 31 Dec of
        the school year — i.e. they must be a Participant (rule 2).
        """
        age = self.age_on_dec_31(school_year)
        if age is None:
            return False
        return Branch.objects.filter(
            min_age_dec_31__isnull=False,
            max_age_dec_31__isnull=False,
            min_age_dec_31__lte=age,
            max_age_dec_31__gte=age,
        ).exists()


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
        constraints = [
            models.UniqueConstraint(fields=["person", "role"], name="uniq_person_role"),
        ]

    def __str__(self):
        return f"{self.person} — {self.role}"


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
        constraints = [
            models.UniqueConstraint(fields=["parent", "child"], name="uniq_parent_child"),
        ]

    def __str__(self):
        return f"{self.parent} → {self.child}"


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
    preferred_language = models.CharField(
        max_length=5,
        choices=AVAILABLE_LANGUAGE_CHOICES,
        default="fr",
        help_text=_("Language used for outgoing emails to this user."),
    )

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
        troop = TroopSettings.get_settings()
        start_date, end_date = troop.school_year_bounds(year)
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
        return _("%(name)s — from %(start)s to %(end)s") % {
            "name": self.name,
            "start": self.start_date,
            "end": self.end_date,
        }

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
        # TODO: dead/broken — `year` shadows the parameter, the method returns
        # None, and there are no callers. Remove it or implement it properly.
        year = cls()  # noqa: F841


class Branch(models.Model):
    name = models.CharField(max_length=30, null=True, blank=True)
    min_age_dec_31 = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Age of the youngest members of the section on December 31 of the school year"
        ),
    )
    max_age_dec_31 = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Age of the oldest members of the section on December 31 of the school year"
        ),
    )

    # The passage follows this link rather than an age ladder, so a troop is
    # free to order, rename or fork its branches however it likes. Both fields
    # are set for the ladder a troop already had by the migration that
    # introduces them; a branch added afterwards starts unlinked (and its
    # members are flagged for review rather than moved somewhere arbitrary).
    promotes_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promoted_from",
        help_text=_("The branch members move into when they outgrow this one."),
    )
    is_top = models.BooleanField(
        default=False,
        help_text=_(
            "The last branch of the ladder: members who outgrow it leave it for good."
        ),
    )

    def __str__(self):
        return _("%(name)s (%(min)s-%(max)s years old)") % {
            "name": self.name,
            "min": self.min_age_dec_31,
            "max": self.max_age_dec_31,
        }

    def section_for(self, sex):
        """The section of this branch to place someone of ``sex`` in, or None.

        None means nobody in this branch can take them: every section it has is
        meant for other people.
        """
        return (
            Section.compatible_with(sex).filter(branch=self).order_by("name").first()
        )


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

    @classmethod
    def compatible_with(cls, sex):
        """The sections open to someone of ``sex``.

        A section that declares BOTH — or that declares nothing at all, which
        is the other way a troop says "this one is mixed" — takes anyone. A
        section declaring a sex takes only that one, and a member whose own sex
        is unknown is only ever placed in a mixed section.

        A classmethod rather than a queryset method on purpose: modeltranslation
        replaces ``Section.objects`` with its own manager, so anything hanging
        off the manager itself would not survive.
        """
        mixed = (
            models.Q(sex__isnull=True)
            | models.Q(sex="")
            | models.Q(sex=cls.Sex.BOTH)
        )
        if sex:
            return cls.objects.filter(mixed | models.Q(sex=sex))
        return cls.objects.filter(mixed)


class Enrollment(models.Model):
    user = models.ForeignKey(Person, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "section", "school_year"], name="uniq_enrollment"
            ),
        ]

    def __str__(self):
        return f"{self.user.first_name} - {self.section.name} ({self.school_year.year})"


def get_registration_admins():
    """Return the email addresses of the registration admins.

    Registration admins hold the "Responsable inscriptions" (ri),
    "Animateur responsable" (ar) or "Admin" (ad) secondary roles. Matching on
    the role short code (not the translated name) keeps this correct across
    languages.
    """
    admins = Person.objects.filter(roles__short__in=["ri", "ar", "ad"]).distinct()
    admins_accounts = Account.objects.filter(person__in=admins)
    return [admin.email for admin in admins_accounts]


class TroopSettings(models.Model):
    """The troop's own settings: one row, edited by staff in the web UI.

    This is *troop content*, not infrastructure. A unit's name, the languages it
    offers, the shape of its scout year — none of it belongs in the environment,
    because the troop edits it in the browser and the value has to survive a
    redeploy. See ``docs/dev/CONTRACT.md`` for where the line is drawn.

    Read it through :meth:`get_settings`; that is the only accessor that both
    guarantees the row exists and serves the cached copy. The row itself is
    created by migration, so a freshly migrated instance already has sane
    defaults rather than an empty settings page.

    Caching note: ``queryset.update()`` / ``queryset.delete()`` bypass the
    ``post_save``/``post_delete`` receivers below and would leave a stale copy
    cached. Nothing does that today; use ``save()`` and ``delete()``.
    """

    CACHE_KEY = "members.TroopSettings"

    # --- Organisation ------------------------------------------------------
    # The unit's name, and the name outgoing email speaks for.
    name = models.CharField(max_length=100, default="Scouts")

    # A short form for places the full name does not fit (nav bar, email tags).
    # Empty means "use `name`"; see `display_short_name`.
    short_name = models.CharField(max_length=40, blank=True)

    # Free text: troops belong to federations this project knows nothing about.
    federation = models.CharField(max_length=120, blank=True)

    # Public contact details, exposed to every template as `contact_email`.
    # Left empty rather than pre-filled: a placeholder that looks like a real
    # address would have a troop's own site publishing somebody else's, and
    # mail to it would leave the unit. The admin is expected to set it.
    contact_email = models.EmailField(default="", blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    footer_address = models.TextField(blank=True)

    # Where replies to automated mail should go, when that is not the sender
    # (`DEFAULT_FROM_EMAIL`). Empty means "reply to the sender".
    reply_to_email = models.EmailField(default="", blank=True)

    # A URL or a block of text, whichever the troop has. Rendered as-is by the
    # footer; see `privacy_policy_url` for the case where it is a link.
    privacy_policy = models.TextField(
        blank=True,
        help_text=_(
            "Link or text of your privacy policy. A URL becomes a link, "
            "anything else is shown as text."
        ),
    )

    # --- Branding ----------------------------------------------------------
    # The unit's own mark. Uploads, not files shipped with the image: the
    # design stays the federation's (see
    # app/static/vendor/template-unite/README.md) and the identity is the
    # troop's, which is the line this project draws everywhere else. Both are
    # optional — an empty logo falls back to the mark shipped with the
    # application, so an instance that configures nothing still has one. Read
    # them through `logo_url`/`favicon_url`, never the field: the fallback
    # lives there.
    logo = models.ImageField(
        upload_to="troop/",
        blank=True,
        help_text=_(
            "Shown in the site header and in outgoing email. "
            "Leave empty to use the default Les Scouts mark."
        ),
    )
    favicon = models.ImageField(
        upload_to="troop/",
        blank=True,
        help_text=_(
            "The small icon browsers show for the site. "
            "Leave empty for no icon."
        ),
    )

    # --- Locale ------------------------------------------------------------
    # Languages enabled on the site. With more than one, a language selector is
    # shown to users; with exactly one, the site is locked to that language.
    # Backed by a PostgreSQL ArrayField (the project is Postgres-only).
    enabled_languages = ArrayField(
        base_field=models.CharField(max_length=5, choices=AVAILABLE_LANGUAGE_CHOICES),
        default=default_enabled_languages,
        help_text=_("Languages available to users in the site language selector."),
    )

    # Language shown to visitors whose browser/cookie language isn't one of the
    # enabled languages (or on a first visit). Must be one of enabled_languages
    # — enforced in clean() and the admin form.
    default_language = models.CharField(
        max_length=5,
        choices=AVAILABLE_LANGUAGE_CHOICES,
        default="fr",
        help_text=_("Default language for visitors. Must be one of the available languages."),
    )

    # ISO 3166-1 alpha-2. Phone numbers are stored in E.164; this only decides
    # how a locally-typed number ("0475 12 34 56") is interpreted and formatted.
    phone_region = models.CharField(
        max_length=2,
        default="BE",
        validators=[validate_phone_region],
        help_text=_("Country code used to parse and format phone numbers, e.g. BE."),
    )

    # ISO 4217. Every amount in the UI is displayed in this currency.
    currency = models.CharField(
        max_length=3,
        default="EUR",
        validators=[validate_currency],
        help_text=_("Three-letter currency code used to display amounts, e.g. EUR."),
    )

    # --- Calendar ----------------------------------------------------------
    # The scout year runs year_start -> year_start + 1 year (default August 1).
    year_start_month = models.PositiveSmallIntegerField(
        default=8, validators=MONTH_VALIDATORS
    )
    year_start_day = models.PositiveSmallIntegerField(
        default=1, validators=DAY_VALIDATORS
    )

    # A child's age is taken on this day (default December 31), which is what
    # decides the section they belong to.
    age_reference_month = models.PositiveSmallIntegerField(
        default=12, validators=MONTH_VALIDATORS
    )
    age_reference_day = models.PositiveSmallIntegerField(
        default=31, validators=DAY_VALIDATORS
    )

    # When sections are prompted to move children up (default May 1).
    passage_month = models.PositiveSmallIntegerField(
        default=5, validators=MONTH_VALIDATORS
    )
    passage_day = models.PositiveSmallIntegerField(default=1, validators=DAY_VALIDATORS)
    passage_mode = models.CharField(
        max_length=10,
        choices=PASSAGE_MODE_CHOICES,
        default=PASSAGE_MODE_AUTO,
        help_text=_(
            "Automatic runs the passage on the date above; manual leaves it to "
            "whoever presses the button."
        ),
    )

    # What happens to members who leave the last branch. Becoming an animator
    # is right for a troop whose oldest members routinely stay on as staff;
    # a troop that would rather look at each one turns this off and gets them
    # flagged for review instead.
    top_branch_graduates_become_leaders = models.BooleanField(
        default=True,
        help_text=_(
            "Members who leave the last branch become animators. Turn this off "
            "to be asked about each of them instead."
        ),
    )

    # How long records of removed members are kept before the cleanup task may
    # discard them.
    archive_retention_years = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1)]
    )

    # --- Modules -----------------------------------------------------------
    # Feature switches. Off means the module is not installed as far as the
    # troop is concerned: its URLs answer 404, its UI disappears — see
    # members/modules.py for the decorator, the mixin and the template tag that
    # read these. What the module stores is left alone, so switching one back
    # on restores it. The settings page and the Django admin stay open on
    # purpose, so a troop can always undo the switch.
    fees_enabled = models.BooleanField(default=True)
    signing_enabled = models.BooleanField(default=True)
    public_agenda_enabled = models.BooleanField(default=True)

    # --- Retained site content ---------------------------------------------
    site_description = models.TextField(
        default="Site officiel de votre unité scoute, permettant d'inscrire les enfants et de gérer les membres."
    )
    site_keywords = models.CharField(
        max_length=255,
        default="scouts belgique baden-powel",
    )

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

    # Customizable text
    photo_consent_text = models.TextField(
        default="J'accepte que les photos ou vidéos soient utilisées par Les Scouts ASBL, dont mon unité fait partie"
    )
    address_placeholder = models.CharField(
        max_length=200,
        default="Ex: Rue de l'Église 1, 1000 Bruxelles",
    )

    # Automated passage (run_passage task) — idempotency marker
    last_passage_school_year = models.IntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Last school year (the « name » field) for which the automatic passage "
            "was executed. Anti-replay: if Celery was stopped on the passage day, "
            "the task catches up at the next startup."
        ),
    )

    # Singleton pattern
    class Meta:
        verbose_name = "Troop Settings"
        verbose_name_plural = "Troop Settings"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Normalise the ISO codes so a lower-case entry in the settings page and
        # the same code typed in lower-case by a script agree on one row.
        if self.phone_region:
            self.phone_region = self.phone_region.upper()
        if self.currency:
            self.currency = self.currency.upper()
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Return the singleton row, creating it if the migration was skipped.

        The migration creates the row, so ``get_or_create`` is a fallback for a
        database that predates it rather than the normal path.
        """
        cached = cache.get(cls.CACHE_KEY)
        if cached is not None:
            return cached

        obj, _created = cls.objects.get_or_create(pk=1)
        cache.set(cls.CACHE_KEY, obj, None)
        return obj

    @classmethod
    def clear_cache(cls):
        """Drop the cached row, so the next read picks up the stored values."""
        cache.delete(cls.CACHE_KEY)

    def display_short_name(self):
        """The short name, or the full name when none was set."""
        return self.short_name or self.name

    def privacy_policy_url(self):
        """The privacy policy as a link, or "" when it is not one.

        The field holds either, so this is what a template should test before
        rendering an ``<a href>``.
        """
        policy = (self.privacy_policy or "").strip()
        if policy.startswith(("http://", "https://")):
            return policy
        return ""

    # --- Branding ----------------------------------------------------------

    def logo_url(self):
        """The unit's logo: the uploaded file, or the built-in default.

        Never returns "" — the header always has something to show, so a troop
        that has uploaded nothing looks the same as before this field existed.
        """
        return self._upload_url(self.logo) or static(DEFAULT_LOGO)

    def favicon_url(self):
        """The site icon, or "" when the troop has not chosen one.

        Empty is the honest answer: there is no default favicon to fall back
        to, and a site with no ``<link rel="icon">`` gets the browser's own
        behaviour, which is what it had before this field existed.
        """
        return self._upload_url(self.favicon)

    @staticmethod
    def _upload_url(field):
        """``field``'s URL, or "" when it holds no file.

        A ``FieldFile`` whose row was written by a migration that has since
        moved the file on disk raises ``ValueError`` rather than returning a
        broken URL, so an unreadable upload degrades to the fallback instead of
        taking the page down with it.
        """
        if not field:
            return ""
        try:
            return field.url
        except ValueError:
            return ""

    # --- Calendar ----------------------------------------------------------
    # Every school-year, age-reference and retention date the application
    # computes is derived here, from the six month/day fields above. Views,
    # Celery tasks and templates must call these rather than reach for the
    # fields — a troop that moves its year boundary or its age reference day
    # must not have to find every place that assumed August or December.

    def school_year_start(self, year):
        """The first day of the school year named ``year``.

        ``year`` is the calendar year the school year starts in — the value
        stored in :attr:`SchoolYear.name`.
        """
        try:
            return date(year, self.year_start_month, self.year_start_day)
        except ValueError:
            # A 29 February start: that day does not exist every year.
            return date(year, 3, 1)

    def school_year_for(self, on_date):
        """The start year of the school year that contains ``on_date``.

        Returned as an integer ``SchoolYear.name``, computed from the
        configured year start, so it also answers for a date no
        :class:`SchoolYear` row covers yet.
        """
        start = self.school_year_start(on_date.year)
        return on_date.year if on_date >= start else on_date.year - 1

    def school_year_bounds(self, year):
        """``(start_date, end_date)`` of the school year named ``year``.

        A school year runs a full twelve months, so it ends the day before the
        next one begins.
        """
        start = self.school_year_start(year)
        end = self.school_year_start(year + 1) - timedelta(days=1)
        return start, end

    def age_reference_date(self, school_year):
        """The day ages are taken on for ``school_year``.

        ``school_year`` is a :class:`SchoolYear` instance or its ``name``. The
        configured reference month/day (31 December by default) is pinned to
        whichever calendar year puts it *inside* the school year, so a troop
        whose year starts in September or in January still gets 31 December of
        that school year rather than of the year before it.
        """
        start = getattr(school_year, "start_date", None)
        if start is None:
            start, _end = self.school_year_bounds(school_year)
        candidate = self._calendar_date(
            start.year, self.age_reference_month, self.age_reference_day
        )
        if candidate < start:
            candidate = self._calendar_date(
                start.year + 1, self.age_reference_month, self.age_reference_day
            )
        return candidate

    def age_at_reference(self, person, school_year=None):
        """``person``'s age on the age reference day of ``school_year``.

        The single definition of "how old is this child this school year". The
        passage task, the member list's branch check and
        :meth:`Person.age_fits_branch` all go through it, so they can no longer
        disagree about which December is meant. Returns ``None`` when the
        birthday or the school year is unknown.
        """
        if person.birthday is None:
            return None
        if school_year is None:
            school_year = SchoolYear.current()
        if school_year is None:
            return None
        reference = self.age_reference_date(school_year)
        return (reference - person.birthday).days // 365

    def passage_datetime(self, school_year):
        """The moment the passage preparing ``school_year`` falls due.

        The configured passage day (1 May by default) in the start calendar
        year of that school year: the passage runs in the spring before the
        year it prepares children for.
        """
        name = getattr(school_year, "name", school_year)
        day = self._calendar_date(name, self.passage_month, self.passage_day)
        return timezone.make_aware(datetime.combine(day, time.min))

    def next_passage_datetime(self, on_date=None):
        """The moment of the next passage — the one preparing the school year
        after the one ``on_date`` (today by default) falls in.
        """
        if on_date is None:
            on_date = timezone.localdate()
        return self.passage_datetime(self.school_year_for(on_date) + 1)

    def _calendar_date(self, year, month, day):
        """``date(year, month, day)``, clamped to that month's last day.

        The month and day fields are validated separately, so a combination
        like 31 February is reachable (through the admin, or through the
        settings page's form). Clamping keeps the nightly tasks and the page
        rendering that read these values from raising on one.
        """
        return date(year, month, min(day, calendar.monthrange(year, month)[1]))

    # --- Archive retention -------------------------------------------------

    def archive_purge_date(self, archived_date):
        """The day a person archived on ``archived_date`` is deleted for good."""
        return archived_date + timedelta(days=self.archive_retention_years * 365)

    def archive_purge_cutoff(self, on_date):
        """The latest ``archived_date`` that is due for deletion on ``on_date``."""
        return on_date - timedelta(days=self.archive_retention_years * 365)

    def archive_warning_cutoff(self, on_date):
        """The ``archived_date`` whose deletion warning is due on ``on_date``.

        The warning goes out :data:`ARCHIVE_WARNING_DAYS` before the purge —
        the ``archived_date`` on which that day is today.
        """
        return self.archive_purge_cutoff(on_date) + timedelta(
            days=ARCHIVE_WARNING_DAYS
        )

    def clean(self):
        """Cross-field rules the individual field validators cannot express."""
        super().clean()

        available = self.enabled_languages or []
        if not available:
            raise ValidationError(_("Select at least one available language."))
        if self.default_language not in available:
            raise ValidationError(
                {
                    "default_language": _(
                        "The default language must be one of the available languages."
                    )
                }
            )


@receiver(post_save, sender=TroopSettings)
@receiver(post_delete, sender=TroopSettings)
def _invalidate_troop_settings_cache(sender, **kwargs):
    """Forget the cached row whenever the stored one changes."""
    TroopSettings.clear_cache()


class ImportantDocument(models.Model):
    """Documents or links accessible to authenticated users."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    url = models.URLField(blank=True)
    file = models.FileField(upload_to="documents/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Important document")
        verbose_name_plural = _("Important documents")

    def __str__(self):
        return self.title
