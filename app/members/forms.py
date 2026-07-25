
from allauth.account.forms import ResetPasswordForm, ResetPasswordKeyForm, SignupForm
from allauth.account.models import EmailConfirmation
from allauth.account.utils import filter_users_by_email, user_pk_to_url_str
from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .constants import (
    ROLE_CHOICES,
)
from .models import Account, Enrollment, Person, PersonRole, Role, SchoolYear, Section


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
        # if "groups" in self.fields.keys():
        #     self.fields["groups"].queryset = CustomGroup.get_all_leaf_nodes()
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

    # Primary role selection
    primary_role = forms.ModelChoiceField(
        queryset=Role.objects.filter(is_primary=True),
        required=True,
        label=_("Primary role"),
    )

    # Secondary roles (multiple selection)
    secondary_roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.filter(is_primary=False),
        required=False,
        label=_("Secondary roles"),
        # widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "5"}),
        widget=forms.CheckboxSelectMultiple,
    )

    # Section enrollments
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["birthday"].widget.format = "%Y-%m-%d"

        # Get current and next school years
        current_year = SchoolYear.current()
        self.current_year = current_year

        try:
            self.next_year = SchoolYear.objects.get(name=current_year.name + 1)
        except SchoolYear.DoesNotExist:
            self.next_year = None

        # Set section labels with year ranges
        self.fields["current_section"].label = _("Section %(range)s") % {
            "range": current_year.range
        }
        if self.next_year:
            self.fields["next_section"].label = _("Section %(range)s") % {
                "range": self.next_year.range
            }

        # Set initial values for roles if instance exists
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

            # Set secondary roles
            secondary_roles = self.instance.roles.filter(is_primary=False)
            if secondary_roles.exists():
                self.fields["secondary_roles"].initial = secondary_roles.all()

    def clean(self):
        cleaned_data = super().clean()
        primary_role = cleaned_data.get("primary_role")
        current_section = cleaned_data.get("current_section")
        next_section = cleaned_data.get("next_section")

        # Validate section enrollment based on role
        if (
            primary_role
            and primary_role.short not in ["e", "a"]
            and (current_section or next_section)
        ):
            raise ValidationError(
                _(
                    "Only the 'Participant' and 'Animator' roles can be enrolled in a section."
                )
            )

        return cleaned_data

    def save(self, commit=True):
        person = super().save(commit=False)

        # Get form data
        primary_role = self.cleaned_data.get("primary_role")
        secondary_roles = self.cleaned_data.get("secondary_roles")
        email = self.cleaned_data.get("email")

        if commit:
            person.primary_role = primary_role
            person.save()

            # Handle roles
            PersonRole.objects.filter(person=person, role__is_primary=False).delete()
            for role in secondary_roles:
                PersonRole.objects.create(person=person, role=role)

            # Handle section enrollments
            current_section = self.cleaned_data.get("current_section")
            next_section = self.cleaned_data.get("next_section")

            # Current year enrollment
            if current_section:
                enrollment, created = Enrollment.objects.update_or_create(
                    user=person,
                    school_year=self.current_year,
                    defaults={"section": current_section},
                )
            else:
                # Remove enrollment if section is cleared
                Enrollment.objects.filter(
                    user=person, school_year=self.current_year
                ).delete()

            # Next year enrollment
            if next_section and self.next_year:
                enrollment, created = Enrollment.objects.update_or_create(
                    user=person,
                    school_year=self.next_year,
                    defaults={"section": next_section},
                )
            elif self.next_year:
                # Remove enrollment if section is cleared
                Enrollment.objects.filter(
                    user=person, school_year=self.next_year
                ).delete()

            # Handle Account creation/update
            if email:
                if hasattr(person, "account"):
                    # Update existing account
                    person.account.email = email
                    person.account.save()
                else:
                    # Create new account
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

    # Account fields
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
        from .models import SiteSettings
        site_settings = SiteSettings.get_settings()
        self.fields["photo_consent"].label = site_settings.photo_consent_text
        person = self.instance.person
        parent_active_role = Role.objects.get(short="pa")

        # An Account must have a Person
        if not hasattr(self.instance, "person"):
            raise ValueError("Account instance is missing required Person relationship")

        # Populate form fields from Person
        self.fields["first_name"].initial = self.instance.person.first_name
        self.fields["last_name"].initial = self.instance.person.last_name
        self.fields["totem"].initial = self.instance.person.totem
        self.fields["address"].initial = self.instance.person.address
        self.fields["phone"].initial = self.instance.person.phone
        self.fields["photo_consent"].initial = self.instance.person.photo_consent
        self.fields["email"].initial = self.instance.email

        # Set primary role
        locked, reason = person.has_role_dependencies()
        self.role_locked = locked
        self.lock_reason = reason

        if locked:
            # Replace the radio select with a hidden field preserving current value
            self.fields["primary_role"] = forms.CharField(
                widget=forms.HiddenInput,
                initial=person.primary_role.short,
            )
            self.fields["parent_active"].widget = forms.HiddenInput()
        else:
            if person.primary_role.short == "p":
                self.fields["primary_role"].initial = "p"
                if parent_active_role in person.roles.all():
                    self.fields["parent_active"].initial = True
            elif person.primary_role.short == "a":
                self.fields["primary_role"].initial = "a"
            elif person.primary_role.short == "e":
                self.fields["primary_role"].initial = "e"

    def save(self, commit=True):
        person = self.instance.person
        parent_active_role = Role.objects.get(short="pa")

        # Update Person fields
        person.first_name = self.cleaned_data["first_name"]
        person.last_name = self.cleaned_data["last_name"]
        person.totem = self.cleaned_data.get("totem")
        person.address = self.cleaned_data.get("address")
        person.phone = self.cleaned_data.get("phone")
        person.photo_consent = self.cleaned_data.get("photo_consent", False)
        person.primary_role = Role.objects.get(
            short=self.cleaned_data.get("primary_role")
        )
        print(person.primary_role.short, person.primary_role.name)
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        person = self.instance
        if person and person.pk:
            if account := Account.objects.filter(person=person).first():
                self.fields["email"].initial = account.email
        self.fields["birthday"] = forms.DateField(
            label=self.fields["birthday"].label,
            widget=forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            required=True,
        )
        # self.fields["birthday"].widget.format = "%Y-%m-%d"
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

        # Create Account if email is provided
        email = self.cleaned_data.get("email")
        if email and commit:
            # Check if this Person already has an Account
            if Account.objects.filter(person=person).exists():
                # Update the existing Account's email
                account = Account.objects.get(person=person)
                account.email = email
                account.save()
            else:
                # Create a new Account for this Person
                account = Account(person=person, email=email)
                account.save()
                reset_password_form = ResetPasswordForm({"email": email})
                if reset_password_form.is_valid():
                    reset_password_form.save(request=None)

        return person


