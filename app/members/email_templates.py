"""Canonical copy for the emails the application sends on its own behalf.

One place, three languages, because the same text is needed to seed a fresh
database (see migration 0021), to render at send time, and to assert against
the database in tests.

Every one of these speaks for the troop, so none of them names one: they all
refer to ``{{ troop_name }}``. The value comes from the troop's own settings
(``members.TroopSettings.name``, resolved in the recipient's language by
``members.mail``), so this copy stays troop-agnostic.

Variables each template expects:

============================ =========================================
``new_child_staff``          ``first_name``, ``last_name``, ``url``
``new_child_parent``         ``parent``, ``first_name``, ``last_name``
``archive_deletion_warning`` ``person_name``, ``deletion_date``
``deregistration_admin``     ``parent``, ``first_name``, ``last_name``, ``url``
``section_message``          ``sender_name``, ``section_name``, ``subject``, ``body``
============================ =========================================
"""

import re

# The languages a template is seeded in. Anything a caller asks for that is not
# in here is resolved to DEFAULT_LANGUAGE by members.mail.send_templated.
LANGUAGES = ("fr", "nl", "en")
DEFAULT_LANGUAGE = "fr"

# Copy this project seeded before the troop name became a variable, and before
# the site-wide templates stopped naming the product. Used by seed() to tell
# seeded rows apart from rows an administrator has rewritten.
LEGACY_MARKERS = ("Scouts de Limal", "TroopConnect")

# The style the call-to-action button has used since the templates were first
# seeded; kept so the emails look unchanged.
_BUTTON = (
    "background-color: #0d6efd; color: #ffffff; padding: 10px 15px; "
    "text-decoration: none; border-radius: 5px;"
)

