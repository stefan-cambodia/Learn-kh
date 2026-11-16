"""Outils communs aux tests : projet temporaire, moteur vocal factice, faux serveurs TTS."""

from __future__ import annotations

import base64
import http.server
import json
import math
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE_TTS = ROOT / "tests" / "fake_tts.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SECRET_PREFIXES = ("GOOGLE_", "AZURE_", "FRKH_", "FAKE_TTS_")


def make_wav(sample_rate: int = 24000, seconds: float = 0.3, channels: int = 1, bits: int = 16,
             amplitude: float = 0.4, declared_size: int | None = None) -> bytes:
    """Fabrique un fichier WAV PCM contenant une note (440 Hz)."""
    frames = int(sample_rate * seconds)
    width = bits // 8
    body = bytearray()
    for i in range(frames):
        value = amplitude * math.sin(2 * math.pi * 440 * i / sample_rate)
        for _ in range(channels):
            if bits == 8:
                body += struct.pack("<B", int(128 + value * 127))
            elif bits == 16:
                body += struct.pack("<h", int(value * 32767))
            else:
                body += int(value * (2 ** (bits - 1) - 1)).to_bytes(width, "little", signed=True)
    size = len(body) if declared_size is None else declared_size
    return (b"RIFF" + struct.pack("<I", (36 + size) & 0xFFFFFFFF) + b"WAVE" + b"fmt "
            + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, sample_rate * channels * width, channels * width, bits)
            + b"data" + struct.pack("<I", size & 0xFFFFFFFF) + bytes(body))


