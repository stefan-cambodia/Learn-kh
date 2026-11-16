"""Outils d'administration : vérification générale, export, corrections, planification, serveur local."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from . import db, srs
from .audio import wavutil
from .curriculum import Curriculum
from .quality import check_trilingual, summarize, vocab_key
from .textutil import LANGS, normalize_text

CRON_MARK = "# fr-kh-learning"
TASK_NAME = "FR-KH Learning"
SYSTEMD_UNIT = "fr-kh-learning"
PUBLIC_DIRS = ("lessons", "audio", "css", "js", "fonts", "data")
# Pages publiques placées à la racine du site, à côté de index.html.
PUBLIC_PAGES = ("alphabet.html", "revision.html", "lexique.html", "manifest.webmanifest")
SECRET_VARS = ("GOOGLE_TTS_API_KEY", "GOOGLE_TTS_ACCESS_TOKEN", "AZURE_SPEECH_KEY")


# --- Vérification générale ---------------------------------------------------------

class Report:
    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def ok(self, message: str) -> None:
        self.lines.append(("ok", message))

    def warn(self, message: str) -> None:
        self.lines.append(("warn", message))

    def error(self, message: str) -> None:
        self.lines.append(("error", message))

    @property
    def errors(self) -> int:
        return sum(1 for level, _ in self.lines if level == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for level, _ in self.lines if level == "warn")

    def render(self) -> str:
        tags = {"ok": "  OK      ", "warn": "  ATTENTION", "error": "  ERREUR  "}
        return "\n".join(f"{tags[level]} {message}" for level, message in self.lines)


def public_files(paths) -> list[Path]:
    files = [paths.index] if paths.index.is_file() else []
    files += [paths.root / name for name in PUBLIC_PAGES if (paths.root / name).is_file()]
    for name in PUBLIC_DIRS:
        directory = paths.root / name
        if directory.is_dir():
            files += [p for p in directory.rglob("*") if p.is_file()]
    return files


def check_project(config, conn, library, deep: bool = False) -> Report:
    """Commande de vérification générale du projet."""
    report = Report()
    paths = config.paths

    # Configuration et secrets
    problems = config.validate()
    for problem in problems:
        report.error(f"Configuration : {problem}")
    if not problems:
        report.ok(f"Configuration valide (génération à {config.get('schedule.time')}, fuseau {config.get('schedule.timezone')})")
    if paths.env.is_file():
        if os.name != "nt" and paths.env.stat().st_mode & 0o077:
            report.warn("Le fichier .env est lisible par d'autres utilisateurs : lancez « chmod 600 .env »")
        else:
            report.ok("Fichier .env présent")
    else:
        report.warn("Fichier .env absent : copiez .env.example vers .env et renseignez vos clés API")
    for lang in LANGS:
        spec = library.spec_for(lang)
        try:
            ready, reason = library.provider(spec.provider).configured()
        except Exception as exc:
            ready, reason = False, str(exc)
        if ready:
            report.ok(f"Voix {spec.locale} : {spec.provider} / {spec.voice}")
        else:
            report.warn(f"Voix {spec.locale} : fournisseur « {spec.provider} » non configuré ({reason}) — "
                        f"les audios {spec.locale} resteront en attente")

    # Base de données
    ok, detail = db.integrity_ok(conn)
    (report.ok if ok else report.error)(f"Base SQLite : contrôle d'intégrité « {detail} »")
    backups = sorted(paths.backups.glob("learning-*.db"))
    if backups:
        age = dt.datetime.now() - dt.datetime.fromtimestamp(backups[-1].stat().st_mtime)
        (report.ok if age.days < 3 else report.warn)(
            f"Sauvegardes : {len(backups)} copie(s), la plus récente date de {age.days} jour(s)")
    else:
        report.warn("Aucune sauvegarde de la base pour l'instant (commande « backup », ou automatique avec « daily »)")

    # Programme pédagogique
    curriculum = Curriculum(paths.content).load()
    summary = summarize(curriculum.issues)
    used = {r["unit_id"] for r in conn.execute("SELECT unit_id FROM lessons WHERE unit_id IS NOT NULL")}
    remaining = [u for u in curriculum.units if u["id"] not in used]
    if curriculum.rejected:
        report.error(f"Programme : {len(curriculum.rejected)} unité(s) écartée(s) pour erreurs "
                     f"({', '.join(name for name, _ in curriculum.rejected)}) — voir « content check »")
    message = (f"Programme : {len(curriculum.units)} unité(s) valide(s), {len(remaining)} restante(s) à enseigner, "
               f"{summary['warnings']} avertissement(s), {summary['uncertain']} traduction(s) à vérifier")
    if not curriculum.units:
        report.error("Programme : aucune unité valide dans content/units")
    elif len(remaining) <= 3:
        report.warn(message + " — pensez à ajouter des unités")
    else:
        report.ok(message)

    # Leçons et pages
    lessons = conn.execute("SELECT * FROM lessons ORDER BY lesson_number").fetchall()
    drafts = [r for r in lessons if r["status"] != "complete"]
    missing_pages = [r["lesson_number"] for r in lessons
                     if r["status"] == "complete" and not (r["html_path"] and (paths.root / r["html_path"]).is_file())]
    if drafts:
        report.warn(f"Leçons interrompues à reprendre : {', '.join(str(r['lesson_number']) for r in drafts)} "
                    f"(« generate --date … » ou « daily »)")
    if missing_pages:
        report.error(f"Pages HTML absentes pour les leçons : {', '.join(map(str, missing_pages))} (« render --all »)")
    if lessons and not missing_pages:
        report.ok(f"Leçons : {len(lessons) - len(drafts)} publiée(s), chacune avec sa page HTML")
    if not lessons:
        report.warn("Aucune leçon générée pour l'instant (« generate »)")
    if lessons and not paths.index.is_file():
        report.error("index.html absent (« render --all »)")
    for needed in ("css/style.css", "js/app.js", "fonts/NotoSansKhmer-Regular.ttf", "templates/base.html"):
        if not (paths.root / needed).is_file():
            report.error(f"Fichier indispensable absent : {needed}")

    # Bibliothèque audio
    audit = library.verify(deep=deep)
    megabytes = audit["bytes"] / 1048576
    report.ok(f"Audio : {audit['ready']} fichier(s) WAV valide(s), {megabytes:.1f} Mo, {audit['seconds'] / 60:.1f} min")
    if audit["corrupt"]:
        report.error(f"Audio : {len(audit['corrupt'])} fichier(s) corrompu(s) (« audio repair »)")
    waiting = [m for m in audit["missing"] if m["reason"] != "fichier supprimé"]
    deleted = [m for m in audit["missing"] if m["reason"] == "fichier supprimé"]
    if deleted:
        report.error(f"Audio : {len(deleted)} fichier(s) supprimé(s) du disque (« audio repair »)")
    if waiting:
        report.warn(f"Audio : {len(waiting)} fichier(s) en attente de génération (« audio missing » pour le détail)")
    if audit["orphans"]:
        report.warn(f"Audio : {len(audit['orphans'])} fichier(s) non référencé(s) (« audio prune »)")

    # Fonctionnement hors ligne et confidentialité des clés
    external, leaked = [], []
    secrets = [os.environ[name] for name in SECRET_VARS if len(os.environ.get(name, "")) >= 8]
    pattern = re.compile(r"""(?:src|href)\s*=\s*["'](?:https?:)?//|url\(\s*["']?(?:https?:)?//|@import\s+["']https?:""", re.I)
    for path in public_files(paths) + [paths.config]:
        if path.suffix.lower() not in (".html", ".css", ".js", ".json", ".svg") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() in (".html", ".css") and pattern.search(text):
            external.append(paths.rel(path))
        if any(secret in text for secret in secrets):
            leaked.append(paths.rel(path))
    if external:
        report.error(f"Ressources externes détectées (le site doit fonctionner hors ligne) : {', '.join(external[:5])}")
    else:
        report.ok("Site autonome : aucune ressource externe, consultable hors connexion")
    if leaked:
        report.error(f"CLÉ API EXPOSÉE dans : {', '.join(leaked)} — retirez-la et régénérez la clé")
    else:
        report.ok("Aucune clé API dans les pages, scripts, données ou configuration")

    # Planification
    state = schedule_state(config)
    (report.ok if state["installed"] else report.warn)(
        f"Planification : {state['detail']}" if state["installed"]
        else "Planification quotidienne non installée (« schedule install »)")
    return report


# --- Export ----------------------------------------------------------------------------

def export_all(config, conn, out_dir: Path | None = None, include_audio: bool = True) -> Path:
    """Archive ZIP autonome : site complet (pages, audio, polices) et données JSON de toutes les leçons."""
    paths = config.paths
    out_dir = Path(out_dir) if out_dir else paths.exports
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"fr-kh-learning-{stamp}.zip"
    tmp = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in public_files(paths):
            if not include_audio and paths.audio in path.parents:
                continue
            archive.write(path, f"fr-kh-learning/{paths.rel(path)}")
        for row in conn.execute("SELECT lesson_number, content_json FROM lessons WHERE status = 'complete' ORDER BY lesson_number"):
            pretty = json.dumps(json.loads(row["content_json"]), ensure_ascii=False, indent=2)
            archive.writestr(f"fr-kh-learning/data/lessons/lesson-{row['lesson_number']:03d}.json", pretty)
    tmp.replace(target)
    return target


# --- Corrections manuelles ----------------------------------------------------------------

def _replace_in_tree(node, find: str, replace: str, fields: tuple[str, ...], counter: list[int]):
    if isinstance(node, dict):
        return {key: (_swap(value, find, replace, counter) if key in fields and isinstance(value, str)
                      else _replace_in_tree(value, find, replace, fields, counter)) for key, value in node.items()}
    if isinstance(node, list):
        return [_replace_in_tree(item, find, replace, fields, counter) for item in node]
    return node


def _swap(value: str, find: str, replace: str, counter: list[int]) -> str:
    hits = value.count(find)
    if hits:
        counter[0] += hits
        return value.replace(find, replace)
    return value


def correct_text(config, conn, find: str, replace: str, lang: str | None = None,
                 lesson: int | None = None, dry_run: bool = False) -> dict:
    """Remplace un texte fautif dans les leçons générées, le vocabulaire et les unités sources."""
    find, replace = normalize_text(find), normalize_text(replace)
    if not find:
        raise ValueError("le texte à rechercher est vide")
    fields = (lang,) if lang else ("fr", "en", "km", "tr")
    if lang == "km":
        fields = ("km",)
    result = {"lessons": [], "vocabulary": 0, "units": [], "occurrences": 0}
    with db.transaction(conn):
        for row in conn.execute("SELECT * FROM lessons WHERE content_json != '{}' ORDER BY lesson_number").fetchall():
            if lesson and row["lesson_number"] != lesson:
                continue
            counter = [0]
            content = _replace_in_tree(json.loads(row["content_json"]), find, replace, fields, counter)
            if not counter[0]:
                continue
            result["lessons"].append(row["lesson_number"])
            result["occurrences"] += counter[0]
            if not dry_run:
                conn.execute("UPDATE lessons SET content_json = ?, title_fr = ?, title_en = ?, title_km = ?, updated_at = ? WHERE id = ?",
                             (json.dumps(content, ensure_ascii=False), content["title"]["fr"], content["title"]["en"],
                              content["title"]["km"], db.utcnow(), row["id"]))
        if not lesson:
            columns = {"fr": ("french_text", "explanation_fr"), "en": ("english_text", "explanation_en"),
                       "km": ("khmer_text", "explanation_km"), "tr": ("transliteration",)}
            for row in conn.execute("SELECT * FROM vocabulary").fetchall():
                updates, counter = {}, [0]
                for field in fields:
                    for column in columns.get(field, ()):
                        value = row[column] or ""
                        swapped = _swap(value, find, replace, counter)
                        if swapped != value:
                            updates[column] = swapped
                if row["example_json"]:
                    example = _replace_in_tree(json.loads(row["example_json"]), find, replace, fields, counter)
                    if json.dumps(example, ensure_ascii=False) != row["example_json"]:
                        updates["example_json"] = json.dumps(example, ensure_ascii=False)
                if not updates:
                    continue
                result["vocabulary"] += 1
                result["occurrences"] += counter[0]
                if not dry_run:
                    merged = {**dict(row), **updates}
                    updates["vocab_key"] = vocab_key({"fr": merged["french_text"], "en": merged["english_text"]})
                    assignments = ", ".join(f"{column} = ?" for column in updates)
                    try:
                        conn.execute(f"UPDATE vocabulary SET {assignments} WHERE id = ?", (*updates.values(), row["id"]))
                    except Exception:
                        updates.pop("vocab_key")
                        assignments = ", ".join(f"{column} = ?" for column in updates)
                        conn.execute(f"UPDATE vocabulary SET {assignments} WHERE id = ?", (*updates.values(), row["id"]))
    if not lesson:
        raw_find = json.dumps(find, ensure_ascii=False)[1:-1]
        raw_replace = json.dumps(replace, ensure_ascii=False)[1:-1]
        for path in sorted(config.paths.content.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            if raw_find not in text:
                continue
            updated = text.replace(raw_find, raw_replace)
            try:
                json.loads(updated)
            except ValueError:
                continue
            result["units"].append(path.name)
            if not dry_run:
                wavutil.atomic_write(path, updated.encode("utf-8"))
    return result


def import_lesson(conn, payload: dict) -> int:
    """Remplace le contenu d'une leçon par une version corrigée à la main (après « lesson export »)."""
    number = int(payload.get("number", 0))
    row = conn.execute("SELECT * FROM lessons WHERE lesson_number = ?", (number,)).fetchone()
    if row is None:
        raise ValueError(f"leçon n° {number} introuvable")
    issues = check_trilingual(payload.get("title"), "titre", need_tr=False)
    for section in ("vocabulary", "expressions", "sentences"):
        for i, entry in enumerate(payload.get(section) or [], 1):
            issues += check_trilingual(entry, f"{section}[{i}]")
    for i, line in enumerate((payload.get("dialogue") or {}).get("lines") or [], 1):
        issues += check_trilingual(line, f"dialogue[{i}]")
    errors = [str(i) for i in issues if i.level == "error"]
    if errors:
        raise ValueError("contenu refusé :\n  " + "\n  ".join(errors))
    payload["date"], payload["number"] = row["lesson_date"], number
    with db.transaction(conn):
        conn.execute("UPDATE lessons SET content_json = ?, title_fr = ?, title_en = ?, title_km = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(payload, ensure_ascii=False), payload["title"]["fr"], payload["title"]["en"],
                      payload["title"]["km"], db.utcnow(), row["id"]))
        for section in ("vocabulary", "expressions"):
            for entry in payload.get(section) or []:
                if not entry.get("vocab_id"):
                    continue
                note = entry.get("note") or {}
                conn.execute(
                    "UPDATE vocabulary SET french_text = ?, english_text = ?, khmer_text = ?, transliteration = ?, "
                    "explanation_fr = ?, explanation_en = ?, explanation_km = ?, example_json = ?, uncertain = ?, "
                    "uncertain_note = ? WHERE id = ?",
                    (entry["fr"], entry["en"], entry["km"], entry.get("tr", ""), note.get("fr", ""), note.get("en", ""),
                     note.get("km", ""),
                     json.dumps(entry["example"], ensure_ascii=False) if entry.get("example") else None,
                     1 if entry.get("uncertain") else 0, entry.get("uncertain_note"), entry["vocab_id"]))
    return number


