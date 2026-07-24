"""Fill msgstr in the generated django.po catalogs from a translation dict.

Idempotent and resumable: always overwrites msgstr from TRANSLATIONS keyed by
the (escaped) msgid text, preserving all comments/flags/references. Re-running
makemessages later merges cleanly; re-running this reapplies the dict.

Run:
    docker compose -f docker-compose-local.yml exec -T web \
        env APPLY_LIST=1 python /app/locale/_apply_translations.py   # list keys
    docker compose -f docker-compose-local.yml exec -T web \
        python /app/locale/_apply_translations.py                    # apply
"""
import os
import re

LOCALE_DIR = os.path.dirname(__file__)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().split("\n")


def _entries(lines):
    out, cur = [], []
    for line in lines:
        if line.strip() == "" and cur:
            out.append(cur)
            cur = []
        else:
            cur.append(line)
    if cur:
        out.append(cur)
    return out


_QUOTED = re.compile(r'"(.*)"$')
_KW = re.compile(r'^(msgid|msgstr) (.*)$')


def _block_value(entry, kw):
    capturing = False
    parts = []
    for line in entry:
        m = _KW.match(line)
        if m and m.group(1) == kw:
            capturing = True
            q = _QUOTED.match(m.group(2))
            if q:
                parts.append(q.group(1))
            continue
        if capturing:
            if line.startswith('"'):
                q = _QUOTED.match(line)
                if q:
                    parts.append(q.group(1))
            else:
                break
    return "".join(parts)


