"""Populate nl/en translations for modeltranslated DB content.

Roles (name + description) and SiteSettings editorial text are generic and get
full nl + en translations. Branches/Sections are this unit's proper names
(totems, branch titles) and are intentionally left to fall back to French
(MODELTRANSLATION_FALLBACK_LANGUAGES). Adjust here if you want those translated.

Uses .update() on the concrete _en/_nl columns so it is independent of the
modeltranslation runtime descriptor.
"""
from django.db import migrations

# short -> (name_en, name_nl, description_en, description_nl)
ROLE_TRANS = {
    "n": ("New", "Nieuw",
          "Account created but not yet validated",
          "Account aangemaakt maar nog niet gevalideerd"),
    "a": ("Animator", "Animator",
          "Staff animator",
          "Staff-animator"),
    "p": ("Parent", "Ouder",
          "Parent of a member",
          "Ouder van een lid"),
    "e": ("Participant", "Deelnemer",
          "Child participant",
          "Deelnemer-kind"),
    "pa": ("Active parent", "Actieve ouder",
           "Parent volunteering to help the unit occasionally",
           "Ouder die af en toe wil helpen"),
    "ar": ("Lead animator", "Verantwoordelijke animator",
           "Animator in charge of a staff",
           "Verantwoordelijke animator van een staff"),
    "t": ("Treasurer", "Penningmeester",
          "Unit treasurer, grants access to membership fees",
          "Penningmeester van de eenheid, geeft toegang tot de lidgelden"),
    "ri": ("Registration manager", "Inschrijvingsbeheerder",
           "Can manage registrations",
           "Kan inschrijvingen beheren"),
    "ad": ("Admin", "Beheerder",
           "Site administrator",
           "Websitebeheerder"),
}

# field -> (en, nl)  (keys are the concrete _en/_nl column suffix sources)
SITE_TRANS = {
    "site_description": (
        "Official website of the Scouts of Limal, presenting our unit and allowing you to register children.",
        "Officiële website van de scouts van Limal, die onze eenheid voorstelt en het mogelijk maakt kinderen in te schrijven.",
    ),
    "email_signature": (
        "Best regards,\nThe unit staff",
        "Met vriendelijke groet,\nDe eenheidsstaff",
    ),
    "registration_message": (
        "Registrations are open for the scouting year.",
        "De inschrijvingen zijn open voor het scoutingjaar.",
    ),
    "photo_consent_text": (
        "I agree that photos or videos may be used by Les Scouts ASBL, of which my unit is part",
        "Ik ga ermee akkoord dat foto's of video's gebruikt worden door Les Scouts ASBL, waarvan mijn eenheid deel uitmaakt",
    ),
    "address_placeholder": (
        "e.g.: Church Street 1, 1000 Brussels",
        "Bijv.: Kerkstraat 1, 1000 Brussel",
    ),
}

# title_fr -> (title_en, title_nl)
DOC_TRANS = {
    "Fiche médicale": ("Medical form", "Medisch formulier"),
}


def forward(apps, schema_editor):
    Role = apps.get_model("members", "Role")
    for short, (en, nl, den, dnl) in ROLE_TRANS.items():
        Role.objects.filter(short=short).update(
            name_en=en, name_nl=nl, description_en=den, description_nl=dnl
        )

    SiteSettings = apps.get_model("members", "SiteSettings")
    update = {}
    for field, (en, nl) in SITE_TRANS.items():
        update[f"{field}_en"] = en
        update[f"{field}_nl"] = nl
    SiteSettings.objects.all().update(**update)

    Doc = apps.get_model("members", "ImportantDocument")
    for fr, (en, nl) in DOC_TRANS.items():
        Doc.objects.filter(title_fr=fr).update(title_en=en, title_nl=nl)


def reverse(apps, schema_editor):
    Role = apps.get_model("members", "Role")
    Role.objects.all().update(
        name_en=None, name_nl=None, description_en=None, description_nl=None
    )
    SiteSettings = apps.get_model("members", "SiteSettings")
    cols = [f"{f}_en" for f in SITE_TRANS] + [f"{f}_nl" for f in SITE_TRANS]
    SiteSettings.objects.all().update(**{c: None for c in cols})
    Doc = apps.get_model("members", "ImportantDocument")
    Doc.objects.all().update(title_en=None, title_nl=None)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0015_alter_importantdocument_options_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
