"""A whole troop's worth of demo data, in French.

``create_test_data`` seeds the handful of accounts the Playwright suite drives.
This seeds a *troop*: four sections with children and leaders in them, seven
families, an agenda, a mailbox, a fee grid, a few documents and the unit's own
settings — enough that a development instance can be clicked through the way
the site is really used, instead of read as a list of fixtures.

Three rules run through it:

* **French.** Names, notes, activities, message bodies and the unit's settings
  are written the way a French-speaking Belgian unit writes them, because that
  is what the demo is meant to read like.
* **Fill, never overwrite** — the rule ``members.setup`` follows, for the same
  reason. A member, message or activity already there is left exactly as it is;
  a second run adds only what the first did not. Members carry a ``DEMO-``
  external id, the field an import matches on, which is what makes them
  recognisable again on the next run.
* **Nothing leaves.** No account is created through a path that notifies
  anyone, no message is sent (``sent_at`` stays null), no attendance is
  reported, and the unit's reply-to address is deliberately left empty — so an
  absence notice has no address to travel to (see
  ``members.absences.section_recipients``). Every demo address sits under the
  reserved ``.test`` TLD, which no resolver will deliver to.

The roster is data at the top of this file rather than rows in a fixture: it is
read against the *troop's own* ladder and school year, which a fixture cannot
know.
"""

import hashlib
import unicodedata
from datetime import date, time, timedelta
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.signals import post_save
from django.utils import timezone

from finance.models import (
    CotisationConfig,
    FeeRule,
    Household,
    HouseholdAdjustment,
    HouseholdMember,
    Payment,
    calculate_balances,
)
from members import setup as troop_setup
from members.models import (
    Absence,
    Account,
    Branch,
    Enrollment,
    ImportantDocument,
    ParentChild,
    Person,
    PersonRole,
    Role,
    SchoolYear,
    Section,
    SectionEvent,
    TroopSettings,
)
from members.signals import notify_admins_on_profile_save
from messaging.models import MessageAttachment, SectionMessage, SectionMessageRecipient

#: Every demo login shares this password.
PASSWORD = "Demo1234!"

#: Reserved TLD (RFC 2606): nothing resolves it, so a demo address cannot reach
#: a real inbox even if something does end up sending.
EMAIL_DOMAIN = "demo.test"

#: Prefix on every member's ``external_id``. That field is the one an import
#: matches on, which makes it the natural answer to "did I already write this
#: person?" on a second run — and it is honest about where these rows came from.
DEMO_ID = "DEMO-"

# The age each section of the demo is built around. A section is found by age
# rather than by name, so the roster lands on whatever ladder the troop has: a
# unit whose sections are called "Meute Saint-Michel" and "Troupe 1ère Wavre"
# still gets its children enrolled in the right place.
AGE_BALADINS = 7
AGE_LOUVETEAUX = 10
AGE_ECLAIREURS = 13
AGE_PIONNIERS = 17

#: Section slug -> the age its members are written at.
SECTION_AGES = {
    "baladins": AGE_BALADINS,
    "louveteaux": AGE_LOUVETEAUX,
    "eclaireurs": AGE_ECLAIREURS,
    "pionniers": AGE_PIONNIERS,
}

#: The unit's own settings. Translated fields are written to French only: the
#: other languages fall back to it (MODELTRANSLATION_FALLBACK_LANGUAGES), which
#: is exactly what a unit that works in French alone would see.
UNIT = {
    "name": "Scouts de Limal",
    "short_name": "Scouts Limal",
    "federation": "Les Scouts — Fédération des scouts Baden-Powell de Belgique",
    "contact_email": f"contact@{EMAIL_DOMAIN}",
    "contact_phone": "010 41 12 34",
    "footer_address": "Local Saint-Martin\nRue de la Station 4\n1300 Wavre",
    "privacy_policy": (
        "Les Scouts ASBL traite vos données pour la gestion des membres de "
        f"l'unité. Écrivez à contact@{EMAIL_DOMAIN} pour exercer vos droits "
        "d'accès et de rectification."
    ),
    "site_description": (
        "Site officiel des Scouts de Limal : inscriptions, agendas de section "
        "et vie de l'unité."
    ),
    "site_keywords": "scouts limal wavre baladins louveteaux éclaireurs pionniers",
    "email_signature": "Salutations cordiales,\nLe staff d'unité des Scouts de Limal",
    "registration_message": (
        "Les inscriptions pour l'année scoute sont ouvertes. Bienvenue chez les "
        "Scouts de Limal !"
    ),
    "photo_consent_text": (
        "J'accepte que les photos et vidéos prises pendant les activités soient "
        "utilisées par Les Scouts ASBL, dont mon unité fait partie."
    ),
    "address_placeholder": "Ex : Rue de la Station 4, 1300 Wavre",
    "facebook_url": "https://www.facebook.com/lesscouts",
    "instagram_url": "https://www.instagram.com/lesscouts",
}

