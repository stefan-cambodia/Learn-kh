"""Pages du serveur avec comptes : connexion, inscription, premier démarrage, « Mon compte »,
gestion des utilisateurs, suivi d'un apprenant et journal.

Ce module ne fabrique que le contenu HTML (libellés en français, anglais et khmer, comme le
reste du site) ; ``frkh.webapp`` l'habille avec le gabarit commun et décide qui voit quoi.
Aucune valeur saisie par un utilisateur n'est insérée sans échappement.
"""

from __future__ import annotations

import datetime as dt

from .accounts import CLI_ACTOR, EVENT_GROUPS
from .langs import LANG_META
from .render import date_label, esc, multi, num_label
from .textutil import LANGS, format_date, to_khmer_digits

# Libellés : (français, anglais, khmer).
TEXT = {
    # Connexion, inscription, premier démarrage
    "login_title": ("Connexion", "Sign in", "ចូលគណនី"),
    "login_intro": ("Connectez-vous pour retrouver vos leçons et votre progression sur tous vos appareils.",
                    "Sign in to find your lessons and your progress on all your devices.",
                    "ចូលគណនីដើម្បីបន្តមេរៀន និងវឌ្ឍនភាពរបស់អ្នកនៅលើគ្រប់ឧបករណ៍។"),
    "register_title": ("Créer un compte", "Create an account", "បង្កើតគណនី"),
    "register_intro": ("Choisissez un identifiant et un mot de passe : votre progression vous suivra d'un appareil à l'autre.",
                       "Choose a username and a password: your progress will follow you from one device to the next.",
                       "ជ្រើសរើសឈ្មោះគណនី និងពាក្យសម្ងាត់៖ វឌ្ឍនភាពរបស់អ្នកនឹងតាមអ្នកពីឧបករណ៍មួយទៅឧបករណ៍មួយ។"),
    "setup_title": ("Premier démarrage", "First start", "ចាប់ផ្តើមលើកដំបូង"),
    "setup_intro": ("Aucun compte n'existe encore. Créez celui de l'administrateur : le code d'installation est affiché "
                    "dans le terminal où tourne le serveur.",
                    "No account exists yet. Create the administrator's: the setup code is shown in the terminal "
                    "where the server is running.",
                    "មិនទាន់មានគណនីនៅឡើយទេ។ សូមបង្កើតគណនីអ្នកគ្រប់គ្រង៖ លេខកូដដំឡើងបង្ហាញនៅលើអេក្រង់របស់ម៉ាស៊ីនមេ។"),
    "no_account": ("Pas encore de compte ?", "No account yet?", "មិនទាន់មានគណនី?"),
    "link_register": ("Créer un compte", "Create an account", "បង្កើតគណនី"),
    "have_account": ("Déjà un compte ?", "Already have an account?", "មានគណនីហើយ?"),
    "ask_admin": ("Pas de compte ? Demandez-en un à l'administrateur du site.",
                  "No account? Ask the site administrator for one.",
                  "គ្មានគណនី? សូមស្នើសុំពីអ្នកគ្រប់គ្រងគេហទំព័រ។"),
    # Liens à usage unique : invitation, nouveau mot de passe
    "invite_title": ("Invitation", "Invitation", "ការអញ្ជើញ"),
    "invite_intro": ("Vous êtes invité à créer votre compte : choisissez un identifiant et un mot de passe.",
                     "You are invited to create your account: choose a username and a password.",
                     "អ្នកត្រូវបានអញ្ជើញឱ្យបង្កើតគណនី៖ សូមជ្រើសរើសឈ្មោះគណនី និងពាក្យសម្ងាត់។"),
    "reset_title": ("Nouveau mot de passe", "New password", "ពាក្យសម្ងាត់ថ្មី"),
    "reset_intro": ("Choisissez un nouveau mot de passe pour le compte « {login} ».",
                    "Choose a new password for the account “{login}”.",
                    "សូមជ្រើសរើសពាក្យសម្ងាត់ថ្មីសម្រាប់គណនី « {login} »។"),
    "link_invalid_title": ("Lien non valable", "Link not valid", "តំណមិនត្រឹមត្រូវ"),
    "link_signed_in": ("Vous êtes déjà connecté. Déconnectez-vous d'abord pour utiliser ce lien.",
                       "You are already signed in. Sign out first to use this link.",
                       "អ្នកបានចូលគណនីរួចហើយ។ សូមចាកចេញជាមុនសិន ដើម្បីប្រើតំណនេះ។"),
    "b_save_password": ("Enregistrer le mot de passe", "Save password", "រក្សាទុកពាក្យសម្ងាត់"),
    # Champs
    "f_login": ("Identifiant", "Username", "ឈ្មោះគណនី"),
    "f_password": ("Mot de passe", "Password", "ពាក្យសម្ងាត់"),
    "f_password2": ("Confirmer le mot de passe", "Confirm password", "បញ្ជាក់ពាក្យសម្ងាត់"),
    "f_current": ("Mot de passe actuel", "Current password", "ពាក្យសម្ងាត់បច្ចុប្បន្ន"),
    "f_new": ("Nouveau mot de passe", "New password", "ពាក្យសម្ងាត់ថ្មី"),
    "f_name": ("Nom affiché", "Display name", "ឈ្មោះបង្ហាញ"),
    "f_profile": ("Ma langue", "My language", "ភាសារបស់ខ្ញុំ"),
    "f_profile_other": ("Langue de l'apprenant", "Learner's language", "ភាសារបស់អ្នករៀន"),
    "f_role": ("Rôle", "Role", "តួនាទី"),
    "f_code_setup": ("Code d'installation", "Setup code", "លេខកូដដំឡើង"),
    "f_code_invite": ("Code d'invitation", "Invitation code", "លេខកូដអញ្ជើញ"),
    "f_active": ("Compte actif : peut se connecter", "Active account: can sign in", "គណនីសកម្ម៖ អាចចូលបាន"),
    "f_must_change": ("Exiger un nouveau mot de passe à la prochaine connexion",
                      "Require a new password at next sign-in",
                      "តម្រូវឱ្យប្តូរពាក្យសម្ងាត់ពេលចូលលើកក្រោយ"),
    "hint_login": ("3 à 32 caractères : lettres minuscules, chiffres, point, tiret.",
                   "3 to 32 characters: lowercase letters, digits, dot, hyphen.",
                   "៣ ដល់ ៣២ តួ៖ អក្សរឡាតាំងតូច លេខ ចំណុច សញ្ញា -។"),
    "hint_password": ("Au moins {min} caractères.", "At least {min} characters.", "យ៉ាងតិច {min} តួ។"),
    "hint_generate": ("Laissez vide pour obtenir un mot de passe provisoire, à changer à la première connexion.",
                      "Leave empty to get a temporary password, to be changed at first sign-in.",
                      "ទុកទទេដើម្បីទទួលបានពាក្យសម្ងាត់បណ្តោះអាសន្ន ដែលត្រូវប្តូរពេលចូលលើកដំបូង។"),
    # Boutons
    "b_login": ("Se connecter", "Sign in", "ចូល"),
    "b_logout": ("Se déconnecter", "Sign out", "ចាកចេញ"),
    "b_register": ("Créer mon compte", "Create my account", "បង្កើតគណនី"),
    "b_save": ("Enregistrer", "Save", "រក្សាទុក"),
    "b_change_password": ("Changer le mot de passe", "Change password", "ប្តូរពាក្យសម្ងាត់"),
    "b_create": ("Créer le compte", "Create account", "បង្កើតគណនី"),
    "b_edit": ("Modifier", "Edit", "កែប្រែ"),
    "b_delete": ("Supprimer le compte", "Delete account", "លុបគណនី"),
    "b_set_password": ("Définir le mot de passe", "Set password", "កំណត់ពាក្យសម្ងាត់"),
    "b_revoke_others": ("Déconnecter mes autres appareils", "Sign out my other devices", "ចាកចេញពីឧបករណ៍ផ្សេងទៀត"),
    "b_revoke_all": ("Fermer toutes ses sessions", "Close all their sessions", "បិទវគ្គទាំងអស់របស់គណនីនេះ"),
    "b_reset_progress": ("Effacer ma progression", "Erase my progress", "លុបវឌ្ឍនភាពរបស់ខ្ញុំ"),
    "b_back": ("Retour à la liste", "Back to the list", "ត្រឡប់ទៅបញ្ជី"),
    "b_users": ("Gérer les utilisateurs", "Manage users", "គ្រប់គ្រងអ្នកប្រើប្រាស់"),
    # Mon compte
    "account_title": ("Mon compte", "My account", "គណនីរបស់ខ្ញុំ"),
    "card_profile": ("Profil", "Profile", "ព័ត៌មានគណនី"),
    "card_password": ("Mot de passe", "Password", "ពាក្យសម្ងាត់"),
    "card_progress": ("Ma progression", "My progress", "វឌ្ឍនភាពរបស់ខ្ញុំ"),
    "card_devices": ("Appareils connectés", "Signed-in devices", "ឧបករណ៍ដែលបានចូល"),
    "must_change": ("Votre mot de passe est provisoire : choisissez-en un nouveau pour continuer.",
                    "Your password is temporary: choose a new one to continue.",
                    "ពាក្យសម្ងាត់របស់អ្នកជាពាក្យសម្ងាត់បណ្តោះអាសន្ន៖ សូមជ្រើសរើសពាក្យសម្ងាត់ថ្មីដើម្បីបន្ត។"),
    "stat_lessons": ("leçons terminées", "lessons completed", "មេរៀនបានបញ្ចប់"),
    "stat_days": ("jours d'activité", "days of activity", "ថ្ងៃដែលបានរៀន"),
    "stat_cards": ("cartes révisées", "cards reviewed", "កាតបានរំលឹក"),
    "progress_hint": ("La progression est enregistrée sur le serveur : elle suit votre compte sur chaque appareil.",
                      "Progress is saved on the server: it follows your account on every device.",
                      "វឌ្ឍនភាពត្រូវបានរក្សាទុកនៅលើម៉ាស៊ីនមេ ហើយតាមគណនីរបស់អ្នកនៅគ្រប់ឧបករណ៍។"),
    "reset_summary": ("Effacer ma progression…", "Erase my progress…", "លុបវឌ្ឍនភាពរបស់ខ្ញុំ…"),
    "reset_confirm": ("Je veux effacer définitivement mes leçons terminées, mes jours d'activité et mes cartes de révision.",
                      "I want to permanently erase my completed lessons, activity days and review cards.",
                      "ខ្ញុំចង់លុបមេរៀនដែលបានបញ្ចប់ ថ្ងៃដែលបានរៀន និងកាតរំលឹករបស់ខ្ញុំចោលជាស្ថាពរ។"),
    "b_track_detail": ("Voir le détail", "See details", "មើលលម្អិត"),
    # Appareils connectés
    "dev_this": ("cet appareil", "this device", "ឧបករណ៍នេះ"),
    "dev_unknown": ("Appareil inconnu", "Unknown device", "ឧបករណ៍មិនស្គាល់"),
    "dev_seen": ("Dernière activité : {date}", "Last active: {date}", "សកម្មភាពចុងក្រោយ៖ {date}"),
    "dev_since": ("Connecté le {date}", "Signed in on {date}", "បានចូលនៅ {date}"),
    "dev_none": ("Aucune session ouverte.", "No open session.", "គ្មានវគ្គកំពុងបើកទេ។"),
    "b_revoke_one": ("Déconnecter", "Sign out", "ចាកចេញ"),
    "card_recent": ("Activité récente du compte", "Recent account activity", "សកម្មភាពថ្មីៗរបស់គណនី"),
    "recent_none": ("Rien pour l'instant.", "Nothing yet.", "មិនទាន់មានអ្វីទេ។"),
    # Suivi d'un apprenant
    "track_title": ("Progression", "Progress", "វឌ្ឍនភាព"),
    "track_last": ("Dernière activité : {date}", "Last activity: {date}", "សកម្មភាពចុងក្រោយ៖ {date}"),
    "track_never": ("Aucune activité enregistrée.", "No activity recorded.", "មិនទាន់មានសកម្មភាពទេ។"),
    "track_users": ("Apprenants", "Learners", "អ្នករៀន"),
    "stat_streak": ("jours d'affilée", "days in a row", "ថ្ងៃជាប់គ្នា"),
    "stat_best": ("meilleure série", "best streak", "ជាប់គ្នាច្រើនបំផុត"),
    "stat_due": ("cartes à revoir", "cards to review", "កាតត្រូវរំលឹក"),
    "card_lessons": ("Leçons", "Lessons", "មេរៀន"),
    "lessons_done_of": ("Terminées : {done} sur {total}", "Completed: {done} of {total}",
                        "បានបញ្ចប់៖ {done} ក្នុងចំណោម {total}"),
    "lessons_none": ("Aucune leçon publiée pour l'instant.", "No lesson published yet.", "មិនទាន់មានមេរៀននៅឡើយទេ។"),
    "lessons_recent": ("Dernières leçons terminées", "Latest completed lessons", "មេរៀនដែលបានបញ្ចប់ចុងក្រោយ"),
    "lesson_done": ("terminée", "completed", "បានបញ្ចប់"),
    "lesson_todo": ("à faire", "to do", "មិនទាន់រៀន"),
    "card_activity": ("Activité", "Activity", "សកម្មភាព"),
    "activity_summary": ("Jours actifs : {n} sur les {total} derniers", "Active days: {n} of the last {total}",
                         "ថ្ងៃបានរៀន៖ {n} ក្នុងរយៈពេល {total} ថ្ងៃចុងក្រោយ"),
    "legend_active": ("jour actif", "active day", "ថ្ងៃបានរៀន"),
    "legend_idle": ("sans activité", "no activity", "មិនបានរៀន"),
    "card_review": ("Révision", "Review", "ការរំលឹក"),
    "review_none": ("Aucune carte révisée pour l'instant.", "No card reviewed yet.", "មិនទាន់បានរំលឹកកាតណាមួយនៅឡើយទេ។"),
    "review_row": ("Connues : {known} sur {cards} révisées", "Known: {known} of {cards} reviewed",
                   "ចេះ៖ {known} ក្នុងចំណោម {cards} កាតដែលបានរំលឹក"),
    "review_due": ("à revoir : {n}", "to review: {n}", "ត្រូវរំលឹក៖ {n}"),
    "review_hint": ("Une carte est « connue » à partir de la troisième boîte de révision.",
                    "A card counts as “known” from the third review box on.",
                    "កាតមួយរាប់ថា « ចេះ » ចាប់ពីប្រអប់រំលឹកទីបីឡើងទៅ។"),
    # Utilisateurs
    "users_title": ("Utilisateurs", "Users", "អ្នកប្រើប្រាស់"),
    "users_intro": ("Créez les comptes, changez les rôles, redonnez un mot de passe oublié ou supprimez un compte.",
                    "Create accounts, change roles, reset a forgotten password or delete an account.",
                    "បង្កើតគណនី ប្តូរតួនាទី កំណត់ពាក្យសម្ងាត់ដែលភ្លេចឡើងវិញ ឬលុបគណនី។"),
    "card_users": ("Comptes", "Accounts", "គណនី"),
    "card_new": ("Nouveau compte", "New account", "គណនីថ្មី"),
    "card_edit": ("Modifier le compte", "Edit account", "កែប្រែគណនី"),
    "col_account": ("Compte", "Account", "គណនី"),
    "col_role": ("Rôle", "Role", "តួនាទី"),
    "col_state": ("État", "Status", "ស្ថានភាព"),
    "col_last": ("Dernière connexion", "Last sign-in", "ចូលចុងក្រោយ"),
    "col_lessons": ("Leçons", "Lessons", "មេរៀន"),
    "col_streak": ("Série", "Streak", "ថ្ងៃជាប់គ្នា"),
    "b_track": ("Suivi", "Progress", "វឌ្ឍនភាព"),
    "card_sessions": ("Sessions ouvertes", "Open sessions", "វគ្គដែលកំពុងបើក"),
    "b_journal_user": ("Tout le journal de ce compte", "Full log for this account", "កំណត់ហេតុទាំងអស់របស់គណនីនេះ"),
    # Invitations, liens de réinitialisation
    "card_invites": ("Invitations", "Invitations", "ការអញ្ជើញ"),
    "invites_intro": ("Un lien d'invitation permet à une personne de créer elle-même son compte. Il ne sert qu'une fois ; "
                      "durée de validité, en jours : {days}.",
                      "An invitation link lets someone create their own account. It works once; days it stays valid: {days}.",
                      "តំណអញ្ជើញអនុញ្ញាតឱ្យនរណាម្នាក់បង្កើតគណនីដោយខ្លួនឯង។ វាប្រើបានតែម្តង។ ចំនួនថ្ងៃដែលវាប្រើបាន៖ {days}។"),
    "f_note": ("Pour qui ? (facultatif)", "For whom? (optional)", "សម្រាប់អ្នកណា? (មិនចាំបាច់)"),
    "b_invite": ("Créer un lien d'invitation", "Create an invitation link", "បង្កើតតំណអញ្ជើញ"),
    "invites_pending": ("Invitations en attente", "Pending invitations", "ការអញ្ជើញដែលកំពុងរង់ចាំ"),
    "invite_anyone": ("Sans nom", "No name", "គ្មានឈ្មោះ"),
    "invite_expires": ("expire le {date}", "expires on {date}", "ផុតកំណត់នៅ {date}"),
    "b_cancel_link": ("Annuler", "Cancel", "បោះបង់"),
    "ok_invite": ("Lien d'invitation créé. Copiez-le maintenant : il ne sera plus affiché.",
                  "Invitation link created. Copy it now: it will not be shown again.",
                  "បានបង្កើតតំណអញ្ជើញ។ សូមចម្លងវាឥឡូវនេះ៖ វានឹងមិនបង្ហាញម្តងទៀតទេ។"),
    "ok_reset_link": ("Lien de nouveau mot de passe pour « {login} » ; durée de validité, en heures : {hours}. "
                      "Copiez-le maintenant : il ne sera plus affiché.",
                      "New-password link for “{login}”; hours it stays valid: {hours}. Copy it now: it will not be shown again.",
                      "តំណពាក្យសម្ងាត់ថ្មីសម្រាប់ « {login} »។ ចំនួនម៉ោងដែលវាប្រើបាន៖ {hours}។ "
                      "សូមចម្លងវាឥឡូវនេះ៖ វានឹងមិនបង្ហាញម្តងទៀតទេ។"),
    "ok_link_cancelled": ("Invitation annulée.", "Invitation cancelled.", "បានបោះបង់ការអញ្ជើញ។"),
    "b_reset_link": ("Créer un lien de nouveau mot de passe", "Create a new-password link", "បង្កើតតំណពាក្យសម្ងាត់ថ្មី"),
    "hint_reset_link": ("Avec ce lien, la personne choisit elle-même son mot de passe : vous n'avez pas à le connaître.",
                        "With this link, the person chooses their own password: you never need to know it.",
                        "ជាមួយតំណនេះ អ្នកប្រើជ្រើសរើសពាក្យសម្ងាត់ដោយខ្លួនឯង៖ អ្នកមិនចាំបាច់ដឹងវាទេ។"),
    "f_link": ("Lien à transmettre", "Link to pass on", "តំណដែលត្រូវផ្ញើ"),
    "b_copy": ("Copier", "Copy", "ចម្លង"),
    "copied": ("Copié", "Copied", "បានចម្លង"),
    "via_invite": ("par invitation", "by invitation", "តាមការអញ្ជើញ"),
    "via_link": ("par lien", "by link", "តាមតំណ"),
    "ev_invite_created": ("Invitation créée", "Invitation created", "បានបង្កើតការអញ្ជើញ"),
    "ev_invite_revoked": ("Invitation annulée", "Invitation cancelled", "បានបោះបង់ការអញ្ជើញ"),
    "ev_reset_link_created": ("Lien de nouveau mot de passe créé", "New-password link created", "បានបង្កើតតំណពាក្យសម្ងាត់ថ្មី"),
    # Journal
    "journal_title": ("Journal", "Activity log", "កំណត់ហេតុ"),
    "journal_intro": ("Connexions, tentatives refusées et opérations sur les comptes, des plus récentes aux plus anciennes.",
                      "Sign-ins, refused attempts and account operations, most recent first.",
                      "ការចូល ការព្យាយាមដែលត្រូវបានបដិសេធ និងប្រតិបត្តិការលើគណនី ពីថ្មីបំផុតទៅចាស់បំផុត។"),
    "jf_all": ("Tout", "All", "ទាំងអស់"),
    "jf_logins": ("Connexions", "Sign-ins", "ការចូល"),
    "jf_failures": ("Échecs", "Failures", "បរាជ័យ"),
    "jf_accounts": ("Comptes", "Accounts", "គណនី"),
    "col_when": ("Date", "Date", "កាលបរិច្ឆេទ"),
    "col_event": ("Événement", "Event", "ព្រឹត្តិការណ៍"),
    "col_by": ("Par", "By", "ដោយ"),
    "col_ip": ("Adresse", "Address", "អាសយដ្ឋាន"),
    "journal_empty": ("Rien à afficher.", "Nothing to show.", "គ្មានអ្វីត្រូវបង្ហាញទេ។"),
    "journal_older": ("Plus anciens", "Older", "ចាស់ជាងនេះ"),
    "journal_newest": ("Revenir aux plus récents", "Back to the most recent", "ត្រឡប់ទៅថ្មីបំផុត"),
    "journal_keep": ("Durée de conservation du journal, en jours : {days}.", "Days the log is kept: {days}.",
                     "ចំនួនថ្ងៃដែលកំណត់ហេតុត្រូវបានរក្សាទុក៖ {days}។"),
    "journal_only": ("Compte :", "Account:", "គណនី៖"),
    "journal_everyone": ("Tous les comptes", "All accounts", "គណនីទាំងអស់"),
    "unknown_login": ("identifiant inconnu", "unknown username", "ឈ្មោះគណនីមិនស្គាល់"),
    "deleted_account": ("compte supprimé", "deleted account", "គណនីត្រូវបានលុប"),
    "cli_actor": ("ligne de commande", "command line", "បន្ទាត់ពាក្យបញ្ជា"),
    "ev_login": ("Connexion", "Sign-in", "ចូលគណនី"),
    "ev_login_failed": ("Échec de connexion", "Failed sign-in", "ចូលមិនបានសម្រេច"),
    "ev_login_blocked": ("Connexion bloquée : trop de tentatives", "Sign-in blocked: too many attempts",
                         "ការចូលត្រូវបានទប់ស្កាត់៖ ព្យាយាមច្រើនដងពេក"),
    "ev_logout": ("Déconnexion", "Sign-out", "ចាកចេញ"),
    "ev_register": ("Inscription", "Registration", "ចុះឈ្មោះ"),
    "ev_setup": ("Premier compte administrateur", "First administrator account", "គណនីអ្នកគ្រប់គ្រងដំបូង"),
    "ev_password_changed": ("Mot de passe changé", "Password changed", "បានប្តូរពាក្យសម្ងាត់"),
    "ev_password_reset": ("Mot de passe redéfini", "Password reset", "បានកំណត់ពាក្យសម្ងាត់ឡើងវិញ"),
    "ev_user_created": ("Compte créé", "Account created", "បានបង្កើតគណនី"),
    "ev_user_updated": ("Compte modifié", "Account updated", "បានកែប្រែគណនី"),
    "ev_role_changed": ("Rôle changé", "Role changed", "បានប្តូរតួនាទី"),
    "ev_user_disabled": ("Compte désactivé", "Account disabled", "បានបិទគណនី"),
    "ev_user_enabled": ("Compte réactivé", "Account re-enabled", "បានបើកគណនីឡើងវិញ"),
    "ev_user_deleted": ("Compte supprimé", "Account deleted", "បានលុបគណនី"),
    "ev_sessions_closed": ("Sessions fermées", "Sessions closed", "បានបិទវគ្គ"),
    "ev_progress_reset": ("Progression effacée", "Progress erased", "បានលុបវឌ្ឍនភាព"),
    "ev_progress_imported": ("Ancienne progression reprise", "Old progress imported", "បាននាំចូលវឌ្ឍនភាពចាស់"),
    "never": ("jamais", "never", "មិនដែល"),
    "you": ("vous", "you", "អ្នក"),
    "role_admin": ("Administrateur", "Administrator", "អ្នកគ្រប់គ្រង"),
    "role_user": ("Apprenant", "Learner", "អ្នករៀន"),
    "state_active": ("Actif", "Active", "សកម្ម"),
    "state_disabled": ("Désactivé", "Disabled", "បានបិទ"),
    "delete_summary": ("Supprimer ce compte…", "Delete this account…", "លុបគណនីនេះ…"),
    "delete_confirm": ("Je veux supprimer définitivement ce compte et toute sa progression.",
                       "I want to permanently delete this account and all its progress.",
                       "ខ្ញុំចង់លុបគណនីនេះ និងវឌ្ឍនភាពទាំងអស់របស់វាចោលជាស្ថាពរ។"),
    # Messages
    "ok_profile": ("Profil enregistré.", "Profile saved.", "បានរក្សាទុកព័ត៌មានគណនី។"),
    "ok_password": ("Mot de passe changé. Vos autres appareils ont été déconnectés.",
                    "Password changed. Your other devices have been signed out.",
                    "បានប្តូរពាក្យសម្ងាត់។ ឧបករណ៍ផ្សេងទៀតរបស់អ្នកត្រូវបានចាកចេញ។"),
    "ok_sessions": ("Autres sessions fermées : {n}.", "Other sessions closed: {n}.", "វគ្គផ្សេងទៀតដែលបានបិទ៖ {n}។"),
    "ok_device": ("Appareil déconnecté.", "Device signed out.", "បានចាកចេញពីឧបករណ៍នោះ។"),
    "ok_progress_reset": ("Progression effacée.", "Progress erased.", "បានលុបវឌ្ឍនភាព។"),
    "ok_created": ("Compte « {login} » créé.", "Account “{login}” created.", "បានបង្កើតគណនី « {login} »។"),
    "ok_updated": ("Compte « {login} » mis à jour.", "Account “{login}” updated.", "បានកែប្រែគណនី « {login} »។"),
    "ok_deleted": ("Compte « {login} » supprimé.", "Account “{login}” deleted.", "បានលុបគណនី « {login} »។"),
    "ok_password_set": ("Mot de passe de « {login} » changé ; ses sessions ont été fermées.",
                        "Password for “{login}” changed; their sessions have been closed.",
                        "បានប្តូរពាក្យសម្ងាត់របស់ « {login} » ហើយវគ្គរបស់គណនីនេះត្រូវបានបិទ។"),
    "temp_password": ("Mot de passe provisoire de « {login} » : {password} — notez-le maintenant, il ne sera plus affiché.",
                      "Temporary password for “{login}”: {password} — note it down now, it will not be shown again.",
                      "ពាក្យសម្ងាត់បណ្តោះអាសន្នរបស់ « {login} »៖ {password} — សូមកត់ទុកឥឡូវនេះ វានឹងមិនបង្ហាញម្តងទៀតទេ។"),
    "ok_sessions_closed": ("Sessions de « {login} » fermées : {n}.", "Sessions of “{login}” closed: {n}.",
                           "វគ្គរបស់ « {login} » ដែលបានបិទ៖ {n}។"),
    "ok_logout": ("Vous êtes déconnecté.", "You have been signed out.", "អ្នកបានចាកចេញហើយ។"),
    # Erreurs
    "e403_title": ("Accès réservé", "Restricted access", "ចូលបានតែអ្នកមានសិទ្ធិ"),
    "e403_text": ("Cette page est réservée aux administrateurs.", "This page is for administrators only.",
                  "ទំព័រនេះសម្រាប់តែអ្នកគ្រប់គ្រងប៉ុណ្ណោះ។"),
    "e404_title": ("Page introuvable", "Page not found", "រកមិនឃើញទំព័រ"),
    "e404_text": ("Cette page n'existe pas.", "This page does not exist.", "ទំព័រនេះមិនមានទេ។"),
    "back_home": ("Retour à l'accueil", "Back to home", "ត្រឡប់ទៅទំព័រដើម"),
}


