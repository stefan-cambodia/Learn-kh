"""Programme pédagogique : chargement des unités et personnalisation des textes."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .quality import Issue, check_bank, check_unit
from .langs import ru_translit
from .textutil import normalize_text

TEXT_FIELDS = ("fr", "en", "km", "tr", "es", "it", "ru", "zh", "zh_tr", "ru_tr")
_YES = {"m": {"km": "បាទ", "tr": "bat"}, "f": {"km": "ចាស", "tr": "tchah"}}


def personalize(text: str, field: str, characters: dict) -> str:
    """Remplace {A}, {B}, {A_yes}, {B_yes} par les prénoms des personnages et la particule de politesse."""
    if "{" not in text:
        return text
    for key in ("A", "B"):
        learner = characters.get(key, {})
        name = learner.get("name", {})
        if field in ("km", "tr", "ru", "zh", "zh_tr"):
            shown = name.get(field) or name.get("latin") or key
        elif field == "ru_tr":
            shown = ru_translit(name["ru"]) if name.get("ru") else (name.get("latin") or key)
        else:
            shown = name.get("latin") or key
        yes = _YES.get(learner.get("gender", "f"), _YES["f"])
        text = text.replace("{%s_yes}" % key, yes["km"] if field == "km" else yes["tr"])
        text = text.replace("{%s}" % key, shown)
    return text


def personalize_tree(node, characters: dict):
    """Normalise et personnalise tous les textes d'une structure de contenu."""
    if isinstance(node, dict):
        return {key: (personalize(normalize_text(value), key, characters)
                      if key in TEXT_FIELDS and isinstance(value, str) else personalize_tree(value, characters))
                for key, value in node.items()}
    if isinstance(node, list):
        return [personalize_tree(item, characters) for item in node]
    return node


class Curriculum:
    """Les unités valides, dans l'ordre de progression."""

    def __init__(self, units_dir: Path, logger: logging.Logger | None = None):
        self.units_dir = Path(units_dir)
        self.log = logger or logging.getLogger("frkh.curriculum")
        self.units: list[dict] = []
        self.rejected: list[tuple[str, list[Issue]]] = []
        self.issues: list[Issue] = []

    def load(self) -> "Curriculum":
        self.units, self.rejected, self.issues = [], [], []
        for path in sorted(self.units_dir.glob("*.json")):
            try:
                unit = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                issue = Issue("error", path.name, f"fichier illisible : {exc}")
                self.rejected.append((path.name, [issue]))
                self.issues.append(issue)
                continue
            issues = check_unit(unit, path.stem)
            self.issues += issues
            if any(i.level == "error" for i in issues):
                # Une unité fautive n'est jamais servie : mieux vaut une leçon de révision qu'une leçon fausse.
                self.rejected.append((path.name, [i for i in issues if i.level == "error"]))
                self.log.error("Unité écartée (%s) : %d erreur(s)", path.name,
                               sum(1 for i in issues if i.level == "error"))
                continue
            unit["_file"] = path.name
            self.units.append(unit)
        self.units.sort(key=lambda u: (u.get("order", 0), u.get("id", "")))
        self.issues += check_bank(self.units)
        return self

    def get(self, unit_id: str) -> dict | None:
        return next((u for u in self.units if u.get("id") == unit_id), None)

    def next_unit(self, used: set[str], level: str = "auto", themes: list[str] | None = None) -> dict | None:
        """Prochaine unité jamais utilisée ; les thèmes configurés passent en premier."""
        candidates = [u for u in self.units if u["id"] not in used]
        if level and level != "auto":
            candidates = [u for u in candidates if u["level"] == level]
        if themes:
            preferred = [u for u in candidates if u["theme"] in themes]
            preferred.sort(key=lambda u: (themes.index(u["theme"]), u["order"]))
            if preferred:
                return preferred[0]
        return candidates[0] if candidates else None
