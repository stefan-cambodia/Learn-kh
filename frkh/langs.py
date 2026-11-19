"""Langues du contenu : les trois langues des profils et les langues supplémentaires.

Les profils (fr, en, km) décident de la langue de l'interface et des explications.
Les leçons montrent en plus l'espagnol, l'italien, le russe et le chinois ; chacun
choisit dans la page les langues qu'il veut voir.

Les traductions supplémentaires sont rangées dans les unités (``es``, ``it``, ``ru``,
``zh`` et ``zh_tr`` pour le pinyin). Le russe reçoit une translittération latine
calculée automatiquement (``ru_tr`` permet de l'imposer). Les leçons créées avant
l'ajout de ces langues sont complétées à partir des unités (``Translations``).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

from .textutil import normalize_text

PROFILE_LANGS = ("fr", "en", "km")
EXTRA_LANGS = ("es", "it", "ru", "zh")
CONTENT_LANGS = PROFILE_LANGS + EXTRA_LANGS

# Champ de translittération de chaque langue qui en a une.
TRANSLIT_FIELD = {"km": "tr", "ru": "ru_tr", "zh": "zh_tr"}
EXTRA_FIELDS = EXTRA_LANGS + ("zh_tr", "ru_tr")

LANG_META = {
    "fr": {"tag": "FR", "listen": "Écouter en français", "locale": "fr-FR", "native": "Français",
           "names": {"fr": "français", "en": "French", "km": "ភាសាបារាំង"}},
    "en": {"tag": "EN", "listen": "Listen in English", "locale": "en-US", "native": "English",
           "names": {"fr": "anglais", "en": "English", "km": "ភាសាអង់គ្លេស"}},
    "km": {"tag": "KH", "listen": "ស្តាប់ជាភាសាខ្មែរ", "locale": "km-KH", "native": "ខ្មែរ",
           "names": {"fr": "khmer", "en": "Khmer", "km": "ភាសាខ្មែរ"}},
    "es": {"tag": "ES", "listen": "Escuchar en español", "locale": "es-ES", "native": "Español",
           "names": {"fr": "espagnol", "en": "Spanish", "km": "ភាសាអេស្ប៉ាញ"}},
    "it": {"tag": "IT", "listen": "Ascolta in italiano", "locale": "it-IT", "native": "Italiano",
           "names": {"fr": "italien", "en": "Italian", "km": "ភាសាអ៊ីតាលី"}},
    "ru": {"tag": "RU", "listen": "Слушать по-русски", "locale": "ru-RU", "native": "Русский",
           "names": {"fr": "russe", "en": "Russian", "km": "ភាសារុស្ស៊ី"}},
    "zh": {"tag": "ZH", "listen": "用中文听", "locale": "zh-CN", "native": "中文",
           "names": {"fr": "chinois", "en": "Chinese", "km": "ភាសាចិន"}},
}

# Attribut lang de la translittération affichée sous le texte.
TRANSLIT_LANG = {"km": "km-Latn", "ru": "ru-Latn", "zh": "zh-Latn-pinyin"}


# --- Russe : translittération latine -------------------------------------------------------
_RU = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y",
    "ь": "'", "э": "e", "ю": "yu", "я": "ya",
}
_RU_VOWELS = set("аеёиоуыэюяъь")


def ru_translit(text: str) -> str:
    """Translittération lisible du russe : привет → privet, спасибо → spasibo, ещё → yeshchyo.

    « е » se lit « ye » en début de mot et après une voyelle (ель → yel', поехать → poyekhat').
    L'accent tonique n'est pas noté.
    """
    text = unicodedata.normalize("NFC", text or "")
    out: list[str] = []
    prev = ""
    for ch in text:
        low = ch.lower()
        if low in _RU:
            value = _RU[low]
            if low == "е" and (not prev or prev in _RU_VOWELS or not prev.isalpha()):
                value = "ye"
            if ch != low and value:
                value = value[0].upper() + value[1:]
            out.append(value)
        else:
            out.append(ch)
        prev = low
    return "".join(out)


def has_cyrillic(text: str) -> bool:
    return any("CYRILLIC" in unicodedata.name(c, "") for c in text if c.isalpha())


def has_han(text: str) -> bool:
    return any(0x4E00 <= ord(c) <= 0x9FFF or 0x3400 <= ord(c) <= 0x4DBF for c in text)


def translit(entry: dict, lang: str) -> str:
    """Translittération affichée sous le texte d'une langue (vide si la langue n'en a pas)."""
    field = TRANSLIT_FIELD.get(lang)
    if not field:
        return ""
    value = entry.get(field) or ""
    if not value and lang == "ru" and entry.get("ru"):
        value = ru_translit(entry["ru"])
    return value


def lang_name(lang: str, ui: str = "fr") -> str:
    return LANG_META[lang]["names"].get(ui) or LANG_META[lang]["names"]["fr"]


# --- Complément des leçons existantes -----------------------------------------------------------
def _key(entry: dict) -> tuple[str, str]:
    return (normalize_text(entry.get("fr", "")).lower(), normalize_text(entry.get("en", "")).lower())


def _walk(content: dict):
    """Toutes les entrées traduisibles d'une leçon (mots, exemples, phrases, répliques, révision)."""
    for section in ("vocabulary", "expressions", "sentences"):
        for entry in content.get(section) or []:
            yield entry
            if isinstance(entry.get("example"), dict):
                yield entry["example"]
    for line in (content.get("dialogue") or {}).get("lines") or []:
        yield line
    review = content.get("review") or {}
    for entry in review.get("words") or []:
        yield entry
        if isinstance(entry.get("example"), dict):
            yield entry["example"]
    for entry in review.get("questions") or []:
        yield entry
    if isinstance(review.get("translation"), dict):
        yield review["translation"]