def texts(key: str, **params) -> dict:
    """Libellé dans les trois langues ; les nombres passent en chiffres khmers pour le khmer."""
    out = {}
    for lang, template in zip(LANGS, TEXT[key]):
        values = {name: to_khmer_digits(value) if lang == "km" and isinstance(value, int) else value
                  for name, value in params.items()}
        out[lang] = template.format(**values) if values else template
    return out


def t(key: str, tag: str = "span", **params) -> str:
    return multi(texts(key, **params), tag=tag)


# --- Briques de formulaire ----------------------------------------------------------------------

def hidden(name: str, value) -> str:
    return f'<input type="hidden" name="{esc(name)}" value="{esc(value)}">'


def field(label: str, name: str, *, kind: str = "text", value="", hint: str = "", required: bool = True,
          autocomplete: str = "off", extra: str = "") -> str:
    """Champ de saisie avec son libellé ; ``label`` et ``hint`` sont du HTML déjà prêt."""
    need = " required" if required else ""
    note = f'<span class="field-hint">{hint}</span>' if hint else ""
    return (f'<label class="field"><span class="field-label">{label}</span>'
            f'<input type="{kind}" name="{esc(name)}" value="{esc(value)}" autocomplete="{autocomplete}"{need} {extra}>'
            f'{note}</label>')


