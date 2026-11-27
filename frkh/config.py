"""Configuration, chemins du projet, fichier .env et journalisation."""

from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path

DEFAULT_CONFIG: dict = {
    "site": {
        "title": "FR-KH Learning",
        "default_profile": "fr",
    },
    # Profils d'apprentissage, désignés par la langue de l'apprenant : c'est la langue de
    # l'interface et des explications. « learns » : langues étudiées, la principale en premier.
    "profiles": {
        "fr": {"label": "FR", "learns": ["km", "en"]},
        "en": {"label": "ENG", "learns": ["km", "fr"]},
        "km": {"label": "KH", "learns": ["fr", "en"]},
    },
    # Les deux personnages des dialogues ({A} et {B} dans les unités).
    "characters": {
        "A": {"name": {"latin": "Dara", "km": "ដារ៉ា", "tr": "da-ra", "ru": "Дара", "zh": "达拉", "zh_tr": "Dálā"},
              "gender": "f"},
        "B": {"name": {"latin": "Alex", "km": "អាឡិច", "tr": "a-lech", "ru": "Алекс", "zh": "亚历克斯",
                       "zh_tr": "Yàlìkèsī"}, "gender": "m"},
    },
    "schedule": {
        "time": "07:00",
        "timezone": "Asia/Phnom_Penh",
        "check_every_minutes": 15,
    },
    "lesson": {
        "level": "auto",
        "themes": [],
        "new_words": 6,
        "expressions": 4,
        "sentences": 3,
        "max_duration_minutes": 10,
    },
    "review": {
        "intervals_days": [1, 3, 7, 14, 30],
        "max_items": 10,
    },
    "languages": {
        "fr": {
            "locale": "fr-FR",
            "provider": "google",
            "voice": "fr-FR-Neural2-F",
            "fallback": {"provider": "azure", "voice": "fr-FR-DeniseNeural"},
        },
        "en": {
            "locale": "en-US",
            "provider": "google",
            "voice": "en-US-Neural2-F",
            "fallback": {"provider": "azure", "voice": "en-US-JennyNeural"},
        },
        "km": {
            "locale": "km-KH",
            "provider": "azure",
            "voice": "km-KH-SreymomNeural",
        },
        "es": {"locale": "es-ES", "provider": "google", "voice": "es-ES-Neural2-A",
               "fallback": {"provider": "azure", "voice": "es-ES-ElviraNeural"}},
        "it": {"locale": "it-IT", "provider": "google", "voice": "it-IT-Neural2-A",
               "fallback": {"provider": "azure", "voice": "it-IT-ElsaNeural"}},
        "ru": {"locale": "ru-RU", "provider": "google", "voice": "ru-RU-Wavenet-A",
               "fallback": {"provider": "azure", "voice": "ru-RU-SvetlanaNeural"}},
        "zh": {"locale": "zh-CN", "provider": "google", "voice": "cmn-CN-Wavenet-A",
               "fallback": {"provider": "azure", "voice": "zh-CN-XiaoxiaoNeural"}},
    },
    # Langues que les pages affichent par défaut (chacun peut ensuite en masquer dans le sélecteur).
    "display": {"languages": ["fr", "en", "km", "es", "it", "ru", "zh"]},
    "audio": {
        # « wav » (PCM 16 bits mono) ou « mp3 » (dix fois plus léger, recommandé pour un site publié ;
        # nécessite ffmpeg). Changer de format : « python3 manage.py audio convert ».
        "format": "wav",
        "mp3_bitrate_kbps": 48,
        "sample_rate_hz": 24000,
        "speaking_rate": 0.9,
        "pitch": 0.0,
        "include_examples": True,
    },
    "tts": {
        "timeout_seconds": 30,
        "retries": 3,
        "retry_backoff_seconds": 2.0,
        "limits": {
            "max_calls_per_run": 400,
            "max_chars_per_day": 20000,
            "max_chars_per_month": 300000,
        },
        "providers": {
            "google": {"endpoint": "https://texttospeech.googleapis.com/v1"},
            "azure": {"region": ""},
            "command": {"command": [], "output_format": "wav", "engine_version": "command-1"},
        },
    },
    "backup": {"keep": 14},
    # Serveur web avec comptes (« manage.py serve ») : voir docs/COMPTES.md.
    "server": {
        "require_login": True,        # False : le site se lit sans compte ; la progression en ligne en demande un
        "registration": "closed",     # « closed » : l'administrateur crée les comptes ; « open » : chacun crée le sien
        "registration_code": "",      # si renseigné, code d'invitation exigé à l'inscription
        "session_days": 30,           # durée d'une session sans visite
        "password_min_length": 8,
        "cookie_secure": "auto",      # « auto » : cookie « Secure » derrière un proxy HTTPS de confiance ; true ou false pour forcer
        "trust_proxy": False,         # True derrière un proxy inverse : X-Forwarded-For, -Proto et -Host sont alors crus
    },
    "logging": {"level": "INFO", "max_bytes": 1048576, "backups": 5},
}