def _legacy_due_for(due_for) -> list[str]:
    """Anciens profils A (khmer) et B (français) ; le profil anglais suit le calendrier du profil français."""
    from .config import LEGACY_PROFILES
    out = {LEGACY_PROFILES.get(p, p) for p in due_for or []}
    if "fr" in out:
        out.add("en")
    return sorted(out)


def refresh_lessons(config, conn, curriculum) -> dict:
    """Reporte dans les leçons déjà générées les textes actuels des unités.

    Mis à jour : titre, conseil, explications (notes), exemples, situations, dialogue (prénoms des
    personnages compris), question de compréhension et exercice de traduction. Le choix des mots,
    les dates, la numérotation et la progression ne changent pas.
    """
    from .curriculum import personalize_tree
    characters = config.characters()
    units = {u["id"]: personalize_tree({k: v for k, v in u.items() if not k.startswith("_")}, characters)
             for u in curriculum.units}
    examples: dict[str, dict] = {}
    entries: dict[tuple[str, str], dict] = {}
    for unit in units.values():
        for section in ("vocabulary", "expressions"):
            for entry in unit[section]:
                entries[(entry["fr"], entry["km"])] = entry
                if entry.get("example"):
                    examples.setdefault(entry["example"]["fr"], entry["example"])

    def refresh(item: dict, source: dict | None) -> None:
        if not source or source.get("fr") != item.get("fr"):
            return
        for key in ("note", "example", "situation"):
            if key in source:
                item[key] = source[key]

    stats = {"lessons": 0, "vocabulary": 0}
    rows = conn.execute("SELECT * FROM lessons WHERE content_json != '{}' ORDER BY kind DESC, lesson_number").fetchall()
    refreshed: dict[int, dict] = {}
    with db.transaction(conn):
        for row in rows:   # leçons d'unité d'abord (« unit » > « review »), les révisions reprennent leur source
            content = json.loads(row["content_json"])
            before = json.dumps(content, ensure_ascii=False, sort_keys=True)
            unit = units.get(content.get("unit_id") or "")
            if content.get("kind") == "unit" and unit:
                content["title"], content["tip"], content["dialogue"] = unit["title"], unit.get("tip"), unit["dialogue"]
                content.setdefault("review", {})["comprehension"] = unit["comprehension"]
                for section in ("vocabulary", "expressions"):
                    for item in content.get(section, []):
                        refresh(item, entries.get((item.get("fr"), item.get("km"))))
                if len(content.get("sentences", [])) <= len(unit["sentences"]):
                    content["sentences"] = unit["sentences"][:len(content.get("sentences", []))]
            elif content.get("kind") == "review" and content.get("source_lesson") in refreshed:
                source = refreshed[content["source_lesson"]]
                content["tip"], content["dialogue"] = source.get("tip"), source.get("dialogue")
                content.setdefault("review", {})["comprehension"] = source.get("review", {}).get("comprehension")
                for section in ("vocabulary", "expressions"):
                    for item in content.get(section, []):
                        refresh(item, entries.get((item.get("fr"), item.get("km"))))
                content["sentences"] = source.get("sentences", [])[:len(content.get("sentences", []))]
            review = content.get("review") or {}
            for word in review.get("words") or []:
                refresh(word, entries.get((word.get("fr"), word.get("km"))))
                word["due_for"] = _legacy_due_for(word.get("due_for"))
            translation = review.get("translation")
            if translation:
                if translation.get("source") == "today" and content.get("sentences"):
                    sentences = content["sentences"]
                    review["translation"] = dict(sentences[content["number"] % len(sentences)], source="today")
                elif translation.get("fr") in examples:
                    review["translation"] = dict(examples[translation["fr"]], source=translation.get("source", "review"))
            refreshed[row["lesson_number"]] = content
            if json.dumps(content, ensure_ascii=False, sort_keys=True) != before:
                conn.execute("UPDATE lessons SET content_json = ?, title_fr = ?, title_en = ?, title_km = ?, updated_at = ? "
                             "WHERE id = ?", (json.dumps(content, ensure_ascii=False), content["title"]["fr"],
                                              content["title"]["en"], content["title"]["km"], db.utcnow(), row["id"]))
                stats["lessons"] += 1
        for row in conn.execute("SELECT * FROM vocabulary").fetchall():
            entry = entries.get((row["french_text"], row["khmer_text"]))
            note = (entry or {}).get("note") or {}
            values = (note.get("fr", ""), note.get("en", ""), note.get("km", ""))
            if entry and values != (row["explanation_fr"] or "", row["explanation_en"] or "", row["explanation_km"] or ""):
                conn.execute("UPDATE vocabulary SET explanation_fr = ?, explanation_en = ?, explanation_km = ?, "
                             "example_json = ? WHERE id = ?",
                             (*values, json.dumps(entry["example"], ensure_ascii=False) if entry.get("example") else None,
                              row["id"]))
                stats["vocabulary"] += 1
    return stats