def login_field(value: str = "", *, autofocus: bool = False, hint: bool = False, autocomplete: str = "username") -> str:
    focus = " autofocus" if autofocus else ""
    return field(t("f_login"), "identifiant", value=value, autocomplete=autocomplete, hint=t("hint_login") if hint else "",
                 extra=f'maxlength="32" autocapitalize="none" autocorrect="off" spellcheck="false"{focus}')


def password_field(label_key: str, name: str, *, new: bool, min_length: int = 0, required: bool = True,
                   hint: str | None = None) -> str:
    """Champ de mot de passe. Sans ``hint``, un nouveau mot de passe rappelle la longueur minimale ;
    ``hint=""`` n'affiche rien."""
    extra = 'maxlength="256"' + (f' minlength="{min_length}"' if new and required and min_length else "")
    if hint is None:
        hint = t("hint_password", min=min_length) if new and min_length else ""
    return field(t(label_key), name, kind="password", autocomplete="new-password" if new else "current-password",
                 required=required, hint=hint, extra=extra)


def choices(label: str, name: str, options, selected: str) -> str:
    """Choix unique à segments (boutons radio) : les libellés peuvent ainsi rester trilingues."""
    items = "".join(
        f'<label class="seg-option"><input type="radio" name="{esc(name)}" value="{esc(value)}"'
        f'{" checked" if value == selected else ""}><span>{text}</span></label>'
        for value, text in options)
    return (f'<fieldset class="field seg-field"><legend class="field-label">{label}</legend>'
            f'<div class="seg" style="--n:{len(options)}">{items}</div></fieldset>')


