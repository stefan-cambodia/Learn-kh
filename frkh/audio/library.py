"""Bibliothèque audio : cache par empreinte SHA-256, génération, contrôle et réparation.

Règle centrale : un texte donné, prononcé avec les mêmes paramètres, n'est
synthétisé qu'une seule fois, quelle que soit la leçon qui le demande.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from .. import db
from ..textutil import normalize_text, slugify
from . import wavutil
from .providers import (TTSError, TTSProvider, TTSUnavailable, VoiceSpec, create_provider)

HASH_PREFIX = 12          # caractères de l'empreinte repris dans le nom du fichier
KEY_VERSION = 1           # à incrémenter si la composition de la clé change


@dataclass
class AudioRef:
    """Résultat d'une demande d'audio pour un texte et une langue."""
    lang: str
    text: str
    text_hash: str
    status: str                 # ready | missing
    path: str | None = None     # relatif à la racine du projet
    duration: float = 0.0
    reason: str = ""
    source: str = ""            # cache | adopted | generated | ""

    @property
    def ready(self) -> bool:
        return self.status == "ready"


class AudioLibrary:
    def __init__(self, config, conn, logger: logging.Logger | None = None,
                 providers: dict[str, TTSProvider] | None = None, sleep=time.sleep):
        self.config = config
        self.conn = conn
        self.log = logger or logging.getLogger("frkh.audio")
        self.paths = config.paths
        self._providers: dict[str, TTSProvider] = dict(providers or {})
        self._specs: dict[str, VoiceSpec] = {}
        self._down: dict[str, str] = {}          # fournisseur -> raison de l'arrêt pour cette exécution
        self._failures: dict[str, int] = {}
        self._checked: dict[str, AudioRef] = {}  # empreintes déjà validées pendant cette exécution
        self._sleep = sleep
        self.run_calls = 0
        self.run_hits = 0
        self.run_errors = 0
        self.run_generated: list[str] = []

    # --- fournisseurs et paramètres -------------------------------------------
    def provider(self, name: str) -> TTSProvider:
        if name not in self._providers:
            settings = self.config.get(f"tts.providers.{name}", {}) or {}
            self._providers[name] = create_provider(name, settings, float(self.config.get("tts.timeout_seconds", 30)))
        return self._providers[name]

    def spec_for(self, lang: str) -> VoiceSpec:
        """Paramètres de synthèse d'une langue ; bascule sur le fournisseur de secours
        uniquement si le fournisseur principal n'est pas configuré."""
        if lang in self._specs:
            return self._specs[lang]
        entry = self.config["languages"][lang]
        provider, voice = entry["provider"], entry.get("voice", "")
        fallback = entry.get("fallback") or {}
        if fallback.get("provider"):
            try:
                primary_ok = self.provider(provider).configured()[0]
                fallback_ok = self.provider(fallback["provider"]).configured()[0]
            except TTSError:
                primary_ok, fallback_ok = True, False
            if not primary_ok and fallback_ok:
                provider, voice = fallback["provider"], fallback.get("voice", voice)
        audio = self.config["audio"]
        spec = VoiceSpec(lang=lang, locale=entry["locale"], provider=provider, voice=voice,
                         speaking_rate=round(float(entry.get("speaking_rate", audio.get("speaking_rate", 1.0))), 3),
                         pitch=round(float(entry.get("pitch", audio.get("pitch", 0.0))), 3),
                         sample_rate=int(audio.get("sample_rate_hz", 24000)))
        self._specs[lang] = spec
        return spec

    def engine_version(self, spec: VoiceSpec) -> str:
        try:
            return self.provider(spec.provider).engine_version
        except TTSError:
            return ""

    # --- clé de cache et nom de fichier -----------------------------------------
    def cache_key(self, text: str, spec: VoiceSpec) -> str:
        """Empreinte SHA-256 de tout ce qui détermine le son produit."""
        payload = {
            "v": KEY_VERSION,
            "text": normalize_text(text),
            "language": spec.lang,
            "locale": spec.locale,
            "provider": spec.provider,
            "voice": spec.voice,
            "speaking_rate": spec.speaking_rate,
            "pitch": spec.pitch,
            "audio": {"encoding": "pcm_s16le", "channels": 1, "bits": 16, "sample_rate": spec.sample_rate},
            "engine": self.engine_version(spec),
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def file_for(self, text: str, spec: VoiceSpec, text_hash: str) -> Path:
        """Nom déterministe : audio/<locale>/<texte-lisible>_<empreinte>.wav"""
        slug = slugify(text, default=spec.lang)
        return self.paths.audio / spec.locale / f"{slug}_{text_hash[:HASH_PREFIX]}.wav"

    # --- consultation sans génération ---------------------------------------------
    def lookup(self, text: str, lang: str) -> AudioRef:
        """État actuel d'un audio, sans jamais appeler le fournisseur (utilisé au rendu HTML)."""
        text = normalize_text(text)
        spec = self.spec_for(lang)
        text_hash = self.cache_key(text, spec)
        cached = self._checked.get(text_hash)
        if cached:
            return cached
        row = self.conn.execute("SELECT * FROM audio_files WHERE text_hash = ?", (text_hash,)).fetchone()
        if row and row["status"] == "ready":
            path = self.paths.root / row["file_path"]
            try:
                if path.stat().st_size == row["file_size"]:
                    return AudioRef(lang, text, text_hash, "ready", row["file_path"], row["duration"], source="cache")
            except OSError:
                pass
            return AudioRef(lang, text, text_hash, "missing", reason="fichier absent ou modifié")
        return AudioRef(lang, text, text_hash, "missing", reason=(row["last_error"] if row else "") or "pas encore généré")

    # --- demande d'un audio -----------------------------------------------------------
    def ensure(self, text: str, lang: str, force: bool = False) -> AudioRef:
        """Retourne l'audio du texte : réutilisé s'il existe et est valide, généré sinon.

        Ne lève jamais d'exception pour une panne du fournisseur : l'audio est
        alors marqué « missing » et sera retenté lors d'une prochaine exécution.
        """
        text = normalize_text(text)
        spec = self.spec_for(lang)
        text_hash = self.cache_key(text, spec)
        if not text:
            return AudioRef(lang, text, text_hash, "missing", reason="texte vide")
        if not force and text_hash in self._checked:
            self._hit()
            return self._checked[text_hash]

        target = self.file_for(text, spec, text_hash)
        row = self.conn.execute("SELECT * FROM audio_files WHERE text_hash = ?", (text_hash,)).fetchone()

        if not force:
            # Fichier déjà enregistré : contrôle rapide. Fichier inconnu de la base : contrôle complet.
            known = bool(row and row["status"] == "ready")
            info = self._valid_file(target, spec, quick=known)
            if info is not None and known and target.stat().st_size != row["file_size"]:
                info = self._valid_file(target, spec)
            if info is not None:
                source = "cache"
                if not row or row["status"] != "ready" or row["file_size"] != target.stat().st_size:
                    # Fichier présent mais inconnu de la base (base restaurée, copie manuelle) : on l'adopte.
                    self._store(text, spec, text_hash, target, info, status="ready")
                    source = "adopted" if not row else "cache"
                    if not row:
                        db.bump(self.conn, self._day(), "audio_adopted")
                self._hit()
                ref = AudioRef(lang, text, text_hash, "ready", self.paths.rel(target), info.duration, source=source)
                self._checked[text_hash] = ref
                return ref
            if row and row["status"] == "ready":
                self.log.warning("Audio absent ou corrompu, à régénérer : %s", self.paths.rel(target))

        ref = self._generate(text, spec, text_hash, target, row)
        if ref.ready:
            self._checked[text_hash] = ref
        return ref

    def _hit(self) -> None:
        self.run_hits += 1
        db.bump(self.conn, self._day(), "cache_hits")

    def _day(self) -> str:
        return self.config.today().isoformat()

    def _valid_file(self, path: Path, spec: VoiceSpec, quick: bool = False):
        if not path.is_file():
            return None
        try:
            check = wavutil.quick_check_file if quick else wavutil.inspect_wav_file
            return check(path, expected_rate=spec.sample_rate)
        except wavutil.AudioFormatError:
            return None

    # --- génération -----------------------------------------------------------------------
    def _budget(self, characters: int) -> str:
        """Retourne une raison de refus si une limite de consommation est atteinte, sinon ''."""
        limits = self.config.get("tts.limits", {}) or {}
        max_calls = int(limits.get("max_calls_per_run", 0) or 0)
        if max_calls and self.run_calls >= max_calls:
            return f"limite de {max_calls} appels par exécution atteinte"
        day = self._day()
        max_day = int(limits.get("max_chars_per_day", 0) or 0)
        if max_day:
            used = self.conn.execute("SELECT COALESCE(SUM(characters), 0) FROM tts_usage WHERE day = ?", (day,)).fetchone()[0]
            if used + characters > max_day:
                return f"limite quotidienne de {max_day} caractères atteinte"
        max_month = int(limits.get("max_chars_per_month", 0) or 0)
        if max_month:
            used = self.conn.execute("SELECT COALESCE(SUM(characters), 0) FROM tts_usage WHERE day LIKE ?",
                                     (day[:7] + "%",)).fetchone()[0]
            if used + characters > max_month:
                return f"limite mensuelle de {max_month} caractères atteinte"
        return ""

    def _generate(self, text: str, spec: VoiceSpec, text_hash: str, target: Path, row) -> AudioRef:
        def missing(reason: str, count_attempt: bool = False) -> AudioRef:
            keep_ready = bool(row and row["status"] == "ready" and self._valid_file(target, spec))
            if not keep_ready:
                self._store(text, spec, text_hash, target, None, status="missing", error=reason,
                            attempts=(row["attempts"] if row else 0) + (1 if count_attempt else 0))
            return AudioRef(spec.lang, text, text_hash, "missing", reason=reason)

        if spec.provider in self._down:
            return missing(self._down[spec.provider])
        try:
            provider = self.provider(spec.provider)
        except TTSError as exc:
            self._down[spec.provider] = str(exc)
            return missing(str(exc))
        ok, reason = provider.configured()
        if not ok:
            self._down[spec.provider] = f"fournisseur « {spec.provider} » non configuré : {reason}"
            self.log.warning("Audio %s indisponible — %s", spec.locale, self._down[spec.provider])
            return missing(self._down[spec.provider])
        refusal = self._budget(len(text))
        if refusal:
            if "limit" not in self._down.get("__budget__", ""):
                self.log.warning("Synthèse vocale suspendue : %s. Les audios restants seront générés plus tard.", refusal)
                self._down["__budget__"] = "limit"
            return missing(refusal)

        retries = max(1, int(self.config.get("tts.retries", 3)))
        backoff = float(self.config.get("tts.retry_backoff_seconds", 2.0))
        last_error = ""
        for attempt in range(1, retries + 1):
            started = time.monotonic()
            self.run_calls += 1
            try:
                result = provider.synthesize(text, spec)
                wav = wavutil.to_wav_pcm16_mono(result.audio, result.fmt, spec.sample_rate, result.sample_rate)
            except TTSError as exc:
                last_error = str(exc)
                self._log_call(spec, text, text_hash, False, started, last_error)
                if isinstance(exc, TTSUnavailable):
                    self._down[spec.provider] = f"fournisseur « {spec.provider} » indisponible : {exc}"
                    break
                if not exc.retryable or attempt == retries:
                    break
                self._sleep(backoff * (2 ** (attempt - 1)))
                continue
            except wavutil.AudioFormatError as exc:
                last_error = f"audio reçu invalide : {exc}"
                self._log_call(spec, text, text_hash, False, started, last_error)
                if attempt == retries:
                    break
                self._sleep(backoff * (2 ** (attempt - 1)))
                continue
            self._log_call(spec, text, text_hash, True, started, None)
            # Le nouveau fichier est complet et vérifié avant de remplacer quoi que ce soit.
            wavutil.atomic_write(target, wav)
            info = wavutil.inspect_wav_file(target, expected_rate=spec.sample_rate)
            self._store(text, spec, text_hash, target, info, status="ready")
            self._failures[spec.provider] = 0
            self.run_generated.append(self.paths.rel(target))
            self.log.info("Audio généré [%s] %s", spec.locale, self.paths.rel(target))
            return AudioRef(spec.lang, text, text_hash, "ready", self.paths.rel(target), info.duration, source="generated")

        self.run_errors += 1
        db.bump(self.conn, self._day(), "tts_errors")
        self.log.error("Échec de la synthèse [%s] « %s » : %s", spec.locale, text[:60], last_error)
        self._failures[spec.provider] = self._failures.get(spec.provider, 0) + 1
        if self._failures[spec.provider] >= 2 and spec.provider not in self._down:
            # Deux textes de suite en échec : le service est en panne, on arrête de le solliciter.
            self._down[spec.provider] = f"fournisseur « {spec.provider} » en panne : {last_error}"
            self.log.error("Fournisseur « %s » mis en pause jusqu'à la prochaine exécution.", spec.provider)
        return missing(last_error, count_attempt=True)

    def _log_call(self, spec: VoiceSpec, text: str, text_hash: str, success: bool, started: float, error) -> None:
        self.conn.execute(
            "INSERT INTO tts_usage(called_at, day, provider, locale, voice, characters, text_hash, success, duration_ms, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.utcnow(), self._day(), spec.provider, spec.locale, spec.voice, len(text), text_hash,
             1 if success else 0, int((time.monotonic() - started) * 1000), error))
        db.bump(self.conn, self._day(), "tts_calls")

    def _store(self, text: str, spec: VoiceSpec, text_hash: str, target: Path, info, *, status: str,
               error: str | None = None, attempts: int | None = None) -> None:
        now = db.utcnow()
        size = target.stat().st_size if info is not None else 0
        checksum = wavutil.sha256_file(target) if info is not None else None
        self.conn.execute(
            """INSERT INTO audio_files(text_hash, text, language, locale, provider, voice, speaking_rate, pitch,
                   sample_rate, engine_version, file_path, file_size, duration, checksum, status, attempts,
                   last_error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(text_hash) DO UPDATE SET
                   file_path = excluded.file_path, file_size = excluded.file_size, duration = excluded.duration,
                   checksum = excluded.checksum, status = excluded.status, last_error = excluded.last_error,
                   attempts = excluded.attempts, updated_at = excluded.updated_at""",
            (text_hash, text, spec.lang, spec.locale, spec.provider, spec.voice, spec.speaking_rate, spec.pitch,
             spec.sample_rate, self.engine_version(spec), self.paths.rel(target), size,
             round(info.duration, 3) if info is not None else 0, checksum, status, attempts or 0, error, now, now))

    # --- contrôle de la bibliothèque --------------------------------------------------------
    def verify(self, deep: bool = False) -> dict:
        """Passe en revue tous les fichiers connus. ``deep`` compare aussi les empreintes de contenu."""
        report = {"ready": 0, "missing": [], "corrupt": [], "orphans": [], "bytes": 0, "seconds": 0.0}
        known: set[str] = set()
        for row in self.conn.execute("SELECT * FROM audio_files ORDER BY locale, file_path"):
            known.add(row["file_path"])
            item = {"file": row["file_path"], "text": row["text"], "locale": row["locale"],
                    "hash": row["text_hash"], "reason": row["last_error"] or ""}
            path = self.paths.root / row["file_path"]
            if row["status"] != "ready":
                item["reason"] = item["reason"] or "pas encore généré"
                report["missing"].append(item)
                continue
            if not path.is_file():
                item["reason"] = "fichier supprimé"
                report["missing"].append(item)
                continue
            try:
                wavutil.inspect_wav_file(path, expected_rate=row["sample_rate"])
                if path.stat().st_size != row["file_size"]:
                    raise wavutil.AudioFormatError("taille différente de celle enregistrée")
                if deep and row["checksum"] and wavutil.sha256_file(path) != row["checksum"]:
                    raise wavutil.AudioFormatError("contenu modifié (empreinte différente)")
            except wavutil.AudioFormatError as exc:
                item["reason"] = str(exc)
                report["corrupt"].append(item)
                continue
            report["ready"] += 1
            report["bytes"] += row["file_size"]
            report["seconds"] += row["duration"]
        if self.paths.audio.is_dir():
            for path in sorted(self.paths.audio.rglob("*.wav")):
                rel = self.paths.rel(path)
                if rel not in known:
                    report["orphans"].append(rel)
        return report

    def mark_damaged(self, report: dict) -> int:
        """Déclasse en « missing » les entrées dont le fichier est absent ou corrompu."""
        count = 0
        for item in report["missing"] + report["corrupt"]:
            cur = self.conn.execute(
                "UPDATE audio_files SET status = 'missing', last_error = ?, updated_at = ? "
                "WHERE text_hash = ? AND status = 'ready'", (item["reason"], db.utcnow(), item["hash"]))
            count += cur.rowcount
        return count

    def find(self, *, text: str | None = None, lang: str | None = None, file: str | None = None,
             text_hash: str | None = None) -> list:
        """Retrouve des audios par texte, fichier ou début d'empreinte."""
        clauses, params = [], []
        if text:
            clauses.append("text = ?")
            params.append(normalize_text(text))
        if lang:
            clauses.append("language = ?")
            params.append(lang)
        if file:
            name = Path(file).name
            clauses.append("(file_path = ? OR file_path LIKE ?)")
            params += [str(file).replace("\\", "/"), f"%/{name}"]
        if text_hash:
            clauses.append("text_hash LIKE ?")
            params.append(text_hash.lower() + "%")
        if not clauses:
            return []
        return self.conn.execute(f"SELECT * FROM audio_files WHERE {' AND '.join(clauses)} ORDER BY id", params).fetchall()

    def prune_stale_missing(self, needed_hashes: set[str]) -> int:
        """Oublie les entrées « missing » qui ne correspondent plus à aucun besoin (voix changée…)."""
        stale = [r["text_hash"] for r in self.conn.execute("SELECT text_hash FROM audio_files WHERE status = 'missing'")
                 if r["text_hash"] not in needed_hashes]
        for text_hash in stale:
            self.conn.execute("DELETE FROM audio_files WHERE text_hash = ?", (text_hash,))
        return len(stale)

    def statistics(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) AS files, COALESCE(SUM(file_size), 0) AS bytes, COALESCE(SUM(duration), 0) AS seconds "
            "FROM audio_files WHERE status = 'ready'").fetchone()
        per_locale = [dict(r) for r in self.conn.execute(
            "SELECT locale, provider, voice, COUNT(*) AS files, COALESCE(SUM(file_size), 0) AS bytes, "
            "COALESCE(SUM(duration), 0) AS seconds FROM audio_files WHERE status = 'ready' "
            "GROUP BY locale, provider, voice ORDER BY locale")]
        usage = self.conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(success), 0) AS ok, COALESCE(SUM(characters), 0) AS chars "
            "FROM tts_usage").fetchone()
        day = self._day()
        today = self.conn.execute("SELECT COUNT(*) AS calls, COALESCE(SUM(characters), 0) AS chars FROM tts_usage "
                                  "WHERE day = ?", (day,)).fetchone()
        month = self.conn.execute("SELECT COUNT(*) AS calls, COALESCE(SUM(characters), 0) AS chars FROM tts_usage "
                                  "WHERE day LIKE ?", (day[:7] + "%",)).fetchone()
        return {
            "files": row["files"], "bytes": row["bytes"], "seconds": row["seconds"], "per_locale": per_locale,
            "missing": self.conn.execute("SELECT COUNT(*) FROM audio_files WHERE status != 'ready'").fetchone()[0],
            "tts_calls": usage["calls"], "tts_success": usage["ok"], "tts_failed": usage["calls"] - usage["ok"],
            "tts_chars": usage["chars"], "cache_hits": db.counter_total(self.conn, "cache_hits"),
            "adopted": db.counter_total(self.conn, "audio_adopted"),
            "today": {"calls": today["calls"], "chars": today["chars"]},
            "month": {"calls": month["calls"], "chars": month["chars"]},
        }
