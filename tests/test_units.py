"""Tests unitaires : cache audio, format WAV, fournisseurs (via de faux serveurs HTTP),
répétition espacée, configuration et contrôle des contenus.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import io
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from support import ROOT, MockTTSServer, clean_env, make_wav

from frkh import db, srs
from frkh.audio import AudioLibrary, wavutil
from frkh.audio.providers import (SynthesisResult, TTSProvider, TTSRequestError, TTSTransientError,
                                  TTSUnavailable, create_provider, provider_names, register_provider)
from frkh.config import DEFAULT_CONFIG, ConfigError, load_config, load_env
from frkh.curriculum import Curriculum, personalize
from frkh.quality import check_bank, check_unit, summarize, vocab_key
from frkh.textutil import fold, format_date, khmer_issues, normalize_text, slugify, speech_text

GOOGLE_KEY = "test-google-key-0123456789"
AZURE_KEY = "test-azure-key-9876543210"


class MemoryTTS(TTSProvider):
    """Fournisseur en mémoire : produit un WAV valide et note chaque appel."""
    name = "memory"
    engine_version = "memory-1"

    def __init__(self):
        super().__init__({})
        self.calls: list[tuple[str, str, str]] = []
        self.error: Exception | None = None
        self.payload: bytes | None = None

    def configured(self):
        return True, ""

    def synthesize(self, text, spec):
        self.calls.append((spec.lang, text, spec.voice))
        if self.error is not None:
            raise self.error
        return SynthesisResult(self.payload or make_wav(spec.sample_rate, 0.3), "wav", spec.sample_rate)


class LibraryCase(unittest.TestCase):
    """Base : un projet vide dans un dossier temporaire, avec une bibliothèque audio prête."""

    config_overrides: dict = {}

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="frkh-unit-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        patcher = mock.patch.dict(os.environ, clean_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "config").mkdir()
        (self.root / "config" / "config.json").write_text(json.dumps(self.make_config()), encoding="utf-8")
        self.config = load_config(self.root)
        self.config.paths.ensure()
        self.conn = db.connect(self.config.paths.database)
        self.addCleanup(self.conn.close)
        self.records: list[logging.LogRecord] = []
        self.logger = logging.getLogger(f"frkh.test.{id(self)}")
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)
        handler = logging.Handler()
        handler.emit = self.records.append
        self.logger.addHandler(handler)
        self.sleeps: list[float] = []

    def make_config(self) -> dict:
        memory = {"provider": "memory", "fallback": None}
        return {"languages": {"fr": dict(memory, locale="fr-FR", voice="v-fr"),
                              "en": dict(memory, locale="en-US", voice="v-en"),
                              "km": dict(memory, locale="km-KH", voice="v-km")},
                **self.config_overrides}

    def library(self, **providers) -> AudioLibrary:
        return AudioLibrary(self.config, self.conn, self.logger, providers=providers or None, sleep=self.sleeps.append)

    def log_text(self) -> str:
        return "\n".join(record.getMessage() for record in self.records)


class AudioCacheTest(LibraryCase):
    def setUp(self):
        super().setUp()
        self.tts = MemoryTTS()
        self.lib = self.library(memory=self.tts)

    def test_same_text_is_generated_once_and_file_name_is_deterministic(self):
        first = self.lib.ensure("Bonjour", "fr")
        again = self.lib.ensure("Bonjour", "fr")
        self.assertTrue(first.ready and again.ready)
        self.assertEqual(first.source, "generated")
        self.assertEqual(first.path, again.path)
        self.assertRegex(first.path, r"^audio/fr-FR/bonjour_[0-9a-f]{12}\.wav$")
        self.assertEqual(first.path, f"audio/fr-FR/bonjour_{first.text_hash[:12]}.wav")
        self.assertEqual(len(first.text_hash), 64, "empreinte SHA-256")
        self.assertEqual(len(self.tts.calls), 1)

        other_run = self.library(memory=self.tts)             # nouvelle exécution, même base
        reused = other_run.ensure("Bonjour", "fr")
        self.assertEqual((reused.source, reused.path), ("cache", first.path))
        self.assertEqual(len(self.tts.calls), 1)
        self.assertEqual((other_run.run_calls, other_run.run_hits), (0, 1))
        self.assertEqual(db.counter_total(self.conn, "cache_hits"), 2)

    def test_identical_looking_texts_share_one_file(self):
        composed, decomposed = "café  crème", "café crème​ "
        self.assertEqual(self.lib.ensure(composed, "fr").path, self.lib.ensure(decomposed, "fr").path)
        self.assertEqual(len(self.tts.calls), 1)

    def test_same_text_in_another_language_is_a_different_audio(self):
        fr, en = self.lib.ensure("six", "fr"), self.lib.ensure("six", "en")
        self.assertNotEqual(fr.text_hash, en.text_hash)
        self.assertTrue(fr.path.startswith("audio/fr-FR/") and en.path.startswith("audio/en-US/"))
        km = self.lib.ensure("សួស្តី", "km")
        self.assertRegex(km.path, r"^audio/km-KH/km_[0-9a-f]{12}\.wav$")
        self.assertEqual(len(self.tts.calls), 3)

    def test_cache_key_depends_on_every_synthesis_parameter(self):
        spec = self.lib.spec_for("fr")
        base = self.lib.cache_key("Bonjour", spec)
        self.assertEqual(base, self.lib.cache_key(" Bonjour ", spec))
        variants = {
            "texte": self.lib.cache_key("Bonjour !", spec),
            "voix": self.lib.cache_key("Bonjour", dataclasses.replace(spec, voice="autre")),
            "locale": self.lib.cache_key("Bonjour", dataclasses.replace(spec, locale="fr-CA")),
            "langue": self.lib.cache_key("Bonjour", dataclasses.replace(spec, lang="en")),
            "vitesse": self.lib.cache_key("Bonjour", dataclasses.replace(spec, speaking_rate=1.0)),
            "hauteur": self.lib.cache_key("Bonjour", dataclasses.replace(spec, pitch=2.0)),
            "fréquence": self.lib.cache_key("Bonjour", dataclasses.replace(spec, sample_rate=22050)),
        }
        self.tts.engine_version = "memory-2"
        variants["version du moteur"] = self.lib.cache_key("Bonjour", spec)
        self.assertEqual(len({base, *variants.values()}), len(variants) + 1, variants)

    def test_changing_the_voice_creates_new_files_and_keeps_the_old_ones(self):
        old = self.lib.ensure("Bonjour", "fr")
        self.config.data["languages"]["fr"]["voice"] = "nouvelle-voix"
        new = self.library(memory=self.tts).ensure("Bonjour", "fr")
        self.assertNotEqual(old.path, new.path)
        self.assertTrue((self.root / old.path).is_file() and (self.root / new.path).is_file())
        self.assertEqual(len(self.tts.calls), 2)

    def test_existing_file_unknown_to_the_database_is_adopted(self):
        ref = self.lib.ensure("Bonjour", "fr")
        self.conn.execute("DELETE FROM audio_files")
        adopted = self.library(memory=self.tts).ensure("Bonjour", "fr")
        self.assertEqual((adopted.source, adopted.path), ("adopted", ref.path))
        self.assertEqual(len(self.tts.calls), 1, "un fichier valide déjà présent n'est jamais resynthétisé")
        self.assertEqual(self.conn.execute("SELECT status FROM audio_files").fetchone()[0], "ready")

    def test_missing_or_corrupted_file_is_regenerated(self):
        ref = self.lib.ensure("Bonjour", "fr")
        path = self.root / ref.path
        path.write_bytes(path.read_bytes()[:100])
        lib = self.library(memory=self.tts)
        self.assertFalse(lib.lookup("Bonjour", "fr").ready)
        self.assertEqual(lib.ensure("Bonjour", "fr").source, "generated")
        path.unlink()
        self.assertEqual(self.library(memory=self.tts).ensure("Bonjour", "fr").source, "generated")
        self.assertEqual(len(self.tts.calls), 3)
        wavutil.inspect_wav_file(path, expected_rate=24000)

    def test_failed_synthesis_never_overwrites_a_valid_file(self):
        ref = self.lib.ensure("Bonjour", "fr")
        original = (self.root / ref.path).read_bytes()
        self.tts.error = TTSTransientError("panne")
        failed = self.library(memory=self.tts).ensure("Bonjour", "fr", force=True)
        self.assertFalse(failed.ready)
        self.assertEqual((self.root / ref.path).read_bytes(), original)
        self.assertEqual(self.conn.execute("SELECT status FROM audio_files").fetchone()[0], "ready")
        self.tts.error, self.tts.payload = None, b"pas du son"
        self.assertFalse(self.library(memory=self.tts).ensure("Bonjour", "fr", force=True).ready)
        self.assertEqual((self.root / ref.path).read_bytes(), original, "une réponse invalide n'écrase rien")

    def test_outage_marks_audio_missing_and_stops_calling_the_provider(self):
        self.tts.error = TTSTransientError("service en panne")
        refs = [self.lib.ensure(text, "fr") for text in ("un", "deux", "trois", "quatre")]
        self.assertTrue(all(not r.ready for r in refs))
        self.assertEqual(len(self.tts.calls), 2 * 3, "trois tentatives pour deux textes, puis mise en pause")
        self.assertEqual(self.sleeps, [2.0, 4.0, 2.0, 4.0], "attente croissante entre les tentatives")
        rows = self.conn.execute("SELECT text, status, last_error FROM audio_files ORDER BY id").fetchall()
        self.assertEqual([r["status"] for r in rows], ["missing"] * 4)
        self.assertIn("service en panne", rows[0]["last_error"])
        self.assertEqual(self.lib.run_errors, 2)

        self.tts.error = None                                   # le service revient : nouvelle exécution
        later = self.library(memory=self.tts)
        self.assertTrue(all(later.ensure(text, "fr").ready for text in ("un", "deux", "trois", "quatre")))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM audio_files WHERE status = 'ready'").fetchone()[0], 4)

    def test_refused_credentials_stop_immediately(self):
        self.tts.error = TTSUnavailable("accès refusé (HTTP 403)")
        self.assertFalse(self.lib.ensure("un", "fr").ready)
        self.assertFalse(self.lib.ensure("deux", "fr").ready)
        self.assertEqual(len(self.tts.calls), 1)

    def test_invalid_request_is_not_retried(self):
        self.tts.error = TTSRequestError("voix inconnue")
        self.assertFalse(self.lib.ensure("un", "fr").ready)
        self.assertEqual((len(self.tts.calls), self.sleeps), (1, []))

    def test_usage_limits(self):
        self.config.data["tts"]["limits"] = {"max_calls_per_run": 2, "max_chars_per_day": 0, "max_chars_per_month": 0}
        lib = self.library(memory=self.tts)
        self.assertEqual([lib.ensure(t, "fr").ready for t in ("un", "deux", "trois")], [True, True, False])
        self.assertIn("appels par exécution", lib.ensure("trois", "fr").reason)
        self.config.data["tts"]["limits"] = {"max_calls_per_run": 0, "max_chars_per_day": 12, "max_chars_per_month": 0}
        lib = self.library(memory=self.tts)
        self.assertTrue(lib.ensure("quatre", "fr").ready)          # 2 + 4 + 6 = 12 caractères aujourd'hui
        self.assertIn("limite quotidienne", lib.ensure("cinq", "fr").reason)
        self.config.data["tts"]["limits"] = {"max_calls_per_run": 0, "max_chars_per_day": 0, "max_chars_per_month": 14}
        self.assertIn("limite mensuelle", self.library(memory=self.tts).ensure("cinq", "fr").reason)
        self.assertEqual(len(self.tts.calls), 3)

    def test_verify_reports_missing_corrupt_and_orphan_files(self):
        paths = [self.root / self.lib.ensure(t, "fr").path for t in ("un", "deux", "trois")]
        paths[0].unlink()
        paths[1].write_bytes(paths[1].read_bytes()[:-10])
        orphan = self.root / "audio" / "fr-FR" / "inconnu_000000000000.wav"
        orphan.write_bytes(make_wav())
        report = self.lib.verify(deep=True)
        self.assertEqual(report["ready"], 1)
        self.assertEqual([m["text"] for m in report["missing"]], ["un"])
        self.assertEqual([c["text"] for c in report["corrupt"]], ["deux"])
        self.assertEqual(report["orphans"], ["audio/fr-FR/inconnu_000000000000.wav"])
        self.assertEqual(self.lib.mark_damaged(report), 2)
        stats = self.lib.statistics()
        self.assertEqual((stats["files"], stats["missing"], stats["tts_calls"]), (1, 2, 3))

    def test_unknown_provider_is_reported_clearly(self):
        self.config.data["languages"]["fr"]["provider"] = "inexistant"
        ref = self.library().ensure("Bonjour", "fr")
        self.assertFalse(ref.ready)
        self.assertIn("fournisseur vocal inconnu", ref.reason)
        self.assertEqual(provider_names(), ["azure", "command", "google"])
        register_provider("memory-test", MemoryTTS)
        self.addCleanup(lambda: __import__("frkh.audio.providers", fromlist=["_REGISTRY"])._REGISTRY.pop("memory-test"))
        self.assertIn("memory-test", provider_names())


class WavFormatTest(unittest.TestCase):
    def read(self, data: bytes) -> tuple[int, int, int, int]:
        with wave.open(io.BytesIO(data), "rb") as wav:
            return wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()

    def test_conversion_to_pcm_16_bit_mono(self):
        for source in (make_wav(44100, 0.5, channels=2), make_wav(22050, 0.5), make_wav(16000, 0.5, bits=8),
                       make_wav(48000, 0.5, bits=24), make_wav(24000, 0.5, channels=2, bits=32)):
            for rate in (22050, 24000):
                channels, width, framerate, frames = self.read(wavutil.to_wav_pcm16_mono(source, "wav", rate))
                self.assertEqual((channels, width, framerate), (1, 2, rate))
                self.assertAlmostEqual(frames / rate, 0.5, delta=0.01)

    def test_raw_pcm_and_streaming_headers(self):
        raw = make_wav(16000, 0.4)[44:]
        self.assertEqual(self.read(wavutil.to_wav_pcm16_mono(raw, "pcm_s16le", 24000, 16000))[:3], (1, 2, 24000))
        with self.assertRaises(wavutil.AudioFormatError):
            wavutil.to_wav_pcm16_mono(raw, "pcm_s16le", 24000)
        streamed = make_wav(24000, 0.4, declared_size=0xFFFFFFFF)   # taille inconnue, courant en sortie d'API
        self.assertEqual(self.read(wavutil.to_wav_pcm16_mono(streamed, "wav", 24000)), (1, 2, 24000, 9600))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent")
    def test_compressed_audio_is_converted_with_ffmpeg(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "a.wav", Path(tmp) / "a.mp3"
            source.write_bytes(make_wav(24000, 0.6))
            done = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), str(target)], capture_output=True)
            if done.returncode != 0:
                self.skipTest("ffmpeg ne sait pas encoder le MP3 sur cette machine")
            channels, width, rate, frames = self.read(wavutil.to_wav_pcm16_mono(target.read_bytes(), "mp3", 22050))
        self.assertEqual((channels, width, rate), (1, 2, 22050))
        self.assertGreater(frames, 22050 * 0.5)

    def test_integrity_checks(self):
        good = make_wav(24000, 0.3)
        info = wavutil.inspect_wav_bytes(good, expected_rate=24000)
        self.assertEqual((info.channels, info.bits, info.sample_rate, info.frames), (1, 16, 24000, 7200))
        self.assertAlmostEqual(info.duration, 0.3, places=3)
        for label, data in (("vide", b""), ("pas un WAV", b"ID3" + bytes(100)), ("tronqué", good[:-200]),
                            ("muet", make_wav(24000, 0.3, amplitude=0.0)), ("trop court", make_wav(24000, 0.01)),
                            ("stéréo", make_wav(24000, 0.3, channels=2)), ("8 bits", make_wav(24000, 0.3, bits=8)),
                            ("mauvaise fréquence", make_wav(22050, 0.3))):
            with self.assertRaises(wavutil.AudioFormatError, msg=label):
                wavutil.inspect_wav_bytes(data, expected_rate=24000)
        with self.assertRaises(wavutil.AudioFormatError):
            wavutil.to_wav_pcm16_mono(b"", "wav", 24000)

    def test_quick_check_and_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sous" / "dossier" / "a.wav"
            wavutil.atomic_write(path, make_wav(24000, 0.3))
            self.assertEqual(wavutil.quick_check_file(path, 24000).frames, 7200)
            self.assertEqual([p.name for p in path.parent.iterdir()], ["a.wav"], "aucun fichier temporaire oublié")
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o600, 0o600)
                self.assertFalse(path.stat().st_mode & 0o111)
            self.assertEqual(len(wavutil.sha256_file(path)), 64)
            with self.assertRaises(wavutil.AudioFormatError):
                wavutil.quick_check_file(path, 22050)
            path.write_bytes(path.read_bytes()[:500])
            with self.assertRaises(wavutil.AudioFormatError):
                wavutil.quick_check_file(path, 24000)
            with self.assertRaises(wavutil.AudioFormatError):
                wavutil.quick_check_file(Path(tmp) / "absent.wav")


class GoogleProviderTest(LibraryCase):
    """Dialogue avec l'API REST Google Cloud Text-to-Speech (faux serveur local)."""

    def setUp(self):
        self.server = MockTTSServer()
        self.addCleanup(self.server.close)
        super().setUp()
        os.environ["GOOGLE_TTS_API_KEY"] = GOOGLE_KEY

    def make_config(self) -> dict:
        return {"tts": {"providers": {"google": {"endpoint": self.server.url + "/v1"}}}}

    def test_request_follows_the_official_rest_api(self):
        lib = self.library()
        ref = lib.ensure("Bonjour, comment ça va ?", "fr")
        self.assertTrue(ref.ready, ref.reason)
        request = self.server.requests[0]
        self.assertEqual((request["method"], request["path"]), ("POST", "/v1/text:synthesize"))
        self.assertEqual(request["headers"]["x-goog-api-key"], GOOGLE_KEY)
        self.assertNotIn(GOOGLE_KEY, request["path"], "la clé voyage dans un en-tête, jamais dans l'URL")
        self.assertEqual(json.loads(request["body"]), {
            "input": {"text": "Bonjour, comment ça va ?"},
            "voice": {"languageCode": "fr-FR", "name": "fr-FR-Neural2-F"},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000, "speakingRate": 0.9},
        })
        with wave.open(str(self.root / ref.path), "rb") as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 24000))
        row = self.conn.execute("SELECT * FROM audio_files").fetchone()
        self.assertEqual((row["provider"], row["voice"], row["locale"], row["engine_version"], row["format"]),
                         ("google", "fr-FR-Neural2-F", "fr-FR", "google-cloud-tts-v1", "wav/pcm_s16le/mono"))
        self.assertEqual(row["file_size"], (self.root / ref.path).stat().st_size)

        self.assertTrue(lib.ensure("Hello", "en").ready)
        self.assertEqual(json.loads(self.server.requests[1]["body"])["voice"], {"languageCode": "en-US", "name": "en-US-Neural2-F"})
        self.assertTrue(self.library().ensure("Bonjour, comment ça va ?", "fr").ready)
        self.assertEqual(len(self.server.requests), 2, "aucun nouvel appel pour un audio déjà en cache")

    def test_british_english_and_22050_hz_are_configurable(self):
        self.config.data["languages"]["en"].update(locale="en-GB", voice="en-GB-Neural2-A")
        self.config.data["audio"].update(sample_rate_hz=22050, speaking_rate=1.0)
        ref = self.library().ensure("Good morning", "en")
        body = json.loads(self.server.requests[0]["body"])
        self.assertEqual(body["voice"], {"languageCode": "en-GB", "name": "en-GB-Neural2-A"})
        self.assertEqual(body["audioConfig"], {"audioEncoding": "LINEAR16", "sampleRateHertz": 22050})
        self.assertTrue(ref.path.startswith("audio/en-GB/"))
        with wave.open(str(self.root / ref.path), "rb") as wav:
            self.assertEqual(wav.getframerate(), 22050)

    def test_audio_at_another_rate_is_resampled(self):
        self.server.wav_rate = 16000
        ref = self.library().ensure("Bonjour", "fr")
        with wave.open(str(self.root / ref.path), "rb") as wav:
            self.assertEqual(wav.getframerate(), 24000)

    def test_rate_limit_is_retried_then_succeeds(self):
        self.server.script = [(429, "application/json", b'{"error": {"message": "Quota exceeded"}}'),
                              (503, "text/plain", b"unavailable")]
        lib = self.library()
        self.assertTrue(lib.ensure("Bonjour", "fr").ready)
        self.assertEqual(len(self.server.requests), 3)
        self.assertEqual(self.sleeps, [2.0, 4.0])
        usage = [(r["success"], r["error"]) for r in self.conn.execute("SELECT * FROM tts_usage ORDER BY id")]
        self.assertEqual([u[0] for u in usage], [0, 0, 1])
        self.assertIn("Quota exceeded", usage[0][1])
        self.assertEqual(lib.statistics()["tts_failed"], 2)

    def test_rejected_key_pauses_the_provider_without_leaking_the_key(self):
        self.server.script = [(403, "application/json", b'{"error": {"message": "API key not valid"}}')]
        lib = self.library()
        first, second = lib.ensure("Bonjour", "fr"), lib.ensure("Merci", "fr")
        self.assertFalse(first.ready or second.ready)
        self.assertEqual(len(self.server.requests), 1, "une clé refusée n'est pas réessayée")
        self.assertIn("API key not valid", first.reason)
        dump = self.log_text() + json.dumps([dict(r) for r in self.conn.execute("SELECT * FROM tts_usage")]) \
            + json.dumps([dict(r) for r in self.conn.execute("SELECT * FROM audio_files")])
        self.assertIn("accès refusé", dump)
        self.assertNotIn(GOOGLE_KEY, dump, "la clé API ne doit apparaître ni dans les journaux ni dans la base")

    def test_bad_request_and_malformed_answer(self):
        self.server.script = [(400, "application/json", b'{"error": {"message": "Voice does not exist"}}'),
                              (200, "application/json", b'{"unexpected": true}')]
        lib = self.library()
        self.assertIn("Voice does not exist", lib.ensure("Bonjour", "fr").reason)
        self.assertIn("audioContent", lib.ensure("Merci", "fr").reason)
        self.assertEqual(len(self.server.requests), 2)
        self.assertEqual(self.sleeps, [])

    def test_network_failure_is_transient(self):
        self.config.data["tts"]["providers"]["google"]["endpoint"] = "http://127.0.0.1:9/v1"
        self.config.data["tts"]["retries"] = 2
        ref = self.library().ensure("Bonjour", "fr")
        self.assertFalse(ref.ready)
        self.assertIn("réseau indisponible", ref.reason)
        self.assertEqual(self.sleeps, [2.0])

    def test_voice_listing(self):
        voices = self.library().provider("google").list_voices("fr-FR")
        self.assertEqual(voices[0]["name"], "fr-FR-Neural2-F")
        self.assertEqual(self.server.requests[0]["path"], "/v1/voices?languageCode=fr-FR")

    def test_without_key_nothing_is_sent(self):
        del os.environ["GOOGLE_TTS_API_KEY"]
        ref = self.library().ensure("Bonjour", "fr")
        self.assertFalse(ref.ready)
        self.assertIn("GOOGLE_TTS_API_KEY", ref.reason)
        self.assertEqual(self.server.requests, [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tts_usage").fetchone()[0], 0)


class AzureProviderTest(LibraryCase):
    """Dialogue avec l'API REST Azure AI Speech, utilisée pour le khmer (faux serveur local)."""

    def setUp(self):
        self.server = MockTTSServer()
        self.addCleanup(self.server.close)
        super().setUp()
        os.environ.update(AZURE_SPEECH_KEY=AZURE_KEY, AZURE_SPEECH_ENDPOINT=self.server.url)

    def make_config(self) -> dict:
        return {}

    def test_khmer_request(self):
        ref = self.library().ensure("សួស្តី សុខសប្បាយទេ?", "km")
        self.assertTrue(ref.ready, ref.reason)
        request = self.server.requests[0]
        self.assertEqual((request["method"], request["path"]), ("POST", "/cognitiveservices/v1"))
        self.assertEqual(request["headers"]["ocp-apim-subscription-key"], AZURE_KEY)
        self.assertEqual(request["headers"]["content-type"], "application/ssml+xml")
        self.assertEqual(request["headers"]["x-microsoft-outputformat"], "riff-24khz-16bit-mono-pcm")
        self.assertTrue(request["headers"]["user-agent"])
        ssml = request["body"].decode("utf-8")
        self.assertIn('xml:lang="km-KH"', ssml)
        self.assertIn('<voice name="km-KH-SreymomNeural">', ssml)
        self.assertIn('<prosody rate="-10%">សួស្តី សុខសប្បាយទេ?</prosody>', ssml)
        self.assertTrue(ref.path.startswith("audio/km-KH/km_"))
        row = self.conn.execute("SELECT provider, voice, locale FROM audio_files").fetchone()
        self.assertEqual(tuple(row), ("azure", "km-KH-SreymomNeural", "km-KH"))

    def test_text_is_escaped_and_sample_rate_selects_the_format(self):
        self.config.data["audio"]["sample_rate_hz"] = 22050
        self.config.data["languages"]["km"]["voice"] = "km-KH-PisethNeural"
        ref = self.library().ensure('ក & ខ <គ>', "km")
        request = self.server.requests[0]
        self.assertEqual(request["headers"]["x-microsoft-outputformat"], "riff-22050hz-16bit-mono-pcm")
        self.assertIn("ក &amp; ខ &lt;គ&gt;", request["body"].decode("utf-8"))
        self.assertIn('<voice name="km-KH-PisethNeural">', request["body"].decode("utf-8"))
        with wave.open(str(self.root / ref.path), "rb") as wav:
            self.assertEqual(wav.getframerate(), 22050)

    def test_azure_takes_over_french_and_english_when_google_is_not_configured(self):
        lib = self.library()
        self.assertEqual((lib.spec_for("fr").provider, lib.spec_for("fr").voice), ("azure", "fr-FR-DeniseNeural"))
        self.assertEqual((lib.spec_for("en").provider, lib.spec_for("en").voice), ("azure", "en-US-JennyNeural"))
        self.assertTrue(lib.ensure("Bonjour", "fr").ready)
        self.assertIn('<voice name="fr-FR-DeniseNeural">', self.server.requests[0]["body"].decode("utf-8"))
        os.environ["GOOGLE_TTS_API_KEY"] = GOOGLE_KEY
        self.assertEqual(self.library().spec_for("fr").provider, "google", "Google reste prioritaire dès qu'il est configuré")

    def test_errors_and_voice_listing(self):
        self.server.script = [(401, "text/plain", b"Access denied due to invalid subscription key")]
        lib = self.library()
        self.assertIn("accès refusé", lib.ensure("សួស្តី", "km").reason)
        self.assertNotIn(AZURE_KEY, self.log_text())
        names = [v["name"] for v in self.library().provider("azure").list_voices("km-KH")]
        self.assertEqual(names, ["km-KH-SreymomNeural", "km-KH-PisethNeural"])

    def test_region_builds_the_official_endpoint(self):
        del os.environ["AZURE_SPEECH_ENDPOINT"]
        provider = create_provider("azure", {})
        self.assertEqual(provider.configured(), (False, "AZURE_SPEECH_REGION absent du fichier .env"))
        os.environ["AZURE_SPEECH_REGION"] = "SouthEastAsia"
        self.assertEqual(provider.configured(), (True, ""))
        self.assertEqual(provider._base(), "https://southeastasia.tts.speech.microsoft.com")


class SpacedRepetitionTest(unittest.TestCase):
    INTERVALS = [1, 3, 7, 14, 30]

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA)
        self.addCleanup(self.conn.close)

    def add_word(self, name: str, day: str, kind: str = "word") -> int:
        cur = self.conn.execute(
            "INSERT INTO vocabulary(vocab_key, kind, french_text, english_text, khmer_text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, kind, name, name, "ក", day))
        srs.introduce(self.conn, cur.lastrowid, day, self.INTERVALS)
        return cur.lastrowid

    def day(self, offset: int) -> str:
        return (dt.date(2026, 1, 1) + dt.timedelta(days=offset)).isoformat()

    def test_stage_follows_the_intervals(self):
        stages = [srs.stage_on(self.day(0), self.day(n), self.INTERVALS) for n in (0, 1, 2, 3, 6, 7, 13, 14, 29, 30, 90)]
        self.assertEqual(stages, [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5])

    def test_reviews_are_scheduled_at_1_3_7_14_30_days(self):
        word = self.add_word("bonjour", self.day(0))
        self.assertEqual(srs.due_items(self.conn, self.day(0), self.INTERVALS, 10), [])
        seen = []
        for offset in range(1, 40):
            due = srs.due_items(self.conn, self.day(offset), self.INTERVALS, 10)
            if due:
                self.assertEqual(sorted(due[0]["due_for"]), ["en", "fr", "km"])
                seen.append(offset)
                srs.record_review(self.conn, word, self.day(offset), self.INTERVALS)
        self.assertEqual(seen, [1, 3, 7, 14, 30])
        rows = self.conn.execute("SELECT * FROM learner_progress").fetchall()
        self.assertEqual(len(rows), 3, "un suivi par profil (fr, en, km)")
        for row in rows:
            self.assertIsNone(row["next_review"], "cycle terminé : le mot est acquis")
            self.assertEqual((row["review_count"], row["learning_level"], row["mastery_score"]), (5, 5, 1.0))
        self.assertEqual(srs.summary(self.conn, self.day(40))[0]["mastered"], 1)

    def test_daily_selection_is_limited_and_rotates_between_due_dates(self):
        old = [self.add_word(f"ancien{i}", self.day(0)) for i in range(4)]
        recent = [self.add_word(f"recent{i}", self.day(6)) for i in range(4)]
        self.add_word("expression", self.day(6), kind="expression")
        picked = srs.due_items(self.conn, self.day(7), self.INTERVALS, 4)
        self.assertEqual(len(picked), 4)
        ids = [p["vocabulary_id"] for p in picked]
        self.assertEqual(len(set(ids) & set(old)), 2, "les mots d'il y a 7 jours et ceux d'hier se partagent la place")
        self.assertEqual(len(set(ids) & set(recent)), 2)
        self.assertEqual({p["stage"] for p in picked}, {1, 3})
        self.assertEqual(srs.due_items(self.conn, self.day(7), self.INTERVALS, 10, exclude=set(old + recent))[0]["kind"], "expression")
        for vocab_id in ids:
            srs.record_review(self.conn, vocab_id, self.day(7), self.INTERVALS)
        again = [p["vocabulary_id"] for p in srs.due_items(self.conn, self.day(7), self.INTERVALS, 10)]
        self.assertFalse(set(again) & set(ids), "un mot révisé aujourd'hui n'est pas reproposé le même jour")

    def test_forget_and_master(self):
        word = self.add_word("merci", self.day(0))
        self.assertEqual(srs.master(self.conn, "km", word, self.day(2), self.INTERVALS), 1)
        due = srs.due_items(self.conn, self.day(2), self.INTERVALS, 10)
        self.assertEqual(sorted(due[0]["due_for"]), ["en", "fr"], "le mot acquis par le profil khmer n'est plus dû que pour les autres")
        srs.forget(self.conn, "km", word, self.day(5), self.INTERVALS)
        row = self.conn.execute("SELECT * FROM learner_progress WHERE learner = 'km'").fetchone()
        self.assertEqual((row["next_review"], row["review_count"], row["mastery_score"]), (self.day(6), 0, 0))


class TextAndContentTest(unittest.TestCase):
    def test_text_normalisation(self):
        self.assertEqual(normalize_text("  café​   noir﻿ "), "café noir")
        self.assertEqual(fold("Évidemment, l'Œuf À LA COQUE"), "evidemment, l'oeuf a la coque")
        self.assertEqual(fold("សួស្តី"), "សួស្តី", "le khmer n'est pas altéré par la recherche")
        self.assertEqual(slugify("S'il vous plaît !"), "s-il-vous-plait")
        self.assertEqual(slugify("សួស្តី", default="km"), "km")
        self.assertLessEqual(len(slugify("mot " * 40)), 32)
        self.assertEqual(speech_text("បាទ / ចាស"), "បាទ, ចាស")
        self.assertEqual(speech_text("Je m'appelle…"), "Je m'appelle")

    def test_khmer_spelling_checks(self):
        for word in ("ខ្ញុំ", "សួស្តី", "អរគុណ", "ឱ្យ", "ឲ្យ", "ញ៉ាំ", "ភោជនីយដ្ឋាន", "កុំព្យូទ័រ", "ស្ត្រី"):
            self.assertEqual(khmer_issues(word), [], word)
        for broken in ("្ក", "ក្", "កាា", "ាក", "ក្ ខ"):
            self.assertTrue(any(level == "error" for level, _ in khmer_issues(broken)), broken)

    def test_dates_in_three_languages(self):
        self.assertEqual(format_date("2026-11-01", "fr"), "dimanche 1er novembre 2026")
        self.assertEqual(format_date("2026-11-15", "en"), "Sunday, November 15, 2026")
        self.assertEqual(format_date("2026-11-15", "km"), "ថ្ងៃអាទិត្យ ទី១៥ ខែវិច្ឆិកា ឆ្នាំ២០២៦")

    def test_personalisation(self):
        characters = DEFAULT_CONFIG["characters"]
        self.assertEqual(personalize("Bonjour {A} !", "fr", characters), "Bonjour Dara !")
        self.assertEqual(personalize("{A_yes} {B}", "km", characters), "ចាស អាឡិច")
        self.assertEqual(personalize("{B_yes}, {A}", "tr", characters), "bat, da-ra")

    def test_unit_validation_catches_mistakes(self):
        unit = json.loads((ROOT / "content" / "units" / "u001-salutations.json").read_text(encoding="utf-8"))
        self.assertEqual(summarize(check_unit(unit))["errors"], 0)
        broken = json.loads(json.dumps(unit))
        broken["vocabulary"][0]["km"] = "sous-dey"
        broken["vocabulary"][1]["en"] = ""
        broken["vocabulary"][2]["pos"] = "truc"
        broken["expressions"][0]["fr"] = "Bonjour {C}"
        broken["dialogue"]["lines"] = [dict(line, speaker="A") for line in broken["dialogue"]["lines"]]
        broken["sentences"] = broken["sentences"][:2]
        messages = " | ".join(str(i) for i in check_unit(broken) if i.level == "error")
        for expected in ("caractères khmers", "texte « en » manquant", "catégorie grammaticale invalide",
                         "variable inconnue {C}", "faire parler A et B", "2 entrées"):
            self.assertIn(expected, messages)
        self.assertEqual(vocab_key({"fr": "Le Père !", "en": "FATHER"}), vocab_key({"fr": "le pere", "en": "father"}))
        duplicate = check_bank([unit, dict(unit, id="u999", order=999)])
        self.assertTrue(any("déjà enseigné" in str(i) for i in duplicate))

    def test_shipped_syllabus_is_valid(self):
        curriculum = Curriculum(ROOT / "content" / "units").load()
        summary = summarize(curriculum.issues)
        self.assertEqual(curriculum.rejected, [], "aucune unité livrée ne doit être écartée")
        self.assertEqual((summary["errors"], summary["warnings"]), (0, 0), [str(i) for i in curriculum.issues if i.level != "info"])
        self.assertGreaterEqual(len(curriculum.units), 21)
        self.assertEqual([u["order"] for u in curriculum.units], list(range(1, len(curriculum.units) + 1)))
        levels = [u["level"] for u in curriculum.units]
        self.assertEqual(levels, sorted(levels, key=("debutant", "elementaire", "intermediaire").index),
                         "progression du niveau débutant vers le niveau intermédiaire")
        self.assertEqual(curriculum.next_unit({"u001"})["id"], "u002")
        self.assertEqual(curriculum.next_unit(set(), themes=["au-marche"])["theme"], "au-marche")
        self.assertEqual(curriculum.next_unit(set(), level="elementaire")["level"], "elementaire")


class LocalServerTest(LibraryCase):
    """Le serveur local ne doit distribuer que le site, jamais les clés, la base ni la configuration."""

    def make_config(self) -> dict:
        return {}

    def setUp(self):
        super().setUp()
        import http.client
        import threading
        from frkh import admin
        for name, body in (("index.html", "<h1>accueil</h1>"), ("lessons/lesson-001.html", "<p>leçon</p>"),
                           ("css/style.css", "body{}"), (".env", "GOOGLE_TTS_API_KEY=" + GOOGLE_KEY),
                           ("manage.py", "print('code')")):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        (self.root / "audio" / "fr-FR").mkdir(parents=True, exist_ok=True)
        self.wav = make_wav(24000, 0.5)
        (self.root / "audio" / "fr-FR" / "bonjour_000000000000.wav").write_bytes(self.wav)
        self.server = admin.make_server(self.config, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.http = http.client

    def get(self, path: str, headers: dict | None = None):
        conn = self.http.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        try:
            conn.request("GET", path, headers=headers or {})          # chemin envoyé tel quel, sans normalisation
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def test_public_site_is_served(self):
        for path, expected in (("/", b"accueil"), ("/index.html", b"accueil"), ("/index.html?x=1#profil=A", b"accueil"),
                               ("/lessons/lesson-001.html", "leçon".encode()), ("/css/style.css", b"body{}")):
            status, body, _ = self.get(path)
            self.assertEqual((status, expected in body), (200, True), path)
        status, body, headers = self.get("/audio/fr-FR/bonjour_000000000000.wav")
        self.assertEqual((status, body), (200, self.wav))
        self.assertEqual(headers["Accept-Ranges"], "bytes")

    def test_private_files_are_never_served(self):
        secrets = ["/.env", "/manage.py", "/config/config.json", "/database/learning.db", "/database/",
                   "/lessons/../.env", "/lessons/%2e%2e/.env", "/css/..%2f.env", "/audio/%2e%2e/database/learning.db",
                   "/lessons/%2e%2e/config/config.json", "/lessons/..%5c.env", "/%2e%2e/%2e%2e/etc/passwd",
                   "/lessons//..//.env", "/lessons/", "/audio/fr-FR/"]
        for path in secrets:
            status, body, _ = self.get(path)
            self.assertEqual(status, 404, f"{path} ne doit pas être accessible")
            self.assertNotIn(GOOGLE_KEY.encode(), body, path)
        if hasattr(os, "symlink"):
            try:
                os.symlink(self.root / ".env", self.root / "lessons" / "lien.html")
            except OSError:
                return
            self.assertEqual(self.get("/lessons/lien.html")[0], 404, "un lien symbolique ne doit pas faire sortir du site")

    def test_partial_requests_for_audio(self):
        path = "/audio/fr-FR/bonjour_000000000000.wav"
        status, body, headers = self.get(path, {"Range": "bytes=0-99"})
        self.assertEqual((status, body, headers["Content-Range"]), (206, self.wav[:100], f"bytes 0-99/{len(self.wav)}"))
        status, body, _ = self.get(path, {"Range": "bytes=100-"})
        self.assertEqual((status, body), (206, self.wav[100:]))
        status, body, _ = self.get(path, {"Range": "bytes=-50"})
        self.assertEqual((status, body), (206, self.wav[-50:]))
        self.assertEqual(self.get(path, {"Range": f"bytes={len(self.wav) + 10}-"})[0], 416)
        self.assertEqual(self.get("/.env", {"Range": "bytes=0-5"})[0], 404)


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="frkh-conf-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        patcher = mock.patch.dict(os.environ, clean_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, payload: dict) -> None:
        (self.root / "config").mkdir(exist_ok=True)
        (self.root / "config" / "config.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_defaults_match_the_specification(self):
        config = load_config(self.root, create=True)
        self.assertTrue((self.root / "config" / "config.json").is_file())
        self.assertEqual(config.validate(), [])
        self.assertEqual((config.get("schedule.time"), config.get("schedule.timezone")), ("07:00", "Asia/Phnom_Penh"))
        self.assertEqual(config.get("review.intervals_days"), [1, 3, 7, 14, 30])
        self.assertEqual([config.locale(lang) for lang in ("fr", "en", "km")], ["fr-FR", "en-US", "km-KH"])
        self.assertEqual(config.get("audio.sample_rate_hz"), 24000)
        self.assertEqual(config.get("languages.fr.provider"), "google")
        self.assertEqual(config.now().utcoffset(), dt.timedelta(hours=7))

    def test_user_values_override_defaults_and_bad_values_are_reported(self):
        self.write({"schedule": {"time": "06:15"}, "lesson": {"new_words": 7}})
        config = load_config(self.root)
        self.assertEqual((config.schedule_time(), config.get("lesson.new_words"), config.get("lesson.expressions")),
                         (dt.time(6, 15), 7, 4))
        self.write({"schedule": {"time": "7h", "timezone": "Mars/Olympus"}, "audio": {"sample_rate_hz": 11025, "speaking_rate": 3},
                    "lesson": {"new_words": 12, "expressions": 1, "max_duration_minutes": 20},
                    "review": {"intervals_days": [3, 1]}, "characters": {"A": {"gender": "x"}},
                    "profiles": {"de": {"learns": ["fr"]}}, "site": {"default_profile": "xx"}})
        problems = " | ".join(load_config(self.root).validate())
        for expected in ("Fuseau horaire inconnu", "sample_rate_hz", "speaking_rate", "new_words", "expressions",
                         "max_duration_minutes", "intervals_days", "characters.A.gender", "profiles.de",
                         "site.default_profile"):
            self.assertIn(expected, problems)
        (self.root / "config" / "config.json").write_text("{ pas du json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(self.root)

    def test_env_file_is_loaded_without_overriding_the_environment(self):
        (self.root / ".env").write_text(
            '# commentaire\nGOOGLE_TTS_API_KEY="cle-du-fichier"\nexport AZURE_SPEECH_KEY=abc\nAZURE_SPEECH_REGION=\nLIGNE SANS EGAL\n',
            encoding="utf-8")
        os.environ["AZURE_SPEECH_KEY"] = "deja-defini"
        loaded = load_env(self.root / ".env")
        self.assertEqual(loaded, {"GOOGLE_TTS_API_KEY": "cle-du-fichier", "AZURE_SPEECH_KEY": "abc"})
        self.assertEqual(os.environ["GOOGLE_TTS_API_KEY"], "cle-du-fichier")
        self.assertEqual(os.environ["AZURE_SPEECH_KEY"], "deja-defini")
        self.assertNotIn("AZURE_SPEECH_REGION", os.environ)

    def test_forced_clock_is_converted_to_the_configured_timezone(self):
        config = load_config(self.root)
        os.environ["FRKH_NOW"] = "2026-03-09T23:30:00+00:00"
        self.assertEqual((config.today().isoformat(), config.now().hour), ("2026-03-10", 6))


if __name__ == "__main__":
    unittest.main(verbosity=2)
