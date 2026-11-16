"""Lecture, conversion et contrôle des fichiers WAV (PCM 16 bits mono), sans dépendance."""

from __future__ import annotations

import array
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

WAVE_FORMAT_PCM = 1
WAVE_FORMAT_EXTENSIBLE = 0xFFFE
MIN_DURATION = 0.05      # secondes
SILENCE_PEAK = 48        # amplitude maximale en dessous de laquelle le fichier est jugé muet


class AudioFormatError(Exception):
    """Le contenu audio est absent, tronqué ou dans un format inattendu."""


@dataclass(frozen=True)
class WavInfo:
    channels: int
    bits: int
    sample_rate: int
    frames: int
    peak: int

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0


def _parse_riff(data: bytes, strict: bool) -> tuple[int, int, int, int, bytes]:
    """Retourne (format, canaux, fréquence, bits, échantillons bruts).

    En mode tolérant, accepte les en-têtes de flux dont la taille déclarée vaut
    0 ou 0xFFFFFFFF (courants en sortie d'API) ; en mode strict, la taille du
    bloc de données doit correspondre exactement au fichier.
    """
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AudioFormatError("en-tête RIFF/WAVE absent")
    pos, fmt = 12, None
    while pos + 8 <= len(data):
        chunk, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        if chunk == b"fmt ":
            if size < 16 or body + 16 > len(data):
                raise AudioFormatError("bloc « fmt » invalide")
            tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", data[body:body + 16])
            if tag == WAVE_FORMAT_EXTENSIBLE and size >= 26:
                tag = struct.unpack("<H", data[body + 24:body + 26])[0]
            fmt = (tag, channels, rate, bits)
        elif chunk == b"data":
            if fmt is None:
                raise AudioFormatError("bloc « data » avant le bloc « fmt »")
            remaining = len(data) - body
            if strict:
                if size != remaining and not (size + (size & 1) == remaining):
                    raise AudioFormatError(
                        f"fichier tronqué ou altéré ({remaining} octets de son, {size} annoncés)")
            elif size == 0 or size > remaining:
                size = remaining
            return (*fmt, data[body:body + size])
        pos = body + size + (size & 1)
    raise AudioFormatError("bloc « data » introuvable")


def _to_samples(pcm: bytes, bits: int) -> array.array:
    """Convertit des échantillons PCM 8/16/24/32 bits en entiers 16 bits signés."""
    if bits == 16:
        samples = array.array("h")
        samples.frombytes(pcm[:len(pcm) - (len(pcm) % 2)])
        if sys.byteorder == "big":
            samples.byteswap()
        return samples
    if bits == 8:
        return array.array("h", ((b - 128) << 8 for b in pcm))
    if bits in (24, 32):
        step = bits // 8
        usable = len(pcm) - (len(pcm) % step)
        return array.array("h", (int.from_bytes(pcm[i + step - 2:i + step], "little", signed=True)
                                 for i in range(0, usable, step)))
    raise AudioFormatError(f"profondeur de {bits} bits non prise en charge")


def _downmix(samples: array.array, channels: int) -> array.array:
    if channels == 1:
        return samples
    usable = len(samples) - (len(samples) % channels)
    return array.array("h", (sum(samples[i:i + channels]) // channels for i in range(0, usable, channels)))


def _resample(samples: array.array, source_rate: int, target_rate: int) -> array.array:
    """Rééchantillonnage par interpolation linéaire (suffisant pour de la voix)."""
    if source_rate == target_rate or not samples:
        return samples
    count = max(1, int(round(len(samples) * target_rate / source_rate)))
    ratio, last = source_rate / target_rate, len(samples) - 1
    out = array.array("h", bytes(2 * count))
    for i in range(count):
        position = i * ratio
        left = int(position)
        if left >= last:
            out[i] = samples[last]
        else:
            frac = position - left
            out[i] = int(samples[left] + (samples[left + 1] - samples[left]) * frac)
    return out


def _build_wav(samples: array.array, sample_rate: int) -> bytes:
    if sys.byteorder == "big":
        samples = array.array("h", samples)
        samples.byteswap()
    pcm = samples.tobytes()
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt " + struct.pack(
        "<IHHIIHH", 16, WAVE_FORMAT_PCM, 1, sample_rate, sample_rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm))
    return header + pcm


def _ffmpeg_to_wav(data: bytes, target_rate: int) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AudioFormatError("format audio compressé reçu : installez ffmpeg pour le convertir en WAV")
    with tempfile.TemporaryDirectory(prefix="frkh-audio-") as tmp:
        source, target = Path(tmp) / "source.bin", Path(tmp) / "target.wav"
        source.write_bytes(data)
        proc = subprocess.run(
            [ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-i", str(source), "-ac", "1", "-ar", str(target_rate),
             "-acodec", "pcm_s16le", "-f", "wav", str(target)],
            capture_output=True, timeout=120)
        if proc.returncode != 0 or not target.is_file():
            raise AudioFormatError("conversion ffmpeg impossible : " + proc.stderr.decode("utf-8", "replace")[:200])
        return target.read_bytes()


