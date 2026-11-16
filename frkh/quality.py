"""Contrôle qualité des contenus trilingues (unités du programme et leçons).

Utilisable seul :  python3 -m frkh.quality content/units/u001-salutations.json
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .textutil import fold, has_khmer, has_latin, khmer_issues, normalize_text

LEVELS = ("debutant", "elementaire", "intermediaire")
POS = ("nom", "verbe", "adjectif", "adverbe", "pronom", "interjection", "nombre",
       "preposition", "conjonction", "particule", "interrogatif", "expression")
PLACEHOLDERS = ("{A}", "{B}", "{A_yes}", "{B_yes}")
_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")
_LIMITS = {"vocabulary": (5, 8), "expressions": (3, 5), "sentences": (3, 3)}


@dataclass
class Issue:
    level: str      # "error" | "warning" | "info"
    where: str
    message: str

    def __str__(self) -> str:
        tag = {"error": "ERREUR", "warning": "ATTENTION", "info": "INFO"}[self.level]
        return f"[{tag}] {self.where} : {self.message}"


def _strip_placeholders(text: str) -> str:
    return _PLACEHOLDER_RE.sub("", text)


def check_trilingual(entry, where: str, need_tr: bool = True, langs=("fr", "en", "km"),
                     mixed: bool = False) -> list[Issue]:
    """Vérifie la présence et la cohérence d'une entrée {fr, en, km, tr}.

    ``mixed`` : texte explicatif (note, conseil) qui peut citer une autre langue.
    """
    issues: list[Issue] = []
    if not isinstance(entry, dict):
        return [Issue("error", where, "entrée absente ou mal formée")]
    for lang in langs:
        raw = entry.get(lang)
        if not isinstance(raw, str) or not normalize_text(raw):
            issues.append(Issue("error", where, f"texte « {lang} » manquant"))
            continue
        for ph in _PLACEHOLDER_RE.findall(raw):
            if ph not in PLACEHOLDERS:
                issues.append(Issue("error", where, f"variable inconnue {ph} ({lang})"))
            elif ph.endswith("_yes}") and lang != "km":
                issues.append(Issue("error", where, f"{ph} n'est permis qu'en khmer et en translittération"))
        text = _strip_placeholders(normalize_text(raw))
        if lang == "km":
            if not has_khmer(text):
                issues.append(Issue("error", where, "le khmer doit être écrit en caractères khmers"))
            if has_latin(text) and not mixed:
                issues.append(Issue("warning", where, f"lettres latines dans le khmer : « {text} »"))
            if text.rstrip().endswith("."):
                issues.append(Issue("warning", where, "phrase khmère terminée par un point latin (utiliser ។)"))
            for level, msg in khmer_issues(text):
                issues.append(Issue(level, where, f"orthographe khmère — {msg}"))
        elif has_khmer(text) and not mixed:
            issues.append(Issue("error", where, f"caractères khmers dans le texte « {lang} »"))
    if need_tr and "km" in langs:
        tr = entry.get("tr")
        if not isinstance(tr, str) or not normalize_text(tr):
            issues.append(Issue("warning", where, "translittération (tr) manquante"))
        else:
            if has_khmer(tr):
                issues.append(Issue("error", where, "la translittération doit être en lettres latines"))
            for ph in _PLACEHOLDER_RE.findall(tr):
                if ph not in PLACEHOLDERS:
                    issues.append(Issue("error", where, f"variable inconnue {ph} (tr)"))
    fr, en = entry.get("fr"), entry.get("en")
    # Les explications (mixed) ne sont pas des traductions l'une de l'autre : chacune vise son lecteur.
    if not mixed and isinstance(fr, str) and isinstance(en, str) and min(len(fr), len(en)) > 0:
        ratio = max(len(fr), len(en)) / min(len(fr), len(en))
        if ratio > 3.2 and max(len(fr), len(en)) > 24:
            issues.append(Issue("warning", where, "longueurs français/anglais très différentes : traduction à relire"))
    if entry.get("uncertain"):
        note = entry.get("uncertain_note") or "traduction signalée comme incertaine"
        issues.append(Issue("info", where, f"à vérifier par un locuteur natif — {note}"))
    return issues


def check_unit(unit: dict, name: str = "") -> list[Issue]:
    """Valide une unité complète du programme."""
    w = name or unit.get("id", "?")
    issues: list[Issue] = []
    if not re.fullmatch(r"u\d{3}", str(unit.get("id", ""))):
        issues.append(Issue("error", w, "identifiant attendu sous la forme u001"))
    if not isinstance(unit.get("order"), int):
        issues.append(Issue("error", w, "champ « order » (entier) manquant"))
    if unit.get("level") not in LEVELS:
        issues.append(Issue("error", w, f"niveau invalide (attendu : {', '.join(LEVELS)})"))
    if not re.fullmatch(r"[a-z0-9-]+", str(unit.get("theme", ""))):
        issues.append(Issue("error", w, "thème attendu en minuscules-avec-tirets"))
    issues += check_trilingual(unit.get("title"), f"{w}/title", need_tr=False)
    tip = unit.get("tip")
    if tip is not None:
        issues += check_trilingual(tip, f"{w}/tip", need_tr=False, langs=("fr", "en", "km"), mixed=True)

    for section, (lo, hi) in _LIMITS.items():
        items = unit.get(section)
        if not isinstance(items, list):
            issues.append(Issue("error", f"{w}/{section}", "section manquante"))
            continue
        if not lo <= len(items) <= hi:
            issues.append(Issue("error", f"{w}/{section}", f"{len(items)} entrées (attendu : {lo} à {hi})"))
        for i, item in enumerate(items, 1):
            here = f"{w}/{section}[{i}]"
            issues += check_trilingual(item, here)
            if not isinstance(item, dict):
                continue
            if section == "vocabulary":
                if item.get("pos") not in POS:
                    issues.append(Issue("error", here, f"catégorie grammaticale invalide : {item.get('pos')!r}"))
                issues += check_trilingual(item.get("example"), f"{here}/example")
            if section in ("vocabulary", "expressions"):
                issues += check_trilingual(item.get("note"), f"{here}/note", need_tr=False,
                                           langs=("fr", "en", "km"), mixed=True)
            if section == "sentences" and item.get("situation") is not None:
                issues += check_trilingual(item.get("situation"), f"{here}/situation", need_tr=False, langs=("fr", "en", "km"))

    dialogue = unit.get("dialogue")
    if not isinstance(dialogue, dict) or not isinstance(dialogue.get("lines"), list):
        issues.append(Issue("error", f"{w}/dialogue", "dialogue manquant"))
    else:
        issues += check_trilingual(dialogue.get("setting"), f"{w}/dialogue/setting", need_tr=False)
        lines = dialogue["lines"]
        if not 4 <= len(lines) <= 8:
            issues.append(Issue("error", f"{w}/dialogue", f"{len(lines)} répliques (attendu : 4 à 8)"))
        speakers = set()
        for i, line in enumerate(lines, 1):
            here = f"{w}/dialogue[{i}]"
            issues += check_trilingual(line, here)
            if isinstance(line, dict):
                if line.get("speaker") not in ("A", "B"):
                    issues.append(Issue("error", here, "locuteur attendu : A ou B"))
                speakers.add(line.get("speaker"))
        if isinstance(lines, list) and lines and speakers != {"A", "B"}:
            issues.append(Issue("error", f"{w}/dialogue", "le dialogue doit faire parler A et B"))

    comp = unit.get("comprehension")
    if not isinstance(comp, dict):
        issues.append(Issue("error", f"{w}/comprehension", "question de compréhension manquante"))
    else:
        issues += check_trilingual(comp.get("question"), f"{w}/comprehension/question", need_tr=False)
        issues += check_trilingual(comp.get("answer"), f"{w}/comprehension/answer", need_tr=False)
    return issues


def vocab_key(entry: dict) -> str:
    """Clé d'identité d'un mot ou d'une expression (insensible aux accents et à la casse)."""
    fr = re.sub(r"[^\w\s']", " ", fold(entry.get("fr", "")))
    en = re.sub(r"[^\w\s']", " ", fold(entry.get("en", "")))
    return " ".join(fr.split()) + " | " + " ".join(en.split())


