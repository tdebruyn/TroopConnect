from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from .models import Account, Person, SchoolYear, Role, Section, PersonRole, Enrollment

from django.db.models import Q
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone

from datetime import datetime
from allauth.account.forms import ResetPasswordForm, ResetPasswordKeyForm, SignupForm
from allauth.account.utils import filter_users_by_email
from allauth.account.views import PasswordResetView, PasswordResetFromKeyView
from allauth.account.models import EmailConfirmation, EmailConfirmationHMAC
from allauth.account.utils import (
    send_email_confirmation,
    user_pk_to_url_str,
)
from allauth.utils import build_absolute_uri
from django.urls import reverse
import uuid

from .constants import (
    ROLE_CHOICES,
    FORM_LABELS,
    ERROR_MESSAGES,
)


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
        labels = {"email": "E-mail"}


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
            "Si un email est fourni, un compte sera créé. Sinon, le compte existant sera utilisé."
        ),
    )

    # Primary role selection
    primary_role = forms.ModelChoiceField(
        queryset=Role.objects.filter(is_primary=True),
        required=True,
        label=_("Rôle principal"),
    )

    # Secondary roles (multiple selection)
    secondary_roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.filter(is_primary=False),
        required=False,
        label=_("Rôles secondaires"),
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
        label=_("Prochaine section"),
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
        self.fields["current_section"].label = _(f"Section {current_year.range}")
        if self.next_year:
            self.fields["next_section"].label = _(f"Section {self.next_year.range}")

        # Set initial values for roles if instance exists
        if self.instance and self.instance.pk:
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
                    "Seuls les rôles 'Animé' et 'Animateur' peuvent être inscrits dans une section."
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
            "first_name": "Prénom",
            "last_name": "Nom",
            "address": "Adresse",
            "phone": "Téléphone",
            "photo_consent": "Photos autorisées",
            "birthday": "Date de naissance (uniquement pour les animé(e)s)",
            "sex": "Sexe (uniquement pour les animé(e)s)",
            "totem": "Totem",
            "note": "Remarques",
        }


class ProfileEditForm(UserChangeForm):
    first_name = forms.CharField(max_length=150, label=_("Prénom"))
    last_name = forms.CharField(max_length=150, label=_("Nom"))
    totem = forms.CharField(max_length=60, required=False, label=_("Totem"))
    address = forms.CharField(required=False, label=_("Adresse"))
    phone = forms.CharField(required=False, label=_("Téléphone"))
    photo_consent = forms.BooleanField(
        required=False,
        label=_(
            "J'accepte que mes photos ou vidéos soient utilisées par Les Scouts ASBL, dont l'unité de Limal fait partie"
        ),
    )

    # Account fields
    email = forms.EmailField()

    primary_role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        label=_("Type de compte"),
        required=True,
        initial="p",
    )

    parent_active = forms.BooleanField(
        required=False,
        label=_("Parent actif, je veux aider l'unité occasionellement"),
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


class ChildForm(forms.ModelForm):
    email = forms.EmailField(
        required=False,
        label=_("Email"),
        help_text=_("Si un email est fourni, un compte sera créé pour l'enfant."),
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
            "sex": "Sexe",
            "first_name": "Prénom",
            "last_name": "Nom",
            "address": "Adresse",
            "phone": "Téléphone",
            "note": "Remarques",
            "birthday": "Date de naissance",
            "totem": "Totem",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        person = self.instance
        if person and person.pk:
            if account := Account.objects.filter(person=person).first():
                self.fields["email"].initial = account.email
        self.fields["birthday"] = forms.DateField(
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
                    "email", "Cet email existe déjà pour un autre utilisateur"
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
    secret_key = forms.CharField(max_length=5, label=_("Clé secrète"))


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

        # Generate the email confirmation HMAC
        email_confirmation_hmac = EmailConfirmationHMAC(email_confirmation)

        # Use the default token generator to create a token for the password reset
        temp_key = default_token_generator.make_token(user)

        # Send the email confirmation
        send_email_confirmation(
            request, email_confirmation, signup=False, custom_key=temp_key
        )

        # Update the user's password reset key with the temporary key
        user_pk = user_pk_to_url_str(user)
        request.session[f"password_reset_key_{user_pk}"] = temp_key


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