TEMPLATES = {
    "new_child_staff": {
        "fr": {
            "subject": (
                "Nouvelle inscription à valider – {{ first_name }} {{ last_name }}"
            ),
            "content": (
                "Bonjour,\n\n"
                "Une nouvelle inscription vient d'être enregistrée sur le site "
                "{{ troop_name }} :\n"
                "{{ first_name }} {{ last_name }}\n\n"
                "Merci de la valider ou de la compléter en cliquant sur le lien "
                "suivant :\n"
                "{{ url }}\n\n"
                "Cordialement,\n"
                "L'équipe d'administration du site {{ troop_name }}"
            ),
            "html_content": (
                "<p>Bonjour,</p>"
                "<p>Une nouvelle inscription vient d'être enregistrée sur le site "
                "<strong>{{ troop_name }}</strong> :</p>"
                "<p><strong>{{ first_name }} {{ last_name }}</strong></p>"
                "<p>Merci de la valider ou de la compléter via le lien suivant :</p>"
                f'<p><a href="{{{{ url }}}}" style="{_BUTTON}">'
                "Valider l'inscription</a></p>"
                "<p>Cordialement,<br>L'équipe d'administration du site "
                "{{ troop_name }}</p>"
            ),
        },
        "nl": {
            "subject": "Nieuwe inschrijving na te kijken – {{ first_name }} {{ last_name }}",
            "content": (
                "Hallo,\n\n"
                "Er is een nieuwe inschrijving geregistreerd op de site van "
                "{{ troop_name }}:\n"
                "{{ first_name }} {{ last_name }}\n\n"
                "Gelieve ze na te kijken of aan te vullen via de volgende link:\n"
                "{{ url }}\n\n"
                "Met vriendelijke groet,\n"
                "Het beheerteam van de site {{ troop_name }}"
            ),
            "html_content": (
                "<p>Hallo,</p>"
                "<p>Er is een nieuwe inschrijving geregistreerd op de site van "
                "<strong>{{ troop_name }}</strong>:</p>"
                "<p><strong>{{ first_name }} {{ last_name }}</strong></p>"
                "<p>Gelieve ze na te kijken of aan te vullen via de volgende link:</p>"
                f'<p><a href="{{{{ url }}}}" style="{_BUTTON}">'
                "Inschrijving nakijken</a></p>"
                "<p>Met vriendelijke groet,<br>Het beheerteam van de site "
                "{{ troop_name }}</p>"
            ),
        },
        "en": {
            "subject": "New registration to review – {{ first_name }} {{ last_name }}",
            "content": (
                "Hello,\n\n"
                "A new registration was just recorded on the {{ troop_name }} site:\n"
                "{{ first_name }} {{ last_name }}\n\n"
                "Please review or complete it using the link below:\n"
                "{{ url }}\n\n"
                "Best regards,\n"
                "The administrators of the {{ troop_name }} site"
            ),
            "html_content": (
                "<p>Hello,</p>"
                "<p>A new registration was just recorded on the "
                "<strong>{{ troop_name }}</strong> site:</p>"
                "<p><strong>{{ first_name }} {{ last_name }}</strong></p>"
                "<p>Please review or complete it using the link below:</p>"
                f'<p><a href="{{{{ url }}}}" style="{_BUTTON}">'
                "Review the registration</a></p>"
                "<p>Best regards,<br>The administrators of the {{ troop_name }} "
                "site</p>"
            ),
        },
    },
    "new_child_parent": {
        "fr": {
            "subject": "Confirmation d'inscription – {{ troop_name }}",
            "content": (
                "Bonjour {{ parent }},\n\n"
                "Nous confirmons la bonne réception de l'inscription de votre "
                "enfant {{ first_name }} {{ last_name }} au sein de notre unité.\n\n"
                "Un membre du staff va examiner l'inscription et prendra contact "
                "avec vous si nécessaire. Vous pouvez consulter et compléter le "
                "dossier depuis votre espace personnel sur le site.\n\n"
                "Cordialement,\n"
                "L'équipe de {{ troop_name }}"
            ),
            "html_content": (
                "<p>Bonjour {{ parent }},</p>"
                "<p>Nous confirmons la bonne réception de l'inscription de votre "
                "enfant <strong>{{ first_name }} {{ last_name }}</strong> au sein "
                "de notre unité.</p>"
                "<p>Un membre du staff va examiner l'inscription et prendra "
                "contact avec vous si nécessaire. Vous pouvez consulter et "
                "compléter le dossier depuis votre espace personnel sur le "
                "site.</p>"
                "<p>Cordialement,<br>L'équipe de {{ troop_name }}</p>"
            ),
        },
        "nl": {
            "subject": "Bevestiging van inschrijving – {{ troop_name }}",
            "content": (
                "Hallo {{ parent }},\n\n"
                "We bevestigen de goede ontvangst van de inschrijving van uw kind "
                "{{ first_name }} {{ last_name }} in onze eenheid.\n\n"
                "Een staflid bekijkt de inschrijving en neemt indien nodig contact "
                "met u op. U kunt het dossier bekijken en aanvullen via uw "
                "persoonlijke ruimte op de site.\n\n"
                "Met vriendelijke groet,\n"
                "Het team van {{ troop_name }}"
            ),
            "html_content": (
                "<p>Hallo {{ parent }},</p>"
                "<p>We bevestigen de goede ontvangst van de inschrijving van uw "
                "kind <strong>{{ first_name }} {{ last_name }}</strong> in onze "
                "eenheid.</p>"
                "<p>Een staflid bekijkt de inschrijving en neemt indien nodig "
                "contact met u op. U kunt het dossier bekijken en aanvullen via uw "
                "persoonlijke ruimte op de site.</p>"
                "<p>Met vriendelijke groet,<br>Het team van {{ troop_name }}</p>"
            ),
        },
        "en": {
            "subject": "Registration confirmation – {{ troop_name }}",
            "content": (
                "Hello {{ parent }},\n\n"
                "We confirm that we have received the registration of your child "
                "{{ first_name }} {{ last_name }} in our unit.\n\n"
                "A member of staff will review the registration and will contact "
                "you if needed. You can view and complete the file from your "
                "account on the site.\n\n"
                "Best regards,\n"
                "The {{ troop_name }} team"
            ),
            "html_content": (
                "<p>Hello {{ parent }},</p>"
                "<p>We confirm that we have received the registration of your "
                "child <strong>{{ first_name }} {{ last_name }}</strong> in our "
                "unit.</p>"
                "<p>A member of staff will review the registration and will "
                "contact you if needed. You can view and complete the file from "
                "your account on the site.</p>"
                "<p>Best regards,<br>The {{ troop_name }} team</p>"
            ),
        },
    },
    "archive_deletion_warning": {
        "fr": {
            "subject": "Suppression imminente de votre compte – {{ troop_name }}",
            "content": (
                "Bonjour,\n\n"
                "Le compte de {{ person_name }} est archivé depuis plus de 4 ans "
                "et 11 mois.\n\n"
                "Conformément à notre politique de conservation des données, ce "
                "compte sera définitivement supprimé le {{ deletion_date }}.\n\n"
                "Si vous souhaitez conserver ce compte, veuillez contacter l'unité "
                "avant cette date.\n\n"
                "Cordialement,\n"
                "{{ troop_name }}"
            ),
            "html_content": (
                "<p>Bonjour,</p>"
                "<p>Le compte de <strong>{{ person_name }}</strong> est archivé "
                "depuis plus de 4 ans et 11 mois.</p>"
                "<p>Conformément à notre politique de conservation des données, ce "
                "compte sera <strong>définitivement supprimé le "
                "{{ deletion_date }}</strong>.</p>"
                "<p>Si vous souhaitez conserver ce compte, veuillez contacter "
                "l'unité avant cette date.</p>"
                "<p>Cordialement,<br>{{ troop_name }}</p>"
            ),
        },
        "nl": {
            "subject": "Uw account wordt binnenkort verwijderd – {{ troop_name }}",
            "content": (
                "Hallo,\n\n"
                "Het account van {{ person_name }} is al meer dan 4 jaar en 11 "
                "maanden gearchiveerd.\n\n"
                "Volgens ons bewaarbeleid wordt dit account definitief verwijderd "
                "op {{ deletion_date }}.\n\n"
                "Wil u dit account behouden, neem dan voor die datum contact op met "
                "de eenheid.\n\n"
                "Met vriendelijke groet,\n"
                "{{ troop_name }}"
            ),
            "html_content": (
                "<p>Hallo,</p>"
                "<p>Het account van <strong>{{ person_name }}</strong> is al meer "
                "dan 4 jaar en 11 maanden gearchiveerd.</p>"
                "<p>Volgens ons bewaarbeleid wordt dit account <strong>definitief "
                "verwijderd op {{ deletion_date }}</strong>.</p>"
                "<p>Wil u dit account behouden, neem dan voor die datum contact op "
                "met de eenheid.</p>"
                "<p>Met vriendelijke groet,<br>{{ troop_name }}</p>"
            ),
        },
        "en": {
            "subject": "Your account will be deleted soon – {{ troop_name }}",
            "content": (
                "Hello,\n\n"
                "The account of {{ person_name }} has been archived for more than "
                "4 years and 11 months.\n\n"
                "In line with our data retention policy, this account will be "
                "permanently deleted on {{ deletion_date }}.\n\n"
                "If you want to keep this account, please contact the unit before "
                "that date.\n\n"
                "Best regards,\n"
                "{{ troop_name }}"
            ),
            "html_content": (
                "<p>Hello,</p>"
                "<p>The account of <strong>{{ person_name }}</strong> has been "
                "archived for more than 4 years and 11 months.</p>"
                "<p>In line with our data retention policy, this account will be "
                "<strong>permanently deleted on {{ deletion_date }}</strong>.</p>"
                "<p>If you want to keep this account, please contact the unit "
                "before that date.</p>"
                "<p>Best regards,<br>{{ troop_name }}</p>"
            ),
        },
    },
    "deregistration_admin": {
        "fr": {
            "subject": "Désinscription à traiter – {{ first_name }} {{ last_name }}",
            "content": (
                "Bonjour,\n\n"
                "{{ parent }} a demandé la désinscription de "
                "{{ first_name }} {{ last_name }} pour l'année scolaire en cours.\n\n"
                "Une désinscription en cours d'année ne peut pas être traitée "
                "automatiquement : le suivi de la cotisation et des attestations "
                "doit être clôturé manuellement. Merci de suivre la procédure "
                "décrite dans le règlement interne.\n\n"
                "Fiche du membre : {{ url }}\n\n"
                "Cordialement,\n"
                "L'équipe d'administration du site {{ troop_name }}"
            ),
            "html_content": (
                "<p>Bonjour,</p>"
                "<p><strong>{{ parent }}</strong> a demandé la désinscription de "
                "<strong>{{ first_name }} {{ last_name }}</strong> pour l'année "
                "scolaire en cours.</p>"
                "<p>Une désinscription en cours d'année ne peut pas être traitée "
                "automatiquement : le suivi de la cotisation et des attestations "
                "doit être clôturé manuellement. Merci de suivre la procédure "
                "décrite dans le règlement interne.</p>"
                f'<p><a href="{{{{ url }}}}" style="{_BUTTON}">'
                "Ouvrir la fiche du membre</a></p>"
                "<p>Cordialement,<br>L'équipe d'administration du site "
                "{{ troop_name }}</p>"
            ),
        },
        "nl": {
            "subject": "Uitschrijving te behandelen – {{ first_name }} {{ last_name }}",
            "content": (
                "Hallo,\n\n"
                "{{ parent }} heeft de uitschrijving aangevraagd van "
                "{{ first_name }} {{ last_name }} voor het lopende schooljaar.\n\n"
                "Een uitschrijving tijdens het jaar kan niet automatisch verwerkt "
                "worden: de opvolging van het lidgeld en de attesten moet "
                "handmatig afgesloten worden. Gelieve de procedure in het "
                "huishoudelijk reglement te volgen.\n\n"
                "Fiche van het lid: {{ url }}\n\n"
                "Met vriendelijke groet,\n"
                "Het beheerteam van de site {{ troop_name }}"
            ),
            "html_content": (
                "<p>Hallo,</p>"
                "<p><strong>{{ parent }}</strong> heeft de uitschrijving "
                "aangevraagd van <strong>{{ first_name }} {{ last_name }}</strong> "
                "voor het lopende schooljaar.</p>"
                "<p>Een uitschrijving tijdens het jaar kan niet automatisch "
                "verwerkt worden: de opvolging van het lidgeld en de attesten "
                "moet handmatig afgesloten worden. Gelieve de procedure in het "
                "huishoudelijk reglement te volgen.</p>"
                f'<p><a href="{{{{ url }}}}" style="{_BUTTON}">'
                "Fiche van het lid openen</a></p>"
                "<p>Met vriendelijke groet,<br>Het beheerteam van de site "
                "{{ troop_name }}</p>"
            ),
        },
        "en": {
            "subject": "Deregistration to process – {{ first_name }} {{ last_name }}",
            "content": (
                "Hello,\n\n"
                "{{ parent }} has asked to deregister "
                "{{ first_name }} {{ last_name }} for the current school year.\n\n"
                "A mid-year deregistration cannot be processed automatically: the "
                "membership fee and the attestations have to be closed by hand. "
                "Please follow the procedure described in the internal "
                "regulations.\n\n"
                "Member record: {{ url }}\n\n"
                "Best regards,\n"
                "The administrators of the {{ troop_name }} site"
            ),
            "html_content": (
                "<p>Hello,</p>"
                "<p><strong>{{ parent }}</strong> has asked to deregister "
                "<strong>{{ first_name }} {{ last_name }}</strong> for the current "
                "school year.</p>"
                "<p>A mid-year deregistration cannot be processed automatically: "
                "the membership fee and the attestations have to be closed by "
                "hand. Please follow the procedure described in the internal "
                "regulations.</p>"
                f'<p><a href="{{{{ url }}}}" style="{_BUTTON}">'
                "Open the member record</a></p>"
                "<p>Best regards,<br>The administrators of the {{ troop_name }} "
                "site</p>"
            ),
        },
    },
    "section_message": {
        "fr": {
            "subject": "{{ subject }}",
            "content": (
                "Message de {{ sender_name }} (Section {{ section_name }})\n\n"
                "{{ body }}\n\n"
                "---\n"
                "Ce message a été envoyé via le site {{ troop_name }}."
            ),
            "html_content": (
                "<p><strong>Message de {{ sender_name }}</strong> "
                "(Section {{ section_name }})</p>"
                "<p>{{ body|linebreaksbr }}</p>"
                "<hr>"
                "<p><small>Ce message a été envoyé via le site "
                "{{ troop_name }}.</small></p>"
            ),
        },
        "nl": {
            "subject": "{{ subject }}",
            "content": (
                "Bericht van {{ sender_name }} ({{ section_name }})\n\n"
                "{{ body }}\n\n"
                "---\n"
                "Dit bericht werd verstuurd via de site {{ troop_name }}."
            ),
            "html_content": (
                "<p><strong>Bericht van {{ sender_name }}</strong> "
                "({{ section_name }})</p>"
                "<p>{{ body|linebreaksbr }}</p>"
                "<hr>"
                "<p><small>Dit bericht werd verstuurd via de site "
                "{{ troop_name }}.</small></p>"
            ),
        },
        "en": {
            "subject": "{{ subject }}",
            "content": (
                "Message from {{ sender_name }} ({{ section_name }})\n\n"
                "{{ body }}\n\n"
                "---\n"
                "This message was sent through the {{ troop_name }} site."
            ),
            "html_content": (
                "<p><strong>Message from {{ sender_name }}</strong> "
                "({{ section_name }})</p>"
                "<p>{{ body|linebreaksbr }}</p>"
                "<hr>"
                "<p><small>This message was sent through the {{ troop_name }} "
                "site.</small></p>"
            ),
        },
    },
}


