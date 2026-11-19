"""Contrat commun à tous les fournisseurs de synthèse vocale.

Pour brancher un autre moteur, il suffit d'écrire une classe dérivée de
``TTSProvider`` et de l'enregistrer avec ``register_provider`` (voir
``frkh/audio/providers/__init__.py``). Le reste de l'application ne connaît
que cette interface.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceSpec:
    """Paramètres complets d'une synthèse : ils entrent tous dans la clé de cache."""
    lang: str            # fr | en | km | es | it | ru | zh
    locale: str          # fr-FR | en-US | en-GB | km-KH | es-ES | it-IT | ru-RU | zh-CN
    provider: str
    voice: str
    speaking_rate: float
    pitch: float
    sample_rate: int
    audio_format: str = "wav"   # format des fichiers de la bibliothèque : wav | mp3
    bitrate: int = 0            # kbit/s, pour le MP3


@dataclass
class SynthesisResult:
    audio: bytes
    fmt: str = "wav"                 # wav | pcm_s16le | mp3 | ogg…
    sample_rate: int | None = None   # obligatoire pour pcm_s16le


class TTSError(Exception):
    """Erreur de synthèse. ``retryable`` indique si une nouvelle tentative immédiate a un sens."""
    retryable = False


class TTSUnavailable(TTSError):
    """Fournisseur non configuré ou identifiants refusés : inutile d'insister pendant cette exécution."""


class TTSTransientError(TTSError):
    """Panne passagère (réseau, serveur, limitation de débit)."""
    retryable = True


class TTSRequestError(TTSError):
    """Requête refusée (voix inconnue, texte invalide…)."""


class TTSProvider(ABC):
    name = ""
    engine_version = ""

    def __init__(self, settings: dict | None = None, timeout: float = 30.0):
        self.settings = settings or {}
        self.timeout = timeout

    @abstractmethod
    def configured(self) -> tuple[bool, str]:
        """(True, "") si les identifiants nécessaires sont présents, sinon (False, raison)."""

    @abstractmethod
    def synthesize(self, text: str, spec: VoiceSpec) -> SynthesisResult:
        """Synthétise ``text`` et retourne le son brut ; lève une ``TTSError`` en cas d'échec."""

    def list_voices(self, locale: str | None = None) -> list[dict]:
        raise TTSRequestError(f"le fournisseur « {self.name} » ne sait pas lister ses voix")


def http_request(url: str, *, method: str = "GET", headers: dict | None = None,
                 body: bytes | None = None, timeout: float = 30.0) -> bytes:
    """Requête HTTPS avec traduction des pannes en erreurs de synthèse typées.

    Les messages d'erreur ne contiennent jamais les en-têtes : les clés API ne
    peuvent donc pas se retrouver dans les journaux.
    """
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = _error_detail(exc)
        exc.close()
        if exc.code in (401, 403):
            raise TTSUnavailable(f"accès refusé (HTTP {exc.code}) : {detail}") from None
        if exc.code == 429 or exc.code >= 500:
            raise TTSTransientError(f"service momentanément indisponible (HTTP {exc.code}) : {detail}") from None
        raise TTSRequestError(f"requête refusée (HTTP {exc.code}) : {detail}") from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise TTSTransientError(f"réseau indisponible : {reason}") from None


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:
        return exc.reason or ""
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            return str(payload["error"].get("message", raw))[:300]
    except ValueError:
        pass
    return " ".join(raw.split())[:300] or str(exc.reason)
