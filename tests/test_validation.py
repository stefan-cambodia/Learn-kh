"""Tests de validation de bout en bout (section 15 du cahier des charges).

Chaque test pilote la vraie ligne de commande (manage.py) dans un projet
temporaire. La synthèse vocale est assurée par un moteur local factice branché
sur le fournisseur « command » : il produit de vrais fichiers WAV et consigne
chaque appel, ce qui permet de compter précisément les synthèses effectuées.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
import wave
import zipfile
from pathlib import Path

from support import ROOT, Project

from frkh.generator import audio_items
from frkh.lock import ProcessLock
from frkh.textutil import has_khmer

DAYS = ("2026-03-01", "2026-03-02", "2026-03-03")
SOURCE_RE = re.compile(r'<source src="\.\./(audio/[^"]+)" type="audio/wav">')
EXTERNAL_RE = re.compile(r"""(?:src|href)\s*=\s*["'](?:https?:)?//|url\(\s*["']?(?:https?:)?//|@import\s+["']https?:""", re.I)


class ThreeLessonsTest(unittest.TestCase):
    """Trois leçons consécutives, puis tous les contrôles demandés sur le résultat."""

    @classmethod
    def setUpClass(cls):
        cls.project = Project()
        cls.outputs = [cls.project.run("generate", "--date", day).stdout for day in DAYS]

    @classmethod
    def tearDownClass(cls):
        cls.project.cleanup()

    # --- pages et index -------------------------------------------------------------
    def test_01_three_consecutive_lessons_each_with_its_own_page(self):
        rows = self.project.query("SELECT * FROM lessons ORDER BY lesson_number")
        self.assertEqual([r["lesson_number"] for r in rows], [1, 2, 3])
        self.assertEqual([r["lesson_date"] for r in rows], list(DAYS))
        self.assertTrue(all(r["status"] == "complete" for r in rows))
        self.assertEqual(len({r["unit_id"] for r in rows}), 3, "chaque leçon doit avoir son propre thème")
        pages = set()
        for row in rows:
            path = self.project.dir / row["html_path"]
            self.assertTrue(path.is_file(), row["html_path"])
            html = path.read_text(encoding="utf-8")
            pages.add(html)
            for part in ("vocabulary", "expressions", "sentences", "dialogue", "review"):
                self.assertIn(f'<section class="part part-{part}" id="{part}"', html)
            self.assertIn(row["title_fr"], html)
            self.assertIn(row["title_km"], html)
            self.assertIn('href="../index.html"', html)
            self.assertLessEqual(row["estimated_duration"], 600, "une leçon dure moins de 10 minutes")
        self.assertEqual(len(pages), 3)
        second = self.project.page(2)
        self.assertIn('href="lesson-001.html"', second)
        self.assertIn('href="lesson-003.html"', second)
        self.assertNotIn('href="lesson-000.html"', self.project.page(1))
        self.assertNotIn('href="lesson-004.html"', self.project.page(3))

    def test_02_index_lists_the_three_lessons_newest_first(self):
        index = self.project.index()
        numbers = [int(n) for n in re.findall(r'<li class="lesson-card"[^>]*data-number="(\d+)"', index)]
        self.assertEqual(numbers, [3, 2, 1])
        for number in (1, 2, 3):
            self.assertIn(f'href="lessons/lesson-{number:03d}.html"', index)
        self.assertIn("FR-KH Learning", index)
        self.assertIn('<time datetime="2026-03-03">', index)
        self.assertIn('id="search"', index)
        search = re.search(r'data-number="1"', index) and re.search(r'data-search="([^"]*)"[^>]*data-number="1"', index).group(1)
        first = self.project.lesson(1)["vocabulary"][0]
        for needle in ("2026-03-01", first["km"], first["en"].lower(), "salutations"):
            self.assertIn(needle, search, f"la recherche doit couvrir « {needle} »")

    # --- traductions et khmer ---------------------------------------------------------
    def test_03_translations_present_in_three_languages(self):
        for number in (1, 2, 3):
            content = self.project.lesson(number)
            self.assertTrue(5 <= len(content["vocabulary"]) <= 8)
            self.assertTrue(3 <= len(content["expressions"]) <= 5)
            self.assertEqual(len(content["sentences"]), 3)
            self.assertEqual(len(content["review"]["questions"]), 3)
            self.assertTrue(content["review"]["translation"])
            self.assertTrue(content["review"]["comprehension"])
            self.assertEqual({line["speaker"] for line in content["dialogue"]["lines"]}, {"A", "B"})
            entries = content["vocabulary"] + content["expressions"] + content["sentences"] + content["dialogue"]["lines"]
            entries += [e["example"] for e in content["vocabulary"]]
            for entry in entries:
                for lang in ("fr", "en", "km"):
                    self.assertTrue(entry.get(lang, "").strip(), f"leçon {number} : texte {lang} manquant dans {entry}")
                self.assertTrue(has_khmer(entry["km"]), entry["km"])
                self.assertFalse(has_khmer(entry["fr"] + entry["en"]))
                self.assertTrue(entry.get("tr"), "la translittération accompagne le khmer")
                self.assertNotIn("{", entry["fr"] + entry["en"] + entry["km"], "variables remplacées par les prénoms")
            self.assertEqual(content["quality"]["errors"], 0)
            for entry in content["vocabulary"]:
                self.assertTrue(entry["pos"] and entry["note"]["fr"] and entry["note"]["en"] and entry["note"]["km"])

    def test_04_khmer_is_rendered_with_embedded_unicode_font(self):
        html = self.project.page(1)
        self.assertIn('<meta charset="utf-8">', html)
        first = self.project.lesson(1)["vocabulary"][0]
        self.assertIn(f'<p class="lang-main" lang="km">{first["km"]}</p>', html)
        self.assertIsNone(re.search(r"&#x?1[79]|&#6\d{3};", html), "le khmer est écrit en caractères Unicode, pas en entités")
        css = (self.project.dir / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("@font-face", css)
        fonts = re.findall(r'url\("?(\.\./fonts/[^")]+)"?\)', css)
        self.assertTrue(fonts, "la police khmère doit être chargée depuis le dossier local fonts/")
        for font in fonts:
            data = (self.project.dir / "css" / font).resolve().read_bytes()
            self.assertGreater(len(data), 50000)
            # Police khmère en TrueType ; police des titres (Fraunces) en WOFF2.
            self.assertIn(data[:4], (b"\x00\x01\x00\x00", b"wOF2"), "fichier TrueType ou WOFF2 attendu")
            if "Khmer" in font:
                self.assertEqual(data[:4], b"\x00\x01\x00\x00", "fichier TrueType attendu pour le khmer")
        self.assertIn("Noto Sans Khmer", css)

    # --- audio ---------------------------------------------------------------------------
    def test_05_every_audio_link_points_to_a_valid_wav(self):
        seen = set()
        for number in (1, 2, 3):
            html = self.project.page(number)
            sources = SOURCE_RE.findall(html)
            self.assertGreater(len(sources), 30)
            self.assertNotIn("audio-missing", html)
            self.assertEqual(html.count("<audio controls preload=\"none\""), len(sources))
            for lang, locale in (("fr", "fr-FR"), ("en", "en-US"), ("km", "km-KH"), ("es", "es-ES"),
                                 ("it", "it-IT"), ("ru", "ru-RU"), ("zh", "zh-CN")):
                self.assertTrue(any(s.startswith(f"audio/{locale}/") for s in sources), f"audio {lang} absent")
            for source in sources:
                self.assertRegex(source, r"^audio/(fr-FR|en-US|km-KH|es-ES|it-IT|ru-RU|zh-CN)/[a-z0-9-]+_[0-9a-f]{12}\.wav$")
                seen.add(source)
        for source in seen:
            with wave.open(str(self.project.dir / source), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1, "mono")
                self.assertEqual(wav.getsampwidth(), 2, "16 bits")
                self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(wav.getcomptype(), "NONE", "PCM non compressé")
                self.assertGreater(wav.getnframes(), 1000)
        ready = self.project.scalar("SELECT COUNT(*) FROM audio_files WHERE status = 'ready'")
        self.assertEqual(ready, len(self.project.wav_files()))
        self.assertEqual({str(p.relative_to(self.project.dir)).replace(os.sep, "/") for p in self.project.wav_files()}, seen)

    def test_06_word_reused_in_two_lessons_is_synthesized_once(self):
        calls = self.project.calls()
        self.assertEqual(len(calls), len(set(calls)), "aucun texte ne doit être synthétisé deux fois")
        first = set(audio_items(self.project.lesson(1)))
        second = set(audio_items(self.project.lesson(2)))
        shared = first & second
        self.assertTrue(shared, "la leçon 2 doit réutiliser des mots de la leçon 1 (révision)")
        for item in shared:
            self.assertEqual(calls.count(item), 1, f"« {item[1]} » réutilisé : un seul appel TTS attendu")
        reused = int(re.search(r"réutilisations du cache : (\d+)", self.outputs[1]).group(1))
        self.assertGreaterEqual(reused, len(shared), "les audios communs viennent du cache")
        self.assertEqual(len(calls), self.project.scalar("SELECT COUNT(*) FROM audio_files"))

        before = len(calls)
        output = self.project.run("generate", "--date", DAYS[0], "--force").stdout
        self.assertIn("Appels TTS      : 0", output)
        self.assertEqual(len(self.project.calls()), before, "repasser sur une leçon ne relance aucune synthèse")

        stats = json.loads(self.project.run("stats", "--json").stdout)
        self.assertEqual(stats["audio"]["tts_calls"], before)
        self.assertGreater(stats["audio"]["cache_hits"], 0)
        self.assertEqual(stats["audio"]["files"], before)
        self.assertGreater(stats["audio"]["bytes"], 0)

    def test_07_same_date_never_generates_a_second_lesson(self):
        before = len(self.project.calls())
        output = self.project.run("generate", "--date", DAYS[1]).stdout
        self.assertIn("La leçon existe déjà", output)
        self.assertEqual(self.project.scalar("SELECT COUNT(*) FROM lessons"), 3)
        self.assertEqual(len(self.project.calls()), before)

    def test_08_deleted_audio_file_is_the_only_one_regenerated(self):
        row = self.project.query("SELECT * FROM audio_files WHERE language = 'fr' AND text = 'merci'")[0]
        target = self.project.dir / row["file_path"]
        others = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in self.project.wav_files() if p != target}
        before = self.project.calls()
        target.unlink()

        verify = self.project.run("audio", "verify", expect=1).stdout
        self.assertIn("Supprimés du disque  : 1", verify)
        self.assertIn(row["file_path"], verify)
        self.assertIn("merci", self.project.run("audio", "missing").stdout)

        repair = self.project.run("audio", "repair").stdout
        self.assertIn("Audios générés    : 1", repair)
        self.assertEqual(self.project.calls()[len(before):], [("fr", "merci")], "seul le fichier supprimé est régénéré")
        self.assertTrue(target.is_file())
        with wave.open(str(target), "rb") as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 24000))
        for path, state in others.items():
            self.assertEqual((path.stat().st_mtime_ns, path.stat().st_size), state, f"{path.name} ne devait pas être touché")
        self.assertIn("Corrompus            : 0", self.project.run("audio", "verify").stdout)
        self.assertNotIn("audio-missing", self.project.page(1))

    def test_09_corrupted_audio_file_is_detected_and_repaired(self):
        row = self.project.query("SELECT * FROM audio_files WHERE language = 'en' AND text = 'thank you'")[0]
        target = self.project.dir / row["file_path"]
        data = target.read_bytes()
        target.write_bytes(data[:len(data) // 2])
        before = len(self.project.calls())
        verify = self.project.run("audio", "verify", expect=1).stdout
        self.assertIn("Corrompus            : 1", verify)
        fixed = self.project.run("audio", "verify", "--fix").stdout
        self.assertIn("1 fichier(s) régénéré(s)", fixed)
        self.assertEqual(self.project.calls()[before:], [("en", "thank you")])
        self.assertEqual(target.read_bytes(), data)

    def test_10_regenerate_one_specific_audio(self):
        row = self.project.query("SELECT * FROM audio_files WHERE language = 'fr' AND text = 'bonjour'")[0]
        before = len(self.project.calls())
        output = self.project.run("audio", "regen", "--text", "bonjour", "--lang", "fr").stdout
        self.assertIn(f"Régénéré : {row['file_path']}", output)
        self.assertEqual(self.project.calls()[before:], [("fr", "bonjour")])
        before = len(self.project.calls())
        self.project.run("audio", "regen", "--file", Path(row["file_path"]).name)
        self.assertEqual(self.project.calls()[before:], [("fr", "bonjour")])
        self.assertEqual(self.project.scalar("SELECT COUNT(*) FROM audio_files WHERE text = 'bonjour' AND language = 'fr'"), 1)

    # --- hors connexion et confidentialité --------------------------------------------------
    def test_11_site_works_offline_and_exposes_no_api_key(self):
        secret = "TEST-SECRET-KEY-0123456789"
        (self.project.dir / ".env").write_text(f"GOOGLE_TTS_API_KEY={secret}\nAZURE_SPEECH_KEY={secret}-AZ\n", encoding="utf-8")
        os.chmod(self.project.dir / ".env", 0o600)
        try:
            self.project.run("render", "--all")
            check = self.project.run("check").stdout
        finally:
            (self.project.dir / ".env").unlink()
        self.assertIn("Site autonome : aucune ressource externe", check)
        self.assertIn("Aucune clé API dans les pages", check)
        self.assertIn("Bilan : 0 erreur(s)", check)
        public = [self.project.dir / "index.html"]
        for name in ("lessons", "css", "js", "data"):
            public += [p for p in (self.project.dir / name).rglob("*") if p.is_file()]
        for path in public:
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn(secret, text, f"clé API exposée dans {path.name}")
            if path.suffix in (".html", ".css"):
                self.assertIsNone(EXTERNAL_RE.search(text), f"ressource externe dans {path.name}")
        for script in re.findall(r'<script[^>]*src="([^"]+)"', self.project.page(1)):
            self.assertTrue(script.startswith("../js/"), script)
        for name in ("lessons.json", "vocabulary.json", "audio-library.json"):
            self.assertTrue(json.loads((self.project.dir / "data" / name).read_text(encoding="utf-8")))

    # --- progression ----------------------------------------------------------------------------
    def test_12_spaced_repetition_reviews_yesterdays_words(self):
        first, second = self.project.lesson(1), self.project.lesson(2)
        taught = {e["vocab_id"] for e in first["vocabulary"] + first["expressions"]}
        words = second["review"]["words"]
        self.assertTrue(words, "la leçon du lendemain doit proposer des mots à revoir")
        for word in words:
            self.assertIn(word["vocab_id"], taught)
            self.assertEqual(word["days"], 1)
            self.assertEqual(word["from_lesson"], 1)
        self.assertIn("recall-list", self.project.page(2))
        reviewed = words[0]["vocab_id"]
        rows = self.project.query("SELECT * FROM learner_progress WHERE vocabulary_id = ?", (reviewed,))
        self.assertEqual({r["learner"] for r in rows}, {"fr", "en", "km"}, "un suivi par profil")
        for row in rows:
            self.assertEqual(row["introduced_on"], DAYS[0])
            self.assertEqual(row["last_review"], DAYS[1])
            self.assertEqual(row["next_review"], "2026-03-04", "prochaine révision à J+3")
            self.assertEqual(row["review_count"], 1)
            self.assertGreater(row["mastery_score"], 0)
        vocabulary = self.project.scalar("SELECT COUNT(*) FROM vocabulary")
        self.assertEqual(self.project.scalar("SELECT COUNT(*) FROM learner_progress"), 3 * vocabulary)
        self.assertEqual(self.project.scalar("SELECT COUNT(*) FROM lesson_vocabulary WHERE is_new = 1"), vocabulary,
                         "un mot n'est présenté comme nouveau qu'une seule fois")
        self.assertTrue(all(q["source"] == "review" for q in second["review"]["questions"]))

    # --- administration ---------------------------------------------------------------------------
    def test_13_administration_commands(self):
        run = self.project.run
        self.assertIn("3 page(s) de leçon", run("render", "--all").stdout)
        self.assertIn("lessons/lesson-002.html", run("render", "2").stdout)
        self.assertIn("Appels TTS effectués", run("stats").stdout)
        self.assertIn("Fichiers WAV", run("stats").stdout)
        self.assertIn("unité(s) valide(s)", run("content", "check").stdout)
        self.assertIn("leçon 1", run("content", "list").stdout)
        self.assertIn("Les salutations", run("lesson", "list").stdout)
        self.assertIn("prêt", run("tts", "status").stdout)
        self.assertIn("manage.py daily --quiet", run("schedule", "show").stdout)
        self.assertIn("Prochaines révisions", run("progress", "show").stdout)
        self.assertIn("0 audio(s) inutilisé(s)", run("audio", "prune", "--dry-run").stdout)

        self.assertIn("Sauvegarde créée", run("backup").stdout)
        backups = list((self.project.dir / "database" / "backups").glob("learning-*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes()[:15], b"SQLite format 3")

        out = self.project.dir / "sortie"
        run("export", "--out", str(out))
        archive = next(out.glob("fr-kh-learning-*.zip"))
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            self.assertIsNone(zf.testzip())
        for expected in ("fr-kh-learning/index.html", "fr-kh-learning/lessons/lesson-001.html",
                         "fr-kh-learning/css/style.css", "fr-kh-learning/js/app.js",
                         "fr-kh-learning/fonts/NotoSansKhmer-Regular.ttf", "fr-kh-learning/data/lessons.json",
                         "fr-kh-learning/data/lessons/lesson-003.json"):
            self.assertIn(expected, names)
        self.assertTrue(any(n.startswith("fr-kh-learning/audio/km-KH/") for n in names))
        self.assertFalse(any(".env" in n or "learning.db" in n or "config.json" in n for n in names))

        self.assertIn("est marqué comme acquis", run("progress", "master", "--learner", "km", "--word", "merci").stdout)
        row = self.project.query("SELECT p.* FROM learner_progress p JOIN vocabulary v ON v.id = p.vocabulary_id "
                                 "WHERE v.french_text = 'merci' AND p.learner = 'km'")[0]
        self.assertIsNone(row["next_review"])
        self.assertEqual(row["mastery_score"], 1)
        self.assertIn("sera revu dès demain", run("progress", "forget", "--learner", "both", "--word", "merci").stdout)

    def test_14_manual_correction_updates_page_and_only_the_changed_audio(self):
        content = self.project.lesson(1)
        old = content["vocabulary"][0]["example"]["fr"]
        new = "Bonjour, vous allez bien ?"
        simulation = self.project.run("correct", "--find", old, "--replace", new, "--lang", "fr", "--dry-run").stdout
        self.assertIn("[simulation]", simulation)
        self.assertIn(old, json.dumps(self.project.lesson(1), ensure_ascii=False))
        before = len(self.project.calls())
        self.project.run("correct", "--find", old, "--replace", new, "--lang", "fr")
        self.assertEqual(self.project.lesson(1)["vocabulary"][0]["example"]["fr"], new)
        self.assertIn(new, self.project.page(1))
        self.assertNotIn(f">{old}<", self.project.page(1))
        self.assertEqual(self.project.calls()[before:], [("fr", new)], "seul l'audio du texte corrigé est généré")
        unit = next((self.project.dir / "content" / "units").glob("u001-*.json")).read_text(encoding="utf-8")
        self.assertIn(new, unit, "la correction est reportée dans l'unité source")

        stale = self.project.query("SELECT * FROM audio_files WHERE language = 'fr' AND text = ?", (old,))[0]
        files = len(self.project.wav_files())
        dry = self.project.run("audio", "prune", "--dry-run").stdout
        self.assertIn("1 audio(s) inutilisé(s)", dry)
        self.assertIn(stale["file_path"], dry)
        self.assertTrue((self.project.dir / stale["file_path"]).is_file(), "la simulation ne supprime rien")
        self.project.run("audio", "prune")
        self.assertFalse((self.project.dir / stale["file_path"]).exists())
        self.assertEqual(len(self.project.wav_files()), files - 1, "seul l'audio devenu inutile est supprimé")
        self.assertIn("Corrompus            : 0", self.project.run("audio", "verify").stdout)

        exported = self.project.dir / "lecon-2.json"
        self.project.run("lesson", "export", "2", str(exported))
        payload = json.loads(exported.read_text(encoding="utf-8"))
        payload["sentences"][0]["en"] = "Hello, my name is Alex and I am very happy."
        exported.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.project.run("lesson", "import", str(exported))
        self.assertIn("I am very happy.", self.project.page(2))
        payload["sentences"][0]["km"] = "no khmer here"
        exported.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.project.run("lesson", "import", str(exported), expect=1)

    def test_15_site_in_a_real_browser(self):
        """Lecture réelle des WAV, police khmère, recherche et absence de requête réseau (Firefox + Node.js)."""
        if os.environ.get("FRKH_SKIP_BROWSER") or not (shutil.which("node") and shutil.which("firefox")):
            self.skipTest("Node.js et Firefox sont nécessaires pour ce contrôle")
        proc = subprocess.run(["node", str(ROOT / "tests" / "browser_check.mjs"), str(self.project.dir)],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 échec(s)", proc.stdout)


class InterruptionTest(unittest.TestCase):
    """Coupure brutale pendant la génération, puis reprise sans duplication."""

    def setUp(self):
        self.project = Project(units=("u001", "u002"))
        self.addCleanup(self.project.cleanup)

    def test_killed_generation_resumes_without_duplicates(self):
        killed = self.project.run("generate", "--date", DAYS[0], env={"FAKE_TTS_KILL_AT": "10"}, expect=None)
        self.assertNotEqual(killed.returncode, 0, "le processus doit avoir été tué en pleine génération")
        self.assertEqual(len(self.project.calls()), 10)
        rows = self.project.query("SELECT * FROM lessons")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "draft", "une leçon inachevée n'est pas publiée")
        self.assertFalse((self.project.dir / "lessons" / "lesson-001.html").exists())
        self.assertEqual(len(self.project.wav_files()), 9, "les neuf audios terminés avant la coupure sont conservés")
        self.assertFalse(list((self.project.dir / "audio").rglob(".tmp-*")), "aucun fichier à moitié écrit")
        vocabulary = self.project.scalar("SELECT COUNT(*) FROM vocabulary")
        self.assertIn("Leçons interrompues à reprendre : 1", self.project.run("check", expect=None).stdout)

        resumed = self.project.run("generate", "--date", DAYS[0]).stdout
        self.assertIn("Leçon reprise après interruption", resumed)
        rows = self.project.query("SELECT * FROM lessons")
        self.assertEqual(len(rows), 1, "pas de leçon en double")
        self.assertEqual((rows[0]["lesson_number"], rows[0]["status"], rows[0]["audio_missing"]), (1, "complete", 0))
        self.assertTrue((self.project.dir / "lessons" / "lesson-001.html").is_file())
        self.assertEqual(self.project.scalar("SELECT COUNT(*) FROM vocabulary"), vocabulary, "pas de vocabulaire en double")
        self.assertEqual(self.project.scalar("SELECT COUNT(*) FROM learner_progress"), 3 * vocabulary)

        calls = self.project.calls()
        for item in calls[:9]:
            self.assertEqual(calls.count(item), 1, "un audio déjà enregistré n'est pas resynthétisé à la reprise")
        self.assertEqual(calls.count(calls[9]), 2, "seul l'audio interrompu est redemandé")
        self.assertEqual(len(calls), len(set(calls)) + 1)
        self.assertEqual(len(self.project.wav_files()), len(set(calls)))

        self.project.run("generate", "--date", DAYS[1])
        self.assertEqual([r["lesson_number"] for r in self.project.query("SELECT lesson_number FROM lessons ORDER BY 1")], [1, 2])
        self.assertIn('data-number="2"', self.project.index())

    def test_two_generations_cannot_run_at_the_same_time(self):
        self.project.run("init")
        lock = ProcessLock(self.project.dir / "database" / ".generation.lock").acquire()
        try:
            busy = self.project.run("generate", "--date", DAYS[0], expect=2)
            self.assertIn("déjà en cours", busy.stderr)
            self.assertEqual(self.project.scalar("SELECT COUNT(*) FROM lessons"), 0)
        finally:
            lock.release()
        self.project.run("generate", "--date", DAYS[0], "--no-audio")
        self.assertEqual(self.project.scalar("SELECT COUNT(*) FROM lessons"), 1)


class ProviderOutageTest(unittest.TestCase):
    """Fournisseur vocal en panne : la leçon est créée quand même, l'audio est rattrapé ensuite."""

    def setUp(self):
        self.project = Project(units=("u001", "u002"))
        self.addCleanup(self.project.cleanup)

    def test_outage_does_not_block_the_lesson_and_audio_is_retried(self):
        output = self.project.run("generate", "--date", DAYS[0], env={"FAKE_TTS_FAIL": "1"}).stdout
        self.assertIn("Nouvelle leçon créée", output)
        row = self.project.query("SELECT * FROM lessons")[0]
        self.assertEqual(row["status"], "complete")
        self.assertGreater(row["audio_missing"], 30)
        html = self.project.page(1)
        self.assertIn("audio-missing", html)
        self.assertIn("Audio pas encore disponible", html)
        self.assertIn(self.project.lesson(1)["vocabulary"][0]["km"], html, "le texte est conservé")
        self.assertNotIn("<audio", html)
        self.assertIn("badge-pending", self.project.index())
        self.assertEqual(self.project.wav_files(), [])
        self.assertLessEqual(len(self.project.calls()), 4, "un fournisseur en panne n'est pas sollicité en boucle")
        self.assertIn("fichier(s) à générer", self.project.run("audio", "missing").stdout)
        errors = (self.project.dir / "logs" / "errors.log").read_text(encoding="utf-8")
        self.assertIn("Échec de la synthèse", errors)

        # Le lendemain, la tâche planifiée crée la nouvelle leçon et rattrape les audios en attente.
        self.project.run("daily", env={"FRKH_NOW": f"{DAYS[1]}T07:05:00"})
        self.project.run("daily", env={"FRKH_NOW": f"{DAYS[1]}T08:10:00"})
        rows = self.project.query("SELECT * FROM lessons ORDER BY lesson_number")
        self.assertEqual([(r["status"], r["audio_missing"]) for r in rows], [("complete", 0), ("complete", 0)])
        self.assertNotIn("audio-missing", self.project.page(1))
        self.assertIn("<audio controls preload=\"none\"", self.project.page(1))
        self.assertNotIn("badge-pending", self.project.index())

    def test_a_valid_audio_is_never_overwritten_by_a_failed_attempt(self):
        self.project.run("generate", "--date", DAYS[0])
        row = self.project.query("SELECT * FROM audio_files WHERE language = 'km' ORDER BY id LIMIT 1")[0]
        target = self.project.dir / row["file_path"]
        original = target.read_bytes()
        failed = self.project.run("audio", "regen", "--hash", row["text_hash"][:16], env={"FAKE_TTS_FAIL": "1"}, expect=1)
        self.assertIn("l'ancien fichier, s'il existe, est conservé", failed.stdout)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(self.project.scalar("SELECT status FROM audio_files WHERE text_hash = ?", (row["text_hash"],)), "ready")
        self.assertNotIn("audio-missing", self.project.page(1))

    def test_consumption_limits_stop_the_calls_but_not_the_lesson(self):
        project = Project(units=("u001",), config={"tts": {"limits": {"max_chars_per_day": 60}}})
        self.addCleanup(project.cleanup)
        project.run("generate", "--date", DAYS[0])
        self.assertLessEqual(sum(len(text) for _, text in project.calls()), 60)
        self.assertGreater(len(project.calls()), 0)
        row = project.query("SELECT * FROM lessons")[0]
        self.assertEqual(row["status"], "complete")
        self.assertGreater(row["audio_missing"], 0)
        self.assertIn("limite quotidienne", (project.dir / "logs" / "app.log").read_text(encoding="utf-8"))