def rows():
    """Yield ``(name, language, fields)`` for every seeded template row.

    post_office resolves a template by the exact pair ``(name, language)``, so
    every language a caller might ask for needs its own row.
    """
    for name, by_language in TEMPLATES.items():
        for language in LANGUAGES:
            yield name, language, by_language[language]


def _canonical_pairs():
    return {(name, language) for name, language, _ in rows()}


def _looks_seeded(text):
    """Whether ``text`` is copy this project seeded rather than an edit.

    The seeded copy used to name one troop outright, and the site-wide
    templates used to name the product. A row still containing one of those is
    one nobody has rewritten in the admin, so a migration may replace it. The
    check is deliberately conservative: rewriting an administrator's own
    wording would be a silent edit of their content, which is worse than
    leaving an old template in place.
    """
    return any(marker in (text or "") for marker in LEGACY_MARKERS)


def seed(EmailTemplate, force=False):
    """Write the canonical copy into ``EmailTemplate``, replacing what is there.

    Takes the model as an argument so a data migration can pass the historical
    version from ``apps.get_model``.

    By default only rows that still hold copy this project seeded are
    overwritten, so an administrator's own wording survives. That check cannot
    recognise *this* module's copy, though -- once a row holds it, it no longer
    matches :data:`LEGACY_MARKERS` -- so a migration that changes the canonical
    copy must pass ``force=True``, having decided the new copy is what belongs
    there. Without it, such a migration would quietly do nothing on any
    database seeded since this was introduced.
    """
    for name, language, fields in rows():
        existing = EmailTemplate.objects.filter(name=name, language=language).first()

        if existing is None:
            EmailTemplate.objects.create(name=name, language=language, **fields)
            continue

        current = existing.subject + existing.content + existing.html_content
        if force or _looks_seeded(current):
            for field, value in fields.items():
                setattr(existing, field, value)
            existing.save()

    # Rows seeded under a language that is no longer used -- post_office's
    # default "" row, historically -- would otherwise linger and stay reachable
    # by name. Anything rewritten by hand is left where it is.
    canonical = _canonical_pairs()
    for row in EmailTemplate.objects.filter(name__in=TEMPLATES):
        if (row.name, row.language) in canonical:
            continue
        if _looks_seeded(row.subject + row.content + row.html_content):
            row.delete()


def variables_used():
    """Every ``{{ variable }}`` the canonical copy refers to.

    Used by the tests to prove the senders supply everything the templates
    ask for.
    """
    found = set()
    for _, _, fields in rows():
        for value in fields.values():
            found.update(re.findall(r"{{\s*(\w+)", value))
    return found
