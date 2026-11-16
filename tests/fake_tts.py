#!/usr/bin/env python3
"""Moteur vocal factice, réservé aux tests automatiques.

Il se branche sur le fournisseur « command » comme n'importe quel moteur local :
le texte arrive sur l'entrée standard et un vrai fichier WAV (PCM 16 bits mono)
est écrit à l'emplacement demandé. Le son est une simple note dont la durée
dépend de la longueur du texte : cela suffit pour contrôler le cache, la reprise
après interruption et la lecture dans le navigateur, sans clé API ni réseau.

Usage : fake_tts.py <fichier_sortie> <frequence_hz> <langue>

Variables d'environnement :
    FAKE_TTS_LOG       fichier où chaque appel est consigné (langue <TAB> texte) ;
    FAKE_TTS_FAIL      "1" pour simuler une panne du moteur ;
    FAKE_TTS_KILL_AT   numéro de l'appel à partir duquel le processus appelant est tué
                       (simulation d'une coupure brutale pendant la génération).
"""

import math
import os
import signal
import struct
import sys
import zlib


def main() -> int:
    output, sample_rate, lang = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    text = sys.stdin.buffer.read().decode("utf-8").strip()

    calls = 0
    log = os.environ.get("FAKE_TTS_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(f"{lang}\t{text}\n")
        with open(log, encoding="utf-8") as handle:
            calls = sum(1 for _ in handle)

    kill_at = int(os.environ.get("FAKE_TTS_KILL_AT") or 0)
    if kill_at and calls >= kill_at:
        os.kill(os.getppid(), signal.SIGTERM if os.name == "nt" else signal.SIGKILL)
        return 9

    if os.environ.get("FAKE_TTS_FAIL") == "1":
        print("moteur factice : panne simulée", file=sys.stderr)
        return 3

    base = {"fr": 392.0, "en": 494.0, "km": 587.0}.get(lang, 440.0)
    frequency = base + zlib.crc32(text.encode("utf-8")) % 60
    duration = min(3.0, 0.25 + 0.03 * len(text))
    frames = int(sample_rate * duration)
    fade = max(1, int(sample_rate * 0.02))
    samples = bytearray()
    for i in range(frames):
        envelope = min(1.0, i / fade, (frames - i) / fade)
        samples += struct.pack("<h", int(9000 * envelope * math.sin(2 * math.pi * frequency * i / sample_rate)))
    header = (b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE" + b"fmt "
              + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
              + b"data" + struct.pack("<I", len(samples)))
    with open(output, "wb") as handle:
        handle.write(header + bytes(samples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
