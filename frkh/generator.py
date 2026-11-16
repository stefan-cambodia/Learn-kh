"""Générateur de leçons : choix du thème, construction, audio, pages HTML, statistiques."""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass, field

from . import db, srs
from .audio import AudioLibrary
from .curriculum import Curriculum, personalize_tree
from .quality import check_trilingual, summarize, vocab_key
from .textutil import LANGS, speech_text

CONTENT_VERSION = 1

# Temps de lecture moyens, en secondes, utilisés pour garantir une leçon de moins de 10 minutes.
SECONDS = {"vocabulary": 26, "expressions": 24, "sentences": 34, "dialogue": 16, "review_word": 5, "quiz": 60}
MIN_WORDS, MIN_EXPRESSIONS = 5, 3


class GenerationError(Exception):
    pass


@dataclass
class GenerationResult:
    status: str                      # created | resumed | refreshed | exists
    lesson_number: int
    lesson_date: str
    title: str
    kind: str = "unit"
    html_path: str = ""
    audio_ready: int = 0
    audio_missing: int = 0
    tts_calls: int = 0
    cache_hits: int = 0
    estimated_seconds: int = 0
    messages: list[str] = field(default_factory=list)


def estimate_seconds(content: dict) -> int:
    return (SECONDS["vocabulary"] * len(content.get("vocabulary", []))
            + SECONDS["expressions"] * len(content.get("expressions", []))
            + SECONDS["sentences"] * len(content.get("sentences", []))
            + SECONDS["dialogue"] * len(content.get("dialogue", {}).get("lines", []))
            + SECONDS["review_word"] * len(content.get("review", {}).get("words", []))
            + SECONDS["quiz"])


def audio_items(content: dict, include_examples: bool = True) -> list[tuple[str, str]]:
    """Tous les couples (langue, texte) d'une leçon qui doivent avoir un fichier audio."""
    seen: set[tuple[str, str]] = set()
    items: list[tuple[str, str]] = []

    def add(entry: dict | None) -> None:
        if not isinstance(entry, dict):
            return
        for lang in LANGS:
            text = speech_text(entry.get(lang, ""))
            if text and (lang, text) not in seen:
                seen.add((lang, text))
                items.append((lang, text))

    for entry in content.get("vocabulary", []):
        add(entry)
        if include_examples:
            add(entry.get("example"))
    for section in ("expressions", "sentences"):
        for entry in content.get(section, []):
            add(entry)
    for line in content.get("dialogue", {}).get("lines", []):
        add(line)
    review = content.get("review", {})
    for entry in review.get("words", []):
        add(entry)
    for entry in review.get("questions", []):
        add(entry)
    add(review.get("translation"))
    return items


def _entry_from_row(row) -> dict:
    """Reconstruit une entrée de leçon à partir de la table ``vocabulary``."""
    entry = {
        "vocab_id": row["id"], "kind": row["kind"],
        "fr": row["french_text"], "en": row["english_text"], "km": row["khmer_text"],
        "tr": row["transliteration"] or "", "pos": row["category"] or "",
        "note": {"fr": row["explanation_fr"] or "", "km": row["explanation_km"] or ""},
    }
    if row["example_json"]:
        entry["example"] = json.loads(row["example_json"])
    if row["uncertain"]:
        entry["uncertain"] = True
        entry["uncertain_note"] = row["uncertain_note"] or ""
    return entry