def clean_env(extra: dict | None = None) -> dict:
    """Environnement sans clé API ni réglage hérité de la machine du développeur."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(SECRET_PREFIXES)}
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost"})
    env.update(extra or {})
    return env


def fake_tts_config(extra: dict | None = None) -> dict:
    """Configuration qui confie les trois langues au moteur factice, via le fournisseur « command »."""
    config = {
        "languages": {
            "fr": {"locale": "fr-FR", "provider": "command", "voice": "fake-fr", "fallback": None},
            "en": {"locale": "en-US", "provider": "command", "voice": "fake-en", "fallback": None},
            "km": {"locale": "km-KH", "provider": "command", "voice": "fake-km"},
        },
        "tts": {
            "retries": 1, "retry_backoff_seconds": 0,
            "providers": {"command": {
                "command": [sys.executable, str(FAKE_TTS), "{output}", "{sample_rate}", "{lang}"],
                "engine_version": "fake-1"}},
        },
    }
    return merge(config, extra or {})


def merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in extra.items():
        out[key] = merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


class Project:
    """Copie de travail jetable du projet (gabarits, styles, polices et quelques unités)."""

    def __init__(self, units: tuple[str, ...] | None = ("u001", "u002", "u003", "u004"), config: dict | None = None,
                 raw_config: dict | None = None):
        self.dir = Path(tempfile.mkdtemp(prefix="frkh-test-")).resolve()
        for name in ("templates", "css", "js", "fonts"):
            shutil.copytree(ROOT / name, self.dir / name)
        target = self.dir / "content" / "units"
        target.mkdir(parents=True)
        for path in sorted((ROOT / "content" / "units").glob("*.json")):
            if units is None or path.name[:4] in units:
                shutil.copy(path, target / path.name)
        (self.dir / "config").mkdir()
        payload = raw_config if raw_config is not None else fake_tts_config(config)
        (self.dir / "config" / "config.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.tts_log = self.dir / "fake-tts.log"

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    # --- ligne de commande ------------------------------------------------------
    def run(self, *args: str, env: dict | None = None, expect: int | None = 0) -> subprocess.CompletedProcess:
        full_env = clean_env({"FAKE_TTS_LOG": str(self.tts_log)})
        full_env.update(env or {})
        proc = subprocess.run([sys.executable, str(ROOT / "manage.py"), "--root", str(self.dir), *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=full_env, timeout=600)
        if expect is not None and proc.returncode != expect:
            raise AssertionError(f"manage.py {' '.join(args)} → code {proc.returncode} (attendu {expect})\n"
                                 f"--- sortie ---\n{proc.stdout}\n--- erreurs ---\n{proc.stderr}")
        return proc

    # --- observation ------------------------------------------------------------
    def calls(self) -> list[tuple[str, str]]:
        """Appels réellement reçus par le moteur vocal factice : (langue, texte)."""
        if not self.tts_log.is_file():
            return []
        return [tuple(line.split("\t", 1)) for line in self.tts_log.read_text(encoding="utf-8").splitlines() if line]

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(str(self.dir / "database" / "learning.db"), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def scalar(self, sql: str, params: tuple = ()):
        rows = self.query(sql, params)
        return rows[0][0] if rows else None

    def lesson(self, number: int) -> dict:
        return json.loads(self.scalar("SELECT content_json FROM lessons WHERE lesson_number = ?", (number,)))

    def page(self, number: int) -> str:
        return (self.dir / "lessons" / f"lesson-{number:03d}.html").read_text(encoding="utf-8")

    def index(self) -> str:
        return (self.dir / "index.html").read_text(encoding="utf-8")

    def wav_files(self) -> list[Path]:
        return sorted((self.dir / "audio").rglob("*.wav"))


class MockTTSServer:
    """Faux service HTTP imitant la forme des API Google Cloud TTS et Azure AI Speech.

    Il sert à vérifier les requêtes émises (URL, en-têtes, corps) et la réaction
    aux erreurs HTTP, sans réseau ni clé réelle.
    """

    def __init__(self):
        self.requests: list[dict] = []
        self.script: list[tuple[int, str, bytes]] = []     # réponses imposées, consommées dans l'ordre
        self.wav_rate: int | None = None                   # fréquence renvoyée (None = celle demandée)
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                request = {"method": self.command, "path": self.path, "body": body,
                           "headers": {k.lower(): v for k, v in self.headers.items()}}
                outer.requests.append(request)
                status, content_type, payload = outer.script.pop(0) if outer.script else outer.respond(request)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = _serve

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def respond(self, request: dict) -> tuple[int, str, bytes]:
        path = request["path"]
        if path.endswith("/text:synthesize"):
            payload = json.loads(request["body"])
            rate = self.wav_rate or payload["audioConfig"].get("sampleRateHertz", 24000)
            audio = base64.b64encode(make_wav(rate, 0.4)).decode("ascii")
            return 200, "application/json", json.dumps({"audioContent": audio}).encode("utf-8")
        if "/voices" in path and request["method"] == "GET" and "cognitiveservices" not in path:
            voices = {"voices": [{"name": "fr-FR-Neural2-F", "languageCodes": ["fr-FR"], "ssmlGender": "FEMALE",
                                  "naturalSampleRateHertz": 24000}]}
            return 200, "application/json", json.dumps(voices).encode("utf-8")
        if path.endswith("/cognitiveservices/v1"):
            fmt = request["headers"].get("x-microsoft-outputformat", "")
            rate = self.wav_rate or {"riff-22050hz-16bit-mono-pcm": 22050, "riff-24khz-16bit-mono-pcm": 24000}.get(fmt, 24000)
            return 200, "audio/x-wav", make_wav(rate, 0.4)
        if path.endswith("/cognitiveservices/voices/list"):
            voices = [{"ShortName": "km-KH-SreymomNeural", "Locale": "km-KH", "Gender": "Female", "SampleRateHertz": "24000"},
                      {"ShortName": "km-KH-PisethNeural", "Locale": "km-KH", "Gender": "Male", "SampleRateHertz": "24000"},
                      {"ShortName": "fr-FR-DeniseNeural", "Locale": "fr-FR", "Gender": "Female", "SampleRateHertz": "24000"}]
            return 200, "application/json", json.dumps(voices).encode("utf-8")
        return 404, "application/json", b'{"error": {"message": "not found"}}'

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