def check_bank(units: list[dict]) -> list[Issue]:
    """Contrôles transversaux : identifiants, ordre et doublons de vocabulaire."""
    issues: list[Issue] = []
    seen_ids: dict[str, str] = {}
    seen_order: dict[int, str] = {}
    seen_vocab: dict[str, str] = {}
    for unit in units:
        uid = str(unit.get("id"))
        if uid in seen_ids:
            issues.append(Issue("error", uid, "identifiant d'unité en double"))
        seen_ids[uid] = uid
        order = unit.get("order")
        if order in seen_order:
            issues.append(Issue("error", uid, f"même numéro d'ordre que {seen_order[order]}"))
        seen_order[order] = uid
        for section in ("vocabulary", "expressions"):
            for item in unit.get(section) or []:
                if not isinstance(item, dict):
                    continue
                key = vocab_key(item)
                if key in seen_vocab and seen_vocab[key] != uid:
                    issues.append(Issue("warning", f"{uid}/{section}",
                                        f"« {item.get('fr')} » déjà enseigné dans {seen_vocab[key]}"))
                seen_vocab.setdefault(key, uid)
    return issues


def summarize(issues: list[Issue]) -> dict:
    return {
        "errors": sum(1 for i in issues if i.level == "error"),
        "warnings": sum(1 for i in issues if i.level == "warning"),
        "uncertain": sum(1 for i in issues if i.level == "info"),
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    paths = [Path(a) for a in argv] or sorted(Path("content/units").glob("*.json"))
    units, issues = [], []
    for path in paths:
        try:
            unit = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(Issue("error", path.name, f"fichier illisible : {exc}"))
            continue
        units.append(unit)
        issues += check_unit(unit, path.stem)
    issues += check_bank(units)
    for issue in issues:
        print(issue)
    s = summarize(issues)
    print(f"{len(units)} unité(s) — {s['errors']} erreur(s), {s['warnings']} avertissement(s), "
          f"{s['uncertain']} traduction(s) à vérifier")
    return 1 if s["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
