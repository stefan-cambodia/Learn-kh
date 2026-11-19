#!/usr/bin/env python3
"""Moteur vocal « Google Traduction » pour le fournisseur « command ».

Utilise la voix du bouton « Écouter » de translate.google.com (service non
officiel, sans clé API). Le texte est lu sur l'entrée standard ; le résultat est
un WAV PCM mono 16 bits écrit dans le fichier de sortie.

    gtranslate_tts.py --lang km --output out.wav --sample-rate 24000 --rate 0.9

Nécessite ffmpeg. Les textes de plus de 180 caractères sont découpés aux
ponctuations puis recollés.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://translate.google.com/translate_tts"
MAX_CHARS = 180
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def split_text(text: str) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= MAX_CHARS:
        return [text]
    pieces = [p for p in re.split(r"(?<=[.!?។៕,;:،。！？，；：])\s*", text) if p]
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        while len(piece) > MAX_CHARS:  # morceau sans ponctuation : couper aux espaces
            cut = piece.rfind(" ", 0, MAX_CHARS)
            cut = cut if cut > 0 else MAX_CHARS
            chunks.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if current and len(current) + 1 + len(piece) > MAX_CHARS:
            chunks.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


def fetch(chunk: str, lang: str, index: int, total: int) -> bytes:
    query = urllib.parse.urlencode({"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": chunk,
                                    "total": total, "idx": index, "textlen": len(chunk)})
    request = urllib.request.Request(f"{ENDPOINT}?{query}", headers={"User-Agent": USER_AGENT,
                                                                     "Referer": "https://translate.google.com/"})
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
            if data:
                return data
            last_error = "réponse vide"
        except Exception as exc:  # noqa: BLE001 — on réessaie puis on signale l'erreur
            last_error = exc
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Google Traduction n'a pas répondu ({lang}) : {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", required=True, help="code langue Google : fr, en, km…")
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-rate", type=int, default=24000)
    parser.add_argument("--rate", type=float, default=1.0, help="vitesse (0.5 à 2.0)")
    args = parser.parse_args()

    text = sys.stdin.read().strip()
    if not text:
        print("texte vide", file=sys.stderr)
        return 2
    chunks = split_text(text)
    lang = {"zh": "zh-CN"}.get(args.lang, args.lang)
    mp3 = b"".join(fetch(chunk, lang, i, len(chunks)) for i, chunk in enumerate(chunks))

    filters = []
    if abs(args.rate - 1.0) > 1e-3:
        filters = ["-filter:a", f"atempo={min(2.0, max(0.5, args.rate)):g}"]
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", "pipe:0", *filters,
                           "-ac", "1", "-ar", str(args.sample_rate), "-c:a", "pcm_s16le", args.output],
                          input=mp3, capture_output=True)
    if proc.returncode != 0:
        print(f"ffmpeg : {proc.stderr.decode('utf-8', 'replace').strip()[:200]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
