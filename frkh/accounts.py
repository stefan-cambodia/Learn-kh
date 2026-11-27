"""Comptes utilisateurs du serveur web : mots de passe, sessions et progression par compte.

Ce module ne connaît pas HTTP : il range tout dans la base SQLite du projet (tables ``users``,
``user_sessions`` et ``user_progress``) et applique les règles — identifiants valides, mots de
passe hachés, dernier administrateur protégé. Le serveur (``frkh.webapp``) et la ligne de
commande (``manage.py users``) s'appuient tous deux sur lui.

Sécurité, en bref :
- les mots de passe ne sont jamais stockés : seulement leur empreinte scrypt, avec un sel par
  compte (PBKDF2 si scrypt manque) ; les paramètres sont écrits dans l'empreinte, ce qui permet
  de les durcir plus tard sans casser les comptes existants ;
- un jeton de session est tiré au hasard à chaque connexion ; la base n'en garde que le SHA-256,
  si bien qu'une copie de la base ne permet pas de se connecter ;
- un identifiant inconnu coûte le même temps de calcul qu'un mauvais mot de passe.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
import unicodedata

from . import db, progress_sync
from .textutil import LANGS, to_khmer_digits

ROLES = ("admin", "user")
LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
NAME_MAX = 60
PASSWORD_MAX = 256

# Coût du hachage : scrypt N=2^14, r=8, p=5 (16 Mo de mémoire), équivalent recommandé par l'OWASP.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 5
PBKDF2_ITERATIONS = 600_000
# Sans visuels ambigus (0/O, 1/l/I) : pour les mots de passe provisoires et le code d'installation.
PLAIN_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"

SESSION_REFRESH_SECONDS = 3600      # l'échéance d'une session active est repoussée au plus une fois par heure
SESSION_CACHE_SECONDS = 20          # une page charge des dizaines de fichiers : on ne relit pas la base à chaque fois

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    login                TEXT    NOT NULL UNIQUE,
    display_name         TEXT    NOT NULL,
    password_hash        TEXT    NOT NULL,
    role                 TEXT    NOT NULL DEFAULT 'user',
    profile              TEXT    NOT NULL DEFAULT 'fr',
    active               INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    progress_reset_at    INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL,
    last_login_at        TEXT
);

CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash   TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token   TEXT    NOT NULL,
    created_at   INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    user_agent   TEXT    NOT NULL DEFAULT '',
    ip           TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);

CREATE TABLE IF NOT EXISTS user_progress (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key        TEXT    NOT NULL,
    value      TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, key)
);
"""

