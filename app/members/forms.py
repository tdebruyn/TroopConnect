from allauth.account.forms import ResetPasswordForm, SignupForm
from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from homepage.models import TimelineActivity

from . import modules
from .constants import (
    ROLE_CHOICES,
)
from .models import (
    ADULT_AGE,
    AVAILABLE_LANGUAGE_CHOICES,
    Absence,
    Account,
    Enrollment,
    ImportantDocument,
    Person,
    PersonRole,
    Role,
    SchoolYear,
    Section,
    SectionEvent,
    TroopSettings,
)
from .modules import module_enabled
from .permissions import (
    ANIMATEUR,
    ANIME,
    AUTRE_MEMBRE,
    PARENT,
    TRESORIER,
    get_person,
    reportable_children,
    secondary_roles_for,
)


def secondary_role_queryset(primary_role=None):
    """The secondary roles a troop can hand out to a person of `primary_role`.

    An animateur may lead the unit team or be their section's communications
    lead; the unit administration belongs to Parents and Autres membres. The
    Treasurer role is hidden while the membership-fees module is switched off:
    with the finance screens gone it grants nothing, so offering it would only
    invite a troop to file someone under a responsibility that does not exist.
    The role itself is untouched — see AdminUserUpdateForm.save(), which keeps
    roles this form does not offer.

    "Parent actif" means a parent who helps the unit occasionally, so it is
    only offered to a Parent; AdminUserUpdateForm.save() clears it from anyone
    whose primary role moves away from Parent.
    """
    roles = Role.objects.filter(short__in=secondary_roles_for(
        getattr(primary_role, "short", None)
    ))
    if not module_enabled(modules.FEES):
        roles = roles.exclude(short=TRESORIER)
    return roles


class SectionModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class CustomSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class AccountCreationForm(UserCreationForm):
    class Meta:
        model = Account
        fields = ("email", "password1", "password2")
        labels = {"email": _("Email")}


class AccountChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs["class"] = "form-control"


