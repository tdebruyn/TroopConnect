from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
    Group,
)
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from phonenumber_field.modelfields import PhoneNumberField
from django.db.models import Q, Count
from datetime import datetime
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords


class CustomUserManager(BaseUserManager):
    def create_user(
        self,
        username,
        first_name,
        last_name,
        birthday=None,
        is_staff=False,
        is_superuser=False,
        email=None,
        password=None,
    ):
        if not username:
            raise ValueError("Le nom d'utilisateur est obligatoire")
        user = self.model(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=self.normalize_email(email),
            birthday=birthday,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self, username, first_name, last_name, email=None, password=None
    ):
        is_staff = True
        is_superuser = True
        return self.create_user(
            username,
            first_name,
            last_name,
            is_staff,
            is_superuser,
            email,
            password,
        )


class CustomUser(AbstractBaseUser, PermissionsMixin):
    MALE = "m"
    FEMALE = "f"
    SEX = [(MALE, "Masculin"), (FEMALE, "Féminin")]
    email = models.EmailField(unique=True, null=True, blank=True)
    username = models.CharField(primary_key=True, max_length=30, unique=True)
    password = models.CharField(max_length=128, null=True, blank=True)
    birthday = models.DateField(
        null=True, blank=True, help_text=_("Required only for childrens")
    )
    secret_key = models.CharField(max_length=30, null=True, blank=True)
    address = models.CharField(max_length=200, null=True, blank=True)
    phone = PhoneNumberField(region="BE", null=True, blank=True)
    first_name = models.CharField(max_length=150, null=True, blank=True)
    last_name = models.CharField(max_length=150, null=True, blank=True)
    sex = models.CharField(max_length=1, choices=SEX, null=True, blank=True)
    totem = models.CharField(max_length=60, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    parents = models.ManyToManyField("CustomUser", blank=True, related_name="children")
    photo_consent = models.BooleanField(
        default=False, help_text="I give my consent to use my photo"
    )
    note = models.TextField(max_length=500, null=True, blank=True)
    history = HistoricalRecords(m2m_fields=[PermissionsMixin.groups.field])
    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name", "last_name", "birthday", "email"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def save(self, *args, **kwargs):
        if not self.password:
            self.set_unusable_password()
        super().save(*args, **kwargs)

    def get_group_from_type(self, type):
        """
        The roles of the users is determined by the groups they belong to.
        Groups have different purposes, like permissions, age group, ...
        The purpose of the groups is defined by the group's parent.  Like, "baladin"'s parent is "section"

        This method returns, for this user instance, the group it belongs to, based on the parent group.
        For example, get_group_from_parent("Parents") will return "Parent Actif" or "Parent Passif"
        """
        groups_from_type = CustomGroup.objects.filter(
            Q(parents__name=type) | Q(parents__parents__name=type)
        ).filter(id__in=self.groups.all())
        if groups_from_type.exists():
            return groups_from_type
        return None

    def get_adult(self):
        adult = self.get_group_from_type("Adulte")
        if adult is None:
            return _("Enfant")
        else:
            return adult.first()

    def get_section(self):
        sections = self.get_group_from_type("Section")
        if sections is None:
            return None
        for section in sections:
            if section.year == SchoolYear.current():
                return section
        for section in sections:
            if section.year is None:
                return section
            if section.year.name > SchoolYear.current().name:
                return section
        return None

    def get_section_year(self, year):
        if year is None or year == "":
            return self.get_section()
        sections = self.get_group_from_type("Section")
        if sections is None:
            return None
        for section in sections:
            if section.year and section.year.pk == int(year):
                return section
        return self.get_section()

    def birthday_to_int(self):
        if self.birthday:
            return int(self.birthday.strftime("%Y%m%d"))
        return None

    def current_date_to_int(self):
        today = datetime.now().date()
        return int(today.strftime("%Y%m%d"))

    def is_adult(self):
        if self.birthday:
            birthday_int = self.birthday_to_int()
            current_date_int = self.current_date_to_int()
            return (current_date_int - birthday_int) > 180000
        return True


class CustomGroup(Group):
    group_name = models.CharField(_("name"), max_length=150, default="changeme")
    year = models.ForeignKey(
        "SchoolYear", null=True, blank=True, on_delete=models.CASCADE
    )
    description = models.CharField(max_length=200, null=True, blank=True)
    parents = models.ForeignKey(
        "CustomGroup",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
    )

    def get_children(top_name):
        return CustomGroup.objects.filter(parents__name=top_name)

    def get_leaf_nodes(top_name):
        top = CustomGroup.objects.get(name=top_name)
        work_qs = top.children.all()
        result_qs = top.children.all()
        for item in work_qs:
            if item.children.exists():
                result_qs = result_qs | item.children.all()
                result_qs = result_qs.exclude(pk=item.pk)
        return result_qs

    # def has_parents(self, parent):
    #     return self.parents == CustomGroup.objects.get(name=parent)

    def get_all_leaf_nodes():
        return CustomGroup.objects.annotate(child_count=Count("children")).filter(
            child_count=0
        )

    def is_base(self):
        return self.parents == None

    def is_adult(self):
        return self.has_parents("Adulte")

    def has_top_parent(self, top_parent):
        return CustomGroup.objects.filter(
            Q(parents__name=top_parent) | Q(parents__parents__name=top_parent)
        ).exists()

    def save(self, *args, **kwargs):
        if self.group_name and self.year:
            self.name = f"{self.group_name} {self.year.name}"
        elif self.group_name:
            self.name = self.group_name
        else:
            raise ValidationError("group_name cannot be null")
        super().save(*args, **kwargs)

    class Meta:
        # constraints = [
        #     models.UniqueConstraint(fields=["name", "year"], name="name_year")
        # ]
        verbose_name = _("group")
        verbose_name_plural = _("groups")


class SchoolYear(models.Model):
    name = models.IntegerField(
        unique=True,
        help_text=_("Calendar year from the start of the time period"),
    )
    start_date = models.DateField()
    end_date = models.DateField()
    range = models.CharField(max_length=12, null=True)

    def __str__(self):
        return _(f"{self.name} --> du {self.start_date}, au {self.end_date}")

    def current():
        current_time = datetime.now().date()
        return SchoolYear.objects.filter(
            start_date__lte=current_time, end_date__gte=current_time
        ).first()

    def birth_year_range():
        """
        Generates a dict like this: {2016: {"name": "baladin}, {"color": "ls-baladin"}, 2017...}
        """
        ages = Age.objects.all().order_by("start_age")
        current_year = int(SchoolYear.current().name)
        year_range = {}
        year_choice = []
        for current_age, next_age in zip(ages, ages[1:]):
            for year in range(
                current_year - current_age.start_age,
                current_year - next_age.start_age,
                -1,
            ):
                year_range[year] = {
                    "name": current_age.name,
                    "color": current_age.color,
                }
        for year in year_range.keys():
            year_choice.append((year, f'{year} - {year_range[year]["name"]}'))
        return year_range, tuple(year_choice)


class Age(models.Model):
    name = models.CharField(max_length=30, null=True, blank=True)
    start_age = models.PositiveSmallIntegerField()
    color = models.CharField(max_length=60, null=True, blank=True)


def get_registration_admins():
    admin_group = CustomGroup.objects.get(name="InscriptionAdmin")
    admins = CustomUser.objects.filter(groups=admin_group)
    return [admin.email for admin in admins]