def unit_entries(unit: dict):
    """Entrées traduisibles d'une unité du programme."""
    for section in ("vocabulary", "expressions", "sentences"):
        for entry in unit.get(section) or []:
            if isinstance(entry, dict):
                yield entry
                if isinstance(entry.get("example"), dict):
                    yield entry["example"]
    for line in (unit.get("dialogue") or {}).get("lines") or []:
        if isinstance(line, dict):
            yield line


class Translations:
    """Index des traductions supplémentaires des unités, par couple (français, anglais).

    Sert à compléter les leçons enregistrées avant l'ajout d'une langue, et les mots
    de révision reconstruits depuis la base.
    """

    def __init__(self, units_dir: Path, characters: dict, logger: logging.Logger | None = None):
        from .curriculum import personalize_tree
        self.index: dict[tuple[str, str], dict] = {}
        self.by_fr: dict[str, dict] = {}
        log = logger or logging.getLogger("frkh.langs")
        for path in sorted(Path(units_dir).glob("*.json")):
            try:
                unit = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.warning("Unité illisible pour les traductions : %s (%s)", path.name, exc)
                continue
            unit = personalize_tree(unit, characters)
            for entry in unit_entries(unit):
                extra = {f: entry[f] for f in EXTRA_FIELDS if isinstance(entry.get(f), str) and entry[f].strip()}
                if not extra:
                    continue
                key = _key(entry)
                self.index.setdefault(key, extra)
                self.by_fr.setdefault(key[0], extra)

    def lookup(self, entry: dict) -> dict:
        key = _key(entry)
        return self.index.get(key) or self.by_fr.get(key[0]) or {}

    def enrich(self, content: dict) -> bool:
        """Complète (ou met à jour) les langues supplémentaires d'une leçon ; True si quelque chose a changé."""
        changed = False
        for entry in _walk(content):
            if not isinstance(entry, dict) or not entry.get("fr"):
                continue
            for field, value in self.lookup(entry).items():
                if entry.get(field) != value:
                    entry[field] = value
                    changed = True
        return changed


_SPACES = re.compile(r"\s+")


def search_text(entry: dict) -> str:
    """Tous les textes d'une entrée, pour la recherche (langues et translittérations)."""
    parts = [entry.get(lang, "") for lang in CONTENT_LANGS]
    parts += [translit(entry, lang) for lang in TRANSLIT_FIELD]
    return _SPACES.sub(" ", " ".join(p for p in parts if p)).strip()