def to_wav_pcm16_mono(data: bytes, fmt: str, target_rate: int, source_rate: int | None = None) -> bytes:
    """Normalise n'importe quelle sortie de moteur vocal en WAV PCM 16 bits mono."""
    if not data:
        raise AudioFormatError("réponse audio vide")
    fmt = (fmt or "wav").lower()
    if fmt in ("pcm", "pcm_s16le", "raw", "linear16-raw"):
        if not source_rate:
            raise AudioFormatError("fréquence d'échantillonnage inconnue pour un flux PCM brut")
        samples, rate = _to_samples(data, 16), source_rate
    else:
        if fmt != "wav" or data[:4] != b"RIFF":
            data = _ffmpeg_to_wav(data, target_rate)
        tag, channels, rate, bits, pcm = _parse_riff(data, strict=False)
        if tag != WAVE_FORMAT_PCM:
            tag, channels, rate, bits, pcm = _parse_riff(_ffmpeg_to_wav(data, target_rate), strict=False)
        samples = _downmix(_to_samples(pcm, bits), channels)
    wav = _build_wav(_resample(samples, rate, target_rate), target_rate)
    inspect_wav_bytes(wav, expected_rate=target_rate)
    return wav


def inspect_wav_bytes(data: bytes, expected_rate: int | None = None) -> WavInfo:
    """Contrôle strict : WAV PCM, mono, 16 bits, non tronqué, non muet."""
    tag, channels, rate, bits, pcm = _parse_riff(data, strict=True)
    if tag != WAVE_FORMAT_PCM:
        raise AudioFormatError("le fichier n'est pas en PCM non compressé")
    if channels != 1:
        raise AudioFormatError(f"{channels} canaux (mono attendu)")
    if bits != 16:
        raise AudioFormatError(f"{bits} bits (16 bits attendus)")
    if expected_rate and rate != expected_rate:
        raise AudioFormatError(f"{rate} Hz ({expected_rate} Hz attendus)")
    samples = _to_samples(pcm, 16)
    info = WavInfo(channels, bits, rate, len(samples), max(max(samples, default=0), -min(samples, default=0)))
    if info.duration < MIN_DURATION:
        raise AudioFormatError("fichier audio vide ou trop court")
    if info.peak < SILENCE_PEAK:
        raise AudioFormatError("fichier audio muet")
    return info


def inspect_wav_file(path: Path, expected_rate: int | None = None) -> WavInfo:
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise AudioFormatError(f"fichier illisible : {exc}") from exc
    return inspect_wav_bytes(data, expected_rate)


def quick_check_file(path: Path, expected_rate: int | None = None) -> WavInfo:
    """Contrôle rapide (en-tête et taille) : détecte un fichier absent, tronqué ou d'un autre format
    sans relire tous les échantillons. Le contrôle complet reste ``inspect_wav_file``."""
    path = Path(path)
    try:
        total = path.stat().st_size
        with open(path, "rb") as handle:
            head = handle.read(4096)
    except OSError as exc:
        raise AudioFormatError(f"fichier illisible : {exc}") from exc
    if len(head) < 44 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        raise AudioFormatError("en-tête RIFF/WAVE absent")
    pos, fmt = 12, None
    while pos + 8 <= len(head):
        chunk, size = head[pos:pos + 4], struct.unpack("<I", head[pos + 4:pos + 8])[0]
        body = pos + 8
        if chunk == b"fmt " and body + 16 <= len(head):
            tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", head[body:body + 16])
            fmt = (tag, channels, rate, bits)
        elif chunk == b"data":
            if fmt is None:
                break
            tag, channels, rate, bits = fmt
            if tag != WAVE_FORMAT_PCM or channels != 1 or bits != 16:
                raise AudioFormatError("format différent de PCM 16 bits mono")
            if expected_rate and rate != expected_rate:
                raise AudioFormatError(f"{rate} Hz ({expected_rate} Hz attendus)")
            if body + size != total and body + size + (size & 1) != total:
                raise AudioFormatError("fichier tronqué ou altéré")
            info = WavInfo(channels, bits, rate, size // 2, -1)
            if info.duration < MIN_DURATION:
                raise AudioFormatError("fichier audio vide ou trop court")
            return info
        pos = body + size + (size & 1)
    raise AudioFormatError("structure WAV invalide")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _umask() -> int:
    global _UMASK
    if _UMASK is None:
        _UMASK = os.umask(0)
        os.umask(_UMASK)
    return _UMASK


_UMASK: int | None = None


def atomic_write(path: Path, data: bytes) -> None:
    """Écrit le fichier complet ou rien : jamais de fichier à moitié écrit en cas d'interruption."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=path.suffix, dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            # mkstemp crée un fichier privé (0600) : on rend les droits habituels (0644 selon l'umask)
            # pour que le site reste lisible par un serveur web ou un autre compte de la machine.
            os.chmod(tmp_name, 0o666 & ~_umask())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