class LessonService:
    """Orchestre la création d'une leçon de bout en bout."""

    def __init__(self, config, conn, logger: logging.Logger | None = None,
                 library: AudioLibrary | None = None, renderer=None):
        self.config = config
        self.conn = conn
        self.log = logger or logging.getLogger("frkh.generator")
        self.library = library or AudioLibrary(config, conn, self.log)
        self.curriculum = Curriculum(config.paths.content, self.log)
        if renderer is None:
            from .render import SiteRenderer
            renderer = SiteRenderer(config, conn, self.library, self.log)
        self.renderer = renderer
        self.intervals = [int(i) for i in config.get("review.intervals_days", [1, 3, 7, 14, 30])]

    # --- point d'entrée -----------------------------------------------------------
    def generate(self, day: dt.date | str | None = None, force: bool = False,
                 with_audio: bool = True) -> GenerationResult:
        day = (day or self.config.today())
        day = day.isoformat() if isinstance(day, dt.date) else str(dt.date.fromisoformat(day))
        run_id = self._start_run("generate", day)
        try:
            row = self.conn.execute("SELECT * FROM lessons WHERE lesson_date = ?", (day,)).fetchone()
            if row is not None and row["status"] == "complete" and not force:
                self.log.info("La leçon du %s existe déjà (n° %d) : rien à faire.", day, row["lesson_number"])
                result = GenerationResult("exists", row["lesson_number"], day, row["title_fr"], row["kind"],
                                          row["html_path"] or "", audio_missing=row["audio_missing"],
                                          estimated_seconds=row["estimated_duration"])
                self._end_run(run_id, "exists", result)
                return result

            messages: list[str] = []
            if row is None:
                self.log.info("Étapes 1 à 5 — profils, historique, vocabulaire appris, thème du jour, construction (%s)", day)
                content = self._create(day, messages)
                status = "created"
            else:
                content = json.loads(row["content_json"])
                status = "refreshed" if row["status"] == "complete" else "resumed"
                if status == "resumed":
                    self.log.warning("Reprise de la leçon n° %d du %s, interrompue avant la fin.", row["lesson_number"], day)
            number = content["number"]

            self.log.info("Étape 7 — fichiers audio de la leçon n° %d (seuls les manquants sont générés)", number)
            ready, missing = self._audio(content, with_audio)

            self.log.info("Étapes 8 à 10 — enregistrement, page HTML et index")
            html_path = self.renderer.render_lesson(number, content=content)
            self.conn.execute(
                "UPDATE lessons SET status = 'complete', html_path = ?, audio_missing = ?, updated_at = ? "
                "WHERE lesson_number = ?", (html_path, missing, db.utcnow(), number))
            self.renderer.render_neighbours(number)
            self.renderer.render_index()
            self.renderer.export_data()

            result = GenerationResult(status, number, day, content["title"]["fr"], content.get("kind", "unit"),
                                      html_path, ready, missing, self.library.run_calls, self.library.run_hits,
                                      content.get("estimated_seconds", 0), messages)
            if missing:
                result.messages.append(f"{missing} audio(s) pas encore disponible(s) : ils seront retentés automatiquement.")
            self.log.info("Étapes 11 et 12 — leçon n° %d « %s » : %d audio(s) prêt(s), %d manquant(s), "
                          "%d appel(s) TTS, %d réutilisation(s) du cache", number, result.title, ready, missing,
                          self.library.run_calls, self.library.run_hits)
            self._end_run(run_id, "ok", result)
            return result
        except BaseException as exc:
            self._end_run(run_id, "failed", None, message=f"{type(exc).__name__}: {exc}")
            raise

    # --- construction du contenu ------------------------------------------------------
    def _create(self, day: str, messages: list[str]) -> dict:
        self.curriculum.load()
        for name, issues in self.curriculum.rejected:
            messages.append(f"Unité écartée pour erreurs : {name} ({len(issues)} erreur(s))")
        with db.transaction(self.conn):
            if self.conn.execute("SELECT 1 FROM lessons WHERE lesson_date = ?", (day,)).fetchone():
                raise GenerationError(f"Une leçon existe déjà pour le {day}.")
            last = self.conn.execute("SELECT MAX(lesson_number) AS n, MAX(lesson_date) AS d FROM lessons").fetchone()
            number = (last["n"] or 0) + 1
            if last["d"] and day < last["d"]:
                messages.append(f"Date antérieure à la dernière leçon ({last['d']}) : la numérotation suit l'ordre de création.")
            used = {r["unit_id"] for r in self.conn.execute("SELECT unit_id FROM lessons WHERE unit_id IS NOT NULL")}
            unit = self.curriculum.next_unit(used, str(self.config.get("lesson.level", "auto")),
                                             list(self.config.get("lesson.themes", []) or []))
            now = db.utcnow()
            cur = self.conn.execute(
                "INSERT INTO lessons(lesson_number, lesson_date, theme, title_fr, title_en, title_km, level, kind, "
                "unit_id, content_json, status, created_at, updated_at) VALUES (?, ?, '', '', '', '', '', 'unit', NULL, '{}', 'draft', ?, ?)",
                (number, day, now, now))
            lesson_id = cur.lastrowid
            if unit is not None:
                content = self._from_unit(unit, day, number, lesson_id)
            else:
                content = self._review_lesson(day, number, lesson_id)
                messages.append("Programme terminé : leçon de révision composée à partir des acquis. "
                                "Ajoutez de nouvelles unités dans content/units pour continuer la progression.")
            self._add_review(content, day, lesson_id)
            content["estimated_seconds"] = estimate_seconds(content)
            content["quality"] = self._quality(content)
            self.conn.execute(
                "UPDATE lessons SET theme = ?, title_fr = ?, title_en = ?, title_km = ?, level = ?, kind = ?, unit_id = ?, "
                "estimated_duration = ?, content_json = ? WHERE id = ?",
                (content["theme"], content["title"]["fr"], content["title"]["en"], content["title"]["km"],
                 content["level"], content["kind"], content.get("unit_id"), content["estimated_seconds"],
                 json.dumps(content, ensure_ascii=False), lesson_id))
        self.log.info("Leçon n° %d construite : « %s » (%s, %s, ≈ %d min)", number, content["title"]["fr"],
                      content["kind"], content["level"], round(content["estimated_seconds"] / 60))
        quality = content["quality"]
        self.log.info("Étape 6 — contrôle des traductions : %d erreur(s), %d avertissement(s), %d à vérifier",
                      quality["errors"], quality["warnings"], quality["uncertain"])
        if quality["uncertain"]:
            messages.append(f"{quality['uncertain']} traduction(s) signalée(s) « à vérifier » dans cette leçon.")
        return content

    def _counts(self, unit: dict) -> tuple[int, int, int]:
        """Nombre de mots, d'expressions et de phrases, réduit si la leçon dépasserait la durée maximale."""
        lesson = self.config["lesson"]
        words = min(max(int(lesson.get("new_words", 6)), MIN_WORDS), 8, len(unit["vocabulary"]))
        expressions = min(max(int(lesson.get("expressions", 4)), MIN_EXPRESSIONS), 5, len(unit["expressions"]))
        sentences = min(int(lesson.get("sentences", 3)), len(unit["sentences"]))
        budget = int(lesson.get("max_duration_minutes", 10)) * 60
        fixed = SECONDS["sentences"] * sentences + SECONDS["dialogue"] * len(unit["dialogue"]["lines"]) + SECONDS["quiz"]

        def total() -> int:
            return fixed + SECONDS["vocabulary"] * words + SECONDS["expressions"] * expressions

        while total() > budget and words > MIN_WORDS:
            words -= 1
        while total() > budget and expressions > MIN_EXPRESSIONS:
            expressions -= 1
        return words, expressions, sentences

    def _from_unit(self, raw_unit: dict, day: str, number: int, lesson_id: int) -> dict:
        unit = personalize_tree({k: v for k, v in raw_unit.items() if not k.startswith("_")}, self.config["learners"])
        n_words, n_expressions, n_sentences = self._counts(unit)
        content = {
            "version": CONTENT_VERSION, "number": number, "date": day, "kind": "unit",
            "unit_id": unit["id"], "theme": unit["theme"], "level": unit["level"],
            "title": unit["title"], "tip": unit.get("tip"),
            "vocabulary": [], "expressions": [],
            "sentences": unit["sentences"][:n_sentences],
            "dialogue": unit["dialogue"],
            "review": {"words": [], "questions": [], "translation": None, "comprehension": unit["comprehension"]},
        }
        position = 0
        for section, kind, entries in (("vocabulary", "word", unit["vocabulary"][:n_words]),
                                       ("expressions", "expression", unit["expressions"][:n_expressions])):
            for entry in entries:
                vocab_id, is_new = self._upsert_vocab(entry, kind, unit["id"], lesson_id)
                item = dict(entry, vocab_id=vocab_id, is_new=is_new, kind=kind)
                content[section].append(item)
                self._link(lesson_id, vocab_id, is_new, section, position)
                position += 1
                if is_new:
                    srs.introduce(self.conn, vocab_id, day, self.intervals)
                else:
                    srs.record_review(self.conn, vocab_id, day, self.intervals)
        return content

    def _review_lesson(self, day: str, number: int, lesson_id: int) -> dict:
        """Leçon sans nouveauté, composée des acquis les moins bien maîtrisés."""
        past = self.conn.execute(
            "SELECT * FROM lessons WHERE kind = 'unit' AND content_json != '{}' ORDER BY lesson_number").fetchall()
        if not past:
            raise GenerationError(
                "Aucune unité valide dans content/units : impossible de construire une leçon. "
                "Lancez « python3 manage.py content check » pour voir les erreurs.")
        rotation = self.conn.execute("SELECT COUNT(*) FROM lessons WHERE kind = 'review' AND id != ?", (lesson_id,)).fetchone()[0]
        source_row = past[rotation % len(past)]
        source = json.loads(source_row["content_json"])
        lesson = self.config["lesson"]
        content = {
            "version": CONTENT_VERSION, "number": number, "date": day, "kind": "review",
            "unit_id": None, "theme": source["theme"], "level": past[-1]["level"],
            "source_lesson": source_row["lesson_number"],
            "title": {"fr": "Révision : " + source["title"]["fr"], "en": "Review: " + source["title"]["en"],
                      "km": "រំលឹកមេរៀន៖ " + source["title"]["km"]},
            "tip": source.get("tip"),
            "vocabulary": [], "expressions": [],
            "sentences": source.get("sentences", [])[:int(lesson.get("sentences", 3))],
            "dialogue": source["dialogue"],
            "review": {"words": [], "questions": [], "translation": None,
                       "comprehension": source.get("review", {}).get("comprehension")},
        }
        position = 0
        for section, kind, count in (("vocabulary", "word", max(MIN_WORDS, min(int(lesson.get("new_words", 6)), 8))),
                                     ("expressions", "expression", max(MIN_EXPRESSIONS, min(int(lesson.get("expressions", 4)), 5)))):
            rows = self.conn.execute(
                "SELECT v.*, MIN(p.mastery_score) AS mastery, MIN(p.last_review) AS seen, "
                "MIN(COALESCE(p.next_review, '9999-12-31')) AS due FROM vocabulary v "
                "LEFT JOIN learner_progress p ON p.vocabulary_id = v.id WHERE v.kind = ? GROUP BY v.id "
                "ORDER BY (due <= ?) DESC, mastery ASC, seen ASC, v.id ASC LIMIT ?", (kind, day, count)).fetchall()
            for row in rows:
                item = dict(_entry_from_row(row), is_new=False)
                content[section].append(item)
                self._link(lesson_id, row["id"], False, section, position)
                position += 1
                srs.record_review(self.conn, row["id"], day, self.intervals)
                self.conn.execute("UPDATE learner_progress SET last_review = ? WHERE vocabulary_id = ?", (day, row["id"]))
        return content

    def _add_review(self, content: dict, day: str, lesson_id: int) -> None:
        """Partie 5 : mots à revoir (répétition espacée), trois questions, traduction."""
        today_ids = {e["vocab_id"] for e in content["vocabulary"] + content["expressions"]}
        budget = int(self.config.get("lesson.max_duration_minutes", 10)) * 60
        room = max(0, (budget - estimate_seconds(content)) // SECONDS["review_word"])
        limit = min(int(self.config.get("review.max_items", 10)), room)
        words: list[dict] = []
        first_lessons = {r["id"]: r["lesson_number"] for r in self.conn.execute("SELECT id, lesson_number FROM lessons")}
        position = 100
        for due in srs.due_items(self.conn, day, self.intervals, limit, exclude=today_ids) if limit else []:
            row = self.conn.execute("SELECT * FROM vocabulary WHERE id = ?", (due["vocabulary_id"],)).fetchone()
            entry = _entry_from_row(row)
            entry.update(stage=due["stage"], due_for=sorted(due["due_for"]),
                         days=self.intervals[min(due["stage"], len(self.intervals)) - 1],
                         from_lesson=first_lessons.get(row["first_lesson_id"]))
            words.append(entry)
            srs.record_review(self.conn, row["id"], day, self.intervals)
            self._link(lesson_id, row["id"], False, "review", position)
            position += 1
        review = content["review"]
        review["words"] = words

        # Trois petites questions : d'abord les mots revus, puis ceux du jour.
        pool = [w for w in words if w["kind"] == "word"] + [w for w in words if w["kind"] != "word"]
        pool += list(reversed(content["vocabulary"]))
        questions, seen = [], set()
        for entry in pool:
            if entry["vocab_id"] in seen:
                continue
            seen.add(entry["vocab_id"])
            questions.append({k: entry.get(k, "") for k in ("vocab_id", "fr", "en", "km", "tr")}
                             | {"source": "review" if "stage" in entry else "today"})
            if len(questions) == 3:
                break
        review["questions"] = questions

        # Exercice de traduction : de préférence une phrase d'une ancienne leçon.
        asked = {q["vocab_id"] for q in questions}
        candidates = [w for w in sorted(words, key=lambda w: -w["stage"]) if w.get("example") and w["vocab_id"] not in asked]
        candidates += [w for w in words if w.get("example")]
        if candidates:
            review["translation"] = dict(candidates[0]["example"], source="review")
        elif content["sentences"]:
            review["translation"] = dict(content["sentences"][content["number"] % len(content["sentences"])], source="today")

    def _upsert_vocab(self, entry: dict, kind: str, unit_id: str, lesson_id: int) -> tuple[int, bool]:
        key = vocab_key(entry)
        row = self.conn.execute("SELECT id FROM vocabulary WHERE vocab_key = ?", (key,)).fetchone()
        if row:
            return row["id"], False
        note = entry.get("note") or {}
        cur = self.conn.execute(
            "INSERT INTO vocabulary(vocab_key, kind, french_text, english_text, khmer_text, transliteration, category, "
            "explanation_fr, explanation_km, example_json, uncertain, uncertain_note, unit_id, first_lesson_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (key, kind, entry["fr"], entry["en"], entry["km"], entry.get("tr", ""),
             entry.get("pos") or ("expression" if kind == "expression" else ""), note.get("fr", ""), note.get("km", ""),
             json.dumps(entry["example"], ensure_ascii=False) if entry.get("example") else None,
             1 if entry.get("uncertain") else 0, entry.get("uncertain_note"), unit_id, lesson_id, db.utcnow()))
        return cur.lastrowid, True

    def _link(self, lesson_id: int, vocab_id: int, is_new: bool, section: str, position: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO lesson_vocabulary(lesson_id, vocabulary_id, is_new, section, position) "
            "VALUES (?, ?, ?, ?, ?)", (lesson_id, vocab_id, 1 if is_new else 0, section, position))

    def _quality(self, content: dict) -> dict:
        """Étape 6 du processus quotidien : contrôle de cohérence des trois langues."""
        issues = []
        where = f"leçon {content['number']}"
        issues += check_trilingual(content["title"], f"{where}/titre", need_tr=False)
        for section in ("vocabulary", "expressions", "sentences"):
            for i, entry in enumerate(content[section], 1):
                issues += check_trilingual(entry, f"{where}/{section}[{i}]")
                if entry.get("example"):
                    issues += check_trilingual(entry["example"], f"{where}/{section}[{i}]/exemple")
        for i, line in enumerate(content["dialogue"]["lines"], 1):
            issues += check_trilingual(line, f"{where}/dialogue[{i}]")
        for issue in issues:
            if issue.level == "error":
                self.log.error("Qualité — %s", issue)
            elif issue.level == "warning":
                self.log.warning("Qualité — %s", issue)
        return dict(summarize(issues), issues=[str(i) for i in issues if i.level != "info"][:20])

    # --- audio --------------------------------------------------------------------------
    def _audio(self, content: dict, with_audio: bool = True) -> tuple[int, int]:
        ready = missing = 0
        include = bool(self.config.get("audio.include_examples", True))
        for lang, text in audio_items(content, include):
            ref = self.library.ensure(text, lang) if with_audio else self.library.lookup(text, lang)
            if ref.ready:
                ready += 1
            else:
                missing += 1
        return ready, missing

    def lesson_numbers(self) -> list[int]:
        return [r["lesson_number"] for r in self.conn.execute(
            "SELECT lesson_number FROM lessons WHERE content_json != '{}' ORDER BY lesson_number")]

    def repair_audio(self, scope: str = "all", lessons: list[int] | None = None) -> dict:
        """Régénère uniquement les audios manquants ou corrompus, puis met les pages à jour.

        ``scope="all"`` contrôle d'abord toute la bibliothèque (commande d'administration) ;
        ``scope="incomplete"`` ne traite que les leçons qui attendent encore des audios
        (reprise automatique quotidienne, très légère).
        """
        run_id = self._start_run("audio-repair", None)
        include = bool(self.config.get("audio.include_examples", True))
        needed: set[str] = set()
        totals = {"ready": 0, "missing": 0, "generated": 0, "lessons": 0, "damaged": 0}
        try:
            if scope == "all":
                totals["damaged"] = self.library.mark_damaged(self.library.verify())
            touched: list[int] = []
            rows = self.conn.execute("SELECT * FROM lessons WHERE content_json != '{}' ORDER BY lesson_number").fetchall()
            for row in rows:
                if lessons and row["lesson_number"] not in lessons:
                    continue
                if scope == "incomplete" and not (row["audio_missing"] or row["status"] != "complete"):
                    continue
                content = json.loads(row["content_json"])
                ready = missing = 0
                for lang, text in audio_items(content, include):
                    ref = self.library.ensure(text, lang)
                    needed.add(ref.text_hash)
                    ready, missing = ready + ref.ready, missing + (not ref.ready)
                totals["ready"] += ready
                totals["missing"] += missing
                totals["lessons"] += 1
                if row["status"] == "complete":
                    touched.append(row["lesson_number"])
                    self.conn.execute("UPDATE lessons SET audio_missing = ?, updated_at = ? WHERE id = ?",
                                      (missing, db.utcnow(), row["id"]))
            if scope == "all" and not lessons:
                from . import alphabet
                alpha = alphabet.ensure_audio(self.library, alphabet.load(self.config))
                needed |= alpha["hashes"]
                totals["ready"] += alpha["ready"]
                totals["missing"] += alpha["missing"]
                self.renderer.render_alphabet()
                self.library.prune_stale_missing(needed)
            totals["generated"] = len(self.library.run_generated)
            for number in touched:
                self.renderer.render_lesson(number)
            if touched:
                self.renderer.render_index()
                self.renderer.export_data()
            self._end_run(run_id, "ok", None,
                          message=f"{totals['generated']} audio(s) généré(s), {totals['missing']} manquant(s)")
            return totals
        except BaseException as exc:
            self._end_run(run_id, "failed", None, message=f"{type(exc).__name__}: {exc}")
            raise

    # --- journal des exécutions ---------------------------------------------------------------
    def _start_run(self, command: str, day: str | None) -> int:
        cur = self.conn.execute("INSERT INTO runs(started_at, command, lesson_date) VALUES (?, ?, ?)",
                                (db.utcnow(), command, day))
        return cur.lastrowid

    def _end_run(self, run_id: int, status: str, result: GenerationResult | None, message: str = "") -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at = ?, status = ?, tts_calls = ?, cache_hits = ?, errors = ?, message = ? WHERE id = ?",
            (db.utcnow(), status, self.library.run_calls, self.library.run_hits, self.library.run_errors,
             message or (result.title if result else ""), run_id))
