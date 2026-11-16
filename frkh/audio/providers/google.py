"""Google Cloud Text-to-Speech — API REST officielle (v1, text:synthesize).

Authentification, par ordre de priorité :
  1. GOOGLE_TTS_API_KEY            clé API restreinte à « Cloud Text-to-Speech API » ;
  2. GOOGLE_TTS_ACCESS_TOKEN       jeton OAuth déjà obtenu ;
  3. GOOGLE_APPLICATION_CREDENTIALS  compte de service (nécessite le paquet google-auth).

Remarque : Google Cloud TTS ne propose pas de voix khmère (km-KH). Le khmer est
donc confié à un autre fournisseur dans config/config.json.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse

from .base import (SynthesisResult, TTSProvider, TTSRequestError, TTSUnavailable, VoiceSpec,
                   http_request)

_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class GoogleTTS(TTSProvider):
    name = "google"
    engine_version = "google-cloud-tts-v1"

    def __init__(self, settings=None, timeout=30.0):
        super().__init__(settings, timeout)
        self.endpoint = str(self.settings.get("endpoint") or "https://texttospeech.googleapis.com/v1").rstrip("/")
        self._token: tuple[str, float] | None = None

    def configured(self) -> tuple[bool, str]:
        if os.environ.get("GOOGLE_TTS_API_KEY") or os.environ.get("GOOGLE_TTS_ACCESS_TOKEN"):
            return True, ""
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                import google.auth  # noqa: F401
                return True, ""
            except ImportError:
                return False, ("GOOGLE_APPLICATION_CREDENTIALS est défini mais le paquet « google-auth » "
                               "n'est pas installé (pip install google-auth requests)")
        return False, "GOOGLE_TTS_API_KEY absent du fichier .env"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        key = os.environ.get("GOOGLE_TTS_API_KEY")
        if key:
            headers["X-Goog-Api-Key"] = key
            return headers
        token = os.environ.get("GOOGLE_TTS_ACCESS_TOKEN") or self._service_account_token()
        headers["Authorization"] = f"Bearer {token}"
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if project:
            headers["X-Goog-User-Project"] = project
        return headers

    def _service_account_token(self) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        try:
            import google.auth
            import google.auth.transport.requests
            credentials, _ = google.auth.default(scopes=[_SCOPE])
            credentials.refresh(google.auth.transport.requests.Request())
        except ImportError:
            raise TTSUnavailable("paquet « google-auth » manquant pour utiliser un compte de service") from None
        except Exception as exc:  # identifiants illisibles, réseau…
            raise TTSUnavailable(f"identifiants Google inutilisables : {exc}") from None
        expiry = credentials.expiry.timestamp() if getattr(credentials, "expiry", None) else time.time() + 1800
        self._token = (credentials.token, expiry)
        return credentials.token

    def synthesize(self, text: str, spec: VoiceSpec) -> SynthesisResult:
        ok, reason = self.configured()
        if not ok:
            raise TTSUnavailable(reason)
        audio_config: dict = {"audioEncoding": "LINEAR16", "sampleRateHertz": spec.sample_rate}
        if abs(spec.speaking_rate - 1.0) > 1e-6:
            audio_config["speakingRate"] = spec.speaking_rate
        if abs(spec.pitch) > 1e-6:
            audio_config["pitch"] = spec.pitch
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": spec.locale, "name": spec.voice},
            "audioConfig": audio_config,
        }
        raw = http_request(f"{self.endpoint}/text:synthesize", method="POST", headers=self._headers(),
                           body=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=self.timeout)
        try:
            content = json.loads(raw)["audioContent"]
            audio = base64.b64decode(content)
        except (ValueError, KeyError, TypeError):
            raise TTSRequestError("réponse inattendue de Google Cloud TTS (audioContent absent)") from None
        return SynthesisResult(audio=audio, fmt="wav", sample_rate=spec.sample_rate)

    def list_voices(self, locale: str | None = None) -> list[dict]:
        ok, reason = self.configured()
        if not ok:
            raise TTSUnavailable(reason)
        url = f"{self.endpoint}/voices"
        if locale:
            url += "?" + urllib.parse.urlencode({"languageCode": locale})
        payload = json.loads(http_request(url, headers=self._headers(), timeout=self.timeout))
        return [{"name": v.get("name"), "locales": v.get("languageCodes", []),
                 "gender": str(v.get("ssmlGender", "")).lower(),
                 "sample_rate": v.get("naturalSampleRateHertz")} for v in payload.get("voices", [])]