def find_vocabulary(conn, word: str) -> list:
    word = normalize_text(word)
    rows = conn.execute("SELECT * FROM vocabulary WHERE french_text = ? OR english_text = ? OR khmer_text = ? "
                        "COLLATE NOCASE", (word, word, word)).fetchall()
    if not rows:
        like = f"%{word}%"
        rows = conn.execute("SELECT * FROM vocabulary WHERE french_text LIKE ? OR english_text LIKE ? OR khmer_text LIKE ?",
                            (like, like, like)).fetchall()
    return rows


def set_progress(config, conn, action: str, learner: str, word: str) -> list[str]:
    intervals = [int(i) for i in config.get("review.intervals_days", [1, 3, 7, 14, 30])]
    day = config.today().isoformat()
    rows = find_vocabulary(conn, word)
    if len(rows) > 1:
        raise ValueError("plusieurs mots correspondent : " + ", ".join(f"« {r['french_text']} »" for r in rows[:8]))
    if not rows:
        raise ValueError(f"mot introuvable : « {word} »")
    from .config import LEGACY_PROFILES
    learner = LEGACY_PROFILES.get(learner, learner)
    learners = srs.LEARNERS if learner in ("all", "both") else (learner,)
    for name in learners:
        (srs.forget if action == "forget" else srs.master)(conn, name, rows[0]["id"], day, intervals)
    return [rows[0]["french_text"], rows[0]["khmer_text"]]