# Messages d'erreur : (français, anglais, khmer). « {min} » et « {minutes} » sont des nombres.
MESSAGES = {
    "login_invalid": (
        "Identifiant : 3 à 32 caractères, lettres minuscules sans accent, chiffres, point, tiret ou tiret bas ; "
        "il commence par une lettre ou un chiffre.",
        "Username: 3 to 32 characters, plain lowercase letters, digits, dot, hyphen or underscore; "
        "it starts with a letter or a digit.",
        "ឈ្មោះគណនី៖ ៣ ដល់ ៣២ តួ ប្រើអក្សរឡាតាំងតូច លេខ ចំណុច សញ្ញា - ឬ _ ហើយចាប់ផ្តើមដោយអក្សរ ឬលេខ។"),
    "login_taken": ("Cet identifiant est déjà utilisé.", "This username is already taken.",
                    "ឈ្មោះគណនីនេះមានគេប្រើហើយ។"),
    "name_invalid": ("Le nom affiché doit compter de 1 à 60 caractères.",
                     "The display name must be 1 to 60 characters long.",
                     "ឈ្មោះបង្ហាញត្រូវមានពី ១ ដល់ ៦០ តួ។"),
    "password_short": ("Le mot de passe doit compter au moins {min} caractères.",
                       "The password must be at least {min} characters long.",
                       "ពាក្យសម្ងាត់ត្រូវមានយ៉ាងតិច {min} តួ។"),
    "password_long": ("Le mot de passe est trop long (256 caractères au plus).",
                      "The password is too long (256 characters at most).",
                      "ពាក្យសម្ងាត់វែងពេក (ច្រើនបំផុត ២៥៦ តួ)។"),
    "password_same_as_login": ("Le mot de passe ne doit pas être identique à l'identifiant.",
                               "The password must not be the same as the username.",
                               "ពាក្យសម្ងាត់មិនត្រូវដូចឈ្មោះគណនីទេ។"),
    "password_mismatch": ("Les deux mots de passe ne sont pas identiques.", "The two passwords do not match.",
                          "ពាក្យសម្ងាត់ទាំងពីរមិនដូចគ្នាទេ។"),
    "password_wrong": ("Le mot de passe actuel est incorrect.", "The current password is incorrect.",
                       "ពាក្យសម្ងាត់បច្ចុប្បន្នមិនត្រឹមត្រូវទេ។"),
    "password_unchanged": ("Le nouveau mot de passe doit être différent de l'ancien.",
                           "The new password must be different from the old one.",
                           "ពាក្យសម្ងាត់ថ្មីត្រូវខុសពីពាក្យសម្ងាត់ចាស់។"),
    "role_invalid": ("Rôle inconnu.", "Unknown role.", "មិនស្គាល់តួនាទីនេះទេ។"),
    "profile_invalid": ("Langue inconnue.", "Unknown language.", "មិនស្គាល់ភាសានេះទេ។"),
    "user_missing": ("Ce compte n'existe pas, ou plus.", "This account does not exist, or no longer does.",
                     "គណនីនេះមិនមានទេ។"),
    "last_admin": ("Impossible : il doit rester au moins un administrateur actif.",
                   "Not possible: at least one active administrator must remain.",
                   "មិនអាចទេ៖ ត្រូវមានអ្នកគ្រប់គ្រងសកម្មយ៉ាងតិចម្នាក់។"),
    "self_forbidden": ("Vous ne pouvez ni désactiver ni supprimer votre propre compte.",
                       "You cannot disable or delete your own account.",
                       "អ្នកមិនអាចបិទ ឬលុបគណនីផ្ទាល់ខ្លួនបានទេ។"),
    "credentials": ("Identifiant ou mot de passe incorrect.", "Incorrect username or password.",
                    "ឈ្មោះគណនី ឬពាក្យសម្ងាត់មិនត្រឹមត្រូវ។"),
    "throttled": ("Trop de tentatives. Réessayez dans {minutes} min.",
                  "Too many attempts. Try again in {minutes} min.",
                  "ព្យាយាមច្រើនដងពេក។ សូមព្យាយាមម្តងទៀតក្នុងរយៈពេល {minutes} នាទី។"),
    "csrf": ("Le formulaire a expiré. Rechargez la page et recommencez.",
             "The form has expired. Reload the page and try again.",
             "ទម្រង់នេះផុតកំណត់ហើយ។ សូមផ្ទុកទំព័រឡើងវិញ រួចព្យាយាមម្តងទៀត។"),
    "setup_code": ("Code d'installation incorrect. Il est affiché dans le terminal du serveur.",
                   "Incorrect setup code. It is shown in the server's terminal.",
                   "លេខកូដដំឡើងមិនត្រឹមត្រូវទេ។ វាបង្ហាញនៅលើអេក្រង់របស់ម៉ាស៊ីនមេ។"),
    "invite_code": ("Code d'invitation incorrect.", "Incorrect invitation code.", "លេខកូដអញ្ជើញមិនត្រឹមត្រូវទេ។"),
    "confirm_required": ("Cochez la case de confirmation.", "Tick the confirmation box.", "សូមគូសប្រអប់បញ្ជាក់។"),
}


class AccountError(Exception):
    """Refus d'une opération sur un compte ; ``code`` désigne le message (``MESSAGES``)."""

    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params

    def texts(self) -> dict:
        """Le message dans les trois langues d'interface."""
        return message_texts(self.code, **self.params)

    def __str__(self) -> str:
        return self.texts()["fr"]


def message_texts(code: str, **params) -> dict:
    out = {}
    for lang, template in zip(LANGS, MESSAGES[code]):
        values = {key: to_khmer_digits(value) if lang == "km" else value for key, value in params.items()}
        out[lang] = template.format(**values)
    return out


# --- Mots de passe ----------------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _normalize_password(password: str) -> bytes:
    """Même mot de passe quel que soit le clavier : forme Unicode NFKC, puis UTF-8."""
    return unicodedata.normalize("NFKC", password).encode("utf-8")


