from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from allauth.account.forms import SignupForm
from django import forms
from .models import CustomUser, CustomGroup, SchoolYear
from django.db.models import Q
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.contrib.sites.shortcuts import get_current_site


from datetime import datetime
from allauth.account.forms import ResetPasswordForm, ResetPasswordKeyForm
from allauth.account.utils import filter_users_by_email
from allauth.account.views import PasswordResetView, PasswordResetFromKeyView
from allauth.account.models import EmailConfirmation, EmailConfirmationHMAC
from allauth.account.utils import (
    send_email_confirmation,
    user_pk_to_url_str,
    user_username,
    get_adapter,
)
from allauth.utils import build_absolute_uri
from django.urls import reverse


class SectionModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.group_name


class CustomSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class AccountCreationForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "groups" in self.fields.keys():
            self.fields["groups"].queryset = CustomGroup.objects.filter(
                parents__isnull=True
            )

    class Meta:
        model = CustomUser
        fields = ("username", "email", "password1", "password2")
        labels = {"username": "Nom d'utilisateur", "email": "E-mail"}


class CustomUserChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "groups" in self.fields.keys():
            self.fields["groups"].queryset = CustomGroup.get_all_leaf_nodes()
        for visible in self.visible_fields():
            visible.field.widget.attrs["class"] = "form-control"




class AdminUserUpdateForm(UserChangeForm):
    adult = forms.ModelChoiceField(
        queryset=CustomGroup.objects.none(),
        required=False,
        label=_("Type d'adulte"),
    )
    current_section = SectionModelChoiceField(
        queryset=CustomGroup.objects.none(),
        required=False,
        label=_("Section"),
    )
    next_section = SectionModelChoiceField(
        queryset=CustomGroup.objects.none(),
        required=False,
        label=_("Next Section"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["birthday"].widget.format = "%Y-%m-%d"
        
        # Lazy load querysets to avoid migration issues
        self.fields['adult'].queryset = CustomGroup.get_leaf_nodes("Adulte")
        
        # Get current school year and set current section queryset and label
        current_year = SchoolYear.current()
        self.fields['current_section'].queryset = CustomGroup.get_leaf_nodes("Section").filter(year=current_year)
        self.fields['current_section'].label = _("Section %s" % current_year.range)

        # Set next section queryset and label
        next_year_name = current_year.name + 1
        try:
            next_year = SchoolYear.objects.get(name=next_year_name)
            self.fields['next_section'].queryset = CustomGroup.get_leaf_nodes("Section").filter(year=next_year)
            self.fields['next_section'].label = _("Section %s" % next_year.range)
        except SchoolYear.DoesNotExist:
            # Handle case where the next school year does not yet exist
            self.fields['next_section'].queryset = CustomGroup.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        adult = cleaned_data.get("adult")
        current_section = cleaned_data.get("current_section")
        next_section = cleaned_data.get("next_section")
        birthday = cleaned_data.get("birthday")

        # Convert birthday to integer for age calculation
        if birthday:
            birthday_int = int(birthday.strftime("%Y%m%d"))
        else:
            birthday_int = None

        # Validation for adult and section assignment
        if adult and adult.pk != 8 and (current_section or next_section):
            raise ValidationError(
                _("To assign a section, leave 'Adult Type' empty for a child or select 'Animateur'.")
            )

        # Age validation for adult
        if adult and birthday_int:
            today_int = int(datetime.now().strftime("%Y%m%d"))
            age = (today_int - birthday_int) // 10000
            if age < 18:
                raise ValidationError(
                    _("To be marked as an adult, the user must be over 18. Remove 'Type d'adulte' if not applicable.")
                )

    def save(self, commit=True):
        user = super().save(commit=False)
        adult = self.cleaned_data.get("adult")
        
        # Clear previous adult groups and set new adult group if selected
        for g in CustomGroup.get_leaf_nodes("Adulte"):
            user.groups.remove(g)
        if adult:
            user.groups.add(adult)
        
        # Set current and next sections
        current_section = self.cleaned_data.get("current_section")
        next_section = self.cleaned_data.get("next_section")
        if current_section:
            user.groups.add(current_section)
        if next_section:
            user.groups.add(next_section)
        
        if commit:
            user.save()
        return user

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "username",
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
            "email": "E-mail",
            "first_name": "Prénom",
            "last_name": "Nom",
            "address": "Adresse",
            "phone": "Téléphone",
            "photo_consent": "Photos autorisées",
            "birthday": "Date de naissance",
            "sex": "Sexe",
            "totem": "Totem",
            "note": "Remarques",
            "adult": "Type d'adulte",
        }



class AdultUserChangeForm(UserChangeForm):
    """
    This form is used to provide details about adult users.
    """
    
    group = forms.ModelChoiceField(queryset=CustomGroup.objects.none(), label="Type d'adulte")  # Start with empty queryset

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Lazy load 'Adulte' groups queryset for the group field and define self.groups
        self.groups = CustomGroup.get_leaf_nodes("Adulte")
        self.fields['group'].queryset = self.groups

    def save(self, commit=True):
        user = super().save(commit=False)
        group = self.cleaned_data["group"]
        
        # Remove all adult groups and add the selected group
        for g in self.groups:
            user.groups.remove(g)
        user.groups.add(group)
        
        if commit:
            user.save()
        return user

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "first_name",
            "last_name",
            "address",
            "phone",
            "photo_consent",
        ]
        labels = {
            "email": "E-mail",
            "first_name": "Prénom",
            "last_name": "Nom",
            "address": "Adresse",
            "phone": "Téléphone",
            "photo_consent": (
                "J'accepte que les photos ou vidéos sur lesquelles mon (mes) enfant(s) figure(nt) soient utilisées "
                "par Les Scouts ASBL, dont l'unité de Limal fait partie"
            ),
        }



class ChildForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].required = False
        self.fields["password2"].required = False
        self.fields["password1"].widget.attrs["autocomplete"] = "off"
        self.fields["password2"].widget.attrs["autocomplete"] = "off"
        self.fields["birthday"].widget.format = "%Y-%m-%d"
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["sex"].required = True
        self.fields["birthday"].required = True

    class Meta:
        model = CustomUser
        fields = [
            "username",
            "first_name",
            "last_name",
            "sex",
            "birthday",
            "address",
            "phone",
            "parents",
            "email",
            "note",
        ]
        labels = {
            # "username": "Nom d'utilisateur",
            "sex": "Sexe",
            "email": "E-mail",
            "first_name": "Prénom",
            "last_name": "Nom",
            "address": "Adresse",
            "phone": "Téléphone",
            "note": "Remarques",
            "password1": "Mot de passe (FACULTATIF)",
            "birthday": "Date de naissance",
        }


class ChildChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["birthday"].widget.format = "%Y-%m-%d"
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["sex"].required = True
        self.fields["birthday"].required = True

    class Meta:
        model = CustomUser
        fields = [
            "username",
            "first_name",
            "last_name",
            "sex",
            "birthday",
            "address",
            "phone",
            "email",
            "note",
        ]
        labels = {
            # "username": "Nom d'utilisateur",
            "sex": "Sexe",
            "email": "E-mail",
            "first_name": "Prénom",
            "last_name": "Nom",
            "address": "Adresse",
            "phone": "Téléphone",
            "note": "Remarques",
            "password1": "Mot de passe (FACULTATIF)",
            "birthday": "Date de naissance",
        }


class ChildFromKey(forms.Form):
    secret_key = forms.CharField(max_length=5, label=_("Clé secrète"))


class ChildAccountCreateForm(ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        child = kwargs.pop("child_user", None)
        self.user = CustomUser.objects.get(username=child)
        super(ResetPasswordForm, self).__init__(*args, **kwargs)

    def _send_password_reset_mail(self, request, email, users, **kwargs):
        token_generator = kwargs.get("token_generator", default_token_generator)

        temp_key = token_generator.make_token(self.user)

        # save it to the password reset model
        # password_reset = PasswordReset(user=user, temp_key=temp_key)
        # password_reset.save()

        # send the password reset email
        uid = user_pk_to_url_str(self.user)
        path = reverse(
            "members:child_account_create_confirm",
            kwargs=dict(uidb36=uid, key=temp_key),
        )
        url = build_absolute_uri(request, path)

        context = {
            "current_site": get_current_site(request),
            "user": self.user,
            "password_reset_url": url,
            "uid": uid,
            "key": temp_key,
            "request": request,
        }

        context["username"] = user_username(self.user)
        get_adapter(request).send_mail(
            "account/email/create_child_account", email, context
        )


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