def _escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# msgid text -> (French, Dutch). Key is the .po inner-quote (escaped) form.
TRANSLATIONS = {
    # --- participant (English source; fr=animé, nl=deelnemer) ---
    "Participant": ("Animé", "Deelnemer"),
    "Participants of a section": ("Animés d'une section", "Deelnemers van een sectie"),
    "Only the 'Participant' and 'Animator' roles can be enrolled in a section.": ("Seuls les rôles « Animé » et « Animateur » peuvent être inscrits dans une section.", "Enkel de rollen 'Deelnemer' en 'Animator' kunnen in een sectie worden ingeschreven."),
    "Date of birth (only for participants)": ("Date de naissance (uniquement pour les animé(e)s)", "Geboortedatum (enkel voor deelnemers)"),
    "Sex (only for participants)": ("Sexe (uniquement pour les animé(e)s)", "Geslacht (enkel voor deelnemers)"),
    "Date of birth is required for a participant.": ("La date de naissance est obligatoire pour un animé.", "De geboortedatum is verplicht voor een deelnemer."),
    "Sex is required for a participant.": ("Le sexe est obligatoire pour un animé.", "Het geslacht is verplicht voor een deelnemer."),
    "Everyone of a section (parents, participants and animators)": ("Tout le monde d'une section (parents, animés et animateurs)", "Iedereen van een sectie (ouders, deelnemers en animators)"),
    # --- allauth / email templates (source was French; kept for fr, translated to nl) ---
    "Vous recevez ce mail parce que vous ou quelqu'un d'autre a tenté de créer un compte avec l'adresse e-mail suivante:\\n\\n%(email)s\\n\\nCependant, un compte utilisant cette adresse e-mail existe déjà.  En cas où vous avez oublié votre mot de passe, veuillez utiliser la procédure de mot de passe oublié pour récupérer votre compte.\\n\\n%(password_reset_url)s": (
        "Vous recevez ce mail parce que vous ou quelqu'un d'autre a tenté de créer un compte avec l'adresse e-mail suivante :\n\n%(email)s\n\nCependant, un compte utilisant cette adresse e-mail existe déjà. En cas où vous avez oublié votre mot de passe, veuillez utiliser la procédure de mot de passe oublié pour récupérer votre compte.\n\n%(password_reset_url)s",
        "Je ontvangt deze e-mail omdat jij of iemand anders hebt geprobeerd een account aan te maken met het volgende e-mailadres:\n\n%(email)s\n\nEr bestaat echter al een account met dit e-mailadres. Als je je wachtwoord bent vergeten, gebruik dan de procedure 'wachtwoord vergeten' om je account te herstellen.\n\n%(password_reset_url)s",
    ),
    'Compte déjà existant': ("Compte déjà existant", "Account bestaat al"),
    "Tu reçois ce message parce qu'un de tes parents à choisi de te créer un compte sur le site de l'unité.  \\nPour finaliser l'inscription et choisir un mot de passe, clique sur le lien ci-dessous.\\n\\n%(password_reset_url)s\\nCela peut être ignoré si tu n'as pas demandé de réinitialisation de mot de passe. ": (
        "Tu reçois ce message parce qu'un de tes parents a choisi de te créer un compte sur le site de l'unité.\nPour finaliser l'inscription et choisir un mot de passe, clique sur le lien ci-dessous.\n\n%(password_reset_url)s\nTu peux ignorer ce message si tu n'as pas demandé de réinitialisation de mot de passe.",
        "Je ontvangt dit bericht omdat een van je ouders ervoor heeft gekozen een account voor je aan te maken op de website van de eenheid.\nOm je inschrijving af te ronden en een wachtwoord te kiezen, klik op de onderstaande link.\n\n%(password_reset_url)s\nJe kunt dit negeren als je geen wachtwoordreset hebt aangevraagd.",
    ),
    'Réinitialisation de mot de passe': ("Réinitialisation de mot de passe", "Wachtwoord opnieuw instellen"),
    "Tu a reçu ce message parce qu'un de tes parents à choisi de te créer un compte sur le site de l'unité.  Pour finaliser l'inscription et choisir un mot de passe, clique sur le lien ci-desous.": (
        "Tu as reçu ce message parce qu'un de tes parents a choisi de te créer un compte sur le site de l'unité. Pour finaliser l'inscription et choisir un mot de passe, clique sur le lien ci-dessous.",
        "Je hebt dit bericht ontvangen omdat een van je ouders ervoor heeft gekozen een account voor je aan te maken op de website van de eenheid. Om je inschrijving af te ronden en een wachtwoord te kiezen, klik op de onderstaande link.",
    ),
    'Ton nom d\'utilisateur est \\"%(username)s\\".': ("Ton nom d'utilisateur est « %(username)s ».", 'Je gebruikersnaam is "%(username)s".'),
    "Création d'un compte sur le site de votre unité scoute": ("Création d'un compte sur le site de votre unité scoute", "Een account aanmaken op de website van je scoutseenheid"),
    'Veuillez confirmer votre adresse e-mail': ("Veuillez confirmer votre adresse e-mail", "Bevestig je e-mailadres"),
    "Tu reçois ce message parce qu’un compte a été créé pour toi sur le site de l’unité, ou qu’une réinitialisation de mot de passe a été demandée.\\n\\nPour finaliser l’inscription ou choisir un nouveau mot de passe, clique sur le lien ci-dessous :\\n\\n%(password_reset_url)s\\n\\nSi tu n’es pas à l’origine de cette demande, tu peux simplement ignorer ce message.": (
        "Tu reçois ce message parce qu'un compte a été créé pour toi sur le site de l'unité, ou qu'une réinitialisation de mot de passe a été demandée.\n\nPour finaliser l'inscription ou choisir un nouveau mot de passe, clique sur le lien ci-dessous :\n\n%(password_reset_url)s\n\nSi tu n'es pas à l'origine de cette demande, tu peux simplement ignorer ce message.",
        "Je ontvangt dit bericht omdat er een account voor je is aangemaakt op de website van de eenheid, of omdat een wachtwoordreset is aangevraagd.\n\nOm je inschrijving af te ronden of een nieuw wachtwoord te kiezen, klik op de onderstaande link:\n\n%(password_reset_url)s\n\nAls jij deze aanvraag niet hebt gedaan, kun je dit bericht gewoon negeren.",
    ),
    "Vous recevez ce mail parce que vous ou quelqu'un d'autre a demandé un mot de passe pour votre compte utilisateur.\\nCependant, nous n'avons pas de compte avec l'adresse e-mail %(email)s dans notre base de données.\\n\\nCe mail peut être ignoré si vous n'avez pas demandé de réinitialisation de mot de passe.\\n\\nSi c'était vous, vous pouvez vous inscrire pour un compte en utilisant le lien ci-dessous.": (
        "Vous recevez ce mail parce que vous ou quelqu'un d'autre a demandé un mot de passe pour votre compte utilisateur.\nCependant, nous n'avons pas de compte avec l'adresse e-mail %(email)s dans notre base de données.\n\nCe mail peut être ignoré si vous n'avez pas demandé de réinitialisation de mot de passe.\n\nSi c'était vous, vous pouvez vous inscrire pour un compte en utilisant le lien ci-dessous.",
        "Je ontvangt deze e-mail omdat jij of iemand anders een wachtwoord heeft aangevraagd voor je gebruikersaccount.\nWij hebben echter geen account met het e-mailadres %(email)s in onze database.\n\nJe kunt deze e-mail negeren als je geen wachtwoordreset hebt aangevraagd.\n\nAls jij het was, kun je je inschrijven voor een account via de onderstaande link.",
    ),

    # --- auth / login / password reset / signup ---
    'Confirm email address': ("Confirmer l'adresse e-mail", "E-mailadres bevestigen"),
    'Please confirm that <a href=\\"mailto:%(email)s\\">%(email_addr)s</a> is the email address of %(user_display)s.': (
        'Veuillez confirmer que <a href="mailto:%(email)s">%(email_addr)s</a> est l\'adresse e-mail de %(user_display)s.',
        'Bevestig dat <a href="mailto:%(email)s">%(email_addr)s</a> het e-mailadres is van %(user_display)s.',
    ),
    'Confirm': ("Confirmer", "Bevestigen"),
    'This link is no longer valid. Please <a href=\\"%(email_url)s\\">submit a new email confirmation request</a>.': (
        'Ce lien n\'est plus valide. Veuillez <a href="%(email_url)s">soumettre une nouvelle demande de confirmation</a>.',
        'Deze link is niet meer geldig. <a href="%(email_url)s">Dien een nieuwe bevestigingsaanvraag in</a>.',
    ),
    'Log in': ("Se connecter", "Aanmelden"),
    'Send': ("Envoyer", "Versturen"),
    'Remember me': ("Se souvenir de moi", "Onthoud mij"),
    'Forgot password?': ("Mot de passe oublié ?", "Wachtwoord vergeten?"),
    'Incorrect username or password': ("Nom d'utilisateur ou mot de passe incorrect", "Onjuiste gebruikersnaam of wachtwoord"),
    'Or log in with': ("Ou connectez-vous avec", "Of meld je aan met"),
    'Sign Out': ("Se déconnecter", "Afmelden"),
    'Are you sure you want to sign out?': ("Êtes-vous sûr de vouloir vous déconnecter ?", "Ben je zeker dat je wilt afmelden?"),
    'Change Password': ("Changer de mot de passe", "Wachtwoord wijzigen"),
    'Forgot Password?': ("Mot de passe oublié ?", "Wachtwoord vergeten?"),
    'Password Reset': ("Réinitialisation du mot de passe", "Wachtwoord opnieuw instellen"),
    "Forgotten your password? Enter your e-mail address below, and we'll send you an e-mail allowing you to reset it.": (
        "Mot de passe oublié ? Saisissez votre adresse e-mail ci-dessous et nous vous enverrons un e-mail pour le réinitialiser.",
        "Wachtwoord vergeten? Vul hieronder je e-mailadres in en we sturen je een e-mail om het opnieuw in te stellen.",
    ),
    'Reset My Password': ("Réinitialiser mon mot de passe", "Mijn wachtwoord opnieuw instellen"),
    'Please contact us if you have any trouble resetting your password.': ("Contactez-nous si vous rencontrez des difficultés pour réinitialiser votre mot de passe.", "Neem contact met ons op als je problemen hebt bij het opnieuw instellen van je wachtwoord."),
    "We have sent you an email. If you haven't received it, check your spam folder. Otherwise, contact us if you haven't received it within a few minutes.": (
        "Nous vous avons envoyé un e-mail. Si vous ne l'avez pas reçu, vérifiez vos courriers indésirables. Sinon, contactez-nous si vous ne l'avez pas reçu dans les quelques minutes.",
        "We hebben je een e-mail gestuurd. Heb je deze niet ontvangen, controleer dan je spammap. Neem anders contact met ons op als je hem binnen enkele minuten niet hebt ontvangen.",
    ),
    'Bad Token': ("Jeton invalide", "Ongeldig token"),
    'The password reset link was invalid, possibly because it has already been used.  Please request a <a href=\\"%(passwd_reset_url)s\\">new password reset</a>.': (
        'Le lien de réinitialisation du mot de passe était invalide, peut-être parce qu\'il a déjà été utilisé. Veuillez demander une <a href="%(passwd_reset_url)s">nouvelle réinitialisation</a>.',
        'De link voor het opnieuw instellen van het wachtwoord was ongeldig, mogelijk omdat deze al is gebruikt. Vraag een <a href="%(passwd_reset_url)s">nieuwe wachtwoordreset</a> aan.',
    ),
    'change password': ("changer de mot de passe", "wachtwoord wijzigen"),
    'Your password is now changed.': ("Votre mot de passe a été modifié.", "Je wachtwoord is gewijzigd."),
    'Create your account': ("Créez votre compte", "Maak je account aan"),
    'To request enrollment for one or more children in our unit, a parent must first register on our site by following the procedure below. Then, the parent can add their children to submit an enrollment request.': (
        "Pour demander l'inscription d'un ou plusieurs enfants dans notre unité, un parent doit d'abord s'inscrire sur notre site en suivant la procédure ci-dessous. Ensuite, le parent peut ajouter ses enfants pour soumettre une demande d'inscription.",
        "Om inschrijving aan te vragen voor een of meer kinderen in onze eenheid, moet een ouder zich eerst registreren op onze website via de onderstaande procedure. Daarna kan de ouder zijn/haar kinderen toevoegen om een inschrijvingsaanvraag in te dienen.",
    ),
    'Create your account (for parents and animators only)': ("Créez votre compte (réservé aux parents et animateurs)", "Maak je account aan (enkel voor ouders en animators)"),
    'Messages': ("Messages", "Berichten"),
    'Verify your email address': ("Vérifiez votre adresse e-mail", "Verifieer je e-mailadres"),
    'A verification email has been sent. Follow the link provided to finalize the creation of your account. If you can\'t find the verification email in your main inbox, check your spam and notifications. Contact us at <span style=\\"white-space: nowrap;\\">%(contact_email)s</span> if you don\'t receive a verification email in the next few minutes.': (
        'Un e-mail de vérification a été envoyé. Suivez le lien fourni pour finaliser la création de votre compte. Si vous ne trouvez pas l\'e-mail de vérification dans votre boîte de réception principale, vérifiez vos courriers indésirables et notifications. Contactez-nous à <span style="white-space: nowrap;">%(contact_email)s</span> si vous ne recevez pas d\'e-mail de vérification dans les prochaines minutes.',
        'Er is een verificatie-e-mail verzonden. Volg de link om de aanmaak van je account af te ronden. Als je de verificatie-e-mail niet in je postvak vindt, controleer dan je spam en meldingen. Neem contact met ons op via <span style="white-space: nowrap;">%(contact_email)s</span> als je binnen enkele minuten geen verificatie-e-mail ontvangt.',
    ),

    # --- member list / pagination ---
    'Filter': ("Filtrer", "Filteren"),
    'Reset': ("Réinitialiser", "Resetten"),
    'Actions': ("Actions", "Acties"),
    'Incompatible age: %(detail)s': ("Âge incompatible : %(detail)s", "Incompatibele leeftijd: %(detail)s"),
    'Edit': ("Modifier", "Bewerken"),
    'No results': ("Aucun résultat", "Geen resultaten"),
    'Previous': ("Précédent", "Vorige"),
    'Page %(page_num)s of %(page_count)s': ("Page %(page_num)s sur %(page_count)s", "Pagina %(page_num)s van %(page_count)s"),
    'Next': ("Suivant", "Volgende"),
    'First': ("Premier", "Eerste"),
    'Last': ("Dernier", "Laatste"),
    'Child': ("Enfant", "Kind"),
    'Member': ("Membre", "Lid"),
    'Account type cannot be changed. Reason: %(reason)s.': ("Le type de compte ne peut pas être modifié. Raison : %(reason)s.", "Het accounttype kan niet worden gewijzigd. Reden: %(reason)s."),
    'Parents': ("Parents", "Ouders"),
    'Create an account for %(first_name)s': ("Créer un compte pour %(first_name)s", "Een account aanmaken voor %(first_name)s"),
    "Create an account so your child can access their section's information and edit their own details.": (
        "Créez un compte pour que votre enfant puisse accéder aux informations de sa section et modifier ses propres données.",
        "Maak een account aan zodat je kind de informatie van zijn sectie kan raadplegen en zijn eigen gegevens kan bewerken.",
    ),
    "If they are over 18, they will also be able to detach their account from their parents', who will no longer receive information about them or membership fee reminders.": (
        "S'il a plus de 18 ans, il pourra également détacher son compte de celui de ses parents, qui ne recevront plus d'informations le concernant ni de rappels de cotisation.",
        "Als hij/zij ouder is dan 18, kan hij/zij ook zijn/haar account loskoppelen van dat van de ouders, die dan geen informatie of lidgeldherinneringen meer over hem/haar zullen ontvangen.",
    ),
    "An email will be sent to your child's address with a link. It will allow them to create a password and validate their account.": (
        "Un e-mail sera envoyé à l'adresse de votre enfant avec un lien. Il lui permettra de créer un mot de passe et de valider son compte.",
        "Er wordt een e-mail naar het adres van je kind gestuurd met een link. Hiermee kan het een wachtwoord aanmaken en zijn/haar account valideren.",
    ),
    'Email sent': ("E-mail envoyé", "E-mail verzonden"),
    'An email with a link has been sent to your child. They must click this link to finalize the creation of their account and set a password.': (
        "Un e-mail contenant un lien a été envoyé à votre enfant. Il doit cliquer sur ce lien pour finaliser la création de son compte et définir un mot de passe.",
        "Er is een e-mail met een link naar je kind gestuurd. Het moet op deze link klikken om de aanmaak van zijn/haar account af te ronden en een wachtwoord in te stellen.",
    ),
    'Child information': ("Informations de l'enfant", "Gegevens van het kind"),
    '(optional)': ("(facultatif)", "(optioneel)"),
    "If different from parent's": ("Si différente de celle du parent", "Indien verschillend van de ouder"),
    'The field below should only be filled in if you want to create an account for the child, which is recommended after age 12.': (
        "Le champ ci-dessous ne doit être rempli que si vous souhaitez créer un compte pour l'enfant, ce qui est recommandé à partir de 12 ans.",
        "Onderstaand veld hoeft enkel te worden ingevuld als je een account wilt aanmaken voor het kind, wat wordt aangeraden vanaf 12 jaar.",
    ),
    'They will receive an email to choose a password.': ("Il recevra un e-mail pour choisir un mot de passe.", "Hij/zij ontvangt een e-mail om een wachtwoord te kiezen."),
    'Do not enter your own address.': ("N'indiquez pas votre propre adresse.", "Vul niet je eigen adres in."),
    'To create an account': ("Pour créer un compte", "Een account aanmaken"),
    "Child's secret key": ("Code secret de l'enfant", "Geheime code van het kind"),

    # --- deregister / detach ---
    'Deregister': ("Désinscrire", "Uitschrijven"),
    'Detach': ("Détacher", "Loskoppelen"),
    'Confirm that you want to deregister %(first_name)s': ("Confirmez que vous souhaitez désinscrire %(first_name)s", "Bevestig dat je %(first_name)s wilt uitschrijven"),
    "A deregistration for the following year or for an enrollment in the 'request' state will be processed immediately.": (
        "Une désinscription pour l'année suivante ou pour une inscription dans l'état « request » sera traitée immédiatement.",
        "Een uitschrijving voor het volgende jaar of voor een inschrijving in de status 'request' wordt onmiddellijk verwerkt.",
    ),
    'If the deregistration is requested for the current year and the enrollment is active, it will require manual intervention. Make sure you have followed the procedure described in the internal regulations.': (
        "Si la désinscription est demandée pour l'année en cours et que l'inscription est active, une intervention manuelle sera nécessaire. Assurez-vous d'avoir suivi la procédure décrite dans le règlement intérieur.",
        "Als de uitschrijving wordt aangevraagd voor het lopende jaar en de inschrijving actief is, is een handmatige tussenkomst nodig. Zorg ervoor dat je de procedure uit het huishoudelijk reglement hebt gevolgd.",
    ),
    'The year starts on August 1st, right after camp.': ("L'année commence le 1er août, juste après le camp.", "Het jaar start op 1 augustus, vlak na het kamp."),
    'Deregister %(first_name)s for the current year': ("Désinscrire %(first_name)s pour l'année en cours", "%(first_name)s uitschrijven voor het lopende jaar"),
    'Deregister %(first_name)s for next year': ("Désinscrire %(first_name)s pour l'année suivante", "%(first_name)s uitschrijven voor het volgende jaar"),
    'Confirm that you want to detach %(first_name)s': ("Confirmez que vous souhaitez détacher %(first_name)s", "Bevestig dat je %(first_name)s wilt loskoppelen"),

    # --- documents / onboarding / profile ---
    'Back': ("Retour", "Terug"),
    'Link': ("Lien", "Link"),
    'Download': ("Télécharger", "Downloaden"),
    'No documents available.': ("Aucun document disponible.", "Geen documenten beschikbaar."),
    'Welcome! Complete your profile': ("Bienvenue ! Complétez votre profil", "Welkom! Maak je profiel compleet"),
    'To continue, please complete your profile by filling in the information below.': ("Pour continuer, veuillez compléter votre profil en remplissant les informations ci-dessous.", "Om verder te gaan, maak je profiel compleet door onderstaande gegevens in te vullen."),
    'Continue': ("Continuer", "Doorgaan"),
    'Your profile': ("Votre profil", "Je profiel"),
    'The address is managed by the responsible parent.': ("L'adresse est gérée par le parent responsable.", "Het adres wordt beheerd door de verantwoordelijke ouder."),
    'Change password': ("Changer de mot de passe", "Wachtwoord wijzigen"),
    'To associate an already enrolled <span class=\\"text-ls-bleu-clair\\">child</span>, ask the parent who enrolled the child for the \\"Secret key\\" and click on <span class=\\"text-ls-vert-base\\">Add an existing child with a key</span>.': (
        'Pour associer un <span class="text-ls-bleu-clair">enfant</span> déjà inscrit, demandez le « Code secret » au parent qui a inscrit l\'enfant et cliquez sur <span class="text-ls-vert-base">Ajouter un enfant existant avec un code</span>.',
        'Om een reeds ingeschreven <span class="text-ls-bleu-clair">kind</span> te koppelen, vraag de "Geheime code" aan de ouder die het kind heeft ingeschreven en klik op <span class="text-ls-vert-base">Een bestaand kind toevoegen met een code</span>.',
    ),
    'If a parent no longer wishes to receive emails about an enrolled child, they can <span class=\\"text-ls-orange\\">detach</span> them, provided at least one other parent remains.': (
        'Si un parent ne souhaite plus recevoir d\'e-mails concernant un enfant inscrit, il peut le <span class="text-ls-orange">détacher</span>, à condition qu\'au moins un autre parent reste.',
        'Als een ouder geen e-mails meer wil ontvangen over een ingeschreven kind, kan hij/zij het <span class="text-ls-orange">loskoppelen</span>, op voorwaarde dat er minstens één andere ouder overblijft.',
    ),
    'Copy key': ("Copier le code", "Code kopiëren"),
    'Secret key': ("Code secret", "Geheime code"),
    'Loading...': ("Chargement…", "Laden…"),
    'Add a new child': ("Ajouter un nouvel enfant", "Een nieuw kind toevoegen"),
    'Add an existing child with a key': ("Ajouter un enfant existant avec un code", "Een bestaand kind toevoegen met een code"),
    'Secondary role': ("Rôle secondaire", "Tweede rol"),
    'Complete your registration': ("Complétez votre inscription", "Maak je inschrijving compleet"),
    'You are about to log in with your %(provider_name)s account. Please complete the form below to finalize your registration.': (
        "Vous êtes sur le point de vous connecter avec votre compte %(provider_name)s. Veuillez compléter le formulaire ci-dessous pour finaliser votre inscription.",
        "Je staat op het punt je aan te melden met je %(provider_name)s-account. Vul het onderstaande formulier in om je inschrijving af te ronden.",
    ),

    # --- member views / detach logic ---
    '%(age)s years old — branch %(branch)s: %(min)s-%(max)s years old': ("%(age)s ans — branche %(branch)s : %(min)s-%(max)s ans", "%(age)s jaar — tak %(branch)s: %(min)s-%(max)s jaar"),
    '%(first)s %(last)s added.': ("%(first)s %(last)s ajouté(e).", "%(first)s %(last)s toegevoegd."),
    'Invalid request': ("Requête invalide", "Ongeldig verzoek"),
    '%(first)s modified.': ("%(first)s modifié(e).", "%(first)s gewijzigd."),
    '%(first)s is not attached to your account.': ("%(first)s n'est pas rattaché(e) à votre compte.", "%(first)s is niet gekoppeld aan je account."),
    'You cannot detach %(first)s.\\nTo detach a child, they must either be attached to other parents, or be over 18 years old and have an associated account.\\n%(first)s has %(count)s parent(s)\\n%(first)s was born on %(birthday)s and %(has_account)s.': (
        "Vous ne pouvez pas détacher %(first)s.\nPour détacher un enfant, il doit soit être rattaché à d'autres parents, soit avoir plus de 18 ans et disposer d'un compte.\n%(first)s a %(count)s parent(s)\n%(first)s est né(e) le %(birthday)s et %(has_account)s.",
        "Je kunt %(first)s niet loskoppelen.\nOm een kind los te koppelen, moet het ofwel aan andere ouders gekoppeld zijn, ofwel ouder zijn dan 18 jaar en een account hebben.\n%(first)s heeft %(count)s ouder(s)\n%(first)s is geboren op %(birthday)s en %(has_account)s.",
    ),
    'has an account': ("a un compte", "heeft een account"),
    'does not have an account': ("n'a pas de compte", "heeft geen account"),
    'To confirm that you want to detach %(first)s from your account, click \\"Detach\\".': (
        'Pour confirmer que vous souhaitez détacher %(first)s de votre compte, cliquez sur « Détacher ».',
        'Om te bevestigen dat je %(first)s van je account wilt loskoppelen, klik op "Loskoppelen".',
    ),

    # --- messaging ---
    'Parents of a section': ("Parents d'une section", "Ouders van een sectie"),
    'Animators of a section': ("Animateurs d'une section", "Animators van een sectie"),
    'Animés of a section': ("Animés d'une section", "Animés van een sectie"),
    'Everyone of a section (parents, animés and animators)': ("Tout le monde d'une section (parents, animés et animateurs)", "Iedereen van een sectie (ouders, animés en animators)"),
    'All animators': ("Tous les animateurs", "Alle animators"),
    'Unit council': ("Conseil d'unité", "Eenheidsraad"),
    'Unit staff': ("Staff d'unité", "Eenheidsstaff"),
    'Active parents': ("Parents actifs", "Actieve ouders"),
    'Everyone': ("Tout le monde", "Iedereen"),
    'Message subject': ("Sujet du message", "Onderwerp van het bericht"),
    'Message content': ("Contenu du message", "Inhoud van het bericht"),
    'Attachment (optional)': ("Pièce jointe (facultatif)", "Bijlage (optioneel)"),
    'Date (agenda)': ("Date (agenda)", "Datum (agenda)"),
    'Optional. If provided, an event will be added to the agenda.': ("Facultatif. Si renseigné, un événement sera ajouté à l'agenda.", "Optioneel. Indien opgegeven wordt er een evenement aan de agenda toegevoegd."),
    'All users': ("Tous les utilisateurs", "Alle gebruikers"),
    'sent': ("envoyé", "verzonden"),
    'ignored': ("ignoré", "genegeerd"),
    'Info': ("Info", "Info"),
    'No recipient found.': ("Aucun destinataire trouvé.", "Geen ontvanger gevonden."),
    'Message history': ("Historique des messages", "Berichtengeschiedenis"),
    'Sent messages': ("Messages envoyés", "Verzonden berichten"),
    'Send a message': ("Envoyer un message", "Een bericht versturen"),
    'Sent': ("Envoyé", "Verzonden"),
    'Ignored': ("Ignoré", "Genegeerd"),
    'All members': ("Tous les membres", "Alle leden"),
    'No message sent.': ("Aucun message envoyé.", "Geen bericht verstuurd."),
    'Compose a message': ("Composer un message", "Een bericht opstellen"),
    'Attachments (optional, max 10)': ("Pièces jointes (facultatif, max 10)", "Bijlagen (optioneel, max 10)"),
    'Remove': ("Retirer", "Verwijderen"),
    'Check a document to add its link to the message.': ("Cochez un document pour ajouter son lien au message.", "Vink een document aan om de link ervan aan het bericht toe te voegen."),
    'Load': ("Charger", "Laden"),
    'Select a group and click \\"Load\\" to display recipients.': ('Sélectionnez un groupe et cliquez sur « Charger » pour afficher les destinataires.', 'Selecteer een groep en klik op "Laden" om de ontvangers weer te geven.'),
    'No member found.': ("Aucun membre trouvé.", "Geen lid gevonden."),
    'Message detail': ("Détail du message", "Berichtdetail"),
    'Back to history': ("Retour à l'historique", "Terug naar geschiedenis"),
    'Sender': ("Expéditeur", "Afzender"),
    'Content': ("Contenu", "Inhoud"),
    'Attachments': ("Pièces jointes", "Bijlagen"),
    'Status': ("Statut", "Status"),
    'Sent %(sent_at)s': ("Envoyé %(sent_at)s", "Verzonden %(sent_at)s"),
    'No message.': ("Aucun message.", "Geen bericht."),
    '\\n\\nImportant documents:\\n': ("\n\nDocuments importants :\n", "\n\nBelangrijke documenten:\n"),
    'You are not enrolled in any section this year.': ("Vous n'êtes inscrit(e) dans aucune section cette année.", "Je bent dit jaar in geen enkele sectie ingeschreven."),
    'Message sent to %(count)s recipient(s).': ("Message envoyé à %(count)s destinataire(s).", "Bericht verzonden naar %(count)s ontvanger(s)."),

    # --- navbar / common ---
    'Toggle navigation': ("Basculer la navigation", "Navigatie in-/uitklappen"),
    'Sections': ("Sections", "Secties"),
    'No section': ("Aucune section", "Geen sectie"),
    'Administration': ("Administration", "Beheer"),
    'Member management': ("Gestion des membres", "Ledenbeheer"),
    'Animator tools': ("Outils animateur", "Animator-tools"),
    'Language': ("Langue", "Taal"),
    'Change': ("Modifier", "Wijzigen"),
    'Toggle dropdown': ("Ouvrir le menu déroulant", "Dropdown in-/uitklappen"),
    'My profile': ("Mon profil", "Mijn profiel"),
    'My documents': ("Mes documents", "Mijn documenten"),
    'Log out': ("Se déconnecter", "Afmelden"),
    'Sign up': ("S'inscrire", "Registreren"),


    # --- finance ---
    'Amount (€)': ("Montant (€)", "Bedrag (€)"),
    'Date': ("Date", "Datum"),
    'Note': ("Note", "Opmerking"),
    'Subject': ("Sujet", "Onderwerp"),
    'Membership fee reminder': ("Rappel de cotisation", "Herinnering lidgeld"),
    'Message': ("Message", "Bericht"),
    'Use {prenom} and {solde} as variables.': ("Utilisez {prenom} et {solde} comme variables.", "Gebruik {prenom} en {solde} als variabelen."),
    'Hello {prenom},\\n\\nYour membership fee balance is {solde}€.\\nPlease proceed with the payment.\\n\\nBest regards,\\nThe treasurer': (
        "Bonjour {prenom},\n\nLe solde de votre cotisation est de {solde}€.\nMerci de procéder au paiement.\n\nCordialement,\nLe trésorier",
        "Beste {prenom},\n\nHet openstaande saldo van je lidgeld is {solde}€.\nGelieve de betaling te verrichten.\n\nMet vriendelijke groet,\nDe penningmeester",
    ),
    'Full fee (eldest child)': ("Cotisation complète (enfant aîné)", "Volledig lidgeld (oudste kind)"),
    'Sibling discount (amount deducted per additional brother/sister)': ("Réduction familiale (montant déduit par frère/sœur supplémentaire)", "Gezinskorting (bedrag afgetrokken per extra broer/zus)"),
    'Flat fee for animators/staff': ("Cotisation forfaitaire animateurs/staff", "Forfaitair lidgeld voor animators/staff"),
    'Late penalty as a percentage (e.g. 10.00 for 10%)': ("Pénalité de retard en pourcentage (ex. 10.00 pour 10%)", "Boete voor laatte betaling in procent (bv. 10.00 voor 10%)"),
    'Deadline before the late penalty applies': ("Date limite avant l'application de la pénalité de retard", "Uiterste datum vooraleer de boete wordt toegepast"),
    'Fee configuration': ("Configuration des cotisations", "Instellingen lidgeld"),
    'Fee configurations': ("Configurations des cotisations", "Instellingen lidgelden"),
    'Membership fees %(range)s': ("Cotisations %(range)s", "Lidgelden %(range)s"),
    'Payment': ("Paiement", "Betaling"),
    'Payments': ("Paiements", "Betalingen"),
    'Membership fees': ("Cotisations", "Lidgelden"),
    'Financial management — %(year_range)s': ("Gestion financière — %(year_range)s", "Financieel beheer — %(year_range)s"),
    'Send reminders': ("Envoyer les rappels", "Herinneringen versturen"),
    'Configuration': ("Configuration", "Instellingen"),
    'Full fee': ("Cotisation complète", "Volledig lidgeld"),
    'Sibling discount': ("Réduction familiale", "Gezinskorting"),
    'Animator flat fee': ("Cotisation forfaitaire animateur", "Forfaitair lidgeld animator"),
    'Late penalty': ("Pénalité de retard", "Boete laatte betaling"),
    'Deadline': ("Date limite", "Uiterste datum"),
    'Children (%(count)s)': ("Enfants (%(count)s)", "Kinderen (%(count)s)"),
    'Name': ("Nom", "Naam"),
    'Due': ("À payer", "Te betalen"),
    'Paid': ("Payé", "Betaald"),
    'Balance': ("Solde", "Saldo"),
    'Late': ("En retard", "Te laat"),
    'Action': ("Action", "Actie"),
    'Yes': ("Oui", "Ja"),
    'Pay': ("Payer", "Betalen"),
    'History': ("Historique", "Geschiedenis"),
    'No child enrolled.': ("Aucun enfant inscrit.", "Geen kind ingeschreven."),
    'Animators (%(count)s)': ("Animateurs (%(count)s)", "Animators (%(count)s)"),
    'Payment history — %(person)s': ("Historique des paiements — %(person)s", "Betalingengeschiedenis — %(person)s"),
    'Close': ("Fermer", "Sluiten"),
    'Amount': ("Montant", "Bedrag"),
    'Recorded by': ("Enregistré par", "Geregistreerd door"),
    'No payment recorded.': ("Aucun paiement enregistré.", "Geen betaling geregistreerd."),
    'Record a payment': ("Enregistrer un paiement", "Een betaling registreren"),
    'Treasurer': ("Trésorier", "Penningmeester"),
    'Save': ("Enregistrer", "Opslaan"),
    'Cancel': ("Annuler", "Annuleren"),
    'Membership fee reminders': ("Rappels de cotisation", "Herinneringen lidgeld"),
    '%(counter)s adult with an unpaid balance.': ("%(counter)s adulte avec un solde impayé.", "%(counter)s volwassene met een openstaand saldo."),
    'Send the reminders': ("Envoyer les rappels", "Herinneringen versturen"),
    'Recipients': ("Destinataires", "Ontvangers"),
    'Parent': ("Parent", "Ouder"),
    'Children': ("Enfants", "Kinderen"),
    'No current school year defined.': ("Aucune année scolaire courante définie.", "Geen lopend schooljaar gedefinieerd."),
    'Person not found.': ("Personne introuvable.", "Persoon niet gevonden."),
    'Payment of %(amount)s€ recorded for %(person)s.': ("Paiement de %(amount)s€ enregistré pour %(person)s.", "Betaling van %(amount)s€ geregistreerd voor %(person)s."),
    'Failed to send to %(email)s.': ("Échec d'envoi à %(email)s.", "Verzenden naar %(email)s mislukt."),
    'Reminders sent to %(count)s adult(s).': ("Rappels envoyés à %(count)s adulte(s).", "Herinneringen verstuurd naar %(count)s volwassene(n)."),

    # --- homepage / agenda / FAQ ---
    'Title': ("Titre", "Titel"),
    'Description': ("Description", "Omschrijving"),
    'Section': ("Section", "Sectie"),
    'Agenda': ("Agenda", "Agenda"),
    'Calendar of activities': ("Calendrier des activités", "Activiteitenkalender"),
    'Section: %(section_name)s': ("Section : %(section_name)s", "Sectie: %(section_name)s"),
    'No upcoming event.': ("Aucun événement à venir.", "Geen aankomend evenement."),
    'FAQ': ("FAQ", "FAQ"),
    'Frequently asked questions.': ("Questions fréquemment posées.", "Veelgestelde vragen."),
    'Main Description': ("Description principale", "Hoofdbeschrijving"),
    "Roll on the floor purring your whiskers off intrigued by the shower burrow under covers, and play time, rub face on everything, intently sniff hand, or pelt around the house and up and down stairs chasing phantoms. Attack feet. Damn that dog shake treat bag under the bed drink water out of the faucet for lick butt love to play with owner's hair tie. Swat at dog give attitude.": (
        "Texte de présentation de l'unité. Modifiez-le depuis les paramètres du site pour décrire votre unité, ses sections et ses activités.",
        "Voorstellingstekst van de eenheid. Pas deze aan via de instellingen van de website om je eenheid, zijn secties en zijn activiteiten te beschrijven.",
    ),

    # --- admin / member management ---
    'Personal info': ("Informations personnelles", "Persoonlijke gegevens"),
    'Preferences': ("Préférences", "Voorkeuren"),
    'Permissions': ("Permissions", "Machtigingen"),
    'Languages': ("Langues", "Talen"),
    'Site information': ("Informations du site", "Websitegegevens"),
    'Contact information': ("Coordonnées", "Contactgegevens"),
    'Social media': ("Réseaux sociaux", "Sociale media"),
    'Email settings': ("Paramètres e-mail", "E-mailinstellingen"),
    'Registration settings': ("Paramètres d'inscription", "Inschrijvingsinstellingen"),
    'Customizable text': ("Texte personnalisable", "Aanpasbare tekst"),
    'Animator': ("Animateur", "Animator"),
    'Animé': ("Animé", "Animé"),
    'Email': ("E-mail", "E-mail"),
    'First name': ("Prénom", "Voornaam"),
    'Last name': ("Nom", "Achternaam"),
    'Address': ("Adresse", "Adres"),
    'Phone': ("Téléphone", "Telefoon"),
    'Adult type': ("Type d'adulte", "Type volwassene"),
    'Enable secondary role': ("Activer un rôle secondaire", "Tweede rol inschakelen"),
    'I agree that photos or videos in which my child(ren) appear may be used by Les Scouts ASBL, of which my unit is part': ("J'accepte que les photos ou vidéos dans lesquelles mon/mes enfant(s) apparaît(apparaissent) puissent être utilisées par Les Scouts ASBL, dont mon unité fait partie", "Ik ga ermee akkoord dat foto's of video's waarop mijn kind(eren) staat/staan gebruikt mogen worden door Les Scouts ASBL, waarvan mijn eenheid deel uitmaakt"),
    'Your profile has been updated successfully.': ("Votre profil a été mis à jour avec succès.", "Je profiel is met succes bijgewerkt."),
    'No user found matching this ID.': ("Aucun utilisateur ne correspond à cet identifiant.", "Geen gebruiker gevonden met deze ID."),
    'You do not have permission to view this profile.': ("Vous n'avez pas la permission de consulter ce profil.", "Je hebt geen toestemming om dit profiel te raadplegen."),
    'AdultUserChangeForm can only be used with existing accounts': ("AdultUserChangeForm ne peut être utilisé qu'avec des comptes existants", "AdultUserChangeForm kan enkel gebruikt worden met bestaande accounts"),
    'Account instance is missing required Person relationship': ("L'instance de compte n'a pas la relation Person requise", "Accountinstantie mist de vereiste Person-relatie"),
    'Ascending': ("Croissant", "Oplopend"),
    'Descending': ("Décroissant", "Aflopend"),
    'Ordering': ("Tri", "Sortering"),
    'Birth year': ("Année de naissance", "Geboortejaar"),
    'School year': ("Année scolaire", "Schooljaar"),
    'Role': ("Rôle", "Rol"),
    'All roles': ("Tous les rôles", "Alle rollen"),
    'If an email is provided, an account will be created. Otherwise, the existing account will be used.': ("Si une adresse e-mail est fournie, un compte sera créé. Sinon, le compte existant sera utilisé.", "Als een e-mailadres wordt opgegeven, wordt een account aangemaakt. Anders wordt het bestaande account gebruikt."),
    'Primary role': ("Rôle principal", "Hoofdrol"),
    'Secondary roles': ("Rôles secondaires", "Tweede rollen"),
    'Next section': ("Section suivante", "Volgende sectie"),
    'Section %(range)s': ("Section %(range)s", "Sectie %(range)s"),
    "Only the 'Animé' and 'Animator' roles can be enrolled in a section.": ("Seuls les rôles « Animé » et « Animateur » peuvent être inscrits dans une section.", "Enkel de rollen 'Animé' en 'Animator' kunnen in een sectie worden ingeschreven."),
    'Photos allowed': ("Photos autorisées", "Foto's toegestaan"),
    'Date of birth (only for animé(e)s)': ("Date de naissance (uniquement pour les animé(e)s)", "Geboortedatum (enkel voor animé(e)s)"),
    'Sex (only for animé(e)s)': ("Sexe (uniquement pour les animé(e)s)", "Geslacht (enkel voor animé(e)s)"),
    'Totem': ("Totem", "Totem"),
    'Notes': ("Notes", "Opmerkingen"),
    'Account type': ("Type de compte", "Accounttype"),
    'Active parent, I want to help the unit occasionally': ("Parent actif, je souhaite aider l'unité occasionnellement", "Actieve ouder, ik wil de eenheid af en toe helpen"),
    'If an email is provided, an account will be created for the child.': ("Si une adresse e-mail est fournie, un compte sera créé pour l'enfant.", "Als een e-mailadres wordt opgegeven, wordt er een account aangemaakt voor het kind."),
    'Sex': ("Sexe", "Geslacht"),
    'Date of birth': ("Date de naissance", "Geboortedatum"),
    'This email already exists for another user': ("Cette adresse e-mail existe déjà pour un autre utilisateur", "Dit e-mailadres bestaat al voor een andere gebruiker"),
    'Secret key (6 characters)': ("Code secret (6 caractères)", "Geheime code (6 tekens)"),
    'Boy': ("Garçon", "Jongen"),
    'Girl': ("Fille", "Meisje"),
    'First 6 characters of the UUID — key to link a parent to a child': ("6 premiers caractères de l'UUID — clé pour lier un parent à un enfant", "Eerste 6 tekens van de UUID — code om een ouder aan een kind te koppelen"),
    'Date on which the member was archived': ("Date à laquelle le membre a été archivé", "Datum waarop het lid werd gearchiveerd"),
    'Manual override for passage: section assigned the following year': ("Remplacement manuel pour le passage : section attribuée l'année suivante", "Handmatige overschrijving voor de passage: sectie toegewezen het volgende jaar"),
    'Date of birth is required for an animé.': ("La date de naissance est obligatoire pour un animé.", "De geboortedatum is verplicht voor een animé."),
    'Sex is required for an animé.': ("Le sexe est obligatoire pour un animé.", "Het geslacht is verplicht voor een animé."),
    'Pending': ("En attente", "In behandeling"),
    'linked sections': ("sections liées", "gekoppelde secties"),
    'linked children': ("enfants liés", "gekoppelde kinderen"),
    'Language used for outgoing emails to this user.': ("Langue utilisée pour les e-mails sortants adressés à cet utilisateur.", "Taal voor uitgaande e-mails naar deze gebruiker."),
    'Calendar year from the start of the time period': ("Année civile à partir du début de la période", "Burgerjaar vanaf het begin van de periode"),
    '%(name)s — from %(start)s to %(end)s': ("%(name)s — du %(start)s au %(end)s", "%(name)s — van %(start)s tot %(end)s"),
    'Age of the youngest members of the section on December 31 of the school year': ("Âge des plus jeunes membres de la section au 31 décembre de l'année scolaire", "Leeftijd van de jongste leden van de sectie op 31 december van het schooljaar"),
    'Age of the oldest members of the section on December 31 of the school year': ("Âge des plus âgés des membres de la section au 31 décembre de l'année scolaire", "Leeftijd van de oudste leden van de sectie op 31 december van het schooljaar"),
    '%(name)s (%(min)s-%(max)s years old)': ("%(name)s (%(min)s-%(max)s ans)", "%(name)s (%(min)s-%(max)s jaar)"),
    'Languages available to users in the site language selector.': ("Langues proposées aux utilisateurs dans le sélecteur de langue du site.", "Talen die beschikbaar zijn voor gebruikers in de taalkiezer van de website."),
    'Last school year (the « name » field) for which the automatic passage was executed. Anti-replay: if Celery was stopped on the passage day, the task catches up at the next startup.': ("Dernière année scolaire (champ « name ») pour laquelle le passage automatique a été exécuté. Anti-rejeu : si Celery était arrêté le jour du passage, la tâche se rattrape au prochain démarrage.", "Laatste schooljaar (het veld « name ») waarvoor de automatische passage werd uitgevoerd. Anti-herhaling: als Celery stopte op de dag van de passage, haalt de taal dit in bij de volgende opstart."),
    'Important document': ("Document important", "Belangrijk document"),
    'Important documents': ("Documents importants", "Belangrijke documenten"),

    # --- site settings: language selection ---
    'Available languages': ("Langues disponibles", "Beschikbare talen"),
    'Default language': ("Langue par défaut", "Standaardtaal"),
    'Default language for visitors. Must be one of the available languages.': ("Langue par défaut des visiteurs. Doit faire partie des langues disponibles.", "Standaardtaal voor bezoekers. Moet een van de beschikbare talen zijn."),
    'Select at least one available language.': ("Sélectionnez au moins une langue disponible.", "Selecteer minstens één beschikbare taal."),
    'The default language must be one of the available languages.': ("La langue par défaut doit faire partie des langues disponibles.", "De standaardtaal moet een van de beschikbare talen zijn."),

}


