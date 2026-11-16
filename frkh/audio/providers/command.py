"""Fournisseur « command » : n'importe quel moteur vocal local piloté en ligne de commande.

Exemple (Piper, entièrement hors ligne) dans config/config.json :

    "tts": {"providers": {"command": {
        "command": ["piper", "--model", "{voice}", "--output_file", "{output}"],
        "output_format": "wav",
        "engine_version": "piper-1.2"
    }}}

Le texte est transmis sur l'entrée standard et par la variable {text}. Variables
disponibles : {text} {output} {voice} {locale} {lang} {rate} {pitch} {sample_rate}.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import (SynthesisResult, TTSProvider, TTSRequestError, TTSTransientError, TTSUnavailable,
                   VoiceSpec)


class CommandTTS(TTSProvider):
    name = "command"

    def __init__(self, settings=None, timeout=30.0):
        super().__init__(settings, timeout)
        self.command = [str(part) for part in (self.settings.get("command") or [])]
        self.output_format = str(self.settings.get("output_format") or "wav")
        self.engine_version = str(self.settings.get("engine_version") or "command-1")

    def configured(self) -> tuple[bool, str]:
        if not self.command:
            return False, "tts.providers.command.command est vide dans config/config.json"
        if not shutil.which(self.command[0]) and not Path(self.command[0]).is_file():
            return False, f"programme introuvable : {self.command[0]}"
        return True, ""

    def synthesize(self, text: str, spec: VoiceSpec) -> SynthesisResult:
        ok, reason = self.configured()
        if not ok:
            raise TTSUnavailable(reason)
        with tempfile.TemporaryDirectory(prefix="frkh-tts-") as tmp:
            output = Path(tmp) / f"output.{self.output_format}"
            values = {"text": text, "output": str(output), "voice": spec.voice, "locale": spec.locale,
                      "lang": spec.lang, "rate": f"{spec.speaking_rate:g}", "pitch": f"{spec.pitch:g}",
                      "sample_rate": str(spec.sample_rate)}
            try:
                argv = [part.format(**values) for part in self.command]
            except (KeyError, IndexError, ValueError) as exc:
                raise TTSRequestError(f"modèle de commande invalide : {exc}") from None
            try:
                proc = subprocess.run(argv, input=text.encode("utf-8"), capture_output=True, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                raise TTSTransientError("le moteur vocal local n'a pas répondu à temps") from None
            except OSError as exc:
                raise TTSUnavailable(f"impossible de lancer le moteur vocal local : {exc}") from None
            if proc.returncode != 0:
                detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["erreur inconnue"]
                raise TTSTransientError(f"le moteur vocal local a échoué (code {proc.returncode}) : {detail[0][:200]}")
            audio = output.read_bytes() if output.is_file() else proc.stdout
            if not audio:
                raise TTSTransientError("le moteur vocal local n'a produit aucun son")
            return SynthesisResult(audio=audio, fmt=self.output_format, sample_rate=spec.sample_rate)
