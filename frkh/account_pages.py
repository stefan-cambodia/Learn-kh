"""Pages du serveur avec comptes : connexion, inscription, premier démarrage, « Mon compte »
et gestion des utilisateurs.

Ce module ne fabrique que le contenu HTML (libellés en français, anglais et khmer, comme le
reste du site) ; ``frkh.webapp`` l'habille avec le gabarit commun et décide qui voit quoi.
Aucune valeur saisie par un utilisateur n'est insérée sans échappement.
"""

from __future__ import annotations

import datetime as dt

from .langs import LANG_META
from .render import esc, multi, num_label
from .textutil import LANGS, to_khmer_digits

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
    "sessions_count": ("Sessions ouvertes, celle-ci comprise : {n}.", "Open sessions, including this one: {n}.",
                       "វគ្គដែលកំពុងបើក រួមទាំងវគ្គនេះ៖ {n}។"),
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


def flashes(messages) -> str:
    """Messages à afficher une fois : liste de (« ok » ou « error », {fr, en, km})."""
    return "".join(
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


def error_page(title_key: str, text_key: str) -> str:
    return (f'<article class="auth">{head(title_key, t(text_key))}'
            f'<p class="auth-alt"><a class="btn btn-ghost" href="./">{t("back_home")}</a></p></article>')


# --- Mon compte -----------------------------------------------------------------------------------

def stat(value: int, label_key: str) -> str:
    return f'<div class="acct-stat"><span class="acct-stat-value">{num_label(value)}</span><span class="acct-stat-label">{t(label_key)}</span></div>'


def account_page(config, *, user, csrf: str, messages, summary: dict, sessions: int, min_length: int) -> str:
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
                f'<details class="acct-danger"><summary>{t("reset_summary")}</summary>{reset}</details>')
    devices = (f'<p class="acct-line">{t("sessions_count", n=sessions)}</p>'
               + form("compte", csrf, what="sessions", body=button("b_revoke_others", "btn-ghost"))
               + form("deconnexion", csrf, css="js-logout", body=button("b_logout", "btn-ghost")))
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


def users_table(config, users, summaries: dict, current_id: int, editing_id: int | None) -> str:
    rows = []
    for user in users:
        you = f' <span class="badge badge-you">{t("you")}</span>' if user.id == current_id else ""
        state = ("state_active", "is-on") if user.active else ("state_disabled", "is-off")
        last = local_time(config, user.last_login_at) or t("never")
        selected = " is-editing" if user.id == editing_id else ""
        rows.append(
            f'<tr class="user-row{selected}">'
            f'<td class="user-cell-id" data-label="{esc(TEXT["col_account"][0])}"><span class="user-name">{esc(user.name)}</span>{you}'
            f'<span class="user-login">{esc(user.login)}</span></td>'
            f'<td data-label="{esc(TEXT["col_role"][0])}"><span class="badge badge-role-{user.role}">'
            f'{t("role_admin" if user.is_admin else "role_user")}</span></td>'
            f'<td data-label="{esc(TEXT["col_state"][0])}"><span class="user-state {state[1]}">{t(state[0])}</span></td>'
            f'<td class="user-cell-last" data-label="{esc(TEXT["col_last"][0])}">{last}</td>'
            f'<td class="user-cell-num" data-label="{esc(TEXT["col_lessons"][0])}">{num_label(summaries.get(user.id, {}).get("lessons", 0))}</td>'
            f'<td class="user-cell-action"><a class="btn btn-small btn-ghost" href="utilisateurs?u={user.id}#modifier">{t("b_edit")}</a></td>'
            f'</tr>')
    headers = "".join(f'<th scope="col">{t(key)}</th>' for key in ("col_account", "col_role", "col_state", "col_last", "col_lessons"))
    return (f'<div class="users-wrap"><table class="users"><thead><tr>{headers}<th scope="col"><span class="visually-hidden">'
            f'{t("b_edit")}</span></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def user_editor(config, *, target, csrf: str, is_self: bool, min_length: int) -> str:
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
    sessions = form("utilisateurs", csrf, what="sessions", body=uid + button("b_revoke_all", "btn-ghost"))
    delete = ""
    if not is_self:
        delete = (f'<details class="acct-danger"><summary>{t("delete_summary")}</summary>'
                  + form("utilisateurs", csrf, what="supprimer", css="acct-danger-form", body=(
                      uid + checkbox(t("delete_confirm"), "confirmer", required=True) + button("b_delete", "btn-danger")))
                  + '</details>')
    title = f'{t("card_edit")} <span class="acct-login">{esc(target.login)}</span>'
    back = f'<p class="acct-back"><a href="utilisateurs">{t("b_back")}</a></p>'
    return (f'<section class="acct-card acct-editor" id="modifier"><h2 class="acct-card-title">{title}</h2>'
            f'<div class="acct-editor-grid"><div>{details}</div><div>{password}{sessions}{delete}</div></div>{back}</section>')


def new_user_form(config, *, csrf: str, values: dict, min_length: int) -> str:
    return form("utilisateurs", csrf, what="creer", css="acct-form-cols", body=(
        login_field(values.get("identifiant", ""), hint=True, autocomplete="off")
        + field(t("f_name"), "nom", value=values.get("nom", ""), required=False, extra='maxlength="60"')
        + choices(t("f_role"), "role", role_options(), values.get("role") or "user")
        + choices(t("f_profile_other"), "profil", profile_options(config), values.get("profil") or config.default_profile())
        + password_field("f_password", "motdepasse", new=True, min_length=min_length, required=False, hint=t("hint_generate"))
        + button("b_create")))


def users_page(config, *, user, csrf: str, messages, users, summaries: dict, target, values: dict, min_length: int) -> str:
    editor = user_editor(config, target=target, csrf=csrf, is_self=target.id == user.id, min_length=min_length) if target else ""
    table = card(f'{t("card_users")} <span class="acct-count">{num_label(len(users))}</span>',
                 users_table(config, users, summaries, user.id, target.id if target else None), "acct-card-wide")
    create = card(t("card_new"), new_user_form(config, csrf=csrf, values=values, min_length=min_length))
    return (f'<article class="acct acct-users">{head("users_title", t("users_intro"))}{flashes(messages)}'
            f'{editor}{table}{create}</article>')