# --- Planification quotidienne --------------------------------------------------------------

def _python() -> str:
    return sys.executable or "python3"


def cron_line(config) -> str:
    every = max(1, min(59, int(config.get("schedule.check_every_minutes", 15))))
    root = config.paths.root
    return (f'*/{every} * * * * cd "{root}" && "{_python()}" manage.py daily --quiet '
            f'>> "{root / "logs" / "cron.log"}" 2>&1 {CRON_MARK}')


def _run(argv: list[str], data: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=data, capture_output=True, text=True, timeout=30)


def _crontab() -> str | None:
    if not shutil.which("crontab"):
        return None
    proc = _run(["crontab", "-l"])
    return proc.stdout if proc.returncode == 0 else ""


def _cron_service_active() -> bool:
    if not shutil.which("systemctl"):
        return True
    return any(_run(["systemctl", "is-active", name]).stdout.strip() == "active" for name in ("cronie", "cron", "crond"))


def _systemd_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user"


def systemd_units(config) -> dict[str, str]:
    every = max(1, min(59, int(config.get("schedule.check_every_minutes", 15))))
    root = config.paths.root
    service = (f"[Unit]\nDescription=FR-KH Learning — leçon quotidienne\n\n[Service]\nType=oneshot\n"
               f"WorkingDirectory={root}\nExecStart=\"{_python()}\" \"{root / 'manage.py'}\" daily --quiet\n")
    timer = (f"[Unit]\nDescription=FR-KH Learning — vérification toutes les {every} minutes\n\n[Timer]\n"
             f"OnCalendar=*:0/{every}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")
    return {f"{SYSTEMD_UNIT}.service": service, f"{SYSTEMD_UNIT}.timer": timer}