#: ``TroopSettings`` fields modeltranslation keeps a column per language for.
UNIT_TRANSLATED = frozenset(
    {
        "name",
        "site_description",
        "site_keywords",
        "email_signature",
        "registration_message",
        "photo_consent_text",
        "address_placeholder",
    }
)

#: The staff. ``leads`` names the section its animateur is enrolled in — which
#: is what makes them that section's leader on the agenda, see
#: ``members.permissions.can_edit_section_agenda``. ``staff`` opens the Django
#: admin; the roles are what open the unit's own staff pages.
STAFF = [
    {
        "key": "amelie-gerard",
        "first": "Amélie",
        "last": "Gérard",
        "address": "Rue du Bassin 8, 1300 Wavre",
        "sex": "F",
        "age": 31,
        "month": 1,
        "day": 27,
        "phone": "+32 495 12 34 56",
        "primary": "am",
        "secondary": ["ar"],
        "staff": True,
        "note": "Chef d'unité",
    },
    {
        "key": "claire-delvaux",
        "first": "Claire",
        "last": "Delvaux",
        "address": "Place Cardinal Mercier 3, 1300 Wavre",
        "sex": "F",
        "age": 24,
        "month": 5,
        "day": 12,
        "phone": "+32 476 21 07 43",
        "primary": "a",
        "leads": "louveteaux",
        "note": "Animatrice responsable de la meute",
    },
    {
        "key": "thomas-renard",
        "first": "Thomas",
        "last": "Renard",
        "address": "Rue de Bruxelles 41, 1300 Wavre",
        "sex": "M",
        "age": 27,
        "month": 9,
        "day": 3,
        "phone": "+32 474 55 90 18",
        "primary": "a",
        "leads": "eclaireurs",
        "note": "Animateur responsable de la troupe",
    },
    {
        "key": "sophie-marchal",
        "first": "Sophie",
        "last": "Marchal",
        "address": "Avenue des Combattants 17, 1300 Wavre",
        "sex": "F",
        "age": 22,
        "month": 11,
        "day": 8,
        "phone": "+32 478 33 61 29",
        "primary": "a",
        "leads": "baladins",
        "note": "Animatrice des baladins",
    },
    {
        "key": "julien-lambert",
        "first": "Julien",
        "last": "Lambert",
        "address": "Rue Sainte-Anne 22, 1300 Wavre",
        "sex": "M",
        "age": 25,
        "month": 3,
        "day": 19,
        "phone": "+32 473 77 44 52",
        "primary": "am",
        "secondary": ["t"],
        "note": "Trésorier de l'équipe d'unité",
    },
]

#: The site's own administrator, kept apart from the staff because the demo
#: wants one login that opens everything, the Django admin included.
SUPERADMIN = {
    "key": "camille-bourgeois",
    "first": "Camille",
    "last": "Bourgeois",
    "address": "Rue des Mésanges 6, 1301 Bierges",
        "sex": "F",
    "age": 34,
    "month": 10,
    "day": 12,
    "phone": "+32 498 30 21 09",
    "primary": "am",
    "note": "Administratrice du site",
}

