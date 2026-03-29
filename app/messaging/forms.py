from django import forms


class ComposeMessageForm(forms.Form):
    subject = forms.CharField(
        max_length=200,
        label="Objet du message",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        label="Contenu du message",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 10}),
    )