def windows_command(config) -> list[str]:
    """Commande « schtasks ». On passe par pythonw.exe quand il existe : aucune fenêtre ne
    s'ouvre toutes les quelques minutes ; les journaux sont écrits par l'application (logs/)."""
    every = max(1, min(59, int(config.get("schedule.check_every_minutes", 15))))
    python = Path(_python())
    windowless = python.with_name("pythonw.exe")
    if python.name.lower() == "python.exe" and windowless.is_file():
        python = windowless
    action = f'"{python}" "{config.paths.root / "manage.py"}" daily --quiet'
    return ["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(every), "/TN", TASK_NAME, "/TR", action]


def default_method() -> str:
    if os.name == "nt":
        return "windows"
    if shutil.which("crontab") and _cron_service_active():
        return "cron"
    if shutil.which("systemctl"):
        return "systemd"
    return "cron"


def schedule_state(config) -> dict:
    """Indique si la génération automatique est installée, et par quel moyen."""
    try:
        if os.name == "nt":
            proc = _run(["schtasks", "/Query", "/TN", TASK_NAME])
            return {"installed": proc.returncode == 0, "method": "windows",
                    "detail": f"tâche planifiée Windows « {TASK_NAME} »"}
        table = _crontab()
        if table and CRON_MARK in table:
            detail = "tâche cron installée"
            if not _cron_service_active():
                detail += " (ATTENTION : le service cron n'est pas actif sur cette machine)"
            return {"installed": True, "method": "cron", "detail": detail}
        if shutil.which("systemctl"):
            proc = _run(["systemctl", "--user", "is-enabled", f"{SYSTEMD_UNIT}.timer"])
            if proc.stdout.strip() == "enabled":
                return {"installed": True, "method": "systemd", "detail": "minuterie systemd (utilisateur) activée"}
    except (OSError, subprocess.SubprocessError):
        pass
    return {"installed": False, "method": default_method(), "detail": "non installée"}


def schedule_install(config, method: str = "auto") -> str:
    method = default_method() if method == "auto" else method
    config.paths.logs.mkdir(parents=True, exist_ok=True)
    if method == "windows":
        proc = _run(windows_command(config))
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "schtasks a échoué")
        return f"Tâche planifiée Windows « {TASK_NAME} » créée."
    if method == "systemd":
        directory = _systemd_dir()
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in systemd_units(config).items():
            (directory / name).write_text(body, encoding="utf-8")
        for argv in (["systemctl", "--user", "daemon-reload"],
                     ["systemctl", "--user", "enable", "--now", f"{SYSTEMD_UNIT}.timer"]):
            proc = _run(argv)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or "systemctl a échoué")
        return ("Minuterie systemd (utilisateur) activée. Pour qu'elle tourne aussi sans session ouverte : "
                "« loginctl enable-linger $USER ».")
    table = _crontab()
    if table is None:
        raise RuntimeError("la commande « crontab » est introuvable sur cette machine")
    lines = [line for line in table.splitlines() if CRON_MARK not in line]
    lines.append(cron_line(config))
    proc = _run(["crontab", "-"], "\n".join(lines) + "\n")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "crontab a échoué")
    note = "" if _cron_service_active() else (" ATTENTION : le service cron n'est pas actif "
                                               "(« sudo systemctl enable --now cronie » ou « cron »).")
    return "Tâche cron installée." + note