#: The families. Every member of one shares an address, which is what the fees
#: module infers a household from — see ``finance.models.household_groups``.
FAMILIES = [
    {
        "name": "Dubois",
        "address": "Rue des Tilleuls 12, 1300 Wavre",
        "parents": [
            {
                "key": "nicolas-dubois",
                "first": "Nicolas",
                "sex": "M",
                "age": 42,
                "month": 7,
                "day": 2,
                "phone": "+32 475 21 43 87",
                "primary": "p",
                "account": True,
            },
            {
                "key": "celine-dubois",
                "first": "Céline",
                "sex": "F",
                "age": 40,
                "month": 4,
                "day": 23,
                "phone": "+32 476 88 12 04",
                "primary": "p",
                "account": True,
            },
        ],
        "children": [
            {
                "key": "lea-dubois",
                "first": "Léa",
                "sex": "F",
                "section": "louveteaux",
                "month": 3,
                "day": 14,
                "totem": "Hibou silencieux",
                "account": True,
            },
            {
                "key": "maxime-dubois",
                "first": "Maxime",
                "sex": "M",
                "section": "baladins",
                "month": 6,
                "day": 30,
                "totem": "Écureuil vif",
            },
        ],
    },
    {
        "name": "Moreau",
        "address": "Avenue du Parc 34, 1340 Ottignies",
        "parents": [
            {
                "key": "antoine-moreau",
                "first": "Antoine",
                "sex": "M",
                "age": 45,
                "month": 2,
                "day": 11,
                "phone": "+32 479 14 25 36",
                "primary": "p",
                "secondary": ["ri"],
                "note": "Responsable des inscriptions",
                "account": True,
            }
        ],
        "children": [
            {
                "key": "chloe-moreau",
                "first": "Chloé",
                "sex": "F",
                "section": "eclaireurs",
                "month": 8,
                "day": 5,
                "totem": "Biche rapide",
                "account": True,
            },
            {
                "key": "hugo-moreau",
                "first": "Hugo",
                "sex": "M",
                "section": "louveteaux",
                "month": 10,
                "day": 17,
                "totem": "Castor patient",
            },
        ],
    },
    {
        "name": "Simon",
        "address": "Chaussée de Namur 78, 1300 Wavre",
        "parents": [
            {
                "key": "veronique-simon",
                "first": "Véronique",
                "sex": "F",
                "age": 38,
                "month": 12,
                "day": 6,
                "phone": "+32 472 68 39 70",
                "primary": "p",
                "account": True,
            }
        ],
        "children": [
            {
                "key": "lucas-simon",
                "first": "Lucas",
                "sex": "M",
                "section": "baladins",
                "month": 5,
                "day": 21,
                "totem": "Loutre curieuse",
            }
        ],
    },
    {
        "name": "Petit",
        "address": "Rue du Moulin 5, 1325 Chaumont-Gistoux",
        "parents": [
            {
                "key": "marc-petit",
                "first": "Marc",
                "sex": "M",
                "age": 43,
                "month": 9,
                "day": 28,
                "phone": "+32 471 90 55 13",
                "primary": "p",
                "secondary": ["pa"],
                "note": "Parent volontaire pour les transports",
                "account": True,
            }
        ],
        "children": [
            {
                "key": "emma-petit",
                "first": "Emma",
                "sex": "F",
                "section": "louveteaux",
                "month": 1,
                "day": 9,
                "totem": "Chouette attentive",
            },
            {
                "key": "nathan-petit",
                "first": "Nathan",
                "sex": "M",
                "section": "eclaireurs",
                "month": 4,
                "day": 2,
                "totem": "Sanglier vaillant",
                "account": True,
            },
            {
                "key": "zoe-petit",
                "first": "Zoé",
                "sex": "F",
                "section": "baladins",
                "month": 11,
                "day": 25,
                "totem": "Mésange rieuse",
            },
        ],
    },
    {
        "name": "Lejeune",
        "address": "Chemin des Écoliers 21, 1300 Wavre",
        "parents": [
            {
                "key": "sandrine-lejeune",
                "first": "Sandrine",
                "sex": "F",
                "age": 47,
                "month": 6,
                "day": 15,
                "phone": "+32 477 02 71 84",
                "primary": "p",
                "secondary": ["ri"],
                "note": "Responsable inscriptions",
                "account": True,
            }
        ],
        "children": [
            {
                "key": "alice-lejeune",
                "first": "Alice",
                "sex": "F",
                "section": "pionniers",
                "month": 2,
                "day": 18,
                "totem": "Faucon hardi",
                "account": True,
            }
        ],
    },
]

#: Six activities per section, one per meeting the agenda lays out — three
#: behind today and three ahead of it, so both halves of the calendar hold
#: something whichever day this is run on.
AGENDA = {
    "baladins": {
        "meetings": [
            "Réunion — Jeux de connaissance au local",
            "Réunion — Dans la peau d'un explorateur",
            "Réunion — Bricolage : notre drapeau",
            "Réunion — Grand jeu : les quatre coins",
            "Réunion — Préparation du spectacle",
            "Réunion — Chants et veillée",
        ],
        "day": (
            "Journée — Balade en forêt de Meerdael",
            "Notre première journée de l'année : prévoyez des bottines et un "
            "pique-nique.",
        ),
        "weekend": None,
    },
    "louveteaux": {
        "meetings": [
            "Réunion — Le Livre de la Jungle",
            "Réunion — La piste des sens",
            "Réunion — Construction d'un radeau",
            "Réunion — Grand jeu : Akela nous appelle",
            "Réunion — Cuisine au feu de bois",
            "Réunion — Préparation du week-end",
        ],
        "day": (
            "Journée — Rallye dans Wavre",
            "Un rallye par équipes dans les rues de Wavre, avec les parents à "
            "l'arrivée.",
        ),
        "weekend": (
            "Week-end — La meute s'installe à Profondeville",
            "Départ le samedi matin du local, retour le dimanche à 16h. Sac à "
            "dos, duvet et pique-nique du samedi midi.",
        ),
    },
    "eclaireurs": {
        "meetings": [
            "Réunion — Taille du bois et nœuds",
            "Réunion — Le projet de troupe",
            "Réunion — Lecture de carte et boussole",
            "Réunion — Construction du camp",
            "Réunion — Topographie et orientation",
            "Réunion — Préparation du bivouac",
        ],
        "day": (
            "Journée — Escalade à Beez",
            "Sortie escalade encadrée. Prévoyez une gourde et des chaussures "
            "fermées.",
        ),
        "weekend": (
            "Week-end — Bivouac à Villers-la-Ville",
            "Bivouac sous tente avec cuisine au feu. Le détail du matériel se "
            "trouve dans le message de la troupe.",
        ),
    },
    "pionniers": {
        "meetings": [
            "Réunion — Le projet de l'année",
            "Réunion — Budget et logistique du camp",
            "Réunion — Rencontre avec le staff d'unité",
            "Réunion — Préparation du camp d'été",
            "Réunion — Randonnée préparatoire",
            "Réunion — Solidarité internationale",
        ],
        "day": (
            "Journée — Randonnée des 20 km",
            "Une grande marche en autonomie, par équipes de quatre.",
        ),
        "weekend": None,
    },
}

