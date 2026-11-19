"""Encodage et contrôle des fichiers MP3 (mono), sans dépendance Python.

L'encodage passe par ffmpeg (encodeur libmp3lame). Le contrôle lit les en-têtes
de trames MPEG : il détecte un fichier vide, tronqué ou d'un autre format, et
calcule la durée sans décoder le son.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .wavutil import MIN_DURATION, AudioFormatError

# Débits (kbit/s) de la couche III : MPEG-1, puis MPEG-2 et 2.5.
_BITRATES = {
    1: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0),
    2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0),
}
_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


@dataclass(frozen=True)
class Mp3Info:
    sample_rate: int
    channels: int
    frames: int        # trames MPEG
    samples: int       # échantillons par canal
    bitrate: int       # kbit/s (moyen)

    @property
    def duration(self) -> float:
        return self.samples / self.sample_rate if self.sample_rate else 0.0


def _header(data: bytes, pos: int):
    """(taille de la trame, fréquence, canaux, échantillons, débit) ou None si pas d'en-tête valide ici."""
    if pos + 4 > len(data) or data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return None
    b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
    version = (b1 >> 3) & 3          # 3 : MPEG-1, 2 : MPEG-2, 0 : MPEG-2.5
    layer = (b1 >> 1) & 3            # 1 : couche III
    if version == 1 or layer != 1:
        return None
    bitrate = _BITRATES[1 if version == 3 else 2][b2 >> 4]
    rate_index = (b2 >> 2) & 3
    if not bitrate or rate_index == 3:
        return None
    rate = _RATES[version][rate_index]
    padding = (b2 >> 1) & 1
    samples = 1152 if version == 3 else 576
    size = (samples // 8) * bitrate * 1000 // rate + padding
    channels = 1 if (b3 >> 6) == 3 else 2
    return size, rate, channels, samples, bitrate


def _skip_id3(data: bytes) -> int:
    if data[:3] != b"ID3" or len(data) < 10:
        return 0
    size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
    return 10 + size + (10 if data[5] & 0x10 else 0)


def inspect_mp3_bytes(data: bytes, expected_rate: int | None = None) -> Mp3Info:
    """Contrôle complet : trames MPEG couche III enchaînées jusqu'à la fin du fichier."""
    if not data:
        raise AudioFormatError("fichier MP3 vide")
    pos = _skip_id3(data)
    end = len(data) - (128 if data[-128:-125] == b"TAG" else 0)
    frames = samples = 0
    rate = channels = 0
    bits = 0
    while pos < end:
        head = _header(data, pos)
        if head is None:
            if frames:
                raise AudioFormatError(f"trame MP3 invalide à l'octet {pos} : fichier tronqué ou altéré")
            raise AudioFormatError("en-tête MP3 absent")
        size, frame_rate, frame_channels, frame_samples, bitrate = head
        if pos + size > end:
            raise AudioFormatError("dernière trame MP3 incomplète : fichier tronqué")
        if frames and frame_rate != rate:
            raise AudioFormatError("fréquence d'échantillonnage variable dans le fichier MP3")
        rate, channels = frame_rate, frame_channels
        # La trame « Xing » / « Info » de LAME ne contient pas de son : elle n'entre pas dans la durée.
        body = data[pos + 4: pos + min(size, 64)]
        if not (frames == 0 and (b"Xing" in body or b"Info" in body)):
            frames += 1
            samples += frame_samples
            bits += bitrate
        pos += size
    info = Mp3Info(rate, channels, frames, samples, round(bits / frames) if frames else 0)
    if expected_rate and rate != expected_rate:
        raise AudioFormatError(f"{rate} Hz ({expected_rate} Hz attendus)")
    if info.duration < MIN_DURATION:
        raise AudioFormatError("fichier audio vide ou trop court")
    return info


def inspect_mp3_file(path: Path, expected_rate: int | None = None) -> Mp3Info:
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise AudioFormatError(f"fichier illisible : {exc}") from exc
    return inspect_mp3_bytes(data, expected_rate)


def ffmpeg_ready() -> tuple[bool, str]:
    if not shutil.which("ffmpeg"):
        return False, "ffmpeg est introuvable : il est nécessaire pour produire des fichiers MP3"
    return True, ""


def wav_to_mp3(wav: bytes, sample_rate: int, bitrate_kbps: int) -> bytes:
    """Encode un WAV PCM mono en MP3 mono à débit constant (sans balise ID3)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AudioFormatError("ffmpeg est introuvable : impossible d'encoder en MP3")
    with tempfile.TemporaryDirectory(prefix="frkh-mp3-") as tmp:
        source, target = Path(tmp) / "source.wav", Path(tmp) / "target.mp3"
        source.write_bytes(wav)
        proc = subprocess.run(
            [ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-i", str(source), "-ac", "1", "-ar", str(sample_rate),
             "-codec:a", "libmp3lame", "-b:a", f"{int(bitrate_kbps)}k", "-map_metadata", "-1",
             "-id3v2_version", "0", "-write_id3v1", "0", "-f", "mp3", str(target)],
            capture_output=True, timeout=120)
        if proc.returncode != 0 or not target.is_file():
            raise AudioFormatError("encodage MP3 impossible : " + proc.stderr.decode("utf-8", "replace")[:200])
        data = target.read_bytes()
    inspect_mp3_bytes(data, expected_rate=sample_rate)
    return data