# Plural msgids: key (singular form) -> (fr(sing, plur), nl(sing, plur)).
PLURALS = {
    "%(counter)s adult with an unpaid balance.": (
        ("%(counter)s adulte avec un solde impayé.", "%(counter)s adultes avec un solde impayé."),
        ("%(counter)s volwassene met een openstaand saldo.", "%(counter)s volwassenen met een openstaand saldo."),
    ),
}


def _comment_prefix(entry, stop, include_stop=False):
    """Comment/msgid lines up to `stop`, dropping fuzzy flags and msgmerge's
    `#|` previous-msgid references. Dict translations are authoritative, so a
    fuzzy marker left by a changed msgid would otherwise suppress them at runtime.
    """
    prefix = []
    for ln in entry:
        if ln.startswith(stop):
            if include_stop:
                prefix.append(ln)
            break
        if ln.startswith("#,"):
            flags = [f.strip() for f in ln[2:].split(",") if f.strip() not in ("", "fuzzy")]
            if flags:
                prefix.append("#, " + ", ".join(flags))
            continue
        if ln.startswith("#|"):
            continue
        prefix.append(ln)
    return prefix


def _rewrite(path, lang):
    lines = _read(path)
    entries = _entries(lines)
    updated = []
    missing = []
    for entry in entries:
        key = _block_value(entry, "msgid")
        if key == "":
            new = [ln for ln in entry if not ln.startswith("#, fuzzy")]
            meta = {
                "Language": lang,
                "Language-Team": f"{lang} <{lang}@li.org>",
                "Last-Translator": "TroopConnect <noreply@troop.tomctl.be>",
                "PO-Revision-Date": "2026-07-24 00:00+0200",
                "Content-Type": "text/plain; charset=UTF-8",
            }
            rebuilt = []
            for ln in new:
                if ln.startswith("msgstr "):
                    val = _block_value(new, "msgstr")
                    for k, v in meta.items():
                        val = re.sub(
                            rf'({re.escape(k)}: ).*?(\\n)',
                            rf'\g<1>{v}\g<2>',
                            val,
                        )
                    rebuilt.append(f'msgstr "{val}"')
                else:
                    rebuilt.append(ln)
            updated.append("\n".join(rebuilt))
            continue
        is_plural = any(ln.startswith("msgid_plural") for ln in entry)
        if is_plural:
            if key in PLURALS:
                sing, plur = PLURALS[key][0 if lang == "fr" else 1]
                prefix = _comment_prefix(entry, "msgid_plural", include_stop=True)
                updated.append(
                    "\n".join(prefix)
                    + f'\nmsgstr[0] "{_escape(sing)}"\nmsgstr[1] "{_escape(plur)}"'
                )
            else:
                missing.append(key)
                updated.append("\n".join(entry))
        elif key in TRANSLATIONS:
            val = TRANSLATIONS[key][0 if lang == "fr" else 1]
            prefix = _comment_prefix(entry, "msgstr")
            updated.append("\n".join(prefix) + f'\nmsgstr "{_escape(val)}"')
        else:
            missing.append(key)
            updated.append("\n".join(entry))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(updated) + "\n")
    return missing


if os.environ.get("APPLY_LIST"):
    keys = []
    for lang in ("fr", "nl", "en"):
        p = os.path.join(LOCALE_DIR, lang, "LC_MESSAGES", "django.po")
        for entry in _entries(_read(p)):
            k = _block_value(entry, "msgid")
            if k and k not in keys:
                keys.append(k)
    # Emit a dict skeleton with keys pre-filled (exact escaping); fill values.
    for k in keys:
        print(f"    {k!r}: (\"\", \"\"),")
else:
    miss = {}
    for lang in ("fr", "nl"):
        p = os.path.join(LOCALE_DIR, lang, "LC_MESSAGES", "django.po")
        miss[lang] = _rewrite(p, lang)
    for lang, m in miss.items():
        print(f"[{lang}] untranslated: {len(m)}")
        for k in m:
            print("   ", repr(k))