class ChildFromKey(forms.Form):
    secret_key = forms.CharField(max_length=6, label=_("Secret key (6 characters)"))


class ChildAccountCreateForm(ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        child = kwargs.pop("child_user", None)
        self.user = Person.objects.get(username=child)
        super(ResetPasswordForm, self).__init__(*args, **kwargs)

    # def _send_password_reset_mail(self, request, email, users, **kwargs):
    #     token_generator = kwargs.get("token_generator", default_token_generator)

    #     temp_key = token_generator.make_token(self.user)

    #     # save it to the password reset model
    #     # password_reset = PasswordReset(user=user, temp_key=temp_key)
    #     # password_reset.save()

    #     # send the password reset email
    #     uid = user_pk_to_url_str(self.user)
    #     path = reverse(
    #         "members:child_account_create_confirm",
    #         kwargs=dict(uidb36=uid, key=temp_key),
    #     )
    #     url = build_absolute_uri(request, path)

    #     context = {
    #         "current_site": get_current_site(request),
    #         "user": self.user,
    #         "password_reset_url": url,
    #         "uid": uid,
    #         "key": temp_key,
    #         "request": request,
    #     }

    #     context["username"] = user_username(self.user)
    #     get_adapter(request).send_mail(
    #         "account/email/create_child_account", email, context
    #     )


class ChildAccountCreateConfirmForm(ResetPasswordKeyForm):
    def save(self, request, **kwargs):
        email = self.cleaned_data["email"]
        for user in filter_users_by_email(email):
            self.create_password_and_verify_email(request, user)

    def create_password_and_verify_email(self, request, user):
        # Mark the email address as verified
        user.emailaddress_set.update(verified=True)

        # Create the email confirmation object
        email_address = user.emailaddress_set.get(email=user.email)
        email_confirmation = EmailConfirmation.create(email_address)
        email_confirmation.sent = timezone.now()
        email_confirmation.save()

        # Use the default token generator to create a token for the password reset
        temp_key = default_token_generator.make_token(user)

        # Send the email confirmation
        email_address.send_confirmation(request, signup=False)

        # Update the user's password reset key with the temporary key
        user_pk = user_pk_to_url_str(user)
        request.session[f"password_reset_key_{user_pk}"] = temp_key


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
        super().__init__(*args, **kwargs)
        from .models import SiteSettings
        site_settings = SiteSettings.get_settings()
        self.fields["photo_consent"].label = site_settings.photo_consent_text

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
            # Populate Person fields
            person = self.instance.person
            self.fields["person_first_name"].initial = person.first_name
            self.fields["person_last_name"].initial = person.last_name
            self.fields["person_birthday"].initial = person.birthday
            self.fields["person_sex"].initial = person.sex
            self.fields["person_address"].initial = person.address
            self.fields["person_phone"].initial = person.phone
            self.fields["person_photo_consent"].initial = person.photo_consent
            self.fields["person_note"].initial = person.note
