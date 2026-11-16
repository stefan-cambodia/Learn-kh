"""Synchronisation de la progression entre appareils, par le serveur local (« manage.py serve »).

Le navigateur garde la progression dans son stockage local ; quand le site est servi par
le serveur local, il envoie ce stockage à ``/api/progress``. Le serveur le fusionne avec
ce qu'ont envoyé les autres appareils et renvoie le résultat. Sans serveur (fichiers
ouverts depuis le disque), rien ne change : chaque appareil garde sa propre progression.

Règles de fusion, entrée par entrée (profils : fr, en, km, la langue de l'apprenant) :
- ``frkh-done2-<profil>``  {numéro de leçon: {"d": 0|1, "t": horodatage}}  → la plus récente gagne ;
- ``frkh-boxes-<profil>-<langue>``  {carte: {"b": boîte, "t": horodatage}}  → la plus récente gagne ;
- ``frkh-days-<profil>``  [dates]  → union (jours d'activité, pour la série de jours).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
from pathlib import Path

from .audio import wavutil

KEY_RE = re.compile(r"^frkh-(done2-(fr|en|km)|days-(fr|en|km)|boxes-(fr|en|km)-(fr|en|km))$")
# Anciens profils « A » (khmer) et « B » (français) : clés renommées au chargement.
LEGACY_KEY_RE = re.compile(r"^(frkh-(?:done2|days|boxes))-([AB])((?:-(?:fr|en|km))?)$")
LEGACY_PROFILES = {"A": "km", "B": "fr"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_BODY = 2 * 1024 * 1024
MAX_ENTRIES = 20000
_lock = threading.Lock()


def store_path(config) -> Path:
    return Path(config.paths.database_dir) / "progress-sync.json"


def _stamp(value) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value).timestamp() * 1000
        except ValueError:
            return 0.0
    return 0.0


def _clean_entries(raw, field: str) -> dict:
    """Garde uniquement des entrées {clé: {field: entier, "t": nombre}} raisonnables."""
    if not isinstance(raw, dict):
        return {}
    clean = {}
    for key, entry in list(raw.items())[:MAX_ENTRIES]:
        if not isinstance(key, str) or len(key) > 500 or not isinstance(entry, dict):
            continue
        value = entry.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
            continue
        clean[key] = {field: value, "t": _stamp(entry.get("t"))}
    return clean


def _clean_days(raw) -> list:
    if not isinstance(raw, list):
        return []
    return sorted({d for d in raw[:MAX_ENTRIES] if isinstance(d, str) and DATE_RE.match(d)})


def parse_value(key: str, text):
    """Valeur du stockage local (chaîne JSON) → structure propre, ou None si invalide."""
    if not KEY_RE.match(key) or not isinstance(text, str):
        return None
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if key.startswith("frkh-days-"):
        return _clean_days(raw)
    return _clean_entries(raw, "d" if key.startswith("frkh-done2-") else "b")


def merge_value(key: str, ours, theirs):
    if ours is None:
        return theirs
    if theirs is None:
        return ours
    if key.startswith("frkh-days-"):
        return sorted(set(ours) | set(theirs))
    merged = dict(ours)
    for item, entry in theirs.items():
        if item not in merged or entry["t"] >= merged[item]["t"]:
            merged[item] = entry
    return merged


def load(config) -> dict:
    path = store_path(config)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    state: dict = {}
    for key, value in data.items():
        legacy = LEGACY_KEY_RE.match(key)
        if legacy:
            key = f"{legacy.group(1)}-{LEGACY_PROFILES[legacy.group(2)]}{legacy.group(3)}"
            state[key] = merge_value(key, state.get(key), value)
        elif KEY_RE.match(key):
            state[key] = merge_value(key, state.get(key), value)
    return state


def exchange(config, incoming: dict) -> dict:
    """Fusionne ce qu'envoie un appareil avec l'état enregistré ; renvoie l'état fusionné (chaînes JSON)."""
    with _lock:
        state = load(config)
        for key, text in incoming.items():
            value = parse_value(key, text)
            if value is not None:
                state[key] = merge_value(key, state.get(key), value)
        path = store_path(config)
        path.parent.mkdir(parents=True, exist_ok=True)
        wavutil.atomic_write(path, json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        return {key: json.dumps(value, ensure_ascii=False, separators=(",", ":")) for key, value in state.items()}
