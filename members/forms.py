from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from allauth.account.forms import SignupForm
from django import forms
from .models import CustomUser, CustomGroup
from django.db.models import Q
from django.utils.translation import gettext as _


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
    groups = CustomGroup.get_leaf_nodes("Adulte")
    group = forms.ModelChoiceField(queryset=CustomGroup.get_leaf_nodes("Adulte"))

    def save(self, commit=True):
        user = super().save(commit=False)
        group = self.cleaned_data["group"]
        for g in AdultUserChangeForm.groups:
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
            "totem",
            "sex",
            "birthday",
            "address",
            "phone",
            "group",
            "photo_consent",
            "note",
        ]
        labels = {
            # "username": "Nom d'utilisateur",
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
        }


class AdultUserChangeForm(UserChangeForm):
    """
    This form is used to provide details about user"""

    groups = CustomGroup.get_leaf_nodes("Adulte")
    group = forms.ModelChoiceField(queryset=CustomGroup.get_leaf_nodes("Adulte"))

    def save(self, commit=True):
        user = super().save(commit=False)
        group = self.cleaned_data["group"]
        for g in AdultUserChangeForm.groups:
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
            "group",
            "photo_consent",
        ]
        labels = {
            # "username": "Nom d'utilisateur",
            "email": "E-mail",
            "first_name": "Prénom",
            "last_name": "Nom",
            "address": "Adresse",
            "phone": "Téléphone",
            "photo_consent": "J'accepte que les photos ou vidéos sur lesquelles mon (mes) enfant(s) figure(nt) soient utilisées par Les Scouts ASBL, dont l'unité de Limal fait partie",
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


class ChildFromKey(forms.Form):
    secret_key = forms.CharField(max_length=5, label=_("Clé secrète"))
