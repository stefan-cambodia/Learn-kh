"""Module « Alphabets » : alphabet khmer (consonnes, voyelles, chiffres) et alphabet latin
(noms des lettres en français et en anglais, accents, sons particuliers), avec audio.

Les données se trouvent dans ``content/alphabets.json`` ; la page produite est
``alphabet.html``, à la racine du site, à côté de ``index.html``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .audio import wavutil
from .curriculum import personalize_tree
from .textutil import speech_text

# Consonne de 1re série puis de 2e série : elles font entendre les deux lectures d'une voyelle.
CARRIERS = ("ក", "គ")
DOTTED_CIRCLE = "◌"
PAGE = "alphabet.html"

LABELS = {
    "title": ("Alphabets", "អក្សរ"),
    "kicker": ("Module d'écriture", "ម៉ូឌុលអក្សរ"),
    "subtitle": ("Lettres khmères et latines, avec leur prononciation",
                 "អក្សរខ្មែរ និងអក្សរឡាតាំង ព្រមទាំងការបញ្ចេញសំឡេង"),
    "khmer": ("Alphabet khmer", "អក្សរខ្មែរ"),
    "latin": ("Alphabet latin", "អក្សរឡាតាំង"),
    "consonants": ("Les 33 consonnes", "ព្យញ្ជនៈ៣៣តួ"),
    "vowels": ("Les voyelles", "ស្រៈ"),
    "digits": ("Les chiffres", "លេខ"),
    "letters": ("Les 26 lettres", "អក្សរ២៦តួ"),
    "accents": ("Les accents du français", "សញ្ញាលើអក្សរបារាំង"),
    "sounds": ("Sons à connaître", "សំឡេងពិសេស"),
    "series1": ("1re série", "សំឡេងអ"),
    "series2": ("2e série", "សំឡេងអូ"),
    "rare": ("rare", "កម្រ"),
    "nav": ("Alphabets", "អក្សរ"),
}


def lbl(key: str) -> str:
    from .render import bilingual
    return bilingual(*LABELS[key])


def data_path(paths) -> Path:
    return Path(paths.content).parent / "alphabets.json"


def load(config) -> dict | None:
    path = data_path(config.paths)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    learners = config["learners"]
    for part in ("khmer", "latin"):
        for key in ("intro", "vowels_intro"):
            if key in data.get(part, {}):
                data[part][key] = personalize_tree(data[part][key], learners)
    return data


def vowel_syllables(sign: str) -> list[str]:
    return [carrier + sign for carrier in CARRIERS]


def audio_items(data: dict | None) -> list[tuple[str, str]]:
    """Tous les couples (langue, texte) de la page qui doivent avoir un fichier audio."""
    if not data:
        return []
    seen: set[tuple[str, str]] = set()
    items: list[tuple[str, str]] = []

    def add(lang: str, text: str) -> None:
        text = speech_text(text or "")
        if text and (lang, text) not in seen:
            seen.add((lang, text))
            items.append((lang, text))

    khmer = data.get("khmer", {})
    for consonant in khmer.get("consonants", []):
        add("km", consonant["char"])
        if consonant.get("example"):
            add("km", consonant["example"]["km"])
    for vowel in khmer.get("vowels", []):
        for syllable in vowel_syllables(vowel["sign"]):
            add("km", syllable)
    for digit in khmer.get("digits", []):
        add("km", digit["km"])

    latin = data.get("latin", {})
    for letter in latin.get("letters", []):
        add("fr", letter["fr"]["name"])
        add("en", letter["en"]["name"])
        for example in letter.get("examples", []):
            add(example["lang"], example["word"])
    for accent in latin.get("accents", []):
        add("fr", accent["name"])
        add("fr", accent["example"]["word"])
    for sound in latin.get("sounds", []):
        add(sound["lang"], sound["example"]["word"])
    return items


def ensure_audio(library, data: dict | None) -> dict:
    totals = {"ready": 0, "missing": 0, "hashes": set()}
    for lang, text in audio_items(data):
        ref = library.ensure(text, lang)
        totals["hashes"].add(ref.text_hash)
        totals["ready" if ref.ready else "missing"] += 1
    return totals


# --- rendu ---------------------------------------------------------------------------------------
def _esc(value) -> str:
    from .render import esc
    return esc(value)


def _audio(renderer, text: str, lang: str) -> str:
    return f'<span class="glyph-audio lang-{lang}">{renderer._audio(text, lang, ".")}</span>'


def _intro(intro: dict | None) -> str:
    if not intro:
        return ""
    return (f'<aside class="tip"><p class="note for-b" lang="fr">{_esc(intro.get("fr", ""))}</p>'
            f'<p class="note for-a" lang="km">{_esc(intro.get("km", ""))}</p></aside>')


def _block(anchor: str, title_key: str, body: str, intro: str = "") -> str:
    return (f'<section class="alpha-block" id="{anchor}"><h3 class="alpha-title">{lbl(title_key)}</h3>'
            f'{intro}<div class="glyph-grid">{body}</div></section>')


def _consonants(renderer, khmer: dict) -> str:
    cards = []
    for c in khmer.get("consonants", []):
        series = c.get("series", 1)
        example = ""
        if c.get("example"):
            ex = c["example"]
            example = (f'<div class="glyph-example lang-km"><span class="glyph-word" lang="km">{_esc(ex["km"])}</span>'
                       f'<span class="translit">{_esc(ex["tr"])}</span>'
                       f'<span class="glyph-meaning for-b" lang="fr">{_esc(ex["fr"])}</span>'
                       f'{_audio(renderer, ex["km"], "km")}</div>')
        elif c.get("note"):
            example = (f'<p class="glyph-note for-b" lang="fr">{_esc(c["note"].get("fr", ""))}</p>'
                       f'<p class="glyph-note for-a" lang="km">{_esc(c["note"].get("km", ""))}</p>')
        rare = f'<span class="badge badge-uncertain">{lbl("rare")}</span>' if c.get("note") and not c.get("example") else ""
        cards.append(
            f'<article class="glyph-card series-{series}">'
            f'<div class="glyph-head"><span class="glyph" lang="km">{_esc(c["char"])}</span>'
            f'<span class="glyph-sound">{_esc(c["tr"])}</span>{_audio(renderer, c["char"], "km")}</div>'
            f'<div class="glyph-badges"><span class="badge series-badge">{lbl("series" + str(series))}</span>{rare}</div>'
            f'{example}</article>')
    return "".join(cards)


def _vowels(renderer, khmer: dict) -> str:
    cards = []
    for v in khmer.get("vowels", []):
        rows = []
        for series, (syllable, sound) in enumerate(zip(vowel_syllables(v["sign"]), v["tr"]), start=1):
            rows.append(f'<div class="glyph-row series-{series}"><span class="glyph-syllable" lang="km">{_esc(syllable)}</span>'
                        f'<span class="glyph-sound">{_esc(sound)}</span>{_audio(renderer, syllable, "km")}</div>')
        cards.append(f'<article class="glyph-card glyph-vowel"><div class="glyph-head">'
                     f'<span class="glyph" lang="km">{DOTTED_CIRCLE}{_esc(v["sign"])}</span></div>{"".join(rows)}</article>')
    return "".join(cards)


def _digits(renderer, khmer: dict) -> str:
    return "".join(
        f'<article class="glyph-card glyph-digit"><div class="glyph-head"><span class="glyph" lang="km">{_esc(d["char"])}</span>'
        f'<span class="glyph-latin">{_esc(d["char"].translate(str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")))}</span></div>'
        f'<div class="glyph-example lang-km"><span class="glyph-word" lang="km">{_esc(d["km"])}</span>'
        f'<span class="translit">{_esc(d["tr"])}</span><span class="glyph-meaning for-b" lang="fr">{_esc(d["fr"])}</span>'
        f'{_audio(renderer, d["km"], "km")}</div></article>'
        for d in khmer.get("digits", []))


def _name_row(renderer, lang: str, name: dict) -> str:
    tag = {"fr": "FR", "en": "EN"}[lang]
    return (f'<div class="glyph-row lang-{lang}"><span class="lang-tag" aria-hidden="true">{tag}</span>'
            f'<span class="glyph-name" lang="{lang}">{_esc(name["name"])}</span>'
            f'<span class="glyph-approx" lang="km">{_esc(name["km"])}</span>{_audio(renderer, name["name"], lang)}</div>')


def _letters(renderer, latin: dict) -> str:
    cards = []
    for letter in latin.get("letters", []):
        examples = "".join(
            f'<div class="glyph-example lang-{ex["lang"]}"><span class="glyph-word" lang="{ex["lang"]}">{_esc(ex["word"])}</span>'
            f'<span class="glyph-meaning" lang="km">{_esc(ex["km"])}</span>{_audio(renderer, ex["word"], ex["lang"])}</div>'
            for ex in letter.get("examples", []))
        note = ""
        if letter.get("note", {}).get("km"):
            note = f'<p class="glyph-note" lang="km">{_esc(letter["note"]["km"])}</p>'
        upper = letter["upper"]
        cards.append(
            f'<article class="glyph-card glyph-letter"><div class="glyph-head">'
            f'<span class="glyph glyph-latin-big">{_esc(upper)} {_esc(upper.lower())}</span></div>'
            f'{_name_row(renderer, "fr", letter["fr"])}{_name_row(renderer, "en", letter["en"])}{examples}{note}</article>')
    return "".join(cards)


def _accents(renderer, latin: dict) -> str:
    return "".join(
        f'<article class="glyph-card"><div class="glyph-head"><span class="glyph glyph-latin-big">{_esc(a["char"])}</span>'
        f'<span class="glyph-name lang-fr" lang="fr">{_esc(a["name"])}</span>{_audio(renderer, a["name"], "fr")}</div>'
        f'<p class="glyph-note" lang="km">{_esc(a["note"]["km"])}</p>'
        f'<div class="glyph-example lang-fr"><span class="glyph-word" lang="fr">{_esc(a["example"]["word"])}</span>'
        f'<span class="glyph-meaning" lang="km">{_esc(a["example"]["km"])}</span>{_audio(renderer, a["example"]["word"], "fr")}</div>'
        f'</article>'
        for a in latin.get("accents", []))


def _sounds(renderer, latin: dict) -> str:
    cards = []
    for s in latin.get("sounds", []):
        tag = {"fr": "FR", "en": "EN"}[s["lang"]]
        cards.append(
            f'<article class="glyph-card lang-{s["lang"]}"><div class="glyph-head">'
            f'<span class="lang-tag" aria-hidden="true">{tag}</span>'
            f'<span class="glyph glyph-latin-big glyph-combo">{_esc(s["letters"])}</span>'
            f'<span class="glyph-approx" lang="km">{_esc(s["km"])}</span></div>'
            f'<p class="glyph-note" lang="km">{_esc(s["note"]["km"])}</p>'
            f'<div class="glyph-example lang-{s["lang"]}"><span class="glyph-word" lang="{s["lang"]}">{_esc(s["example"]["word"])}</span>'
            f'<span class="glyph-meaning" lang="km">{_esc(s["example"]["km"])}</span>'
            f'{_audio(renderer, s["example"]["word"], s["lang"])}</div></article>')
    return "".join(cards)


def render(renderer, data: dict | None) -> str | None:
    """Écrit alphabet.html et renvoie son chemin relatif (None si les données sont absentes)."""
    if not data:
        return None
    khmer, latin = data.get("khmer", {}), data.get("latin", {})
    vowels_intro = ""
    if khmer.get("vowels_intro"):
        vi = khmer["vowels_intro"]
        vowels_intro = (f'<p class="alpha-hint for-b" lang="fr">{_esc(vi.get("fr", ""))}</p>'
                        f'<p class="alpha-hint for-a" lang="km">{_esc(vi.get("km", ""))}</p>')
    toc = "".join(f'<a class="chip" href="#{anchor}">{lbl(key)}</a>' for anchor, key in (
        ("consonnes", "consonants"), ("voyelles", "vowels"), ("chiffres", "digits"),
        ("lettres", "letters"), ("accents", "accents"), ("sons", "sounds")))
    khmer_part = (
        f'<section class="part alpha-part" id="khmer"><header class="part-head">'
        f'<span class="part-num" aria-hidden="true" lang="km">ក</span><h2>{lbl("khmer")}</h2></header>'
        f'{_intro(khmer.get("intro"))}'
        f'{_block("consonnes", "consonants", _consonants(renderer, khmer))}'
        f'{_block("voyelles", "vowels", _vowels(renderer, khmer), vowels_intro)}'
        f'{_block("chiffres", "digits", _digits(renderer, khmer))}</section>')
    latin_part = (
        f'<section class="part alpha-part" id="latin"><header class="part-head">'
        f'<span class="part-num" aria-hidden="true">A</span><h2>{lbl("latin")}</h2></header>'
        f'{_intro(latin.get("intro"))}'
        f'{_block("lettres", "letters", _letters(renderer, latin))}'
        f'{_block("accents", "accents", _accents(renderer, latin))}'
        f'{_block("sons", "sounds", _sounds(renderer, latin))}</section>')
    # Le profil A (khmer) apprend l'alphabet latin : sa partie passe en premier.
    content = (
        f'<article class="alphabet">'
        f'<nav class="lesson-nav" aria-label="Navigation"><a class="nav-link nav-home" data-nav href="./index.html">'
        f'{renderer_icon("home")}{lbl_home()}</a></nav>'
        f'<header class="lesson-head"><p class="kicker">{lbl("kicker")}</p>'
        f'<h1 class="tri-title"><span class="t-fr" lang="fr">{_esc(LABELS["title"][0])}</span>'
        f'<span class="t-km" lang="km">{_esc(LABELS["title"][1])}</span></h1>'
        f'<p class="alpha-subtitle">{lbl("subtitle")}</p></header>'
        f'<nav class="alpha-toc" aria-label="Sommaire">{toc}</nav>'
        f'<div class="alpha-parts">{khmer_part}{latin_part}</div></article>')
    page = renderer._page(root=".", title=f'{LABELS["title"][0]} — {renderer.config.get("site.title", "FR-KH Learning")}',
                          description="Alphabet khmer et alphabet latin, avec la prononciation de chaque lettre.",
                          body_class="page-alphabet", content=content)
    target = renderer.paths.index.parent / PAGE
    wavutil.atomic_write(target, page.encode("utf-8"))
    return renderer.paths.rel(target)


def renderer_icon(name: str) -> str:
    from .render import ICONS
    return ICONS[name]


def lbl_home() -> str:
    from .render import ui
    return ui("home")