#: Weeks the meetings sit on, relative to the coming Saturday: three behind
#: today and three ahead, which is all "a section's agenda this half of the
#: year" has to be for the calendar to be worth clicking through.
MEETING_WEEKS = (-3, -2, -1, 0, 1, 2)

#: (section slug, child, reporting parent, reason). The child and the parent
#: are roster keys; the absence goes on that section's next activity.
ABSENCES = [
    (
        "louveteaux",
        "hugo-moreau",
        "antoine-moreau",
        "Week-end chez ses grands-parents à Namur.",
    ),
    (
        "louveteaux",
        "emma-petit",
        "marc-petit",
        "Enrhumée, elle garde la chambre ce samedi.",
    ),
    (
        "baladins",
        "lucas-simon",
        "veronique-simon",
        "Anniversaire de son cousin à Tournai.",
    ),
]

#: Titles and text of the documents the unit keeps for its members.
DOCUMENTS = [
    (
        "Règlement de l'unité",
        "Les règles de vie votées par le conseil d'unité, à lire avec vos enfants.",
    ),
    (
        "Calendrier de l'année scoute",
        "Toutes les activités de l'unité, section par section.",
    ),
    (
        "Fiche médicale",
        "À compléter et à remettre à l'animateur responsable de votre section "
        "avant la première activité.",
    ),
    (
        "Autorisation de sortie",
        "Le document à signer pour les activités qui se déroulent en dehors du local.",
    ),
]

#: What is in the week-end's bag, as the meute's message carries it.
PACKING_LIST = (
    "Liste du matériel — week-end de la meute\n"
    "\n"
    "- Sac à dos\n"
    "- Duvet et drap de sac\n"
    "- Vêtements chauds (une tenue de rechange)\n"
    "- Bottines\n"
    "- Gourde d'un litre\n"
    "- Pique-nique du samedi midi\n"
    "- Brosse à dents et gant de toilette\n"
    "- K-way\n"
)


def _slug(text):
    """``text`` as an email local part: lower-case, accents dropped.

    Django's email validator accepts an ASCII local part only, so "Élodie" has
    to become "elodie" before it can be a login at all.
    """
    folded = unicodedata.normalize("NFKD", text)
    return "".join(char for char in folded if char.isascii() and char.isalnum()).lower()


