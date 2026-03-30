from django import forms

from members.models import Section


RECIPIENT_GROUP_CHOICES = [
    ("section_parents", "Parents d'une section"),
    ("section_animateurs", "Animateurs d'une section"),
    ("section_animes", "Animés d'une section"),
    ("section_all", "Tous d'une section (parents, animés et animateurs)"),
    ("all_animateurs", "Tous les animateurs"),
    ("animateurs_staff", "Conseil d'unité"),
    ("staff", "Staff d'unité"),
    ("active_parents", "Parents actifs"),
    ("everyone", "Tout le monde"),
]


class ComposeMessageForm(forms.Form):
    recipient_group = forms.ChoiceField(
        choices=RECIPIENT_GROUP_CHOICES,
        label="Destinataires",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_recipient_group"}),
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.all(),
        required=False,
        label="Section",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_section"}),
    )
    subject = forms.CharField(
        max_length=200,
        label="Objet du message",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        label="Contenu du message",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 10}),
    )
    attachment = forms.FileField(
        required=False,
        label="Pièce jointe (optionnel)",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
    event_date = forms.DateField(
        required=False,
        label="Date (agenda)",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Optionnel. Si renseigné, un événement sera ajouté à l'agenda.",
    )