def checkbox(label: str, name: str, *, checked: bool = False, required: bool = False) -> str:
    state = (" checked" if checked else "") + (" required" if required else "")
    return (f'<label class="check"><input type="checkbox" name="{esc(name)}" value="1"{state}>'
            f'<span>{label}</span></label>')


def button(label_key: str, css: str = "btn-primary") -> str:
    return f'<button type="submit" class="btn {css}">{t(label_key)}</button>'


def form(action: str, csrf: str, body: str, *, css: str = "", what: str = "") -> str:
    """Formulaire envoyé en POST à une page de la racine ; ``what`` nomme l'opération demandée."""
    op = hidden("action", what) if what else ""
    return (f'<form class="acct-form {css}" method="post" action="{esc(action)}">{hidden("csrf", csrf)}{op}{body}</form>')


def card(title: str, body: str, css: str = "") -> str:
    return f'<section class="acct-card {css}"><h2 class="acct-card-title">{title}</h2>{body}</section>'


def link_flash(message: dict) -> str:
    """Un lien à usage unique, montré une seule fois : ``text`` l'annonce, ``url`` est l'adresse
    complète vue du serveur ; le script la recalcule depuis ``path`` (juste aussi derrière un proxy)."""
    return (f'<div class="flash flash-ok flash-link" role="status">{multi(message["text"], tag="p")}'
            f'<div class="link-row"><input type="text" class="link-url" readonly value="{esc(message["url"])}" '
            f'data-rel="{esc(message["path"])}" aria-label="{esc(TEXT["f_link"][0])}">'
            f'<button type="button" class="btn btn-small" data-copy>'
            f'<span class="copy-idle">{t("b_copy")}</span><span class="copy-done" hidden>{t("copied")}</span></button></div></div>')