class AdminUserUpdateForm(forms.ModelForm):
    email = forms.EmailField(
        required=False,
        label=_("Email"),
        help_text=_(
            "If an email is provided, an account will be created. Otherwise, the existing account will be used."
        ),
    )

    primary_role = forms.ModelChoiceField(
        queryset=Role.objects.filter(is_primary=True),
        required=True,
        label=_("Primary role"),
    )

    # Secondary roles (multiple selection). The queryset is filled in __init__
    # rather than here: which roles a troop can hand out depends on its module
    # switches, and a queryset declared on the class is evaluated once and then
    # shared by every instance (see secondary_role_queryset()).
    secondary_roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.none(),
        required=False,
        label=_("Secondary roles"),
        widget=forms.CheckboxSelectMultiple,
    )

    current_section = SectionModelChoiceField(
        queryset=Section.objects.all(),
        required=False,
        label=_("Section"),
    )
    next_section = SectionModelChoiceField(
        queryset=Section.objects.all(),
        required=False,
        label=_("Next section"),
    )

    def __init__(
        self, *args, can_assign_roles=True, can_edit_photo_consent=False, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.can_assign_roles = can_assign_roles
        self.fields["birthday"].widget.format = "%Y-%m-%d"
        if self.instance.pk and not self.instance.address:
            self.fields["address"].initial = self.instance.effective_address()

        current_year = SchoolYear.current()
        self.current_year = current_year

        try:
            self.next_year = SchoolYear.objects.get(name=current_year.name + 1)
        except SchoolYear.DoesNotExist:
            self.next_year = None

        self.fields["current_section"].label = _("Section %(range)s") % {
            "range": current_year.range
        }
        if self.next_year:
            self.fields["next_section"].label = _("Section %(range)s") % {
                "range": self.next_year.range
            }

        self._suggest_sections_by_age("current_section", current_year)
        self._suggest_sections_by_age("next_section", self.next_year)

        # Photo consent is the family's decision, not the unit team's. A staff
        # reader who is the child's own parent — or the member editing
        # themselves — keeps the right; everyone else sees the answer but can
        # not change it, and a disabled field is never taken from the submit.
        photo_consent = self.fields["photo_consent"]
        photo_consent.disabled = not can_edit_photo_consent
        if not can_edit_photo_consent:
            if current_year and self.instance.age_fits_branch(current_year):
                photo_consent.help_text = _(
                    "Only the parent can change this for their child."
                )
            else:
                photo_consent.help_text = _(
                    "Only the member can change this on their own profile."
                )

        if self.instance and self.instance.pk:
            locked, reason = self.instance.has_role_dependencies()
            self.role_locked = locked
            self.lock_reason = reason

            if locked:
                # Keep the role locked: a hidden ModelChoiceField that
                # round-trips the current primary_role. The cleaned value
                # stays a Role object, so the section validation in clean()
                # and the assignment in save() keep working. The field is
                # still rendered (as a hidden input) in the template.
                self.fields["primary_role"] = forms.ModelChoiceField(
                    queryset=Role.objects.filter(is_primary=True),
                    widget=forms.HiddenInput,
                    initial=self.instance.primary_role_id,
                    required=True,
                    label=_("Primary role"),
                )
            else:
                self.fields["primary_role"].initial = self.instance.primary_role

            # Which roles can be offered follows the primary role that will be
            # submitted, not the one still stored: on a rejected POST the
            # reader changed it already. A locked role cannot change, so its
            # stored value is the submitted one.
            suggested_role = self.instance.primary_role
            if self.is_bound and not locked:
                try:
                    submitted = Role.objects.filter(
                        pk=self.data.get(self.add_prefix("primary_role"))
                    ).first()
                except (TypeError, ValueError):
                    submitted = None
                suggested_role = submitted or suggested_role

            # A participant and a not-yet-validated account hold no secondary
            # role at all. The field is dropped rather than left empty so
            # save() clears any assignment left from an earlier role.
            if not can_assign_roles or not secondary_roles_for(suggested_role.short):
                self.fields.pop("secondary_roles", None)
            else:
                # The stored role is accepted as well as the suggested one:
                # a Parent dropped to Autre membre still has "Parent actif"
                # ticked from the render, and clean() drops it instead of the
                # field rejecting a box the reader was never asked to untick.
                self.fields["secondary_roles"].queryset = (
                    secondary_role_queryset(suggested_role)
                    | secondary_role_queryset(self.instance.primary_role)
                )
                secondary_roles = self.instance.roles.filter(is_primary=False)
                if secondary_roles.exists():
                    self.fields["secondary_roles"].initial = secondary_roles.all()

    def _suggest_sections_by_age(self, field_name, school_year):
        """Put the sections matching a child's age for that year above the rest.

        A member with no enrolment yet gets a dropdown that opens on the two or
        three sections they actually belong in, then a divider, then every
        other section — the same age reference the passage uses, so the
        suggestion cannot disagree with where the child will be moved next.

        Membership of a branch, not the stored primary role, decides: a new
        member is listed before they become a Participant, and age is what
        rule 2 uses to make them one.

        The grouping is per field: an enrolled child still gets their next
        year's sections suggested even though this year's section is set.
        """
        if not school_year or not self.instance.pk:
            return
        if self.instance.enrollment_set.filter(school_year=school_year).exists():
            return

        age = self.instance.age_on_dec_31(school_year)
        if age is None:
            return

        field = self.fields[field_name]
        suggested_pks = set(
            field.queryset.filter(
                branch__min_age_dec_31__isnull=False,
                branch__max_age_dec_31__isnull=False,
                branch__min_age_dec_31__lte=age,
                branch__max_age_dec_31__gte=age,
                pk__in=Section.compatible_with(self.instance.sex),
            ).values_list("pk", flat=True)
        )
        if not suggested_pks:
            return

        suggested, others = [], []
        for section in field.queryset:
            entry = (section.pk, field.label_from_instance(section))
            (suggested if section.pk in suggested_pks else others).append(entry)

        # A single group is not a suggestion, it is the whole list with a
        # heading, so leave the field flat unless there is something to divide.
        if not others:
            return

        choices = []
        if field.empty_label is not None:
            choices.append(("", field.empty_label))
        choices.append((_("Suitable for their age"), suggested))
        choices.append((_("Other sections"), others))
        field.choices = choices

    def _role_for_enrollment(self, current_section, next_section, birthday):
        """The primary role a section assignment implies.

        The current year's section decides when there is one; a section
        prepared for next year only counts when this year has none. The age is
        read on the troop's reference day, like the passage's, and a member
        with no birthday counts as an adult — the same reading as
        ``Person.is_adult``.

        The birthday is the one being submitted: correcting it and assigning
        a section in the same save must not classify the member by the date
        they were stored with.
        """
        year = self.current_year if current_section else self.next_year
        if year is None:
            return None
        age = Person(birthday=birthday).age_on_dec_31(year)
        is_adult = age is None or age >= ADULT_AGE
        return Role.objects.get(short=ANIMATEUR if is_adult else ANIME)

    def clean(self):
        cleaned_data = super().clean()
        primary_role = cleaned_data.get("primary_role")
        current_section = cleaned_data.get("current_section")
        next_section = cleaned_data.get("next_section")

        if current_section or next_section:
            # Enrolling someone is what makes them a participant or a leader.
            # A locked role (an existing section, or linked children) keeps
            # its account type, and a section on such a member is refused.
            if not getattr(self, "role_locked", False):
                derived = self._role_for_enrollment(
                    current_section, next_section, cleaned_data.get("birthday")
                )
                if derived is not None:
                    primary_role = cleaned_data["primary_role"] = derived
            elif primary_role and primary_role.short not in (ANIME, ANIMATEUR):
                raise ValidationError(
                    _(
                        "Only the 'Participant' and 'Animator' roles can be enrolled in a section."
                    )
                )

        # Keep only the roles the submitted primary role can hold. This is
        # what drops "Parent actif" when a Parent becomes an Autre membre in
        # the same submit, and it stops a crafted POST from giving a role the
        # form never offered.
        if "secondary_roles" in self.fields:
            allowed = secondary_roles_for(
                primary_role.short if primary_role else None
            )
            cleaned_data["secondary_roles"] = [
                role
                for role in cleaned_data.get("secondary_roles") or []
                if role.short in allowed
            ]

        return cleaned_data

    def save(self, commit=True):
        person = super().save(commit=False)

        primary_role = self.cleaned_data.get("primary_role")
        secondary_roles = self.cleaned_data.get("secondary_roles")
        email = self.cleaned_data.get("email")

        if commit:
            person.primary_role = primary_role
            person.save()

            # Replace the roles this form offered. A role it hid — the
            # Treasurer role while membership fees are switched off, or every
            # role when the reader may not assign them — must survive an
            # unrelated edit rather than be deleted for not having been on
            # screen to re-submit.
            if self.can_assign_roles and "secondary_roles" in self.fields:
                stored = PersonRole.objects.filter(
                    person=person, role__is_primary=False
                ).filter(role__in=self.fields["secondary_roles"].queryset)
                stored.delete()
                for role in secondary_roles or []:
                    PersonRole.objects.create(person=person, role=role)

            # Whatever path got us here, only the roles allowed beside the new
            # primary role may remain: this clears a Participant's whole set,
            # the unit administration when someone becomes an Animateur, and
            # "Parent actif" when a Parent becomes an Autre membre.
            allowed = secondary_roles_for(
                primary_role.short if primary_role else None
            )
            PersonRole.objects.filter(
                person=person, role__is_primary=False
            ).exclude(role__short__in=allowed).delete()

            current_section = self.cleaned_data.get("current_section")
            next_section = self.cleaned_data.get("next_section")

            if current_section:
                enrollment, created = Enrollment.objects.update_or_create(
                    user=person,
                    school_year=self.current_year,
                    defaults={"section": current_section},
                )
            else:
                Enrollment.objects.filter(
                    user=person, school_year=self.current_year
                ).delete()

            if next_section and self.next_year:
                enrollment, created = Enrollment.objects.update_or_create(
                    user=person,
                    school_year=self.next_year,
                    defaults={"section": next_section},
                )
                # Choosing their section by hand is exactly the decision the
                # passage was asking for, so the flag it left is answered.
                if person.passage_review:
                    person.passage_review = ""
                    person.save(update_fields=["passage_review"])
            elif self.next_year:
                Enrollment.objects.filter(
                    user=person, school_year=self.next_year
                ).delete()

            if email:
                if hasattr(person, "account"):
                    person.account.email = email
                    person.account.save()
                else:
                    Account.objects.create(person=person, email=email)
                    reset_password_form = ResetPasswordForm({"email": email})
                    if reset_password_form.is_valid():
                        reset_password_form.save(request=None)

        return person

    class Meta:
        model = Person
        fields = [
            "first_name",
            "last_name",
            "totem",
            "sex",
            "birthday",
            "address",
            "phone",
            "photo_consent",
            "note",
        ]
        labels = {
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "address": _("Address"),
            "phone": _("Phone"),
            "photo_consent": _("Photos allowed"),
            "birthday": _("Date of birth (only for participants)"),
            "sex": _("Sex (only for participants)"),
            "totem": _("Totem"),
            "note": _("Notes"),
        }


class ProfileEditForm(UserChangeForm):
    first_name = forms.CharField(max_length=150, label=_("First name"))
    last_name = forms.CharField(max_length=150, label=_("Last name"))
    totem = forms.CharField(max_length=60, required=False, label=_("Totem"))
    address = forms.CharField(required=False, label=_("Address"))
    phone = forms.CharField(required=False, label=_("Phone"))
    photo_consent = forms.BooleanField(
        required=False,
        label="",
    )

    email = forms.EmailField()

    primary_role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        label=_("Account type"),
        required=True,
        initial="p",
    )

    parent_active = forms.BooleanField(
        required=False,
        label=_("Active parent, I want to help the unit occasionally"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Account
        fields = ("email",)
        labels = {
            "email": "E-mail",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import TroopSettings
        troop_settings = TroopSettings.get_settings()
        self.fields["photo_consent"].label = troop_settings.photo_consent_text
        person = self.instance.person
        parent_active_role = Role.objects.get(short="pa")

        if not hasattr(self.instance, "person"):
            raise ValueError("Account instance is missing required Person relationship")

        self.fields["first_name"].initial = self.instance.person.first_name
        self.fields["last_name"].initial = self.instance.person.last_name
        self.fields["totem"].initial = self.instance.person.totem
        self.fields["address"].initial = self.instance.person.address
        self.fields["phone"].initial = self.instance.person.phone
        self.fields["photo_consent"].initial = self.instance.person.photo_consent
        self.fields["email"].initial = self.instance.email

        locked, reason = person.has_role_dependencies()
        self.role_locked = locked
        self.lock_reason = reason

        if locked:
            # Replace the radio select with a hidden field preserving current value
            self.fields["primary_role"] = forms.CharField(
                widget=forms.HiddenInput,
                initial=person.primary_role.short,
            )
            # A locked Parent is still allowed to join or leave the active
            # parents — that is a choice about themselves, not a change of
            # account type. Other locked roles cannot hold it at all, so the
            # field stays hidden and only round-trips its (false) value.
            if person.primary_role.short != PARENT:
                self.fields["parent_active"].widget = forms.HiddenInput()
        else:
            if person.age_fits_branch():
                # Rule 2: a person of branch age can only be a Participant.
                self.fields["primary_role"].choices = [
                    c for c in ROLE_CHOICES if c[0] == Person.CHILD_ROLE_SHORT
                ]
                self.fields["primary_role"].initial = Person.CHILD_ROLE_SHORT
            elif person.primary_role.short == "p":
                self.fields["primary_role"].initial = "p"
            elif person.primary_role.short == "a":
                self.fields["primary_role"].initial = "a"
            elif person.primary_role.short == "e":
                self.fields["primary_role"].initial = "e"
            elif person.primary_role.short == AUTRE_MEMBRE:
                self.fields["primary_role"].initial = AUTRE_MEMBRE

        # Seeded regardless of locking: the checkbox is hidden for a locked
        # role, and an unseeded hidden checkbox would read as un-ticked and
        # drop the role on the next save.
        if parent_active_role in person.roles.all():
            self.fields["parent_active"].initial = True

    def clean(self):
        cleaned_data = super().clean()
        person = self.instance.person
        primary_role = cleaned_data.get("primary_role")
        if (
            primary_role
            and not getattr(self, "role_locked", False)
            and person.age_fits_branch()
            and primary_role != Person.CHILD_ROLE_SHORT
        ):
            raise ValidationError(
                _("A person of branch age can only be a Participant.")
            )
        # "Parent actif" only exists alongside the Parent primary role. The
        # checkbox is hidden for other roles, but hiding it does not un-tick
        # it, so a role switch in this same submit could otherwise keep it.
        if primary_role and primary_role != PARENT:
            cleaned_data["parent_active"] = False
        return cleaned_data

    def save(self, commit=True):
        person = self.instance.person
        parent_active_role = Role.objects.get(short="pa")

        person.first_name = self.cleaned_data["first_name"]
        person.last_name = self.cleaned_data["last_name"]
        person.totem = self.cleaned_data.get("totem")
        person.address = self.cleaned_data.get("address")
        person.phone = self.cleaned_data.get("phone")
        person.photo_consent = self.cleaned_data.get("photo_consent", False)
        person.primary_role = Role.objects.get(
            short=self.cleaned_data.get("primary_role")
        )
        account = super().save(commit=False)
        account.email = self.cleaned_data["email"]
        if commit:
            account.save()
            person.save()
            if self.cleaned_data.get("parent_active"):
                person.roles.add(parent_active_role)
            else:
                person.roles.remove(parent_active_role)

        return account


class AnimeProfileForm(forms.ModelForm):
    """Restricted profile form for Animé (child) users.
    Only totem, email, and phone are editable. Address is read-only.
    """

    totem = forms.CharField(max_length=60, required=False, label=_("Totem"))
    phone = forms.CharField(required=False, label=_("Phone"))
    email = forms.EmailField(label=_("Email"))

    class Meta:
        model = Account
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["totem"].initial = self.instance.person.totem
        self.fields["phone"].initial = self.instance.person.phone
        self.fields["email"].initial = self.instance.email

    def save(self, commit=True):
        person = self.instance.person
        person.totem = self.cleaned_data.get("totem")
        person.phone = self.cleaned_data.get("phone")
        account = super().save(commit=False)
        account.email = self.cleaned_data["email"]
        if commit:
            account.save()
            person.save()
        return account


class ChildForm(forms.ModelForm):
    email = forms.EmailField(
        required=False,
        label=_("Email"),
        help_text=_("If an email is provided, an account will be created for the child."),
    )

    class Meta:
        model = Person
        fields = [
            "first_name",
            "last_name",
            "sex",
            "birthday",
            "address",
            "phone",
            "totem",
            "note",
            "photo_consent",
        ]
        labels = {
            "sex": _("Sex"),
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "address": _("Address"),
            "phone": _("Phone"),
            "note": _("Notes"),
            "birthday": _("Date of birth"),
            "totem": _("Totem"),
            "photo_consent": _("Photos allowed"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The wording of the consent is the troop's, exactly as the parent
        # sees it on their own profile.
        self.fields["photo_consent"].label = (
            TroopSettings.get_settings().photo_consent_text
        )
        person = self.instance
        if person and person.pk:
            if not person.address:
                self.fields["address"].initial = person.effective_address()
            if account := Account.objects.filter(person=person).first():
                self.fields["email"].initial = account.email
        self.fields["birthday"] = forms.DateField(
            label=self.fields["birthday"].label,
            widget=forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            required=True,
        )
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["sex"].required = True
        self.fields["birthday"].required = True
        self.fields["totem"].required = False

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        person = self.instance

        if email:
            account_with_email = (
                Account.objects.filter(email=email).exclude(person=person).first()
            )
            if account_with_email:
                self.add_error(
                    "email", _("This email already exists for another user")
                )

        return cleaned_data

    def save(self, commit=True):
        person = super().save(commit=False)

        if commit:
            person.save()
            self.save_account(person)

        return person

    def save_account(self, person):
        """Create or update the child's Account when an email was provided.

        Sending the "choose a password" email is part of the promise made in
        the child form, so it must also happen when the caller saved the
        Person itself (commit=False in add_new_child_view).
        """
        email = self.cleaned_data.get("email")
        if not email:
            return

        if Account.objects.filter(person=person).exists():
            account = Account.objects.get(person=person)
            if account.email != email:
                account.email = email
                account.save()
        else:
            account = Account(person=person, email=email)
            account.save()
            reset_password_form = ResetPasswordForm({"email": email})
            if reset_password_form.is_valid():
                reset_password_form.save(request=None)


class ChildFromKey(forms.Form):
    secret_key = forms.CharField(max_length=6, label=_("Secret key (6 characters)"))

    def clean_secret_key(self):
        """Reject unknown keys here rather than letting the view raise.

        ``add_child_key_view`` resolves the key with ``Person.objects.get()``,
        so without this check a mistyped key returned a 500 instead of a form
        error the parent could correct.
        """
        key = self.cleaned_data["secret_key"]
        if not Person.objects.filter(secret_key=key).exists():
            raise ValidationError(_("No child matches that key."))
        return key


class OnboardingForm(forms.Form):
    first_name = forms.CharField(max_length=150, label=_("First name"))
    last_name = forms.CharField(max_length=150, label=_("Last name"))
    address = forms.CharField(required=False, label=_("Address"))
    phone = forms.CharField(required=False, label=_("Phone"))
    primary_role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        label=_("Account type"),
        required=True,
    )
    photo_consent = forms.BooleanField(
        required=False,
        label="",
    )

    def __init__(self, *args, **kwargs):
        person = kwargs.pop("person", None)
        super().__init__(*args, **kwargs)
        from .models import TroopSettings
        troop_settings = TroopSettings.get_settings()
        self.fields["photo_consent"].label = troop_settings.photo_consent_text

        # Rule 2: a person of branch age can only be a Participant.
        self.fits_branch = bool(person and person.age_fits_branch())
        if self.fits_branch:
            self.fields["primary_role"].choices = [
                c for c in ROLE_CHOICES if c[0] == Person.CHILD_ROLE_SHORT
            ]
            self.fields["primary_role"].initial = Person.CHILD_ROLE_SHORT

    def clean(self):
        cleaned_data = super().clean()
        if (
            self.fits_branch
            and cleaned_data.get("primary_role") != Person.CHILD_ROLE_SHORT
        ):
            raise ValidationError(
                _("A person of branch age can only be a Participant.")
            )
        return cleaned_data

    def save(self, account):
        person = account.person
        person.first_name = self.cleaned_data["first_name"]
        person.last_name = self.cleaned_data["last_name"]
        person.address = self.cleaned_data.get("address", "")
        person.phone = self.cleaned_data.get("phone", "")
        person.photo_consent = self.cleaned_data.get("photo_consent", False)
        person.primary_role = Role.objects.get(
            short=self.cleaned_data["primary_role"]
        )
        person.status = "a"
        person.save()
        return person


class AdminAccountChangeForm(UserChangeForm):
    person_first_name = forms.CharField(max_length=150, required=True)
    person_last_name = forms.CharField(max_length=150, required=True)
    person_birthday = forms.DateField(required=False)
    person_sex = forms.ChoiceField(choices=Person.Sex.choices, required=False)
    person_address = forms.CharField(required=False)
    person_phone = forms.CharField(required=False)
    person_photo_consent = forms.BooleanField(required=False)
    person_note = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        model = Account
        fields = ("email", "password", "is_active", "is_staff")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            person = self.instance.person
            self.fields["person_first_name"].initial = person.first_name
            self.fields["person_last_name"].initial = person.last_name
            self.fields["person_birthday"].initial = person.birthday
            self.fields["person_sex"].initial = person.sex
            self.fields["person_address"].initial = person.address
            self.fields["person_phone"].initial = person.phone
            self.fields["person_photo_consent"].initial = person.photo_consent
            self.fields["person_note"].initial = person.note


class LanguageSelectionMixin(forms.Form):
    """The enabled/default language pair, shared by the admin and the settings page.

    This subclasses ``forms.Form`` rather than being a plain mixin on purpose:
    Django's form metaclass only collects declared fields from bases that are
    themselves forms, so a plain mixin's fields would be silently dropped.
    """

    # The labels are spelled out so they are translatable; the help texts are
    # deliberately left to the model fields, which is the one wording the admin
    # and the settings page both show.
    enabled_languages = forms.MultipleChoiceField(
        required=True,
        choices=AVAILABLE_LANGUAGE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label=_("Enabled languages"),
    )
    default_language = forms.ChoiceField(
        required=True,
        choices=AVAILABLE_LANGUAGE_CHOICES,
        widget=forms.Select,
        label=_("Default language"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Constrain the default-language dropdown to the currently-selected
        # enabled languages (from POST when saving, else the stored value).
        enabled = self._selected_enabled()
        if enabled:
            self.fields["default_language"].choices = [
                (code, label)
                for code, label in AVAILABLE_LANGUAGE_CHOICES
                if code in enabled
            ]

    def _selected_enabled(self):
        """Languages the user has marked enabled, from bound data or instance."""
        if self.is_bound:
            if hasattr(self.data, "getlist"):  # QueryDict (real request)
                return self.data.getlist("enabled_languages")
            value = self.data.get("enabled_languages", [])
        elif self.instance and self.instance.pk:
            value = self.instance.enabled_languages or []
        else:
            value = self.initial.get("enabled_languages", [])
        if isinstance(value, str):
            return [value]
        return list(value or [])

    def clean(self):
        cleaned = super().clean()
        enabled = cleaned.get("enabled_languages") or []
        default = cleaned.get("default_language")
        if not enabled:
            self.add_error(
                "enabled_languages", _("Select at least one available language.")
            )
        elif default and default not in enabled:
            self.add_error(
                "default_language",
                _("The default language must be one of the available languages."),
            )
        return cleaned


class OrganisationSettingsForm(forms.ModelForm):
    """Who the troop is, and how the outside reaches it."""

    class Meta:
        model = TroopSettings
        fields = (
            "name",
            "short_name",
            "federation",
            "contact_email",
            "reply_to_email",
            "contact_phone",
            # The hall, its address and its picture belong to the public
            # page's "Where to find us" block, and are edited in that card.
            "privacy_policy",
            "facebook_url",
            "instagram_url",
            "logo",
            "favicon",
        )
        labels = {
            "name": _("Unit name"),
            "short_name": _("Short name"),
            "federation": _("Federation"),
            "contact_email": _("Public contact email"),
            "reply_to_email": _("Reply-to address"),
            "contact_phone": _("Public phone"),
            "privacy_policy": _("Privacy policy"),
            "facebook_url": _("Facebook page"),
            "instagram_url": _("Instagram profile"),
            "logo": _("Logo"),
            "favicon": _("Favicon"),
        }
        # The two help texts come from the model, so the admin and this page
        # cannot drift apart. Only the file-picker hint is added here.
        widgets = {
            "logo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "favicon": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        help_texts = {
            "short_name": _("Used where the full name does not fit. Empty uses the full name."),
            "reply_to_email": _(
                "Where answers to automated mail should go. "
                "Empty replies to the sender address."
            ),
            "facebook_url": _("Shown in the site footer. Leave empty to hide the link."),
            "instagram_url": _("Shown in the site footer. Leave empty to hide the link."),
        }


class LocaleSettingsForm(LanguageSelectionMixin, forms.ModelForm):
    """The languages offered, and the conventions used to display values."""

    class Meta:
        model = TroopSettings
        fields = ("enabled_languages", "default_language", "phone_region", "currency")
        labels = {
            "phone_region": _("Phone country"),
            "currency": _("Currency"),
        }
        # No help_texts here: the model's own are the single wording for these
        # two, so the admin and this page cannot drift apart.


class CalendarSettingsForm(forms.ModelForm):
    """The dates that shape a scout year."""

    class Meta:
        model = TroopSettings
        fields = (
            "year_start_month",
            "year_start_day",
            "passage_mode",
            "top_branch_graduates_become_leaders",
            "archive_retention_years",
        )
        labels = {
            "year_start_month": _("School year starts — month"),
            "year_start_day": _("School year starts — day"),
            "passage_mode": _("Section passage runs"),
            "top_branch_graduates_become_leaders": _(
                "Members leaving the last branch become animators"
            ),
            "archive_retention_years": _("Keep archived members for (years)"),
        }
        # No age-reference or passage-day fields: ages are fixed on 31 December
        # and the passage on 1 May, and a troop that could move either would
        # move every member's branch without changing a single lesson plan.
        # passage_mode's help text comes from the model, so the admin and this
        # page say the same thing.


class ModuleSettingsForm(forms.ModelForm):
    """Which of the optional modules this troop uses."""

    class Meta:
        model = TroopSettings
        fields = ("fees_enabled", "signing_enabled", "agenda_enabled")
        labels = {
            "fees_enabled": _("Membership fees"),
            # The module sends attestations; "campaign" was the internal model's
            # word for the batch, and naming the switch after it asked a troop
            # to learn that word before it could turn the feature on.
            "signing_enabled": _("Sending attestations"),
            "agenda_enabled": _("Agenda"),
        }


class PublicPageSettingsForm(forms.ModelForm):
    """What a visitor sees on `/`, block by block.

    The content modules are validated together with their switch: a module
    turned on with no words would render a heading over nothing, which reads as
    a page that is broken rather than as one the troop is still writing.
    """

    class Meta:
        model = TroopSettings
        fields = (
            "homepage_band_enabled",
            "homepage_desk_enabled",
            # The window, not the block: the desk may be on screen all year
            # while registrations are closed, which is how a unit answers
            # "can I still register?" without turning the page off.
            "registration_open",
            "registration_message",
            "homepage_place_enabled",
            "homepage_about_enabled",
            "homepage_about_text",
            "homepage_faq_enabled",
            "homepage_faq_text",
            # The introduction's words and everything the place block shows.
            # They live on this form because this is the page that renders
            # them, and an address edited a card away from its own map is a
            # setting nobody finds twice.
            "site_description",
            "footer_address",
            "meeting_place",
            "map_image",
        )
        labels = {
            "homepage_band_enabled": _("Introduction"),
            "homepage_desk_enabled": _("Enrolment desk"),
            "registration_open": _("Registrations open"),
            "registration_message": _("Message while registrations are closed"),
            "homepage_place_enabled": _("Where to find us"),
            "homepage_about_enabled": _("About us"),
            "homepage_about_text": _("About text"),
            "homepage_faq_enabled": _("FAQ"),
            "homepage_faq_text": _("Questions and answers"),
            "site_description": _("Introduction text"),
            "footer_address": _("Address"),
            "meeting_place": _("Meeting place"),
            "map_image": _("Map of the meeting place"),
        }
        help_texts = {
            "homepage_band_enabled": _(
                "Drawn over the photograph, under the unit's name."
            ),
            "homepage_desk_enabled": _(
                "The branches' own ages answer it, so the desk follows the "
                "branches edited in the admin."
            ),
            "registration_open": _(
                "When off, the desk shows your message instead of the "
                "registration form."
            ),
            "registration_message": _(
                "Shown on the public page while registrations are closed."
            ),
            "homepage_place_enabled": _(
                "The hall, the address and its picture."
            ),
            "homepage_about_enabled": _(
                "A longer introduction, on its own sheet."
            ),
            "homepage_faq_enabled": _("Questions parents ask, with your answers."),
            "site_description": _(
                "Shown in the band under the unit's name, and used as the "
                "site's description in search results."
            ),
            "footer_address": _(
                "Shown under “Where to find us” and in the site footer."
            ),
            "meeting_place": _(
                "What the unit calls the place it meets. Empty shows the "
                "address alone."
            ),
        }
        widgets = {
            "map_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    #: The blocks the positions below order. The labels are the switches' own.
    ORDER_LABELS = {
        "desk": _("Enrolment desk"),
        "place": _("Where to find us"),
        "about": _("About us"),
        "faq": _("FAQ"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        order = self.instance.homepage_blocks_in_order()
        positions = {key: index for index, key in enumerate(order, start=1)}
        choices = [(index, index) for index in range(1, len(order) + 1)]
        for key in TroopSettings.HOMEPAGE_BLOCK_KEYS:
            self.fields[f"position_{key}"] = forms.TypedChoiceField(
                choices=choices,
                coerce=int,
                initial=positions[key],
                label=self.ORDER_LABELS[key],
            )
        # The card renders these four together, above the block switches.
        self.order_fields = [
            self[f"position_{key}"]
            for key in TroopSettings.HOMEPAGE_BLOCK_KEYS
        ]

    def clean(self):
        cleaned = super().clean()
        positions = {
            key: cleaned.get(f"position_{key}")
            for key in TroopSettings.HOMEPAGE_BLOCK_KEYS
        }
        if all(value is not None for value in positions.values()):
            if len(set(positions.values())) != len(positions):
                raise ValidationError(
                    _("Each block needs its own position.")
                )
            cleaned["homepage_block_order"] = ",".join(
                sorted(positions, key=lambda key: positions[key])
            )
        # Every language other than the default falls back to it, so the text
        # only has to exist there. Editing a non-default language may leave its
        # field blank; editing the default language with the switch on may not.
        default_language = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
        editing_default = translation.get_language() == default_language
        for enabled, text, label in (
            ("homepage_about_enabled", "homepage_about_text", _("About us")),
            ("homepage_faq_enabled", "homepage_faq_text", _("FAQ")),
        ):
            if not cleaned.get(enabled):
                continue
            has_text = bool((cleaned.get(text) or "").strip())
            if not has_text and not editing_default:
                has_text = bool(
                    (
                        getattr(
                            self.instance, f"{text}_{default_language}", ""
                        )
                        or ""
                    ).strip()
                )
            if not has_text:
                self.add_error(
                    text,
                    _("Write the text before turning %(module)s on.")
                    % {"module": label},
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        order = self.cleaned_data.get("homepage_block_order")
        if order:
            instance.homepage_block_order = order
        if commit:
            instance.save()
        return instance


class DocumentForm(forms.ModelForm):
    """A document the unit hands out, as the documents page edits it.

    A document is a link, a file, or both; one with neither would render a
    tile nobody can open, so the form refuses it rather than letting the list
    grow a dead entry.
    """

    class Meta:
        model = ImportantDocument
        fields = ("title", "description", "url", "file")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "url": forms.URLInput(attrs={"class": "form-control"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }
        labels = {
            "title": _("Title"),
            "description": _("Description"),
            "url": _("Link"),
            "file": _("File"),
        }
        help_texts = {
            "description": _("Optional. Shown under the title."),
            "url": _("A page elsewhere, such as the federation's rules."),
            "file": _("Uploaded here, or leave empty to link to a page."),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("url") and not cleaned.get("file"):
            self.add_error("url", _("Add a link or a file."))
        return cleaned


class WordingSettingsForm(forms.ModelForm):
    """The words the site puts around forms and in its own mail.

    Kept apart from the organisation card because these are not facts about
    the unit: they are the sentences a family reads at the moment they answer
    a form or open an account email, so the person editing them is looking for
    wording, not for contact details.
    """

    class Meta:
        model = TroopSettings
        fields = (
            "email_signature",
            "photo_consent_text",
            "address_placeholder",
        )
        labels = {
            "email_signature": _("Email signature"),
            "photo_consent_text": _("Photo consent"),
            "address_placeholder": _("Address example"),
        }
        help_texts = {
            "email_signature": _("Added to the account emails the site sends."),
            "photo_consent_text": _(
                "The wording beside the photo-consent checkbox on a child's form."
            ),
            "address_placeholder": _(
                "The greyed-out example under an address field."
            ),
        }
        # Both are a sentence or two; the default textarea would give each
        # eight rows of empty paper on a card that already has six fields.
        widgets = {
            "email_signature": forms.Textarea(attrs={"rows": 3}),
            "photo_consent_text": forms.Textarea(attrs={"rows": 3}),
        }


class TimelineActivityForm(forms.ModelForm):
    """One date on the year-line, as the settings card lists it.

    The labels are the card's column headings rather than the model's field
    names, and the model's own help texts are cleared: the card explains the
    list once above it, and a help line repeated under every row would turn a
    list of dates into a paragraph of instructions.
    """

    class Meta:
        model = TimelineActivity
        fields = ("name", "start_date", "end_date")
        labels = {
            "name": _("Activity"),
            "start_date": _("Starts"),
            "end_date": _("Ends"),
        }
        widgets = {
            # `type=date` needs an ISO value; without the explicit format the
            # widget writes the local DD/MM/YYYY and the browser renders an
            # empty control over a date that is actually stored.
            "start_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ""


#: The year-line's dates, edited on the settings page beside the block that
#: draws them. A model formset rather than a nested admin: the dates are the
#: module's content, and a superuser composing a page should not have to leave
#: it to add next autumn's weekend.
TimelineActivityFormSet = forms.modelformset_factory(
    TimelineActivity,
    form=TimelineActivityForm,
    extra=1,
    can_delete=True,
)


class SectionEventForm(forms.ModelForm):
    """One activity on the agenda of the section its leader is editing.

    ``section`` is not a field. The view decides which section is being written
    to and passes it in, so a leader cannot name — or reach — a section they do
    not lead by editing the POST body.
    """

    class Meta:
        model = SectionEvent
        fields = (
            "activity_type",
            "title",
            "description",
            "start_date",
            "start_time",
            "end_date",
            "end_time",
        )
        widgets = {
            "activity_type": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            # The explicit formats matter: a date input only accepts an ISO
            # value, and the localised default would render "26/09/2026" into a
            # field the browser then shows as empty.
            "start_date": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            "start_time": forms.TimeInput(
                format="%H:%M", attrs={"type": "time", "class": "form-control"}
            ),
            "end_date": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            "end_time": forms.TimeInput(
                format="%H:%M", attrs={"type": "time", "class": "form-control"}
            ),
        }

    def __init__(self, *args, section=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        self.fields["end_date"].help_text = _(
            "Leave empty for an activity that lasts a single day."
        )

    def save(self, commit=True):
        event = super().save(commit=False)
        if self.section is not None:
            event.section = self.section
        if commit:
            event.save()
        return event


class AbsenceForm(forms.ModelForm):
    """A parent's notice that one child will miss one activity.

    ``event`` is not a field: the view resolves the activity from the URL and
    passes it in, so the POST body cannot point a notice at an activity of a
    section the parent has nothing to do with. ``child`` is a field, because a
    parent may have several children in the same section — but its queryset is
    the parent's own children *in this activity's section*, so it cannot be
    used to reach another family's child either.
    """

    class Meta:
        model = Absence
        fields = ("child", "reason")
        widgets = {
            "child": forms.Select(attrs={"class": "form-select"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, event=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.reporter = get_person(user)

        children = reportable_children(user, event.section if event else None)
        self.fields["child"].queryset = children
        self.fields["child"].label = _("Child")
        # A parent of one child in this section is not made to choose them.
        if not self.is_bound and children.count() == 1:
            self.fields["child"].initial = children.first()

    def clean_reason(self):
        # Required here although the column is blank-able: a leader reads the
        # reason to decide whether the child needs anything before the next
        # activity, so an empty notice is not worth sending.
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise ValidationError(_("Please give a short explanation."))
        return reason

    def save(self):
        """Record the notice, or rewrite the one already recorded.

        ``event`` and ``child`` are unique together, and reporting twice is a
        parent correcting themselves — or the second parent of the same child
        saying the same thing — rather than an error worth showing. So the
        existing row is updated in place instead of colliding with the
        constraint.
        """
        absence, _ = Absence.objects.update_or_create(
            event=self.event,
            child=self.cleaned_data["child"],
            defaults={
                "reason": self.cleaned_data["reason"],
                "reported_by": self.reporter,
            },
        )
        self.instance = absence
        return absence


class ContactLeadersForm(forms.Form):
    """A parent's message to a section or unit contact.

    The recipients are never taken from the POST body: ``targets`` is resolved
    from the reader's own children by ``members.contacts.contact_targets``, and
    the submitted key must be one of them. A parent therefore cannot address
    another family's section by crafting the form.
    """

    recipient = forms.ChoiceField(
        label=_("Send to"),
        # A select truncates these labels on a phone, and the person the
        # message reaches is the one choice the parent must be able to read.
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    title = forms.CharField(
        max_length=200,
        label=_("Title"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        max_length=5000,
        label=_("Message"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 7}),
    )

    def __init__(self, *args, targets, **kwargs):
        super().__init__(*args, **kwargs)
        self.targets = {target.key: target for target in targets}
        self.fields["recipient"].choices = [
            (key, target.label) for key, target in self.targets.items()
        ]

    def clean_recipient(self):
        key = self.cleaned_data["recipient"]
        if key not in self.targets:
            raise ValidationError(_("Choose who receives your message."))
        return key

    def clean_title(self):
        # The title becomes an email subject. A line break there is a header
        # injection attempt rather than a title, and Django's mail layer would
        # refuse it only at send time, after the form had already said yes.
        title = self.cleaned_data["title"].strip()
        if "\n" in title or "\r" in title:
            raise ValidationError(_("The title cannot contain a line break."))
        return title

    @property
    def target(self):
        """The resolved target the validated message is addressed to."""
        return self.targets[self.cleaned_data["recipient"]]