class Command(BaseCommand):
    help = "Fills a development database with a complete French-speaking troop."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even when the instance is not in DEBUG.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to write demo members: this instance is not in DEBUG. "
                "These are fake people, and a troop that ran this on its own site "
                "would have to unpick two dozen of them by hand. Re-run with "
                "--force if that is really what you want."
            )

        self.created = []
        self.kept = []
        self.warnings = []
        self.people = {}
        self.sections = {}
        self.logins = []
        self.event_count = 0
        self.message_count = 0
        self.payment_count = 0

        # The settings row is cached under a key that names no database, so a
        # server pointed at another one has a copy waiting to be served here.
        # Everything below is read from that row — the values this fills in,
        # and the calendar it turns the roster's ages into birthdays against —
        # so it has to be the row this database actually holds.
        TroopSettings.clear_cache()

        # Creating a member normally mails the registration admins. Seeding a
        # demo is not a registration, so the receiver is out of the way for the
        # length of the run — and put back afterwards, which matters because
        # this can run inside a long-lived process rather than a batch.
        post_save.disconnect(notify_admins_on_profile_save, sender=Person)
        try:
            with transaction.atomic():
                self._foundations()
                self._fill_unit_settings()
                self._add_staff()
                self._add_superadmin()
                self._add_families()
                self._add_leftovers()
                self._add_agenda()
                self._add_absences()
                self._add_messages()
                self._add_fees()
                self._add_documents()
        finally:
            post_save.connect(notify_admins_on_profile_save, sender=Person)

        self._report()

    # --- the pieces --------------------------------------------------------

    def _foundations(self):
        """The things a troop needs before anybody can belong to it.

        The school year comes from ``members.setup`` rather than from here, so
        a seeded instance and one a year of Celery ticks kept running agree on
        where the year boundary is. The ladder is applied only where there is
        none at all: a troop that already chose its sections keeps them, and
        the roster is placed on them by age.
        """
        troop_setup.ensure_school_years()
        self.year = SchoolYear.current()
        if self.year is None:
            raise CommandError(
                "No school year covers today. Run `manage.py setup` first, or "
                "check the unit's year-start settings."
            )

        self.troop = TroopSettings.get_settings()

        if not Branch.objects.exists():
            troop_setup.apply_preset()

        for slug, age in SECTION_AGES.items():
            section = self._section_for(age, None) or self._section_for(age, "M")
            if section is None:
                self.warnings.append(
                    f"no branch takes a {age}-year-old — the {slug} members were "
                    f"left without a section"
                )
            else:
                self.sections[slug] = section

    def _fill_unit_settings(self):
        """The unit's own settings, in French.

        Handed to ``members.setup.fill_settings`` rather than written here, so
        the rule is the one the setup wizard already follows: a value the troop
        chose is kept, and only the blanks and the model's own defaults are
        filled in.
        """
        values = {
            name: {"fr": value} if name in UNIT_TRANSLATED else value
            for name, value in UNIT.items()
        }
        self._record("settings", troop_setup.fill_settings(values))

        # The reply-to address is deliberately not among them: it is what an
        # absence notice falls back to when a section has no address of its own
        # (members.absences.section_recipients), and a demo must not mail.

        self._record("email templates", troop_setup.ensure_email_templates())
        self._record("site pages", troop_setup.ensure_site_pages())

    def _add_staff(self):
        for spec in STAFF:
            person = self._member(spec)
            self._give_login(
                person, is_staff=spec.get("staff", False), role=spec.get("note") or "animateur"
            )
            section = self.sections.get(spec.get("leads"))
            if section is not None:
                self._enroll(person, section)

    def _add_superadmin(self):
        person = self._member(SUPERADMIN)
        self._give_login(
            person, is_staff=True, is_superuser=True, role="accès à tout, admin Django"
        )

    def _add_families(self):
        for family in FAMILIES:
            address = family["address"]
            parents = [
                self._member(
                    spec, last=family["name"], address=address, primary="p"
                )
                for spec in family["parents"]
            ]
            for spec in family["parents"]:
                person = self.people[spec["key"]]
                if spec.get("account"):
                    self._give_login(person, role=f"parent — famille {family['name']}")

            for spec in family["children"]:
                # A child's age is their section's, not a number written beside
                # their name: the roster says "a Louveteau", and the ladder says
                # how old that is this year.
                child = self._member(
                    spec,
                    last=family["name"],
                    address=address,
                    primary="e",
                    age=SECTION_AGES[spec["section"]],
                )
                if spec.get("account"):
                    self._give_login(child, role="animé — compte personnel")

                section = self.sections.get(spec["section"])
                if section is None:
                    continue
                self._enroll(child, section)
                for parent in parents:
                    ParentChild.objects.get_or_create(parent=parent, child=child)

    def _add_leftovers(self):
        """The two members a troop always has besides the enrolled ones.

        Somebody archived two seasons ago, whose record the retention task is
        counting down, and a registration that has come in but not been
        validated yet — the two states the member list is read *for*.
        """
        leaver = self._member(
            {
                "key": "paul-vandenberghe",
                "first": "Paul",
                "last": "Vandenberghe",
                "sex": "M",
                "age": 19,
                "month": 8,
                "day": 21,
                "address": "Rue Haute 3, 1300 Wavre",
                "primary": "e",
                "status": "ar",
                "note": "A quitté l'unité après son année chez les pionniers.",
            }
        )
        if leaver.archived_date is None:
            leaver.archived_date = timezone.localdate() - timedelta(days=400)
            leaver.save(update_fields=["archived_date"])

        newcomer = self._member(
            {
                "key": "ines-foucher",
                "first": "Inès",
                "last": "Foucher",
                "sex": "F",
                "age": AGE_BALADINS,
                "month": 3,
                "day": 7,
                "address": "Rue du Try 16, 1300 Wavre",
                "primary": "n",
                "status": "r",
                "note": "Inscription reçue, en attente de validation.",
            }
        )
        parent = self._member(
            {
                "key": "elodie-foucher",
                "first": "Élodie",
                "last": "Foucher",
                "sex": "F",
                "age": 35,
                "month": 7,
                "day": 4,
                "address": "Rue du Try 16, 1300 Wavre",
                "phone": "+32 470 63 12 88",
                "primary": "p",
            }
        )
        self._give_login(parent, role="parent — inscription en attente")
        ParentChild.objects.get_or_create(parent=parent, child=newcomer)

    def _add_agenda(self):
        """A meeting a week per section, a day out and a week-end.

        Anchored on the coming Saturday rather than on fixed dates, so the
        agenda still has a past and a future whenever this is run.
        """
        today = timezone.localdate()
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)

        for slug, plan in AGENDA.items():
            section = self.sections.get(slug)
            if section is None:
                continue

            for weeks, title in zip(MEETING_WEEKS, plan["meetings"], strict=True):
                self._event(
                    section,
                    SectionEvent.ActivityType.REUNION,
                    title,
                    saturday + timedelta(weeks=weeks),
                    time(14, 0),
                    time(17, 0),
                )

            if plan["day"]:
                title, description = plan["day"]
                self._event(
                    section,
                    SectionEvent.ActivityType.JOURNEE,
                    title,
                    saturday + timedelta(weeks=3, days=1),
                    time(10, 0),
                    time(16, 30),
                    description=description,
                )

            if plan["weekend"]:
                title, description = plan["weekend"]
                start = saturday + timedelta(weeks=4)
                self._event(
                    section,
                    SectionEvent.ActivityType.WEEKEND,
                    title,
                    start,
                    time(10, 0),
                    time(16, 0),
                    end_date=start + timedelta(days=1),
                    description=description,
                )

    def _add_absences(self):
        today = timezone.localdate()
        for slug, child_key, reporter_key, reason in ABSENCES:
            section = self.sections.get(slug)
            child = self.people.get(child_key)
            if section is None or child is None:
                continue

            event = (
                SectionEvent.objects.filter(section=section, start_date__gte=today)
                .order_by("start_date", "start_time")
                .first()
            )
            if event is None:
                continue

            Absence.objects.get_or_create(
                event=event,
                child=child,
                defaults={
                    "reported_by": self.people.get(reporter_key),
                    "reason": reason,
                },
            )

    def _add_messages(self):
        """Three messages: one for the unit, two from a section's leaders.

        The meute's week-end message is left unsent, which is what a leader who
        composed a message and closed the tab leaves behind — and what makes
        the history page show something other than a full column.
        """
        author = self.people.get("amelie-gerard")
        if author is not None:
            self.message_count += self._message(
                author=author,
                section=None,
                subject="Rentrée scoute : les informations pratiques",
                body=(
                    "Bonjour à toutes et tous,\n\n"
                    "L'année scoute redémarre et nous sommes heureux de vous "
                    "retrouver. Quelques informations pratiques pour commencer :"
                    "\n\n"
                    "- Les réunions reprennent ce samedi à 14h au local.\n"
                    "- Les cotisations sont à régler pour la fin du mois ; le "
                    "détail se trouve sur votre page de membre.\n"
                    "- Les fiches médicales de cette année doivent nous revenir "
                    "avant la première activité.\n\n"
                    "N'hésitez pas à répondre à ce message si vous avez la "
                    "moindre question.\n\n"
                    "À samedi,\n"
                    "Le staff d'unité"
                ),
                recipients=list(
                    Person.objects.filter(primary_role__short="p", status="a").distinct()
                ),
                sent=True,
            )

        meute = self.sections.get("louveteaux")
        author = self.people.get("claire-delvaux")
        if meute is not None and author is not None:
            self.message_count += self._message(
                author=author,
                section=meute,
                subject="La meute part en week-end à Profondeville",
                body=(
                    "Chers parents,\n\n"
                    "Le grand week-end de la meute approche ! Nous partirons du "
                    "local le samedi matin à 10h et nous rentrerons le dimanche "
                    "à 16h.\n\n"
                    "Ce qu'il faut dans le sac : un duvet, un drap de sac, des "
                    "vêtements chauds, des bottines, une gourde et un pique-nique "
                    "pour le samedi midi. La liste complète est en pièce jointe."
                    "\n\n"
                    "Merci de nous confirmer la présence de votre enfant avant "
                    "vendredi.\n\n"
                    "Claire, animatrice responsable de la meute"
                ),
                recipients=self._section_recipients(meute),
                sent=False,
                attachment=("liste-materiel-profondeville.txt", PACKING_LIST),
            )

        troupe = self.sections.get("eclaireurs")
        author = self.people.get("thomas-renard")
        if troupe is not None and author is not None:
            self.message_count += self._message(
                author=author,
                section=troupe,
                subject="Matériel pour le bivouac de Villers-la-Ville",
                body=(
                    "Bonjour à tous,\n\n"
                    "Le bivouac approche. Chaque équipe emporte son matériel de "
                    "cuisine et de couchage ; le matériel de construction reste au "
                    "local et sera chargé dans la remorque.\n\n"
                    "Pensez à vérifier vos tentes ce samedi : une toile percée se "
                    "répare au local, pas sur le terrain.\n\n"
                    "Thomas"
                ),
                recipients=self._section_recipients(troupe),
                sent=True,
            )

    def _add_fees(self):
        """The year's fee grid, five settled members and two families that owe.

        The grid is the *flat* method — one price per rank, whatever the branch
        — which is the shape ``FeeRule`` documents first. One family is named as
        a household and carries a manual adjustment, so the treasurer's tools
        have something other than the inferred grouping to show, and two
        families are left owing, so the reminder has somebody to chase.
        """
        config, _ = CotisationConfig.objects.get_or_create(school_year=self.year)
        if config.late_deadline is None:
            config.late_deadline = date(self.year.name, 9, 30)
            config.late_penalty_percent = Decimal("10.00")
            config.save()

        for rank, amount in ((1, "70.00"), (2, "65.00"), (3, "60.00")):
            self._fee_rule(FeeRule.MemberType.CHILD, rank, amount)
            self._fee_rule(FeeRule.MemberType.ANIMATOR, rank, "35.00")

        treasurer = self.people.get("julien-lambert")

        pets = [self.people.get(key) for key in ("emma-petit", "nathan-petit", "zoe-petit")]
        if all(pets):
            household, _ = Household.objects.get_or_create(name="Famille Petit")
            for child in pets:
                HouseholdMember.objects.get_or_create(household=household, person=child)
            HouseholdAdjustment.objects.get_or_create(
                household=household,
                school_year=self.year,
                reason="Geste commercial — inscription tardive des deux aînés",
                defaults={"amount": Decimal("-20.00"), "author": treasurer},
            )

        # What each member owes, as the fees module itself computes it — so the
        # payments below settle the families meant to be settled even if the
        # grid above is repriced later.
        dues = {
            row["person_id"]: row["amount_due"]
            for row in calculate_balances(self.year)
        }

        # The leaders pay the reduced animator fee and have paid it; three
        # families are up to date. The Simons and the Petits are not.
        for key in (
            "amelie-gerard",
            "claire-delvaux",
            "thomas-renard",
            "sophie-marchal",
            "julien-lambert",
            "lea-dubois",
            "maxime-dubois",
            "chloe-moreau",
            "hugo-moreau",
            "alice-lejeune",
        ):
            person = self.people.get(key)
            due = dues.get(person.pk) if person is not None else None
            if due:
                self._pay(person, due, "Cotisation — virement reçu", treasurer)

    def _add_documents(self):
        for title, description in DOCUMENTS:
            _, created = ImportantDocument.objects.get_or_create(
                title_fr=title,
                defaults={"description": description, "url": "https://www.lesscouts.be/"},
            )
            if created:
                self.created.append(f"document « {title} »")

    # --- helpers -----------------------------------------------------------

    def _member(self, spec, **overrides):
        """The person ``spec`` describes, created once and found by its key after.

        Read off ``spec``: ``key``, ``first``, ``last``, ``sex``, ``primary``,
        ``age``, ``month``, ``day``, ``phone``, ``secondary``, ``status``,
        ``totem``, ``note``, ``photo_consent``. Anything else in there —
        ``leads``, ``staff``, ``account``, ``section`` — belongs to the caller,
        which is why they are not read here.

        ``overrides`` are the values the caller knows and the roster does not: a
        child's family name, the address the household is inferred from.

        ``age`` is the age the member is written at, turned into a birthday
        against the school year's own age reference day — so a Louveteau is a
        Louveteau in October and still one in June.
        """
        key = spec["key"]
        external_id = f"{DEMO_ID}{key}"

        existing = Person.objects.filter(external_id=external_id).first()
        if existing is not None:
            self.people[key] = existing
            self.kept.append(str(existing))
            return existing

        values = {
            "first": spec["first"],
            "last": spec.get("last"),
            "sex": spec.get("sex"),
            "primary": spec.get("primary"),
            "age": spec.get("age"),
            "month": spec.get("month", 1),
            "day": spec.get("day", 1),
            "address": spec.get("address", ""),
            "phone": spec.get("phone", ""),
            "totem": spec.get("totem", ""),
            "note": spec.get("note", ""),
            "status": spec.get("status", "a"),
            "secondary": spec.get("secondary", ()),
            "photo_consent": spec.get("photo_consent", False),
        }
        values.update(overrides)

        age = values["age"]
        person = Person(
            external_id=external_id,
            first_name=values["first"],
            last_name=values["last"],
            sex=values["sex"],
            birthday=(
                self._birthday(age, values["month"], values["day"])
                if age is not None
                else None
            ),
            address=values["address"] or None,
            phone=values["phone"] or None,
            totem=values["totem"] or None,
            note=values["note"],
            photo_consent=values["photo_consent"],
            primary_role=self._role(values["primary"]),
            status=values["status"],
        )
        # Validated before it is written, so the demo can no more create a
        # participant without a birthday than a form could.
        person.full_clean()
        person.save()

        for short in values["secondary"]:
            PersonRole.objects.get_or_create(person=person, role=self._role(short))

        self.people[key] = person
        self.created.append(str(person))
        return person

    def _give_login(self, person, *, is_staff=False, is_superuser=False, role=""):
        """Give ``person`` a login, and return the address it uses.

        The address is derived from the name rather than listed beside it, so a
        name the roster changes carries its login with it. It is marked verified
        because allauth refuses a login until it is, and nobody is going to
        click a link in an inbox that does not exist.
        """
        email = f"{_slug(person.first_name)}.{_slug(person.last_name)}@{EMAIL_DOMAIN}"

        account = Account.objects.filter(email=email).first()
        if account is None:
            account = Account(
                person=person,
                email=email,
                is_staff=is_staff,
                is_superuser=is_superuser,
                preferred_language="fr",
            )
            account.set_password(PASSWORD)
            account.save()

        EmailAddress.objects.update_or_create(
            email=email,
            defaults={"user": account, "verified": True, "primary": True},
        )
        self.logins.append((email, role or "membre"))
        return email

    def _role(self, short):
        return Role.objects.get(short=short)

    def _birthday(self, age, month, day):
        """``age`` on the school year's age reference day.

        Measured from that day rather than from today, so every demo member
        keeps the age the roster gives them for the whole school year: nobody
        grows a year older, and outgrows their section, in January.
        """
        reference = self.troop.age_reference_date(self.year)
        return date(reference.year - age, month, day)

    def _section_for(self, age, sex):
        """The section that takes somebody of ``age`` on this troop's ladder.

        Found by age rather than by name, so the roster lands on the sections a
        troop actually has. A branch that declares the age but holds no section
        yet gets one, named after the branch — the alternative is a child the
        troop has nowhere to enrol.
        """
        branch = (
            Branch.objects.filter(
                min_age_dec_31__isnull=False,
                max_age_dec_31__isnull=False,
                min_age_dec_31__lte=age,
                max_age_dec_31__gte=age,
            )
            .order_by("min_age_dec_31")
            .first()
        )
        if branch is None:
            return None

        section = branch.section_for(sex)
        if section is None:
            section = Section.objects.create(
                name_fr=branch.name_fr, branch=branch, sex=Section.Sex.BOTH
            )
            self.created.append(f"section {branch.name_fr}")
        return section

    def _enroll(self, person, section):
        Enrollment.objects.get_or_create(
            user=person, section=section, school_year=self.year
        )

    def _event(
        self,
        section,
        activity_type,
        title,
        start_date,
        start_time,
        end_time,
        end_date=None,
        description="",
    ):
        existing = SectionEvent.objects.filter(
            section=section, title=title, start_date=start_date
        ).first()
        if existing is not None:
            return existing

        event = SectionEvent(
            section=section,
            activity_type=activity_type,
            title=title,
            description=description,
            start_date=start_date,
            start_time=start_time,
            end_time=end_time,
            end_date=end_date,
        )
        event.full_clean()
        event.save()
        self.event_count += 1
        return event

    def _section_recipients(self, section):
        """The section's families, and its own leaders.

        Both, because a message about the week-end goes to the parents who have
        to pack the bag *and* to the animators who did not write it.
        """
        parents = list(
            Person.objects.filter(
                primary_role__short="p",
                status="a",
                children__enrollment__section=section,
                children__enrollment__school_year=self.year,
            ).distinct()
        )
        leaders = Person.objects.filter(
            primary_role__short__in=["a", "ar"],
            status="a",
            enrollment__section=section,
            enrollment__school_year=self.year,
        ).distinct()
        return parents + [leader for leader in leaders if leader not in parents]

    def _message(self, author, section, subject, body, recipients, sent, attachment=None):
        """Write one message; returns 1 when it is new, so the report can count.

        A recipient row is the record of who the message went to, and
        ``sent_at`` is what the history page counts as delivered — so an unsent
        message keeps it null and reads as "composed, not sent".
        """
        message = SectionMessage.objects.filter(
            sender=author, section=section, subject=subject, school_year=self.year
        ).first()
        if message is not None:
            return 0

        message = SectionMessage.objects.create(
            sender=author,
            section=section,
            school_year=self.year,
            subject=subject,
            body=body,
        )
        if attachment is not None:
            self._attach(message, *attachment)

        sent_at = timezone.now() if sent else None
        for recipient in recipients:
            SectionMessageRecipient.objects.get_or_create(
                message=message,
                parent=recipient,
                defaults={"sent_at": sent_at},
            )
        return 1

    def _attach(self, message, name, content):
        """Hang ``content`` off ``message`` as a file, by its own hash.

        The hash is the message module's own deduplication key: the same list
        attached to a second message is the same row, not a second copy on disk.
        """
        payload = content.encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()

        attachment = MessageAttachment.objects.filter(content_hash=digest).first()
        if attachment is None:
            attachment = MessageAttachment(original_name=name, content_hash=digest)
            attachment.file.save(name, ContentFile(payload), save=True)

        message.attachments.add(attachment)

    def _fee_rule(self, member_type, rank, amount):
        FeeRule.objects.get_or_create(
            school_year=self.year,
            branch=None,
            rank=rank,
            member_type=member_type,
            defaults={"amount": Decimal(amount)},
        )

    def _pay(self, person, amount, note, treasurer):
        _, created = Payment.objects.get_or_create(
            person=person,
            school_year=self.year,
            note=note,
            defaults={
                "amount": amount,
                "recorded_by": treasurer,
                "date": timezone.localdate(),
            },
        )
        if created:
            self.payment_count += 1

    def _record(self, label, result):
        for name in result.created:
            self.created.append(f"{label}: {name}")
        for name in result.kept:
            self.kept.append(f"{label}: {name}")

    def _report(self):
        style = self.style
        self.stdout.write(
            style.SUCCESS(
                f"\nScouts de Limal — {len(self.created)} written, "
                f"{len(self.kept)} already there."
            )
        )
        self.stdout.write(
            f"  {len(self.sections)} sections, {self.event_count} activities added, "
            f"{self.message_count} messages, {self.payment_count} payments."
        )

        for warning in self.warnings:
            self.stdout.write(style.WARNING(f"  ! {warning}"))

        self.stdout.write(style.MIGRATE_HEADING(f"\n  Logins (password {PASSWORD}):"))
        for email, role in self.logins:
            self.stdout.write(f"    {email:<36} {role}")
        self.stdout.write(
            "\n  The archived member and the pending registration carry no login.\n"
        )