def _scrypt(secret: bytes, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(secret, salt=salt, n=n, r=r, p=p, dklen=32, maxmem=256 * 1024 * 1024)


def hash_password(password: str) -> str:
    """Empreinte à stocker : « scrypt$N$r$p$sel$empreinte » (ou « pbkdf2_sha256$tours$sel$empreinte »)."""
    secret, salt = _normalize_password(password), secrets.token_bytes(16)
    if hasattr(hashlib, "scrypt"):
        return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(_scrypt(secret, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P))}"
    digest = hashlib.pbkdf2_hmac("sha256", secret, salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Compare en temps constant. Une empreinte illisible ou aux paramètres déraisonnables est refusée."""
    try:
        parts = str(stored).split("$")
        secret = _normalize_password(password)
        if parts[0] == "scrypt" and len(parts) == 6:
            n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
            if not (2 <= n <= 2 ** 20 and n & (n - 1) == 0 and 1 <= r <= 32 and 1 <= p <= 16):
                return False
            salt, expected = base64.b64decode(parts[4]), base64.b64decode(parts[5])
            return hmac.compare_digest(_scrypt(secret, salt, n, r, p), expected)
        if parts[0] == "pbkdf2_sha256" and len(parts) == 4:
            rounds = int(parts[1])
            if not 1 <= rounds <= 10_000_000:
                return False
            salt, expected = base64.b64decode(parts[2]), base64.b64decode(parts[3])
            return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", secret, salt, rounds), expected)
    except (ValueError, TypeError, AttributeError, IndexError):
        return False
    return False


def needs_rehash(stored: str) -> bool:
    """Vrai si l'empreinte date d'un réglage plus faible que l'actuel : elle sera refaite à la connexion."""
    parts = str(stored).split("$")
    if hasattr(hashlib, "scrypt"):
        return parts[:4] != ["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P)]
    return parts[:2] != ["pbkdf2_sha256", str(PBKDF2_ITERATIONS)]


def generate_password(groups: int = 3) -> str:
    """Mot de passe provisoire lisible à voix haute, par exemple « k7mq-x2vd-9hrt » (environ 59 bits)."""
    return "-".join("".join(secrets.choice(PLAIN_ALPHABET) for _ in range(4)) for _ in range(groups))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Limitation des tentatives ----------------------------------------------------------------

class Throttle:
    """Au plus ``limit`` échecs par clé sur ``window`` secondes ; au-delà, la clé est bloquée
    jusqu'à ce que le plus ancien échec sorte de la fenêtre. Tout est en mémoire."""

    MAX_KEYS = 20000

    def __init__(self, limit: int, window: int, clock=time.time):
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._hits.get(key, ()) if now - t < self.window]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def blocked(self, key: str) -> int:
        """Secondes à attendre avant le prochain essai (0 : la clé n'est pas bloquée)."""
        with self._lock:
            now = self.clock()
            hits = self._recent(key, now)
            if len(hits) < self.limit:
                return 0
            return max(1, int(hits[0] + self.window - now) + 1)

    def hit(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            if len(self._hits) >= self.MAX_KEYS:
                for other in list(self._hits):
                    self._recent(other, now)
                if len(self._hits) >= self.MAX_KEYS:
                    self._hits.clear()
            self._hits[key] = self._recent(key, now) + [now]

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


# --- Comptes, sessions, progression -------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class User:
    id: int
    login: str
    name: str
    role: str
    profile: str
    active: bool
    must_change_password: bool
    created_at: str
    last_login_at: str | None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclasses.dataclass(frozen=True)
class Session:
    token_hash: str
    user: User
    csrf_token: str
    created_at: int
    last_seen_at: int
    expires_at: int
    user_agent: str
    ip: str


def normalize_login(value) -> str:
    return str(value or "").strip().lower()


class Accounts:
    """Accès aux comptes. Une seule connexion SQLite, partagée entre les fils d'exécution du
    serveur et protégée par un verrou : chaque opération est courte."""

    def __init__(self, config, clock=time.time):
        self.config = config
        self.clock = clock
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[Session, float]] = {}
        path = config.paths.database
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 30000")
        self._conn.executescript(SCHEMA)
        # Empreinte factice : vérifiée quand l'identifiant est inconnu, pour que la réponse
        # prenne le même temps qu'avec un mauvais mot de passe.
        self._dummy_hash = hash_password(secrets.token_urlsafe(16))

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- réglages ---------------------------------------------------------------------------
    def password_min_length(self) -> int:
        try:
            return max(6, min(64, int(self.config.get("server.password_min_length", 8))))
        except (TypeError, ValueError):
            return 8

    def session_seconds(self) -> int:
        try:
            days = float(self.config.get("server.session_days", 30))
        except (TypeError, ValueError):
            days = 30
        return int(max(1 / 24, min(365, days)) * 86400)

    # --- contrôles --------------------------------------------------------------------------
    def check_login(self, login: str) -> str:
        login = normalize_login(login)
        if not LOGIN_RE.match(login):
            raise AccountError("login_invalid")
        return login

    def check_name(self, name) -> str:
        name = " ".join(str(name or "").split())
        if not 1 <= len(name) <= NAME_MAX or any(unicodedata.category(c) in ("Cc", "Cs") for c in name):
            raise AccountError("name_invalid")
        return name

    def check_password(self, password, login: str = "") -> str:
        password = "" if password is None else str(password)
        if len(password) < self.password_min_length():
            raise AccountError("password_short", min=self.password_min_length())
        if len(password) > PASSWORD_MAX:
            raise AccountError("password_long")
        if login and password.strip().lower() == login.lower():
            raise AccountError("password_same_as_login")
        return password

    def check_profile(self, profile) -> str:
        profile = str(profile or "") or self.config.default_profile()
        if profile not in self.config.profiles():
            raise AccountError("profile_invalid")
        return profile

    @staticmethod
    def check_role(role) -> str:
        if role not in ROLES:
            raise AccountError("role_invalid")
        return role

    # --- comptes ------------------------------------------------------------------------------
    @staticmethod
    def _user(row) -> User:
        return User(id=row["id"], login=row["login"], name=row["display_name"], role=row["role"], profile=row["profile"],
                    active=bool(row["active"]), must_change_password=bool(row["must_change_password"]),
                    created_at=row["created_at"], last_login_at=row["last_login_at"])

    def count_users(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def _active_admins(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1").fetchone()[0])

    def list_users(self) -> list[User]:
        with self._lock:
            return [self._user(row) for row in self._conn.execute("SELECT * FROM users ORDER BY login")]

    def get_user(self, user_id) -> User | None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user(row) if row else None

    def get_by_login(self, login) -> User | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE login = ?", (normalize_login(login),)).fetchone()
        return self._user(row) if row else None

    def _require(self, user_id) -> User:
        user = self.get_user(user_id)
        if user is None:
            raise AccountError("user_missing")
        return user

    def create_user(self, login, name, password, *, role: str = "user", profile=None,
                    must_change_password: bool = False) -> User:
        login = self.check_login(login)
        name = self.check_name(name or login)
        password = self.check_password(password, login)
        role, profile = self.check_role(role), self.check_profile(profile)
        digest, now = hash_password(password), db.utcnow()
        with self._lock:
            try:
                cursor = self._conn.execute(
                    "INSERT INTO users(login, display_name, password_hash, role, profile, active, must_change_password, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                    (login, name, digest, role, profile, int(must_change_password), now, now))
            except sqlite3.IntegrityError:
                raise AccountError("login_taken") from None
            return self._require(cursor.lastrowid)

    def update_user(self, user_id, *, name=None, role=None, profile=None, active=None, actor_id=None) -> User:
        """Modifie un compte. Le dernier administrateur actif ne peut être ni rétrogradé ni désactivé,
        et personne ne désactive son propre compte."""
        with self._lock:
            user = self._require(user_id)
            values = {}
            if name is not None:
                values["display_name"] = self.check_name(name)
            if profile is not None:
                values["profile"] = self.check_profile(profile)
            if role is not None and role != user.role:
                values["role"] = self.check_role(role)
            if active is not None and bool(active) != user.active:
                if not active and actor_id is not None and int(actor_id) == user.id:
                    raise AccountError("self_forbidden")
                values["active"] = int(bool(active))
            loses_admin = user.is_admin and user.active and (values.get("role") == "user" or values.get("active") == 0)
            if loses_admin and self._active_admins() <= 1:
                raise AccountError("last_admin")
            if values:
                values["updated_at"] = db.utcnow()
                self._conn.execute(f"UPDATE users SET {', '.join(f'{key} = ?' for key in values)} WHERE id = ?",
                                   (*values.values(), user.id))
                if values.get("active") == 0:
                    self._conn.execute("DELETE FROM user_sessions WHERE user_id = ?", (user.id,))
                self._cache.clear()
            return self._require(user.id)

    def set_password(self, user_id, password, *, must_change_password: bool = False, keep_token: str | None = None) -> None:
        """Change le mot de passe et ferme les sessions du compte (sauf, au besoin, celle en cours)."""
        with self._lock:
            user = self._require(user_id)
            password = self.check_password(password, user.login)
            self._conn.execute("UPDATE users SET password_hash = ?, must_change_password = ?, updated_at = ? WHERE id = ?",
                               (hash_password(password), int(must_change_password), db.utcnow(), user.id))
            self.revoke_user_sessions(user.id, keep_token=keep_token)

    def check_current_password(self, user_id, password) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT password_hash FROM users WHERE id = ?", (int(user_id),)).fetchone()
        return bool(row) and verify_password(str(password or ""), row["password_hash"])

    def delete_user(self, user_id, *, actor_id=None) -> User:
        """Supprime un compte, ses sessions et sa progression."""
        with self._lock:
            user = self._require(user_id)
            if actor_id is not None and int(actor_id) == user.id:
                raise AccountError("self_forbidden")
            if user.is_admin and user.active and self._active_admins() <= 1:
                raise AccountError("last_admin")
            self._conn.execute("DELETE FROM users WHERE id = ?", (user.id,))
            self._cache.clear()
            return user

    def authenticate(self, login, password) -> User | None:
        """Le compte si l'identifiant et le mot de passe sont bons et le compte actif ; sinon ``None``."""
        login, password = normalize_login(login), str(password or "")
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE login = ?", (login,)).fetchone()
        if row is None or len(password) > PASSWORD_MAX:
            verify_password(password[:PASSWORD_MAX], self._dummy_hash)
            return None
        if not verify_password(password, row["password_hash"]) or not row["active"]:
            return None
        if needs_rehash(row["password_hash"]):
            with self._lock:
                self._conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), row["id"]))
        return self._user(row)

    # --- sessions -----------------------------------------------------------------------------
    def create_session(self, user_id, *, user_agent: str = "", ip: str = "") -> tuple[str, Session]:
        """Ouvre une session : renvoie le jeton (à placer dans le cookie) et la session."""
        token, now = secrets.token_urlsafe(32), int(self.clock())
        digest = token_hash(token)
        with self._lock:
            self._conn.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now,))
            self._conn.execute(
                "INSERT INTO user_sessions(token_hash, user_id, csrf_token, created_at, last_seen_at, expires_at, user_agent, ip) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (digest, int(user_id), secrets.token_urlsafe(24), now, now, now + self.session_seconds(),
                 str(user_agent or "")[:300], str(ip or "")[:64]))
            self._conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (db.utcnow(), int(user_id)))
            self._cache.clear()
            session = self._load_session(digest, now)
        if session is None:
            raise AccountError("user_missing")
        return token, session

    def _load_session(self, digest: str, now: int) -> Session | None:
        row = self._conn.execute(
            "SELECT s.token_hash, s.csrf_token, s.created_at AS s_created, s.last_seen_at, s.expires_at, s.user_agent, s.ip, u.* "
            "FROM user_sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?", (digest,)).fetchone()
        if row is None or row["expires_at"] <= now or not row["active"]:
            return None
        last_seen, expires = row["last_seen_at"], row["expires_at"]
        if now - last_seen >= SESSION_REFRESH_SECONDS:
            last_seen, expires = now, now + self.session_seconds()
            self._conn.execute("UPDATE user_sessions SET last_seen_at = ?, expires_at = ? WHERE token_hash = ?",
                               (last_seen, expires, digest))
        return Session(token_hash=digest, user=self._user(row), csrf_token=row["csrf_token"], created_at=row["s_created"],
                       last_seen_at=last_seen, expires_at=expires, user_agent=row["user_agent"], ip=row["ip"])

    def session(self, token) -> Session | None:
        """La session désignée par un jeton de cookie, si elle est encore valable."""
        if not token or not isinstance(token, str) or len(token) > 200:
            return None
        digest, now = token_hash(token), self.clock()
        with self._lock:
            cached = self._cache.get(digest)
            if cached and cached[1] > now and cached[0].expires_at > now:
                return cached[0]
            session = self._load_session(digest, int(now))
            if session is None:
                self._cache.pop(digest, None)
                return None
            if len(self._cache) > 5000:
                self._cache.clear()
            self._cache[digest] = (session, now + SESSION_CACHE_SECONDS)
            return session

    def revoke_session(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM user_sessions WHERE token_hash = ?", (token_hash(token),))
            self._cache.clear()

    def revoke_user_sessions(self, user_id, *, keep_token: str | None = None) -> int:
        """Ferme les sessions d'un compte ; ``keep_token`` épargne celle de l'appareil en cours."""
        keep = token_hash(keep_token) if keep_token else ""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM user_sessions WHERE user_id = ? AND token_hash != ?", (int(user_id), keep))
            self._cache.clear()
            return cursor.rowcount

    def count_sessions(self, user_id) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM user_sessions WHERE user_id = ? AND expires_at > ?",
                                          (int(user_id), int(self.clock()))).fetchone()[0])

    # --- progression ----------------------------------------------------------------------------
    def _progress(self, user_id: int) -> dict:
        state = {}
        for row in self._conn.execute("SELECT key, value FROM user_progress WHERE user_id = ?", (user_id,)):
            try:
                state[row["key"]] = json.loads(row["value"])
            except ValueError:
                continue
        return state

    def _after_reset(self, key: str, value, reset_ms: int):
        """Écarte ce qui date d'avant la dernière remise à zéro du compte : un autre appareil, resté
        avec l'ancienne progression, ne doit pas la faire revenir."""
        if not reset_ms:
            return value
        if key.startswith("frkh-days-"):
            first = dt.datetime.fromtimestamp(reset_ms / 1000, self.config.tzinfo()).date().isoformat()
            return [day for day in value if day >= first]
        return {item: entry for item, entry in value.items() if entry["t"] > reset_ms}

    def exchange_progress(self, user_id, incoming: dict) -> dict:
        """Fusionne ce qu'envoie un appareil avec la progression du compte ; renvoie l'état fusionné
        (valeurs en chaînes JSON, comme le stockage du navigateur). Mêmes règles que ``progress_sync``.
        Une rubrique envoyée mais vide côté serveur est renvoyée vide : l'appareil s'aligne."""
        user_id = int(user_id)
        with self._lock, db.transaction(self._conn):
            row = self._conn.execute("SELECT progress_reset_at FROM users WHERE id = ?", (user_id,)).fetchone()
            reset_ms = int(row["progress_reset_at"]) if row else 0
            state = self._progress(user_id)
            now, empty = db.utcnow(), {}
            for key, text in incoming.items():
                value = progress_sync.parse_value(key, text) if isinstance(key, str) else None
                if value is None:
                    continue
                value = self._after_reset(key, value, reset_ms)
                if not value and key not in state:
                    empty[key] = "[]" if key.startswith("frkh-days-") else "{}"
                    continue
                merged = progress_sync.merge_value(key, state.get(key), value)
                if merged != state.get(key):
                    state[key] = merged
                    self._conn.execute(
                        "INSERT INTO user_progress(user_id, key, value, updated_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                        (user_id, key, json.dumps(merged, ensure_ascii=False, separators=(",", ":")), now))
            out = {key: json.dumps(value, ensure_ascii=False, separators=(",", ":")) for key, value in state.items()}
            return {**empty, **out}

    def progress_summary(self, user_id) -> dict:
        """Leçons terminées, jours d'activité, cartes révisées et dernière activité (horodatage en ms, ou 0)."""
        with self._lock:
            state = self._progress(int(user_id))
        lessons, days, cards, last = set(), set(), 0, 0.0
        for key, value in state.items():
            if key.startswith("frkh-days-") and isinstance(value, list):
                days.update(value)
                continue
            if not isinstance(value, dict):
                continue
            for item, entry in value.items():
                if not isinstance(entry, dict):
                    continue
                last = max(last, float(entry.get("t") or 0))
                if key.startswith("frkh-done2-"):
                    if entry.get("d") == 1:
                        lessons.add(item)
                else:
                    cards += 1
        return {"lessons": len(lessons), "days": len(days), "cards": cards, "last": last}

    def reset_progress(self, user_id) -> None:
        """Efface la progression du compte. L'instant est noté : ce que les appareils du compte
        gardent d'avant cet instant sera ignoré, puis effacé chez eux à leur prochaine visite."""
        with self._lock, db.transaction(self._conn):
            self._conn.execute("DELETE FROM user_progress WHERE user_id = ?", (int(user_id),))
            self._conn.execute("UPDATE users SET progress_reset_at = ? WHERE id = ?", (int(self.clock() * 1000), int(user_id)))

    def import_shared_progress(self, user_id) -> int:
        """Reprend dans un compte la progression partagée de l'ancien serveur sans comptes
        (``database/progress-sync.json``). Renvoie le nombre de rubriques reprises."""
        state = progress_sync.load(self.config)
        incoming = {key: json.dumps(value, ensure_ascii=False) for key, value in state.items()}
        self._require(user_id)
        self.exchange_progress(user_id, incoming)
        return len(incoming)