LEVEL_LABELS = {
    "debutant": {"fr": "Débutant", "en": "Beginner", "km": "កម្រិតដំបូង"},
    "elementaire": {"fr": "Élémentaire", "en": "Elementary", "km": "កម្រិតបឋម"},
    "intermediaire": {"fr": "Intermédiaire", "en": "Intermediate", "km": "កម្រិតមធ្យម"},
}

# Décalages fixes utilisés seulement si la base de fuseaux horaires est absente
# (Windows sans le paquet « tzdata »). Le Cambodge n'applique pas l'heure d'été.
_FIXED_OFFSETS = {"Asia/Phnom_Penh": 7, "Asia/Bangkok": 7, "Asia/Ho_Chi_Minh": 7, "UTC": 0}


# Langues dans lesquelles l'interface et les explications existent : un profil doit en faire partie.
from .langs import CONTENT_LANGS, EXTRA_LANGS, PROFILE_LANGS  # noqa: E402
# Anciens profils (« A » : personne khmère, « B » : personne française) → nouveaux identifiants.
LEGACY_PROFILES = {"A": "km", "B": "fr"}


class ConfigError(Exception):
    pass


class Paths:
    """Tous les emplacements du projet, relatifs à sa racine."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or os.environ.get("FRKH_ROOT") or Path(__file__).resolve().parent.parent).resolve()
        self.config = self.root / "config" / "config.json"
        self.env = self.root / ".env"
        self.database_dir = self.root / "database"
        self.database = self.database_dir / "learning.db"
        self.backups = self.database_dir / "backups"
        self.lock = self.database_dir / ".generation.lock"
        self.lessons = self.root / "lessons"
        self.audio = self.root / "audio"
        self.data = self.root / "data"
        self.logs = self.root / "logs"
        self.templates = self.root / "templates"
        self.content = self.root / "content" / "units"
        self.css = self.root / "css"
        self.js = self.root / "js"
        self.fonts = self.root / "fonts"
        self.exports = self.root / "exports"
        self.index = self.root / "index.html"

    def ensure(self) -> None:
        for d in (self.database_dir, self.backups, self.lessons, self.audio, self.data, self.logs,
                  self.config.parent):
            d.mkdir(parents=True, exist_ok=True)

    def rel(self, path: Path | str) -> str:
        """Chemin relatif à la racine, avec des barres obliques (portable)."""
        return Path(path).resolve().relative_to(self.root).as_posix()


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_env(path: Path) -> dict[str, str]:
    """Charge un fichier .env (CLÉ=valeur) sans écraser l'environnement existant."""
    loaded: dict[str, str] = {}
    if not path.is_file():
        return loaded
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value:
            loaded[key] = value
            os.environ.setdefault(key, value)
    return loaded


