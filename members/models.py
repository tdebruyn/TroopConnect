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
from django.db.models import Q


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
    parents = models.ManyToManyField("CustomUser", blank=True)
    photo_consent = models.BooleanField(
        default=False, help_text="I give my consent to use my photo"
    )
    note = models.TextField(max_length=500, null=True, blank=True)
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

    def get_group_from_parent(self, parent_group):
        """
        The roles of the users is determined by the groups they belong to.
        Groups have different purposes, like user status (active or inactive), permissions, age group, ...
        The purpose of the groups is defined by their parent group.  Like, "active"'s parent is "Status"

        This method returns, for this user instance, the group it belongs to, based on the parent group.
        For example, get_group_from_parent("Status") will return "active" or "inactive"
        """
        status_groups = CustomGroup.objects.filter(parents__name=parent_group)
        user_groups = self.groups.filter(
            id__in=status_groups.values_list("id", flat=True)
        )
        if user_groups.exists():
            return user_groups.first().name
        return None

    def get_status(self):
        return self.get_group_from_parent("Status")


class CustomGroup(Group):
    year = models.ForeignKey(
        "SchoolYear", null=True, blank=True, on_delete=models.CASCADE
    )
    description = models.CharField(max_length=200, null=True, blank=True)
    parents = models.ForeignKey(
        "CustomGroup", null=True, blank=True, on_delete=models.CASCADE
    )

    def get_childs(self):
        return CustomGroup.objects.filter(Q(parents=self) | Q(parents__parents=self))

    # def has_parents(self, parent):
    #     return self.parents == CustomGroup.objects.get(name=parent)

    def is_base(self):
        return self.parents == None

    def is_adult(self):
        return self.has_parents("Adulte")

    class Meta:
        verbose_name = _("group")
        verbose_name_plural = _("groups")


class SchoolYear(models.Model):
    name = models.IntegerField(
        unique=True,
        help_text=_("Calendar year from the start of the time period"),
    )
    start_date = models.DateField()
    end_date = models.DateField()

    def __str__(self):
        return _(f"{self.name} --> from {self.start_date}, until {self.end_date}")