def flashes(messages) -> str:
    """Messages à afficher une fois : liste de (« ok », « error » ou « link », contenu). Le contenu est
    {fr, en, km}, ou pour « link » un dictionnaire ``text``, ``url``, ``path`` (voir ``link_flash``)."""
    return "".join(
        link_flash(message) if kind == "link" else
        f'<div class="flash flash-{"error" if kind == "error" else "ok"}" role="{"alert" if kind == "error" else "status"}">'
        f'{multi(message, tag="p")}</div>' for kind, message in messages)


def head(title_key: str, intro: str = "") -> str:
    lead = f'<p class="page-intro">{intro}</p>' if intro else ""
    return f'<header class="page-head"><h1 class="page-title">{t(title_key)}</h1>{lead}</header>'


def profile_options(config) -> list:
    return [(key, f'<span lang="{key}">{esc(LANG_META[key]["native"])}</span>') for key in config.profiles()]


ROLE_OPTIONS = (("user", "role_user"), ("admin", "role_admin"))


def role_options() -> list:
    return [(value, t(key)) for value, key in ROLE_OPTIONS]


# --- Pages publiques : connexion, inscription, premier démarrage ----------------------------------

def login_page(*, csrf: str, next_path: str, login: str, messages, registration_open: bool) -> str:
    body = (hidden("suite", next_path) + login_field(login, autofocus=not login)
            + password_field("f_password", "motdepasse", new=False) + button("b_login", "btn-primary btn-wide"))
    if registration_open:
        alt = f'<p class="auth-alt">{t("no_account")} <a href="inscription">{t("link_register")}</a></p>'
    else:
        alt = f'<p class="auth-alt">{t("ask_admin")}</p>'
    return (f'<article class="auth">{head("login_title", t("login_intro"))}{flashes(messages)}'
            f'{form("connexion", csrf, body, css="acct-card auth-card")}{alt}</article>')


def identity_fields(config, values: dict, min_length: int) -> str:
    return (login_field(values.get("identifiant", ""), hint=True)
            + field(t("f_name"), "nom", value=values.get("nom", ""), autocomplete="name", extra='maxlength="60"')
            + choices(t("f_profile"), "profil", profile_options(config), values.get("profil") or config.default_profile())
            + password_field("f_password", "motdepasse", new=True, min_length=min_length)
            + password_field("f_password2", "motdepasse2", new=True, min_length=min_length, hint=""))


def register_page(config, *, csrf: str, values: dict, messages, min_length: int, needs_code: bool) -> str:
    code = field(t("f_code_invite"), "code", value=values.get("code", ""), extra='maxlength="100" autocapitalize="none"') if needs_code else ""
    body = code + identity_fields(config, values, min_length) + button("b_register", "btn-primary btn-wide")
    return (f'<article class="auth">{head("register_title", t("register_intro"))}{flashes(messages)}'
            f'{form("inscription", csrf, body, css="acct-card auth-card")}'
            f'<p class="auth-alt">{t("have_account")} <a href="connexion">{t("b_login")}</a></p></article>')


def setup_page(config, *, csrf: str, values: dict, messages, min_length: int) -> str:
    code = field(t("f_code_setup"), "code", value=values.get("code", ""),
                 extra='maxlength="40" autocapitalize="none" autocorrect="off" spellcheck="false" autofocus')
    body = code + identity_fields(config, values, min_length) + button("b_register", "btn-primary btn-wide")
    return (f'<article class="auth">{head("setup_title", t("setup_intro"))}{flashes(messages)}'
            f'{form("installation", csrf, body, css="acct-card auth-card")}</article>')


def invite_page(config, *, csrf: str, token: str, link, values: dict, messages, min_length: int) -> str:
    """Création de son compte par une personne invitée ; la langue proposée est celle prévue par l'invitation."""
    values = {"nom": link.note, "profil": link.profile, **values}
    body = hidden("c", token) + identity_fields(config, values, min_length) + button("b_register", "btn-primary btn-wide")
    return (f'<article class="auth">{head("invite_title", t("invite_intro"))}{flashes(messages)}'
            f'{form("invitation", csrf, body, css="acct-card auth-card")}</article>')


def reset_page(*, csrf: str, token: str, login: str, messages, min_length: int) -> str:
    body = (hidden("c", token) + hidden("identifiant", login)
            + password_field("f_new", "motdepasse", new=True, min_length=min_length)
            + password_field("f_password2", "motdepasse2", new=True, min_length=min_length, hint="")
            + button("b_save_password", "btn-primary btn-wide"))
    return (f'<article class="auth">{head("reset_title", t("reset_intro", login=login))}{flashes(messages)}'
            f'{form("reinitialisation", csrf, body, css="acct-card auth-card")}</article>')


def notice_page(title_key: str, message: dict, *, home: bool = True) -> str:
    """Page d'un seul message (lien non valable, déjà connecté) ; ``message`` : {fr, en, km}."""
    back = f'<p class="auth-alt"><a class="btn btn-ghost" href="./">{t("back_home")}</a></p>' if home else ""
    return f'<article class="auth">{head(title_key, multi(message))}{back}</article>'


def error_page(title_key: str, text_key: str) -> str:
    return (f'<article class="auth">{head(title_key, t(text_key))}'
            f'<p class="auth-alt"><a class="btn btn-ghost" href="./">{t("back_home")}</a></p></article>')


# --- Mon compte -----------------------------------------------------------------------------------

def stat(value: int, label_key: str) -> str:
    return f'<div class="acct-stat"><span class="acct-stat-value">{num_label(value)}</span><span class="acct-stat-label">{t(label_key)}</span></div>'


def local_epoch(config, seconds) -> str:
    """« 2026-11-27 08:10 » dans le fuseau du site, à partir d'un horodatage en secondes."""
    if not seconds:
        return ""
    return dt.datetime.fromtimestamp(float(seconds), config.tzinfo()).strftime("%Y-%m-%d %H:%M")


