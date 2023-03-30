from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from allauth.account.forms import SignupForm
from django import forms
from .models import CustomUser, CustomGroup, SchoolYear
from django.db.models import Q
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError
from datetime import datetime


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
        queryset=CustomGroup.get_leaf_nodes("Adulte"),
        required=False,
        label=_("Type d'adulte"),
    )
    current_section = SectionModelChoiceField(
        queryset=CustomGroup.get_leaf_nodes("Section").filter(
            year=SchoolYear.current()
        ),
        required=False,
        label=_(f"Section {SchoolYear.current().range}"),
    )
    next_section = SectionModelChoiceField(
        queryset=CustomGroup.get_leaf_nodes("Section").filter(
            year__name=SchoolYear.current().name + 1
        ),
        required=False,
        label=_(
            f"Section {SchoolYear.objects.get(name=SchoolYear.current().name +1).range}"
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["birthday"].widget.format = "%Y-%m-%d"

    def clean(self):
        cleaned_data = super().clean()
        adult = cleaned_data["adult"]
        current_section = cleaned_data["current_section"]
        next_section = cleaned_data["next_section"]
        birthday_int = None
        if cleaned_data["birthday"]:
            birthday_int = int(cleaned_data["birthday"].strftime("%Y%m%d"))
        if adult and adult.pk != 8 and (current_section or next_section):
            raise ValidationError(
                _(
                    "Pour assigner une section, laisser le champ Adulte vide (pour un enfant) ou choisir Animateur"
                )
            )
        if (
            adult
            and birthday_int
            and int(datetime.now().date().strftime("%Y%m%d")) - 180000 < birthday_int
        ):
            raise ValidationError(
                _(
                    'Pour être adulte, il faut avoir plus de 18 ans, retirer la valeur pour "Type d\'adulte"'
                )
            )

    def save(self, commit=True):
        user = super().save(commit=False)
        adult = self.cleaned_data["adult"]
        for g in CustomGroup.get_leaf_nodes("Adulte"):
            user.groups.remove(g)
        if adult:
            user.groups.add(adult)
        current_section = self.cleaned_data["current_section"]
        next_section = self.cleaned_data["next_section"]
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
            "adult": "Type d'adulte",
            "year": "Année",
        }


class AdultUserChangeForm(UserChangeForm):
    """
    This form is used to provide details about user"""

    groups = CustomGroup.get_leaf_nodes("Adulte")
    group = forms.ModelChoiceField(queryset=CustomGroup.get_leaf_nodes("Adulte"))

    def save(self, commit=True):
        user = super().save(commit=False)
        group = self.cleaned_data["group"]
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