def schedule_remove(config) -> str:
    done = []
    if os.name == "nt":
        if _run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME]).returncode == 0:
            done.append("tâche planifiée Windows supprimée")
        return ", ".join(done) or "aucune tâche planifiée à supprimer"
    table = _crontab()
    if table and CRON_MARK in table:
        kept = [line for line in table.splitlines() if CRON_MARK not in line]
        _run(["crontab", "-"], "\n".join(kept) + ("\n" if kept else ""))
        done.append("tâche cron supprimée")
    directory = _systemd_dir()
    if (directory / f"{SYSTEMD_UNIT}.timer").is_file():
        _run(["systemctl", "--user", "disable", "--now", f"{SYSTEMD_UNIT}.timer"])
        for name in systemd_units(config):
            (directory / name).unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"])
        done.append("minuterie systemd supprimée")
    return ", ".join(done) or "aucune planification à supprimer"


# --- Serveur local (pour consulter le site depuis un téléphone du même réseau) ----------------

def make_server(config, host: str = "127.0.0.1", port: int = 8000):
    """Construit le serveur web local. Il ne distribue que le site public : index.html et les
    dossiers de ``PUBLIC_DIRS``. Le fichier .env, la base, la configuration et le code restent
    inaccessibles, y compris par une adresse détournée (« .. » encodé, lien symbolique…)."""
    import http.server
    import socketserver

    root = config.paths.root
    index = root / "index.html"
    allowed = [(root / name).resolve() for name in PUBLIC_DIRS]
    pages = {(root / name).resolve() for name in PUBLIC_PAGES}

    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".webmanifest": "application/manifest+json", ".wav": "audio/wav"}

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def _target(self) -> Path:
            # Chemin réel sur le disque, une fois l'adresse décodée et normalisée : c'est lui qui est contrôlé.
            return Path(self.translate_path(self.path)).resolve()

        def _public(self, target: Path) -> bool:
            if target == root:
                return index.is_file()
            if target == index or target in pages:
                return True
            return any(base == target or base in target.parents for base in allowed)

        def send_head(self):
            target = self._target()
            if not self._public(target):
                self.send_error(404, "Introuvable")
                return None
            # Requêtes partielles, dont certains navigateurs mobiles ont besoin pour lire l'audio.
            header = self.headers.get("Range")
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip()) if header else None
            if not match or not (match.group(1) or match.group(2)) or not target.is_file():
                return super().send_head()
            size = target.stat().st_size
            if match.group(1):
                start = int(match.group(1))
                end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
            else:
                start, end = max(0, size - int(match.group(2))), size - 1
            if start >= size or start > end:
                self.send_error(416, "Plage invalide")
                return None
            handle = open(target, "rb")
            handle.seek(start)
            self._remaining = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(str(target)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(self._remaining))
            self.end_headers()
            return handle

        # --- synchronisation de la progression entre appareils ------------------------------
        def _is_sync(self) -> bool:
            return self.path.split("?", 1)[0] == "/api/progress"

        def _send_json(self, status: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self._is_sync():
                from . import progress_sync
                return self._send_json(200, {"data": progress_sync.exchange(config, {})})
            return super().do_GET()

        def do_POST(self):
            if not self._is_sync():
                return self.send_error(405, "Méthode non autorisée")
            from . import progress_sync
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= progress_sync.MAX_BODY:
                return self._send_json(413, {"error": "taille invalide"})
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                incoming = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(incoming, dict):
                    raise ValueError("champ « data » attendu")
            except (ValueError, UnicodeDecodeError) as exc:
                return self._send_json(400, {"error": str(exc)})
            return self._send_json(200, {"data": progress_sync.exchange(config, incoming)})

        def list_directory(self, path):
            self.send_error(404, "Introuvable")      # pas de liste du contenu des dossiers
            return None

        def copyfile(self, source, outputfile):
            remaining = getattr(self, "_remaining", None)
            if remaining is None:
                return super().copyfile(source, outputfile)
            while remaining > 0:
                block = source.read(min(65536, remaining))
                if not block:
                    break
                outputfile.write(block)
                remaining -= len(block)
            self._remaining = None

        def end_headers(self):
            self.send_header("Accept-Ranges", "bytes")
            super().end_headers()

        def log_message(self, *args):
            pass

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    return Server((host, port), Handler)


def serve(config, host: str = "127.0.0.1", port: int = 8000) -> None:
    with make_server(config, host, port) as httpd:
        shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
        print(f"Site disponible sur http://{shown}:{httpd.server_address[1]}/  (Ctrl+C pour arrêter)")
        if host == "0.0.0.0":
            print("Accessible aussi depuis les autres appareils du réseau local, à l'adresse IP de cet ordinateur.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServeur arrêté.")