BROWSERS = (("Edg", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"), ("Firefox/", "Firefox"),
            ("FxiOS", "Firefox"), ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
SYSTEMS = (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"), ("Mac OS X", "Mac"),
           ("Macintosh", "Mac"), ("CrOS", "ChromeOS"), ("Linux", "Linux"))


def device_name(user_agent: str) -> str:
    """« Firefox · Android » d'après l'en-tête User-Agent (vide si rien n'est reconnu) ; l'ordre des
    marqueurs compte : Edge et Chrome se disent aussi « Safari », Android se dit aussi « Linux »."""
    agent = str(user_agent or "")
    found = [next((name for marker, name in table if marker in agent), "") for table in (BROWSERS, SYSTEMS)]
    return " · ".join(name for name in found if name)


def device_label(user_agent: str) -> str:
    return esc(device_name(user_agent)) or t("dev_unknown")


def sessions_list(config, sessions, *, current: str = "", csrf: str = "", action: str = "") -> str:
    """Les sessions ouvertes d'un compte. Avec ``action``, chacune (sauf celle en cours) a son bouton « Déconnecter »."""
    if not sessions:
        return f'<p class="acct-line">{t("dev_none")}</p>'
    rows = []
    for item in sessions:
        here = item.public_id == current
        badge = f' <span class="badge badge-you">{t("dev_this")}</span>' if here else ""
        close = ""
        if action and not here:
            close = form(action, csrf, what="appareil", css="device-form",
                         body=hidden("session", item.public_id) + button("b_revoke_one", "btn-small btn-ghost"))
        ip = f' · <span class="device-ip">{esc(item.ip)}</span>' if item.ip else ""
        rows.append(
            f'<li class="device"><div class="device-main"><span class="device-name">{device_label(item.user_agent)}{badge}</span>'
            f'<span class="device-meta">{t("dev_seen", date=local_epoch(config, item.last_seen_at))}</span>'
            f'<span class="device-meta">{t("dev_since", date=local_epoch(config, item.created_at))}{ip}</span></div>{close}</li>')
    return f'<ul class="devices">{"".join(rows)}</ul>'


def event_label(event) -> str:
    """Libellé d'un événement du journal, avec sa précision éventuelle (nouveau rôle, nombre de sessions…)."""
    extra = ""
    if event.kind == "role_changed" and event.detail in ("admin", "user"):
        extra = t("role_admin" if event.detail == "admin" else "role_user")
    elif event.kind == "sessions_closed" and event.detail.isascii() and event.detail.isdigit():
        extra = num_label(int(event.detail))
    elif event.kind == "login_failed" and event.detail == "disabled":
        extra = t("state_disabled")
    elif event.kind == "register" and event.detail == "invitation":
        extra = t("via_invite")
    elif event.kind == "password_changed" and event.detail == "link":
        extra = t("via_link")
    elif event.kind in ("invite_created", "invite_revoked") and event.detail:
        extra = esc(event.detail)
    failed = " is-fail" if event.kind in EVENT_GROUPS["failures"] else ""
    return f'<span class="event-kind{failed}">{t(f"ev_{event.kind}")}</span>' + (f' <span class="event-detail">{extra}</span>' if extra else "")


def events_list(config, events) -> str:
    """Liste courte d'événements (« Mon compte », fiche d'un compte) : libellé, date, adresse."""
    if not events:
        return f'<p class="acct-line">{t("recent_none")}</p>'
    rows = []
    for event in events:
        by = ""
        if event.actor:
            by = f' · {t("cli_actor") if event.actor == CLI_ACTOR else esc(event.actor)}'
        ip = f' · <span class="device-ip">{esc(event.ip)}</span>' if event.ip else ""
        rows.append(f'<li class="event"><span class="event-what">{event_label(event)}</span>'
                    f'<span class="device-meta">{local_epoch(config, event.at)}{by}{ip}</span></li>')
    return f'<ul class="events">{"".join(rows)}</ul>'


def account_page(config, *, user, csrf: str, messages, summary: dict, sessions, current: str, events, min_length: int) -> str:
    role = t("role_admin" if user.is_admin else "role_user")
    intro = f'<span class="acct-id">{esc(user.name)} · <span class="acct-login">{esc(user.login)}</span></span> · {role}'
    notice = f'<div class="flash flash-warn" role="alert">{t("must_change", tag="p")}</div>' if user.must_change_password else ""
    profile = form("compte", csrf, what="profil", body=(
        field(t("f_name"), "nom", value=user.name, autocomplete="name", extra='maxlength="60"')
        + choices(t("f_profile"), "profil", profile_options(config), user.profile) + button("b_save")))
    password = form("compte", csrf, what="motdepasse", body=(
        hidden("identifiant", user.login)
        + password_field("f_current", "actuel", new=False)
        + password_field("f_new", "motdepasse", new=True, min_length=min_length)
        + password_field("f_password2", "motdepasse2", new=True, min_length=min_length, hint="")
        + button("b_change_password")))
    reset = form("compte", csrf, what="progression", css="acct-danger-form", body=(
        checkbox(t("reset_confirm"), "confirmer", required=True) + button("b_reset_progress", "btn-danger")))
    progress = (f'<div class="acct-stats">{stat(summary["lessons"], "stat_lessons")}{stat(summary["days"], "stat_days")}'
                f'{stat(summary["cards"], "stat_cards")}</div><p class="acct-hint">{t("progress_hint")}</p>'
                f'<p class="acct-more"><a class="btn btn-small btn-ghost" href="suivi">{t("b_track_detail")}</a></p>'
                f'<details class="acct-danger"><summary>{t("reset_summary")}</summary>{reset}</details>')
    others = form("compte", csrf, what="sessions", body=button("b_revoke_others", "btn-ghost")) if len(sessions) > 1 else ""
    devices = (sessions_list(config, sessions, current=current, csrf=csrf, action="compte") + others
               + form("deconnexion", csrf, css="js-logout", body=button("b_logout", "btn-ghost"))
               + f'<h3 class="acct-sub">{t("card_recent")}</h3>{events_list(config, events)}')
    admin = (f'<p class="acct-admin-link"><a class="btn btn-ghost" href="utilisateurs">{t("b_users")}</a></p>'
             if user.is_admin else "")
    blocks = {"profile": card(t("card_profile"), profile), "password": card(t("card_password"), password),
              "progress": card(t("card_progress"), progress), "devices": card(t("card_devices"), devices)}
    order = ("password", "profile", "progress", "devices") if user.must_change_password else (
        "profile", "password", "progress", "devices")
    ordered = "".join(blocks[name] for name in order)
    return (f'<article class="acct">{head("account_title", intro)}{flashes(messages)}{notice}{admin}'
            f'<div class="acct-grid">{ordered}</div></article>')


# --- Utilisateurs (administrateur) ------------------------------------------------------------------

def local_time(config, stamp: str | None) -> str:
    """« 2026-11-27 08:10 » dans le fuseau du site, à partir d'un horodatage UTC de la base."""
    if not stamp:
        return ""
    try:
        moment = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return esc(stamp)
    return moment.astimezone(config.tzinfo()).strftime("%Y-%m-%d %H:%M")


def cell_label(key: str) -> str:
    """Libellé d'une cellule quand le tableau devient une suite de fiches (téléphone) : la feuille
    de style choisit l'attribut selon la langue du profil."""
    fr, en, km = TEXT[key]
    return f'data-label="{esc(fr)}" data-label-en="{esc(en)}" data-label-km="{esc(km)}"'


def users_table(config, users, summaries: dict, current_id: int, editing_id: int | None) -> str:
    rows = []
    for user in users:
        you = f' <span class="badge badge-you">{t("you")}</span>' if user.id == current_id else ""
        state = ("state_active", "is-on") if user.active else ("state_disabled", "is-off")
        last = local_time(config, user.last_login_at) or t("never")
        selected = " is-editing" if user.id == editing_id else ""
        rows.append(
            f'<tr class="user-row{selected}">'
            f'<td class="user-cell-id" {cell_label("col_account")}><span class="user-name">{esc(user.name)}</span>{you}'
            f'<span class="user-login">{esc(user.login)}</span></td>'
            f'<td {cell_label("col_role")}><span class="badge badge-role-{user.role}">'
            f'{t("role_admin" if user.is_admin else "role_user")}</span></td>'
            f'<td {cell_label("col_state")}><span class="user-state {state[1]}">{t(state[0])}</span></td>'
            f'<td class="user-cell-last" {cell_label("col_last")}>{last}</td>'
            f'<td class="user-cell-num" {cell_label("col_lessons")}>{num_label(summaries.get(user.id, {}).get("lessons", 0))}</td>'
            f'<td class="user-cell-num" {cell_label("col_streak")}>{num_label(summaries.get(user.id, {}).get("streak", 0))}</td>'
            f'<td class="user-cell-action"><a class="btn btn-small btn-ghost" href="suivi?u={user.id}">{t("b_track")}</a> '
            f'<a class="btn btn-small btn-ghost" href="utilisateurs?u={user.id}#modifier">{t("b_edit")}</a></td>'
            f'</tr>')
    headers = "".join(f'<th scope="col">{t(key)}</th>'
                      for key in ("col_account", "col_role", "col_state", "col_last", "col_lessons", "col_streak"))
    return (f'<div class="users-wrap"><table class="users"><thead><tr>{headers}<th scope="col"><span class="visually-hidden">'
            f'{t("b_edit")}</span></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def user_editor(config, *, target, csrf: str, is_self: bool, min_length: int, sessions=(), events=()) -> str:
    uid = hidden("id", target.id)
    details = form("utilisateurs", csrf, what="modifier", body=(
        uid + field(t("f_name"), "nom", value=target.name, extra='maxlength="60"')
        + choices(t("f_role"), "role", role_options(), target.role)
        + choices(t("f_profile_other"), "profil", profile_options(config), target.profile)
        + checkbox(t("f_active"), "actif", checked=target.active) + button("b_save")))
    password = form("utilisateurs", csrf, what="motdepasse", body=(
        uid + hidden("identifiant", target.login)
        + password_field("f_new", "motdepasse", new=True, min_length=min_length, required=False, hint=t("hint_generate"))
        + checkbox(t("f_must_change"), "changer", checked=True) + button("b_set_password", "btn-ghost")))
    reset_link = ""
    if target.active:
        reset_link = form("utilisateurs", csrf, what="lien-motdepasse", css="acct-link-form", body=(
            uid + button("b_reset_link", "btn-ghost") + f'<span class="field-hint">{t("hint_reset_link")}</span>'))
    close_all = form("utilisateurs", csrf, what="sessions", body=uid + button("b_revoke_all", "btn-ghost")) if sessions else ""
    activity = (f'<div class="acct-editor-more"><div><h3 class="acct-sub">{t("card_sessions")}</h3>'
                f'{sessions_list(config, sessions)}{close_all}</div>'
                f'<div><h3 class="acct-sub">{t("card_recent")}</h3>{events_list(config, events)}'
                f'<p class="acct-more"><a class="btn btn-small btn-ghost" href="suivi?u={target.id}">{t("b_track")}</a> '
                f'<a class="btn btn-small btn-ghost" href="journal?u={target.id}">{t("b_journal_user")}</a></p></div></div>')
    delete = ""
    if not is_self:
        delete = (f'<details class="acct-danger"><summary>{t("delete_summary")}</summary>'
                  + form("utilisateurs", csrf, what="supprimer", css="acct-danger-form", body=(
                      uid + checkbox(t("delete_confirm"), "confirmer", required=True) + button("b_delete", "btn-danger")))
                  + '</details>')
    title = f'{t("card_edit")} <span class="acct-login">{esc(target.login)}</span>'
    back = f'<p class="acct-back"><a href="utilisateurs">{t("b_back")}</a></p>'
    return (f'<section class="acct-card acct-editor" id="modifier"><h2 class="acct-card-title">{title}</h2>'
            f'<div class="acct-editor-grid"><div>{details}</div><div>{reset_link}{password}{delete}</div></div>{activity}{back}</section>')


def new_user_form(config, *, csrf: str, values: dict, min_length: int) -> str:
    return form("utilisateurs", csrf, what="creer", css="acct-form-cols", body=(
        login_field(values.get("identifiant", ""), hint=True, autocomplete="off")
        + field(t("f_name"), "nom", value=values.get("nom", ""), required=False, extra='maxlength="60"')
        + choices(t("f_role"), "role", role_options(), values.get("role") or "user")
        + choices(t("f_profile_other"), "profil", profile_options(config), values.get("profil") or config.default_profile())
        + password_field("f_password", "motdepasse", new=True, min_length=min_length, required=False, hint=t("hint_generate"))
        + button("b_create")))


def invites_card(config, *, csrf: str, invites, values: dict, days: int) -> str:
    """Création d'un lien d'invitation, et invitations en attente (annulables)."""
    create = form("utilisateurs", csrf, what="inviter", css="acct-form-cols", body=(
        field(t("f_note"), "pour", value=values.get("pour", ""), required=False, extra='maxlength="60"')
        + choices(t("f_role"), "role", role_options(), "user")
        + choices(t("f_profile_other"), "profil", profile_options(config), config.default_profile())
        + button("b_invite")))
    pending = ""
    if invites:
        rows = []
        for item in invites:
            who = esc(item.note) if item.note else t("invite_anyone")
            lang = esc(LANG_META[item.profile]["native"]) if item.profile in LANG_META else ""
            by = f' · {esc(item.created_by)}' if item.created_by else ""
            rows.append(
                f'<li class="device"><div class="device-main"><span class="device-name">{who}</span>'
                f'<span class="device-meta">{t("role_admin" if item.role == "admin" else "role_user")} · {lang}{by}</span>'
                f'<span class="device-meta">{t("invite_expires", date=local_epoch(config, item.expires_at))}</span></div>'
                + form("utilisateurs", csrf, what="annuler-lien", css="device-form",
                       body=hidden("lien", item.public_id) + button("b_cancel_link", "btn-small btn-ghost")) + '</li>')
        pending = f'<h3 class="acct-sub">{t("invites_pending")}</h3><ul class="devices">{"".join(rows)}</ul>'
    return card(t("card_invites"), f'<p class="acct-hint acct-hint-top">{t("invites_intro", days=days)}</p>{create}{pending}',
                "acct-card-invites")


def users_page(config, *, user, csrf: str, messages, users, summaries: dict, target, values: dict, min_length: int,
               sessions=(), events=(), invites=(), invite_days: int = 7) -> str:
    editor = user_editor(config, target=target, csrf=csrf, is_self=target.id == user.id, min_length=min_length,
                         sessions=sessions, events=events) if target else ""
    table = card(f'{t("card_users")} <span class="acct-count">{num_label(len(users))}</span>',
                 users_table(config, users, summaries, user.id, target.id if target else None), "acct-card-wide")
    create = card(t("card_new"), new_user_form(config, csrf=csrf, values=values, min_length=min_length))
    invite = invites_card(config, csrf=csrf, invites=invites, values=values, days=invite_days)
    tools = f'<p class="acct-admin-link"><a class="btn btn-ghost" href="journal">{t("journal_title")}</a></p>'
    return (f'<article class="acct acct-users">{head("users_title", t("users_intro"))}{flashes(messages)}{tools}'
            f'{editor}{table}{invite}{create}</article>')


# --- Suivi d'un apprenant -----------------------------------------------------------------------------

CALENDAR_WEEKS = 12
RECENT_LESSONS = 5
CURRENT = ' aria-current="page"'


def pill(label: str, href: str, current: bool) -> str:
    """Lien d'une rangée de choix (apprenants, filtres du journal) ; ``label`` et ``href`` sont du HTML prêt."""
    return f'<a class="pill{" is-current" if current else ""}" href="{href}"{CURRENT if current else ""}>{label}</a>'


def meter(done: int, total: int) -> str:
    """Barre de proportion ; le texte qui l'accompagne donne les chiffres."""
    share = 0 if total <= 0 else max(0.0, min(100.0, 100 * done / total))
    return f'<div class="meter" aria-hidden="true"><span style="width:{share:.1f}%"></span></div>'


def stamp_day(config, ms) -> dt.date | None:
    """Le jour d'un horodatage en millisecondes ; ``None`` pour les anciens enregistrements sans date."""
    if not ms or ms < 1e11:
        return None
    return dt.datetime.fromtimestamp(ms / 1000, config.tzinfo()).date()


def lessons_card(config, detail: dict, lessons, today: dt.date) -> str:
    done = detail["lessons"]
    listed = [lesson for lesson in lessons if lesson["date"] <= today.isoformat() or lesson["number"] in done]
    if not listed:
        return card(t("card_lessons"), f'<p class="acct-line">{t("lessons_none")}</p>', "acct-card-wide")
    finished = sum(1 for lesson in listed if lesson["number"] in done)
    chips = []
    for lesson in listed:
        number, is_done = lesson["number"], lesson["number"] in done
        title = " · ".join(dict.fromkeys(value for value in lesson["title"].values() if value))
        state = t("lesson_done" if is_done else "lesson_todo")
        chips.append(f'<li><a class="lchip{" is-done" if is_done else ""}" href="{esc(lesson["path"] or "./")}" '
                     f'title="{number}. {esc(title)}">{num_label(number)}<span class="visually-hidden"> — {state}</span></a></li>')
    by_number = {lesson["number"]: lesson for lesson in listed}
    latest = sorted(((stamp, number) for number, stamp in done.items() if number in by_number), reverse=True)[:RECENT_LESSONS]
    recent = ""
    if latest:
        items = []
        for stamp, number in latest:
            lesson, day = by_number[number], stamp_day(config, stamp)
            when = f'<span class="track-date">{date_label(day, weekday=False)}</span>' if day else ""
            items.append(f'<li><a href="{esc(lesson["path"] or "./")}"><span class="track-num">{num_label(number)}</span>'
                         f'{multi(lesson["title"])}</a>{when}</li>')
        recent = f'<h3 class="acct-sub">{t("lessons_recent")}</h3><ul class="track-recent">{"".join(items)}</ul>'
    legend = (f'<p class="legend"><span class="legend-item"><span class="lchip is-done" aria-hidden="true"></span>{t("lesson_done")}</span>'
              f'<span class="legend-item"><span class="lchip" aria-hidden="true"></span>{t("lesson_todo")}</span></p>')
    body = (f'{meter(finished, len(listed))}<p class="meter-figure">{t("lessons_done_of", done=finished, total=len(listed))}</p>'
            f'<ol class="lchips">{"".join(chips)}</ol>{legend}{recent}')
    return card(t("card_lessons"), body, "acct-card-wide")


def activity_card(detail: dict, today: dt.date) -> str:
    """Les douze dernières semaines, une colonne par semaine (du lundi au dimanche)."""
    active = set(detail["days"])
    start = today - dt.timedelta(days=today.weekday() + 7 * (CALENDAR_WEEKS - 1))
    cells, count = [], 0
    for offset in range(7 * CALENDAR_WEEKS):
        day = start + dt.timedelta(days=offset)
        if day > today:
            cells.append('<span class="cal-day is-future"></span>')
            continue
        on = day.isoformat() in active
        count += on
        cells.append(f'<span class="cal-day{" is-on" if on else ""}" title="{day.isoformat()}"></span>')
    total = (today - start).days + 1
    legend = (f'<p class="legend"><span class="legend-item"><span class="cal-day is-on" aria-hidden="true"></span>{t("legend_active")}</span>'
              f'<span class="legend-item"><span class="cal-day" aria-hidden="true"></span>{t("legend_idle")}</span></p>')
    body = (f'<div class="cal" aria-hidden="true">{"".join(cells)}</div>'
            f'<p class="cal-range"><span>{date_label(start, weekday=False)}</span><span>{date_label(today, weekday=False)}</span></p>'
            f'<p class="meter-figure">{t("activity_summary", n=count, total=total)}</p>{legend}')
    return card(t("card_activity"), body)


def review_card(detail: dict) -> str:
    rows = []
    for lang in LANG_META:
        item = detail["langs"].get(lang)
        if not item:
            continue
        due = f' · {t("review_due", n=item["due"])}' if item["due"] else ""
        rows.append(f'<li class="mrow"><span class="mrow-name" lang="{lang}">{esc(LANG_META[lang]["native"])}</span>'
                    f'{meter(item["known"], item["cards"])}'
                    f'<span class="mrow-figure">{t("review_row", known=item["known"], cards=item["cards"])}{due}</span></li>')
    if not rows:
        return card(t("card_review"), f'<p class="acct-line">{t("review_none")}</p>')
    return card(t("card_review"), f'<ul class="mrows">{"".join(rows)}</ul><p class="acct-hint">{t("review_hint")}</p>')


def track_page(config, *, viewer, target, detail: dict, lessons, today: dt.date, users=()) -> str:
    role = t("role_admin" if target.is_admin else "role_user")
    last = stamp_day(config, detail["last"])
    seen = t("track_never")
    if last:
        seen = multi({lang: text.format(date=format_date(last, lang, weekday=False)) for lang, text in zip(LANGS, TEXT["track_last"])})
    intro = (f'<span class="acct-id">{esc(target.name)} · <span class="acct-login">{esc(target.login)}</span></span> · {role}'
             f'<span class="track-seen">{seen}</span>')
    switch = ""
    if viewer.is_admin and len(users) > 1:
        links = "".join(pill(esc(user.name), f"suivi?u={user.id}", user.id == target.id) for user in users)
        switch = (f'<nav class="track-users"><span class="track-users-label">{t("track_users")}</span>{links}'
                  f'<a class="track-edit" href="utilisateurs?u={target.id}#modifier">{t("card_edit")}</a></nav>')
    stats = (f'<div class="acct-stats track-stats">{stat(len(detail["lessons"]), "stat_lessons")}{stat(detail["streak"], "stat_streak")}'
             f'{stat(detail["best_streak"], "stat_best")}{stat(len(detail["days"]), "stat_days")}'
             f'{stat(detail["cards"], "stat_cards")}{stat(detail["due"], "stat_due")}</div>')
    return (f'<article class="acct track">{head("track_title", intro)}{switch}{stats}'
            f'{lessons_card(config, detail, lessons, today)}'
            f'<div class="acct-grid">{activity_card(detail, today)}{review_card(detail)}</div></article>')


# --- Journal (administrateur) ---------------------------------------------------------------------------

def journal_link(group: str = "", user_id=None, before=None) -> str:
    query = [f"type={group}"] if group else []
    if user_id is not None:
        query.append(f"u={int(user_id)}")
    if before:
        query.append(f"avant={int(before)}")
    return "journal" + (f"?{'&amp;'.join(query)}" if query else "")


def journal_page(config, *, events, group: str, user_id, users: dict, more: bool, paged: bool, days: int) -> str:
    """``users`` : {identifiant numérique: compte} pour les comptes qui existent encore."""
    tabs = "".join(pill(t(label), journal_link(key, user_id), key == group) for key, label in (
        ("", "jf_all"), ("logins", "jf_logins"), ("failures", "jf_failures"), ("accounts", "jf_accounts")))
    only = ""
    if user_id is not None:
        who = users.get(user_id)
        name = f'<span class="acct-login">{esc(who.login)}</span>' if who else t("deleted_account")
        only = (f'<p class="journal-only">{t("journal_only")} {name} '
                f'<a class="btn btn-small btn-ghost" href="{journal_link(group)}">{t("journal_everyone")}</a></p>')
    rows = []
    for event in events:
        if event.login:
            who = users.get(event.user_id)
            account = (f'<a class="acct-login" href="utilisateurs?u={who.id}#modifier">{esc(event.login)}</a>' if who
                       else f'<span class="acct-login">{esc(event.login)}</span>')
        elif event.kind in EVENT_GROUPS["failures"]:
            account = f'<span class="event-unknown">{t("unknown_login")}</span>'
        else:
            account = ""
        by = t("cli_actor") if event.actor == CLI_ACTOR else f'<span class="acct-login">{esc(event.actor)}</span>' if event.actor else ""
        rows.append(
            f'<tr><td class="user-cell-last" {cell_label("col_when")}>{local_epoch(config, event.at)}</td>'
            f'<td class="user-cell-id">{event_label(event)}</td>'
            f'<td {cell_label("col_account")}>{account}</td>'
            f'<td {cell_label("col_by")}>{by}</td>'
            f'<td class="user-cell-last" {cell_label("col_ip")}>{esc(event.ip)}</td></tr>')
    if rows:
        headers = "".join(f'<th scope="col">{t(key)}</th>' for key in ("col_when", "col_event", "col_account", "col_by", "col_ip"))
        table = (f'<div class="users-wrap"><table class="users journal"><thead><tr>{headers}</tr></thead>'
                 f'<tbody>{"".join(rows)}</tbody></table></div>')
    else:
        table = f'<p class="acct-line">{t("journal_empty")}</p>'
    pager = ""
    if more and events:
        pager += f'<a class="btn btn-small btn-ghost" href="{journal_link(group, user_id, events[-1].id)}">{t("journal_older")}</a>'
    if paged:
        pager += f'<a class="btn btn-small btn-ghost" href="{journal_link(group, user_id)}">{t("journal_newest")}</a>'
    pager = f'<p class="journal-pager">{pager}</p>' if pager else ""
    back = f'<p class="acct-admin-link"><a class="btn btn-ghost" href="utilisateurs">{t("b_users")}</a></p>'
    body = f'<nav class="journal-tabs">{tabs}</nav>{only}{table}{pager}<p class="acct-hint">{t("journal_keep", days=days)}</p>'
    return (f'<article class="acct acct-users">{head("journal_title", t("journal_intro"))}{back}'
            f'<section class="acct-card acct-card-wide">{body}</section></article>')
