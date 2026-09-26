"""Guard that newly added user-facing strings ship translated.

The project requires every user-facing string in French *and* Dutch. Nothing
fails when a catalog entry is missing — gettext silently falls back to the
English source — so a missing translation is invisible until someone reads the
French UI. These strings were introduced with the child-lifecycle and reminder
fixes; each must resolve to something other than its English source in both
target languages.
"""

from django.test import SimpleTestCase
from django.utils import translation
from django.utils.translation import gettext

# (source string, fragment expected in the French, fragment expected in Dutch)
NEW_STRINGS = [
    ("%(count)s reminder(s) could not be sent.", "rappel", "herinnering"),
    ("%(first)s will not be re-enrolled next year.", "réinscrit", "opnieuw"),
    ("%(first)s has been deregistered.", "désinscrit", "uitgeschreven"),
    (
        "%(first)s has been deregistered. The registration team has been "
        "notified to complete the current-year procedure.",
        "inscriptions",
        "inschrijvingsteam",
    ),
    ("No child matches that key.", "clé", "sleutel"),
    (
        "The signature PDF should be the same page size as the documents "
        "(e.g. A4); a white background is fine, it is dropped when stamping. "
        "Drag the signature over the preview to position it.",
        "fond blanc",
        "achtergrond",
    ),
    ("Name anchor", "Position du nom", "Positie van de naam"),
    ("Steps", "Étapes", "Stappen"),
    ("Edit campaign", "Modifier la campagne", "Campagne bewerken"),
    (
        "A campaign that has been sent can no longer be changed.",
        "déjà envoyée",
        "verzonden",
    ),
    # Member deletion (archive + purge), added with the super-admin delete flow.
    ("You cannot delete your own account.", "propre compte", "eigen account"),
    (
        "%(name)s has been archived: their login is disabled.",
        "archivé",
        "gearchiveerd",
    ),
    (
        "%(name)s is not archived — archive the member first.",
        "archivez",
        "archiveer",
    ),
    (
        "%(name)s and all their records have been permanently deleted.",
        "définitivement",
        "definitief",
    ),
    ("Archived", "Archivé", "Gearchiveerd"),
    ("Archived member", "Membre archivé", "Gearchiveerd lid"),
    (
        "This member is archived: their login is disabled, but their history "
        "is still stored. Purging destroys the person, their account, "
        "enrolments, payment history and message records for good.",
        "La purge supprime",
        "Definitief verwijderen wist",
    ),
    ("Permanently delete", "définitivement", "Definitief"),
    ("Delete this member", "Supprimer ce membre", "Dit lid verwijderen"),
    (
        "Deleting archives the member and disables their login. Their history "
        "is kept until they are purged.",
        "jusqu'à la purge",
        "tot de purge",
    ),
    ("Delete member", "Supprimer le membre", "Lid verwijderen"),
    ("Delete %(name)s", "Supprimer", "verwijderen"),
    (
        "Deleting %(name)s archives the member. Their account is disabled and "
        "they can no longer log in.",
        "ne peut plus se connecter",
        "niet meer inloggen",
    ),
    (
        "Nothing is destroyed yet: enrolments, payment history and messages "
        "are kept, and the member can still be purged later.",
        "Rien n'est encore détruit",
        "nog niets gewist",
    ),
    ("Enrolments", "Inscriptions", "Inschrijvingen"),
    (
        "Permanently delete %(name)s",
        "Supprimer définitivement",
        "definitief verwijderen",
    ),
    (
        "This permanently destroys %(name)s and everything still linked to "
        "them. This cannot be undone.",
        "irréversible",
        "ongedaan",
    ),
    (
        "Attestation pages that matched this member are kept, but the link to "
        "them is cleared.",
        "attestations liées",
        "Attestationpagina",
    ),
    (
        "Purge an archived member only when the data may really be discarded.",
        "Ne purgez",
        "alleen als",
    ),
    ("Remembered", "Mémorisé", "Onthouden"),
    (
        "Matched by a name correspondence saved in an earlier campaign.",
        "campagne",
        "campagne",
    ),
    # Troop settings: the staff page and the fields it edits. English sources
    # identical to their French wording ("Modules", "Organisation") are left
    # out — this list only proves a translation exists where one is needed.
    ("Settings", "Paramètres", "Instellingen"),
    ("Settings saved.", "Paramètres enregistrés", "Instellingen opgeslagen"),
    ("Unknown settings section.", "Section de paramètres inconnue", "Onbekende instellingensectie"),
    ("Locale", "Langue et région", "Taal en regio"),
    ("Calendar", "Calendrier", "Kalender"),
    ("Unit name", "Nom de l'unité", "Naam van de eenheid"),
    ("Short name", "Nom court", "Korte naam"),
    ("Federation", "Fédération", "Federatie"),
    ("Public contact email", "contact public", "contact-e-mailadres"),
    ("Reply-to address", "Adresse de réponse", "Antwoordadres"),
    ("Privacy policy", "confidentialité", "Privacybeleid"),
    ("Phone country", "Pays des téléphones", "Land van telefoonnummers"),
    ("Currency", "Devise", "Munteenheid"),
    ("Enabled languages", "Langues actives", "Actieve talen"),
    ("Signature campaigns", "Campagnes de signatures", "Handtekeningcampagnes"),
    ("Automatic", "Automatique", "Automatisch"),
    ("Manual", "Manuel", "Handmatig"),
    (
        "Enter a three-letter currency code, e.g. EUR.",
        "trois lettres",
        "drie letters",
    ),
    (
        "%(region)s is not a country code phone numbers can be parsed for.",
        "code pays",
        "landcode",
    ),
    # Section passage: the staff page and the flags it raises.
    ("Section passage", "Passage de section", "Overgang van afdeling"),
    ("Run the passage now", "Lancer le passage", "overgang uitvoeren"),
    ("Waiting for a decision", "attente d'une décision", "Wacht op een beslissing"),
    ("Nobody is waiting for a decision.", "Personne", "Niemand"),
    ("To review", "examiner", "bekijken"),
    (
        "The passage did not run: there is no coming school year yet.",
        "année scolaire à venir",
        "komende scoutjaar",
    ),
    (
        "Passage done: %(promoted)s placed, %(graduated)s graduated, "
        "%(flagged)s waiting for a decision.",
        "Passage effectué",
        "Overgang uitgevoerd",
    ),
    ("No section fits — choose one", "Aucune section", "Geen enkele sectie"),
    (
        "The branch has no next branch set",
        "branche suivante",
        "volgende afdeling",
    ),
    (
        "Leaving the last branch — decide what comes next",
        "dernière branche",
        "laatste afdeling",
    ),
    (
        "Members who leave the last branch become animators. Turn this off to "
        "be asked about each of them instead.",
        "deviennent animateurs",
        "worden animator",
    ),
    (
        "The section passage is waiting for a decision: %(reason)s",
        "attend une décision",
        "wacht op een beslissing",
    ),
    # Branding: the logo and favicon uploads on the settings page.
    (
        "Shown in the site header and in outgoing email. Leave empty to use the "
        "default Les Scouts mark.",
        "en-tête",
        "siteheader",
    ),
    (
        "The small icon browsers show for the site. Leave empty for no icon.",
        "icône",
        "pictogram",
    ),
    # The first-run wizard (members/wizard/): its own chrome, the structure
    # editor and the steps, which a host reads before the site exists.
    ("Set up this instance", "Installer cette instance", "Deze instantie instellen"),
    (
        "A few questions, and your unit's site is ready. Everything here can "
        "be changed later.",
        "Quelques questions",
        "Een paar vragen",
    ),
    ("Setup code", "Code d'installation", "Installatiecode"),
    (
        "That is not this instance's setup code.",
        "Ce n'est pas le code d'installation",
        "niet de installatiecode",
    ),
    (
        "Too many wrong codes from this address. Try again in %(minutes)s minutes.",
        "Trop de codes erronés",
        "Te veel foute codes",
    ),
    ("Done", "Terminé", "Klaar"),
    ("Where to go next", "La suite", "Wat nu"),
    ("Send and finish", "Envoyer et terminer", "Verzenden en afronden"),
    ("Test email", "E-mail de test", "Test-e-mail"),
    (
        "Your unit's site is ready. You can sign in as <strong>%(admin_email)s</strong> "
        "from now on.",
        "Le site de votre unité est prêt",
        "De site van je eenheid is klaar",
    ),
    (
        "Each branch leads to the one below it, and members who outgrow the "
        "last one leave the unit. A branch's ages are the ages its members "
        "are on the day the unit reads them — 31 December unless you change "
        "it later.",
        "Chaque branche mène",
        "Elke afdeling leidt",
    ),
    ("Both", "Mixte", "Gemengd"),
    ("Boys", "Garçons", "Jongens"),
    ("Girls", "Filles", "Meisjes"),
    ("Youngest", "Le plus jeune", "Jongste"),
    ("Oldest", "Le plus âgé", "Oudste"),
    ("Who it takes", "Qui elle accueille", "Wie erin kan"),
    ("Remove this branch", "Supprimer cette branche", "Deze afdeling verwijderen"),
    ("Remove this section", "Supprimer cette section", "Deze sectie verwijderen"),
    (
        "No branch yet. Add the first one.",
        "Aucune branche",
        "Nog geen afdeling",
    ),
    (
        "%(branch)s needs at least one section.",
        "a besoin d'au moins une section",
        "heeft minstens één sectie nodig",
    ),
    (
        "%(branch)s: every section needs a name.",
        "chaque section a besoin d'un nom",
        "elke sectie heeft een naam nodig",
    ),
    (
        "%(branch)s: the youngest age is above the oldest.",
        "l'âge du plus jeune dépasse",
        "jongste leeftijd is hoger",
    ),
    (
        "Branch %(number)s needs a name.",
        "La branche %(number)s a besoin d'un nom",
        "Afdeling %(number)s heeft een naam nodig",
    ),
    ("A unit needs at least one branch.", "au moins une branche", "minstens één afdeling"),
    (
        "The password for this account. Make it a long one.",
        "Choisissez-le long",
        "Kies er een lang",
    ),
    (
        "An account with this address already exists. Use a different "
        "address, or sign in with that one.",
        "Un compte existe déjà",
        "Er bestaat al een account",
    ),
    (
        "That account already existed; kept it.",
        "Ce compte existait déjà",
        "Dat account bestond al",
    ),
    (
        "The administrator account is missing. Go back and create it.",
        "Revenez en arrière",
        "Ga terug om het aan te maken",
    ),
    (
        "The mail backend reported that it sent nothing.",
        "n'avoir rien envoyé",
        "niets verzonden te hebben",
    ),
    (
        "Check EMAIL_URL (or MAIL_SEND_MODE) and DEFAULT_FROM_EMAIL in this "
        "instance's environment.",
        "Vérifiez EMAIL_URL",
        "Controleer EMAIL_URL",
    ),
    ("Test message from %(site)s", "Message de test de", "Testbericht van"),
    (
        "The addresses come from this instance's environment "
        "(DEFAULT_FROM_EMAIL, and the administrator you created a moment "
        "ago); they are not editable here.",
        "Ces adresses viennent",
        "Deze adressen komen",
    ),
    (
        "This sends a test message to your administrator's address and waits "
        "for the mail server's answer. If it arrives, everything the site "
        "sends will arrive too.",
        "Un message de test part",
        "Er gaat een testbericht",
    ),
    ("Saved when you go on.", "Enregistré quand vous", "Opgeslagen wanneer je"),
    (
        "add members one by one, or send families to the registration page "
        "and they will fill in their own.",
        "ajoutez les membres",
        "voeg leden één voor één toe",
    ),
    (
        "the unit's name, its contact details, the languages it offers and "
        "the shape of its scout year.",
        "le nom de l'unité, ses coordonnées",
        "de naam van de eenheid, haar contactgegevens",
    ),
    (
        "where branches, sections and everything else the wizard did not ask "
        "about are edited.",
        "où se modifient les branches",
        "waar afdelingen, secties",
    ),
    (
        "A unit that is moving from another system has a one-off importer "
        "for the old site's database; it is a script run on the server, "
        "described in the repository's contrib/legacy-import/README.md.",
        "importateur ponctuel",
        "eenmalige importeur",
    ),
    ("Removed: %(rows)s.", "Supprimé :", "Verwijderd:"),
    (
        "Stable identifier from a branch preset, used to recognise this "
        "branch again when the preset is applied a second time.",
        "Identifiant stable",
        "Stabiele identificatie",
    ),
    # Section agenda, added with members.SectionEvent.
    ("Meeting", "Réunion", "Vergadering"),
    ("Special day", "Journée spéciale", "Speciale dag"),
    # "Week-end" is deliberately absent: French uses the English word, so the
    # "translated differs from source" half of this test cannot hold for it.
    # Its Dutch msgstr ("Weekend") is in the catalog all the same.
    ("Activity type", "Type d'activité", "Soort activiteit"),
    ("Start date", "Date de début", "Startdatum"),
    ("Start time", "Heure de début", "Starttijd"),
    ("End date", "Date de fin", "Einddatum"),
    ("End time", "Heure de fin", "Eindtijd"),
    (
        "Leave empty for an activity that lasts a single day.",
        "Laissez vide",
        "Laat leeg",
    ),
    (
        "The end date cannot be before the start date.",
        "ne peut pas précéder",
        "kan niet vóór",
    ),
    (
        "The end time cannot be before the start time.",
        "ne peut pas précéder",
        "kan niet vóór",
    ),
    (
        "The activity has been added to the agenda.",
        "ajoutée à l'agenda",
        "toegevoegd aan de agenda",
    ),
    ("The activity has been updated.", "mise à jour", "bijgewerkt"),
    (
        "The activity has been removed from the agenda.",
        "retirée de l'agenda",
        "verwijderd uit de agenda",
    ),
    (
        "What this section is doing, week by week.",
        "semaine après semaine",
        "week na week",
    ),
    (
        "Pick a day to see what is on.",
        "Choisissez un jour",
        "Kies een dag",
    ),
    (
        "You are not linked to any section this year.",
        "aucune section cette année",
        "geen enkele sectie gekoppeld",
    ),
    ("Previous month", "Mois précédent", "Vorige maand"),
    ("Next month", "Mois suivant", "Volgende maand"),
    ("Today", "Aujourd'hui", "Vandaag"),
    ("Add an activity", "Ajouter une activité", "Activiteit toevoegen"),
    ("Nothing planned that day.", "Rien de prévu", "Niets gepland"),
    ("Edit activity", "Modifier l'activité", "Activiteit bewerken"),
    ("New activity", "Nouvelle activité", "Nieuwe activiteit"),
    ("Delete", "Supprimer", "Verwijderen"),
    (
        "Optional, for a message sent to a section: the activity is added "
        "to that section's agenda.",
        "ajoutée à l'agenda de cette section",
        "toegevoegd aan de agenda van die sectie",
    ),
    # Households and their fee adjustments, added with the billing override.
    ("Household", "Foyer", "Huishouden"),
    ("Inferred from the address", "adresse", "adres"),
    (
        "Negative writes off, positive adds to what the household owes",
        "remise",
        "kwijtschelding",
    ),
    ("Billed by address again", "facturé par adresse", "per adres"),
    (
        "Deleting the household does not touch its members: they go back to "
        "being billed by address. Its adjustment lines are deleted with it.",
        "ajustements",
        "aanpassingen",
    ),
    (
        "Household “%(name)s” deleted. Its members are billed by address again.",
        "supprimé",
        "verwijderd",
    ),
    # A section's own address, edited in the Django admin.
    (
        "Where answers to this section's messages should go. Empty uses the "
        "unit's reply-to address.",
        "Laisser vide",
        "Laat leeg",
    ),
    # Reporting a child absent from a future activity.
    ("Report an absence", "Signaler une absence", "afwezigheid melden"),
    (
        "The absence has been reported to the section.",
        "signalée à la section",
        "gemeld aan de sectie",
    ),
    ("The absence has been withdrawn.", "retirée", "ingetrokken"),
    # Member import and export, added with the shared column format.
    ("Import and export", "Importer et exporter", "Importeren en exporteren"),
    ("Export", "Exporter", "Exporteren"),
    ("Members", "Membres", "Leden"),
    ("Columns", "Colonnes", "Kolommen"),
    ("Column", "Colonne", "Kolom"),
    ("Line", "Ligne", "Regel"),
    ("Remark", "Remarque", "Opmerking"),
    ("What this file would do", "Ce que ce fichier ferait", "Wat dit bestand zou doen"),
    ("Import this file", "Importer ce fichier", "Dit bestand importeren"),
    ("Preview the import", "Aperçu de l'import", "Voorbeeld van de import"),
    ("Members file", "Fichier des membres", "Bestand met leden"),
    (
        "Payments file (optional)",
        "Fichier des paiements (facultatif)",
        "Bestand met betalingen (optioneel)",
    ),
    ("Template:", "Modèle :", "Sjabloon:"),
    (
        "Bring members in from a spreadsheet, or take the whole troop out as "
        "one. Both directions use the same columns.",
        "Faites entrer des membres",
        "Haal leden binnen",
    ),
    (
        "Every member, one row each, with the year's balances and the payments "
        "recorded for them.",
        "Tous les membres",
        "Alle leden",
    ),
    (
        "Read-only: the export writes it, the import ignores it.",
        "Lecture seule",
        "Alleen-lezen",
    ),
    # The columns the format adds beyond the ones the member form already had.
    ("External ID", "Identifiant externe", "Externe id"),
    (
        "Parent external IDs",
        "Identifiants externes des parents",
        "Externe ids van de ouders",
    ),
    ("Section this year", "Section cette année", "Sectie dit jaar"),
    ("Section next year", "Section l'année suivante", "Sectie volgend jaar"),
    # What each column accepts, the legend beside the upload form.
    ("A date, e.g. 2020-05-04 or 04/05/2020.", "Une date, par ex.", "Een datum, bv."),
    ("M for a boy, F for a girl.", "pour un garçon", "voor een jongen"),
    ("yes or no.", "oui ou non", "ja of nee"),
    ("An amount, e.g. 12.50.", "Un montant", "Een bedrag"),
    (
        "A role's short code, or its name.",
        "Le code court d'un rôle",
        "De korte code van een rol",
    ),
    (
        "A section name, or branch:name when two sections share one.",
        "branche:nom",
        "tak:naam",
    ),
    ("Separate several values with a semicolon.", "point-virgule", "puntkomma"),
    ("a (active), ar (archived) or r (requested).", "archivé", "gearchiveerd"),
    (
        "The year the school year starts in, e.g. 2025.",
        "L'année de début",
        "Het jaar waarin het schooljaar begint",
    ),
    # What the preview and the import report.
    (
        "No row has anything to report.",
        "Aucune ligne n'a de remarque",
        "Geen enkele rij heeft iets te melden",
    ),
    (
        "A row with an error is not imported, and nothing is written while "
        "one is left. Fix the file and upload it again.",
        "Corrigez le fichier",
        "Verbeter het bestand",
    ),
    (
        "Download the template, fill it in, then upload it here. Nothing is "
        "written until you have read the preview. No email is sent to the "
        "members it creates.",
        "Aucun e-mail n'est envoyé",
        "geen e-mail verstuurd",
    ),
    ("The file is empty.", "fichier est vide", "bestand is leeg"),
    (
        "The file could not be read. Upload a CSV or an XLSX file.",
        "n'a pas pu être lu",
        "kon niet worden gelezen",
    ),
    ("Nothing was imported.", "Rien n'a été importé", "Er is niets geïmporteerd"),
    (
        "Nothing was imported: the file has errors.",
        "le fichier contient des erreurs",
        "het bestand bevat fouten",
    ),
    ("Choose a file to import.", "Choisissez un fichier", "Kies een bestand"),
    (
        "The upload has expired; choose the file again.",
        "téléversement a expiré",
        "upload is verlopen",
    ),
    (
        "%(created)s members created, %(updated)s updated, %(payments)s "
        "payments recorded.",
        "paiements enregistrés",
        "betalingen geregistreerd",
    ),
    # What a row is told when a cell will not do.
    ("%(column)s is required.", "est obligatoire", "is verplicht"),
    (
        "%(column)s is required for a participant.",
        "obligatoire pour un animé",
        "verplicht voor een deelnemer",
    ),
    ("Expected M or F.", "M ou F est attendu", "M of F wordt verwacht"),
    (
        "Expected a date, e.g. 2020-05-04 or 04/05/2020.",
        "Une date est attendue",
        "Een datum wordt verwacht",
    ),
    (
        "Column “%(name)s” is not part of the format and is ignored.",
        "ne fait pas partie du format",
        "maakt geen deel uit",
    ),
    (
        "Two rows name “%(name)s”. Check whether they are the same person.",
        "Vérifiez s'il s'agit",
        "Controleer of het om dezelfde persoon",
    ),
    ("Another member is already called “%(name)s”.", "porte déjà le nom", "heet al"),
    ("No section named “%(name)s”.", "Aucune section ne porte", "Geen enkele sectie heet"),
    (
        "External ID “%(value)s” appears on more than one row.",
        "apparaît sur plusieurs lignes",
        "komt op meer dan één rij",
    ),
    (
        "%(column)s: no member with external ID “%(value)s”.",
        "aucun membre avec l'identifiant externe",
        "geen lid met externe id",
    ),
]


class NewStringTranslationTest(SimpleTestCase):
    def test_translated_in_french(self):
        with translation.override("fr"):
            for source, fragment, _nl in NEW_STRINGS:
                with self.subTest(source=source):
                    translated = gettext(source)
                    self.assertNotEqual(
                        translated, source, f"no French translation for {source!r}"
                    )
                    self.assertIn(fragment, translated)

    def test_translated_in_dutch(self):
        with translation.override("nl"):
            for source, _fr, fragment in NEW_STRINGS:
                with self.subTest(source=source):
                    translated = gettext(source)
                    self.assertNotEqual(
                        translated, source, f"no Dutch translation for {source!r}"
                    )
                    self.assertIn(fragment, translated)