class DailyScheduleTest(unittest.TestCase):
    """Tâche planifiée : heure de génération, une seule leçon par jour, rattrapage, sauvegardes."""

    def setUp(self):
        self.project = Project()
        self.addCleanup(self.project.cleanup)

    def daily(self, moment: str, **env) -> str:
        return self.project.run("daily", env={"FRKH_NOW": moment, **env}).stdout

    def lessons(self) -> list[tuple[int, str, str]]:
        return [(r["lesson_number"], r["lesson_date"], r["status"])
                for r in self.project.query("SELECT * FROM lessons ORDER BY lesson_number")]

    def test_daily_job(self):
        self.daily("2026-03-10T06:30:00")
        self.assertEqual(self.lessons(), [], "rien avant 07h00, heure du Cambodge")
        self.daily("2026-03-10T00:10:00+00:00")
        self.assertEqual(self.lessons(), [(1, "2026-03-10", "complete")], "00h10 UTC = 07h10 à Phnom Penh")
        backups = sorted(p.name for p in (self.project.dir / "database" / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].startswith("learning-20260310-"))

        calls = len(self.project.calls())
        self.daily("2026-03-10T07:30:00")
        self.daily("2026-03-10T23:45:00")
        self.assertEqual(len(self.lessons()), 1, "une seule leçon par jour")
        self.assertEqual(len(self.project.calls()), calls)
        self.assertEqual(len(list((self.project.dir / "database" / "backups").glob("*.db"))), 1)

        self.daily("2026-03-11T07:00:00")
        self.daily("2026-03-13T09:00:00")          # machine éteinte le 12 : pas de leçon ce jour-là
        self.assertEqual(self.lessons(), [(1, "2026-03-10", "complete"), (2, "2026-03-11", "complete"),
                                          (3, "2026-03-13", "complete")])
        self.assertEqual(len(list((self.project.dir / "database" / "backups").glob("*.db"))), 3)

        # Coupure pendant la leçon du 14 : la tâche du lendemain la termine, puis crée celle du 15.
        kill_at = str(len(self.project.calls()) + 5)
        self.project.run("daily", env={"FRKH_NOW": "2026-03-14T07:00:00", "FAKE_TTS_KILL_AT": kill_at}, expect=None)
        self.assertEqual(self.lessons()[-1], (4, "2026-03-14", "draft"))
        self.assertNotIn('data-number="4"', self.project.index())
        self.daily("2026-03-15T07:00:00")
        self.assertEqual(self.lessons()[-2:], [(4, "2026-03-14", "complete"), (5, "2026-03-15", "complete")])
        index = self.project.index()
        self.assertEqual([int(n) for n in re.findall(r'data-number="(\d+)"', index)], [5, 4, 3, 2, 1])

    def test_review_lesson_when_the_syllabus_is_finished(self):
        project = Project(units=("u001", "u002"))
        self.addCleanup(project.cleanup)
        for day in DAYS:
            project.run("generate", "--date", day)
        rows = project.query("SELECT * FROM lessons ORDER BY lesson_number")
        self.assertEqual([r["kind"] for r in rows], ["unit", "unit", "review"])
        content = project.lesson(3)
        self.assertTrue(content["title"]["fr"].startswith("Révision : "))
        self.assertTrue(content["vocabulary"] and content["expressions"])
        self.assertTrue(all(not e["is_new"] for e in content["vocabulary"] + content["expressions"]))
        self.assertEqual(project.scalar("SELECT COUNT(*) FROM lesson_vocabulary WHERE lesson_id = ? AND is_new = 1", (rows[2]["id"],)), 0)
        self.assertIn("Leçon de révision", project.page(3))
        self.assertIn("Programme terminé", project.run("generate", "--date", "2026-03-04").stdout)
        self.assertEqual(len(project.calls()), len(set(project.calls())), "une leçon de révision réutilise les audios existants")


if __name__ == "__main__":
    unittest.main(verbosity=2)
