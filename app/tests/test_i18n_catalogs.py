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
    ("Public agenda", "Agenda public", "Openbare agenda"),
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
