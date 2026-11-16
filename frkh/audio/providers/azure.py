"""Azure AI Speech — API REST officielle de synthèse vocale.

Utilisé par défaut pour le khmer (voix km-KH-SreymomNeural et km-KH-PisethNeural),
que Google Cloud TTS ne propose pas. Peut aussi servir pour le français et l'anglais.

Variables .env : AZURE_SPEECH_KEY et AZURE_SPEECH_REGION (ex. southeastasia).
"""

from __future__ import annotations

import json
import os
from xml.sax.saxutils import escape, quoteattr

from .base import SynthesisResult, TTSProvider, TTSUnavailable, VoiceSpec, http_request

# Formats RIFF/PCM mono 16 bits proposés par le service ; les autres fréquences
# sont obtenues par rééchantillonnage local à partir du 24 kHz.
_FORMATS = {
    8000: "riff-8khz-16bit-mono-pcm",
    22050: "riff-22050hz-16bit-mono-pcm",
    24000: "riff-24khz-16bit-mono-pcm",
    44100: "riff-44100hz-16bit-mono-pcm",
    48000: "riff-48khz-16bit-mono-pcm",
}


class AzureTTS(TTSProvider):
    name = "azure"
    engine_version = "azure-speech-v1"

    def _region(self) -> str:
        return (os.environ.get("AZURE_SPEECH_REGION") or str(self.settings.get("region") or "")).strip().lower()

    def _base(self) -> str:
        custom = os.environ.get("AZURE_SPEECH_ENDPOINT") or self.settings.get("endpoint")
        if custom:
            return str(custom).rstrip("/")
        return f"https://{self._region()}.tts.speech.microsoft.com"

    def configured(self) -> tuple[bool, str]:
        if not os.environ.get("AZURE_SPEECH_KEY"):
            return False, "AZURE_SPEECH_KEY absent du fichier .env"
        if not self._region() and not (os.environ.get("AZURE_SPEECH_ENDPOINT") or self.settings.get("endpoint")):
            return False, "AZURE_SPEECH_REGION absent du fichier .env"
        return True, ""

    def synthesize(self, text: str, spec: VoiceSpec) -> SynthesisResult:
        ok, reason = self.configured()
        if not ok:
            raise TTSUnavailable(reason)
        rate = spec.sample_rate if spec.sample_rate in _FORMATS else 24000
        prosody = [f"rate={quoteattr(f'{round((spec.speaking_rate - 1.0) * 100):+d}%')}"]
        if abs(spec.pitch) > 1e-6:
            prosody.append(f"pitch={quoteattr(f'{spec.pitch:+g}st')}")
        ssml = (
            f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang={quoteattr(spec.locale)}>"
            f"<voice name={quoteattr(spec.voice)}><prosody {' '.join(prosody)}>{escape(text)}</prosody></voice></speak>"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"],
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": _FORMATS[rate],
            "User-Agent": "fr-kh-learning",
        }
        audio = http_request(f"{self._base()}/cognitiveservices/v1", method="POST", headers=headers,
                             body=ssml.encode("utf-8"), timeout=self.timeout)
        return SynthesisResult(audio=audio, fmt="wav", sample_rate=rate)

    def list_voices(self, locale: str | None = None) -> list[dict]:
        ok, reason = self.configured()
        if not ok:
            raise TTSUnavailable(reason)
        raw = http_request(f"{self._base()}/cognitiveservices/voices/list",
                           headers={"Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"]},
                           timeout=self.timeout)
        voices = []
        for v in json.loads(raw):
            if locale and v.get("Locale") != locale:
                continue
            voices.append({"name": v.get("ShortName"), "locales": [v.get("Locale")],
                           "gender": str(v.get("Gender", "")).lower(), "sample_rate": v.get("SampleRateHertz")})
        return voices
