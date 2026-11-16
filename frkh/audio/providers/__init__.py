"""Registre des fournisseurs de synthèse vocale."""

from __future__ import annotations

from .azure import AzureTTS
from .base import (SynthesisResult, TTSError, TTSProvider, TTSRequestError, TTSTransientError,
                   TTSUnavailable, VoiceSpec)
from .command import CommandTTS
from .google import GoogleTTS

_REGISTRY: dict[str, type[TTSProvider]] = {
    "google": GoogleTTS,
    "azure": AzureTTS,
    "command": CommandTTS,
}


def register_provider(name: str, cls: type[TTSProvider]) -> None:
    """Ajoute (ou remplace) un fournisseur, utilisable ensuite dans config.json."""
    _REGISTRY[name] = cls


def provider_names() -> list[str]:
    return sorted(_REGISTRY)


def create_provider(name: str, settings: dict | None = None, timeout: float = 30.0) -> TTSProvider:
    try:
        cls = _REGISTRY[name]
    except KeyError:
        raise TTSRequestError(
            f"fournisseur vocal inconnu : « {name} » (disponibles : {', '.join(provider_names())})") from None
    return cls(settings or {}, timeout)


__all__ = ["AzureTTS", "CommandTTS", "GoogleTTS", "SynthesisResult", "TTSError", "TTSProvider",
           "TTSRequestError", "TTSTransientError", "TTSUnavailable", "VoiceSpec", "create_provider",
           "provider_names", "register_provider"]