class Config:
    def __init__(self, data: dict, paths: Paths, user_keys=()):
        self.data = data
        self.paths = paths
        self._user_keys = set(user_keys)

    def __getitem__(self, key: str):
        return self.data[key]

    def get(self, dotted: str, default=None):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    # --- temps ---------------------------------------------------------------
    def tzinfo(self) -> dt.tzinfo:
        name = self.get("schedule.timezone", "Asia/Phnom_Penh")
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:
            if name in _FIXED_OFFSETS:
                return dt.timezone(dt.timedelta(hours=_FIXED_OFFSETS[name]), name)
            raise ConfigError(
                f"Fuseau horaire inconnu : {name}. Sous Windows, installez le paquet « tzdata » "
                f"(pip install tzdata) ou utilisez Asia/Phnom_Penh.")

    def now(self) -> dt.datetime:
        forced = os.environ.get("FRKH_NOW")
        if forced:
            value = dt.datetime.fromisoformat(forced)
            return value.astimezone(self.tzinfo()) if value.tzinfo else value.replace(tzinfo=self.tzinfo())
        return dt.datetime.now(self.tzinfo())

    def today(self) -> dt.date:
        return self.now().date()

    def schedule_time(self) -> dt.time:
        raw = str(self.get("schedule.time", "07:00"))
        try:
            hour, minute = raw.split(":")
            return dt.time(int(hour), int(minute))
        except ValueError as exc:
            raise ConfigError(f"Heure de génération invalide : {raw!r} (attendu HH:MM)") from exc

    # --- profils et personnages ------------------------------------------------------
    def profiles(self) -> dict[str, dict]:
        """Profils valides, dans l'ordre de la configuration : {"fr": {"label": "FR", "learns": [...]}, …}."""
        out: dict[str, dict] = {}
        for key, spec in (self.data.get("profiles") or {}).items():
            if key not in PROFILE_LANGS or not isinstance(spec, dict):
                continue
            learns = [lang for lang in spec.get("learns") or [] if lang in PROFILE_LANGS and lang != key]
            out[key] = {"label": str(spec.get("label") or key.upper()),
                        "learns": learns or [lang for lang in PROFILE_LANGS if lang != key]}
        return out or {"fr": {"label": "FR", "learns": ["km", "en"]}}

    def default_profile(self) -> str:
        value = str(self.get("site.default_profile", "fr"))
        value = LEGACY_PROFILES.get(value, value)
        profiles = self.profiles()
        return value if value in profiles else next(iter(profiles))

    def characters(self) -> dict:
        """Les deux personnages des dialogues. Accepte l'ancienne rubrique « learners »."""
        legacy = self.data.get("learners")
        if isinstance(legacy, dict) and legacy and "characters" not in self._user_keys:
            return legacy
        return self.data.get("characters") or {}

    # --- langues ---------------------------------------------------------------
    def locale(self, lang: str) -> str:
        return self.data["languages"][lang]["locale"]

    def content_langs(self) -> tuple[str, ...]:
        """Langues des leçons : celles des profils, puis les langues supplémentaires configurées."""
        configured = self.data.get("languages", {})
        return PROFILE_LANGS + tuple(lang for lang in EXTRA_LANGS if lang in configured)

    def display_langs(self) -> list[str]:
        """Langues visibles par défaut dans les pages."""
        wanted = self.get("display.languages") or list(CONTENT_LANGS)
        langs = [lang for lang in self.content_langs() if lang in wanted]
        return langs or list(PROFILE_LANGS)

    def audio_format(self) -> str:
        return str(self.get("audio.format", "wav") or "wav").lower()

    def validate(self) -> list[str]:
        """Retourne la liste des problèmes de configuration (vide si tout va bien)."""
        problems: list[str] = []
        try:
            self.tzinfo()
            self.schedule_time()
        except ConfigError as exc:
            problems.append(str(exc))
        for lang in self.content_langs():
            spec = self.data.get("languages", {}).get(lang)
            if not spec or not spec.get("locale") or not spec.get("provider"):
                problems.append(f"languages.{lang} : « locale » et « provider » sont obligatoires")
        if self.audio_format() not in ("wav", "mp3"):
            problems.append(f"audio.format = {self.get('audio.format')!r} : valeurs admises « mp3 » ou « wav »")
        if self.audio_format() == "mp3" and int(self.get("audio.mp3_bitrate_kbps", 48)) not in (32, 40, 48, 56, 64, 80, 96, 112, 128):
            problems.append("audio.mp3_bitrate_kbps : valeurs admises 32, 40, 48, 56, 64, 80, 96, 112 ou 128")
        unknown = [lang for lang in self.get("display.languages", []) or [] if lang not in CONTENT_LANGS]
        if unknown:
            problems.append(f"display.languages : langue(s) inconnue(s) {', '.join(map(str, unknown))} "
                            f"(possibles : {', '.join(CONTENT_LANGS)})")
        rate = self.get("audio.sample_rate_hz")
        if rate not in (16000, 22050, 24000, 44100, 48000):
            problems.append(f"audio.sample_rate_hz = {rate} : valeurs admises 22050 ou 24000 (16000, 44100, 48000 tolérées)")
        speed = self.get("audio.speaking_rate", 1.0)
        if not isinstance(speed, (int, float)) or not 0.5 <= speed <= 1.5:
            problems.append("audio.speaking_rate doit être compris entre 0.5 et 1.5")
        lesson = self.data.get("lesson", {})
        if not 5 <= int(lesson.get("new_words", 0)) <= 8:
            problems.append("lesson.new_words doit être compris entre 5 et 8")
        if not 3 <= int(lesson.get("expressions", 0)) <= 5:
            problems.append("lesson.expressions doit être compris entre 3 et 5")
        if int(lesson.get("max_duration_minutes", 10)) > 10:
            problems.append("lesson.max_duration_minutes ne doit pas dépasser 10")
        intervals = self.get("review.intervals_days", [])
        if not intervals or sorted(intervals) != list(intervals) or min(intervals) < 1:
            problems.append("review.intervals_days doit être une liste croissante de jours (ex. [1, 3, 7, 14, 30])")
        section = "learners" if self.characters() is self.data.get("learners") else "characters"
        for key in ("A", "B"):
            character = self.characters().get(key, {})
            if not character.get("name", {}).get("latin") or not character.get("name", {}).get("km"):
                problems.append(f"{section}.{key}.name : « latin » et « km » sont obligatoires")
            if character.get("gender") not in ("f", "m"):
                problems.append(f"{section}.{key}.gender doit valoir « f » ou « m »")
        for key, spec in (self.data.get("profiles") or {}).items():
            if key not in PROFILE_LANGS:
                problems.append(f"profiles.{key} : profil inconnu (langues possibles : {', '.join(PROFILE_LANGS)})")
            elif not isinstance(spec, dict) or any(lang not in PROFILE_LANGS or lang == key for lang in spec.get("learns") or []):
                problems.append(f"profiles.{key}.learns : langues étudiées parmi {', '.join(PROFILE_LANGS)}, sauf « {key} »")
        server = self.data.get("server") or {}
        if server.get("registration", "closed") not in ("closed", "open"):
            problems.append("server.registration : valeurs admises « closed » ou « open »")
        if server.get("cookie_secure", "auto") not in ("auto", True, False):
            problems.append("server.cookie_secure : valeurs admises « auto », true ou false")
        days = server.get("session_days", 30)
        if isinstance(days, bool) or not isinstance(days, (int, float)) or not 0 < days <= 365:
            problems.append("server.session_days doit être compris entre 1 et 365")
        length = server.get("password_min_length", 8)
        if isinstance(length, bool) or not isinstance(length, int) or not 6 <= length <= 64:
            problems.append("server.password_min_length doit être compris entre 6 et 64")
        default = LEGACY_PROFILES.get(str(self.get("site.default_profile", "fr")), str(self.get("site.default_profile", "fr")))
        if default not in self.profiles():
            problems.append(f"site.default_profile = {default!r} : doit être l'un des profils ({', '.join(self.profiles())})")
        return problems


