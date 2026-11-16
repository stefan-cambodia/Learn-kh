"""Outils de texte : normalisation, slugs, écriture khmère, dates trilingues."""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata

LANGS = ("fr", "en", "km")

# --- Normalisation -----------------------------------------------------------

_INVISIBLE = dict.fromkeys(map(ord, "​﻿⁠"), None)
_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Forme canonique d'un texte : NFC, sans espaces invisibles, espaces réduits.

    C'est cette forme qui est affichée, envoyée au moteur vocal et hachée pour
    le cache audio : deux textes identiques à l'œil donnent donc la même clé.
    """
    if text is None:
        return ""
    text = unicodedata.normalize("NFC", str(text)).translate(_INVISIBLE)
    return _WS.sub(" ", text).strip()


def fold(text: str) -> str:
    """Forme de recherche : minuscules, sans accents latins (le khmer est conservé)."""
    text = normalize_text(text).lower()
    out = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn" and not is_khmer(ch):
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out)).replace("œ", "oe").replace("æ", "ae")


def slugify(text: str, max_len: int = 32, default: str = "audio") -> str:
    """Slug ASCII déterministe pour les noms de fichiers."""
    text = fold(text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or default


# --- Écriture khmère ---------------------------------------------------------

KH_CONSONANTS = (0x1780, 0x17A2)
KH_INDEP_VOWELS = (0x17A3, 0x17B3)
KH_DEP_VOWELS = (0x17B6, 0x17C5)
KH_COENG = 0x17D2
KH_SHIFTERS = (0x17C9, 0x17CA)
KH_SIGNS = set(range(0x17C6, 0x17D2)) | {0x17DD}
KH_DEPRECATED = {0x17A3, 0x17A4, 0x17B4, 0x17B5, 0x17D3, 0x17D8}
KH_DIGITS = "០១២៣៤៥៦៧៨៩"


def is_khmer(ch: str) -> bool:
    return 0x1780 <= ord(ch) <= 0x17FF or 0x19E0 <= ord(ch) <= 0x19FF


def has_khmer(text: str) -> bool:
    return any(is_khmer(c) for c in text)


def has_latin(text: str) -> bool:
    return any("LATIN" in unicodedata.name(c, "") for c in text if c.isalpha())


def _in(cp: int, rng: tuple[int, int]) -> bool:
    return rng[0] <= cp <= rng[1]


def khmer_issues(text: str) -> list[tuple[str, str]]:
    """Contrôle la structure orthographique d'un texte khmer.

    Retourne une liste de (gravité, message). Ce contrôle repère les fautes de
    frappe structurelles (voyelle sans consonne, pied de lettre orphelin,
    signes doublés…) ; il ne remplace pas la relecture d'un locuteur natif.
    """
    issues: list[tuple[str, str]] = []
    cps = [ord(c) for c in text]
    for i, cp in enumerate(cps):
        if not 0x1780 <= cp <= 0x17FF:
            continue
        prev = cps[i - 1] if i else None
        nxt = cps[i + 1] if i + 1 < len(cps) else None
        here = f"« {text[max(0, i - 3): i + 3]} » (position {i + 1})"
        prev_is_letter = prev is not None and 0x1780 <= prev <= 0x17D3 or prev == 0x17DD

        if cp in KH_DEPRECATED:
            issues.append(("warning", f"caractère khmer déconseillé U+{cp:04X} dans {here}"))
        if cp == KH_COENG:
            if nxt is None or not (_in(nxt, KH_CONSONANTS) or _in(nxt, KH_INDEP_VOWELS)):
                issues.append(("error", f"signe ្ (coeng) non suivi d'une consonne dans {here}"))
            # Une voyelle indépendante peut porter un pied de lettre : ឱ្យ / ឲ្យ (« donner »).
            if prev is None or not (_in(prev, KH_CONSONANTS) or _in(prev, KH_INDEP_VOWELS)
                                    or _in(prev, KH_SHIFTERS) or prev == 0x17CC):
                issues.append(("error", f"signe ្ (coeng) sans consonne de base dans {here}"))
            elif _in(prev, KH_SHIFTERS):
                issues.append(("warning", f"signe diacritique placé avant un pied de lettre dans {here}"))
        elif _in(cp, KH_DEP_VOWELS) or cp in KH_SIGNS:
            if not prev_is_letter:
                issues.append(("error", f"voyelle ou signe sans consonne de base dans {here}"))
            elif prev == cp:
                issues.append(("error", f"signe doublé dans {here}"))
            elif _in(cp, KH_DEP_VOWELS) and _in(prev, KH_DEP_VOWELS):
                issues.append(("error", f"deux voyelles dépendantes consécutives dans {here}"))
            elif _in(cp, KH_SHIFTERS) and _in(prev, KH_DEP_VOWELS):
                issues.append(("warning", f"ordre inhabituel (voyelle avant ៉/៊) dans {here}"))
    return issues


def to_khmer_digits(value) -> str:
    return "".join(KH_DIGITS[int(c)] if c.isdigit() else c for c in str(value))


# --- Dates -------------------------------------------------------------------

_FR_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre"]
_EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
_KM_DAYS = ["ច័ន្ទ", "អង្គារ", "ពុធ", "ព្រហស្បតិ៍", "សុក្រ", "សៅរ៍", "អាទិត្យ"]
_KM_MONTHS = ["មករា", "កុម្ភៈ", "មីនា", "មេសា", "ឧសភា", "មិថុនា", "កក្កដា", "សីហា",
              "កញ្ញា", "តុលា", "វិច្ឆិកា", "ធ្នូ"]


def parse_date(value: str | _dt.date) -> _dt.date:
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    return _dt.date.fromisoformat(str(value))


def format_date(value, lang: str = "fr", weekday: bool = True) -> str:
    d = parse_date(value)
    if lang == "km":
        day = f"ថ្ងៃ{_KM_DAYS[d.weekday()]} " if weekday else ""
        return f"{day}ទី{to_khmer_digits(d.day)} ខែ{_KM_MONTHS[d.month - 1]} ឆ្នាំ{to_khmer_digits(d.year)}"
    if lang == "en":
        day = f"{_EN_DAYS[d.weekday()]}, " if weekday else ""
        return f"{day}{_EN_MONTHS[d.month - 1]} {d.day}, {d.year}"
    day = f"{_FR_DAYS[d.weekday()]} " if weekday else ""
    num = "1er" if d.day == 1 else str(d.day)
    return f"{day}{num} {_FR_MONTHS[d.month - 1]} {d.year}"


# --- Texte prononcé ----------------------------------------------------------

def speech_text(text: str) -> str:
    """Texte réellement envoyé au moteur vocal pour un texte affiché.

    « បាទ / ចាស » se lit comme deux mots séparés par une pause, et les points
    de suspension d'une phrase à compléter (« Je m'appelle… ») ne se lisent pas.
    """
    text = normalize_text(text).replace(" / ", ", ").replace("…", "").replace("...", "")
    return normalize_text(text)