def load_config(root: Path | str | None = None, create: bool = False) -> Config:
    paths = Paths(root)
    load_env(paths.env)
    user: dict = {}
    if paths.config.is_file():
        try:
            user = json.loads(paths.config.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ConfigError(f"config/config.json est illisible : {exc}") from exc
    elif create:
        paths.config.parent.mkdir(parents=True, exist_ok=True)
        paths.config.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return Config(_merge(DEFAULT_CONFIG, user), paths, user_keys=user.keys())


def setup_logging(config: Config, console: bool = True, quiet: bool = False) -> logging.Logger:
    """Journal général (logs/app.log) et journal d'erreurs (logs/errors.log), avec rotation."""
    logger = logging.getLogger("frkh")
    if getattr(logger, "_frkh_ready", False):
        return logger
    level = getattr(logging, str(config.get("logging.level", "INFO")).upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False
    config.paths.logs.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s — %(message)s", "%Y-%m-%d %H:%M:%S")
    kwargs = dict(maxBytes=int(config.get("logging.max_bytes", 1048576)),
                  backupCount=int(config.get("logging.backups", 5)), encoding="utf-8")
    app = logging.handlers.RotatingFileHandler(config.paths.logs / "app.log", **kwargs)
    app.setFormatter(fmt)
    logger.addHandler(app)
    err = logging.handlers.RotatingFileHandler(config.paths.logs / "errors.log", **kwargs)
    err.setLevel(logging.WARNING)
    err.setFormatter(fmt)
    logger.addHandler(err)
    if console and sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setLevel(logging.WARNING if quiet else level)
        stream.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(stream)
    logger._frkh_ready = True  # type: ignore[attr-defined]
    return logger
