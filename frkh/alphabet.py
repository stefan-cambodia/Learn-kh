"""Module « Alphabets » : alphabet khmer (consonnes, voyelles, chiffres), alphabet latin
(noms des lettres en français et en anglais, accents, sons particuliers), alphabet
cyrillique (russe) et écriture chinoise (tons, pinyin, premiers caractères), avec audio.

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

# Libellés : (français, anglais, khmer).
LABELS = {
    "title": ("Alphabets", "Alphabets", "អក្សរ"),
    "subtitle": ("Lettres khmères, latines et cyrilliques, et l'écriture chinoise, avec leur prononciation",
                 "Khmer, Latin and Cyrillic letters, and Chinese writing, with their pronunciation",
                 "អក្សរខ្មែរ ឡាតាំង ស៊ីរីលិក និងអក្សរចិន ព្រមទាំងការបញ្ចេញសំឡេង"),
    "cyrillic": ("Alphabet cyrillique (russe)", "Cyrillic alphabet (Russian)", "អក្សរស៊ីរីលិក (ភាសារុស្ស៊ី)"),
    "cyr_letters": ("Les 33 lettres", "The 33 letters", "អក្សរ៣៣តួ"),
    "chinese": ("Écriture chinoise", "Chinese writing", "អក្សរចិន"),
    "tones": ("Les tons", "Tones", "សំឡេងឡើងចុះ"),
    "initials": ("Les initiales du pinyin", "Pinyin initials", "សំឡេងដើម pinyin"),
    "finals": ("Les finales du pinyin", "Pinyin finals", "សំឡេងចុង pinyin"),
    "characters": ("Premiers caractères", "First characters", "តួអក្សរដំបូង"),
    "toc_cyrillic": ("Cyrillique", "Cyrillic", "ស៊ីរីលិក"),
    "toc_chinese": ("Chinois", "Chinese", "ចិន"),
    "khmer": ("Alphabet khmer", "Khmer alphabet", "អក្សរខ្មែរ"),
    "latin": ("Alphabet latin", "Latin alphabet", "អក្សរឡាតាំង"),
    "consonants": ("Les 33 consonnes", "The 33 consonants", "ព្យញ្ជនៈ៣៣តួ"),
    "vowels": ("Les voyelles", "Vowels", "ស្រៈ"),
    "digits": ("Les chiffres", "Digits", "លេខ"),
    "letters": ("Les 26 lettres", "The 26 letters", "អក្សរ២៦តួ"),
    "accents": ("Les accents du français", "French accents", "សញ្ញាលើអក្សរបារាំង"),
    "sounds": ("Sons à connaître", "Sounds to know", "សំឡេងពិសេស"),
    "series1": ("1re série", "1st series", "សំឡេងអ"),
    "series2": ("2e série", "2nd series", "សំឡេងអូ"),
    "rare": ("rare", "rare", "កម្រ"),
    "nav": ("Alphabets", "Alphabets", "អក្សរ"),
}


def lbl(key: str) -> str:
    from .render import multi
    return multi(LABELS[key])


def _notes(note: dict | None, css: str, fallback: bool = True) -> str:
    """Explication dans la langue du profil (voir render.scoped_notes)."""
    from .render import esc, scoped_notes
    if fallback:
        return scoped_notes(note, css=css)
    return "".join(f'<p class="{css} for-{lang}" lang="{lang}">{esc(text)}</p>'
                   for lang, text in (note or {}).items() if text)


def _meanings(item: dict, css: str = "glyph-meaning", langs=("fr", "en")) -> str:
    """Traduction d'un mot d'exemple, pour les profils dont c'est la langue."""
    return "".join(f'<span class="{css} for-{lang}" lang="{lang}">{_esc(item[lang])}</span>'
                   for lang in langs if item.get(lang))


def data_path(paths) -> Path:
    return Path(paths.content).parent / "alphabets.json"


def load(config) -> dict | None:
    path = data_path(config.paths)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    characters = config.characters()
    for part in ("khmer", "latin"):
        for key in ("intro", "vowels_intro"):
            if key in data.get(part, {}):
                data[part][key] = personalize_tree(data[part][key], characters)
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

    for letter in data.get("cyrillic", {}).get("letters", []):
        add("ru", letter["name"])
        add("ru", letter["example"]["word"])
    chinese = data.get("chinese", {})
    for key in ("tones", "initials", "finals", "characters"):
        for item in chinese.get(key, []):
            add("zh", item["char"])
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
    return f'<aside class="tip">{_notes(intro, "note")}</aside>'


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
                       f'{_meanings(ex)}'
                       f'{_audio(renderer, ex["km"], "km")}</div>')
        elif c.get("note"):
            example = _notes(c["note"], "glyph-note")
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
        f'<span class="translit">{_esc(d["tr"])}</span>{_meanings(d)}'
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
            f'<span class="glyph-meaning" lang="km">{_esc(ex["km"])}</span>{_meanings(ex, langs=("en",))}'
            f'{_audio(renderer, ex["word"], ex["lang"])}</div>'
            for ex in letter.get("examples", []))
        note = _notes(letter.get("note"), "glyph-note", fallback=False)
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
        f'{_notes(a["note"], "glyph-note", fallback=False)}'
        f'<div class="glyph-example lang-fr"><span class="glyph-word" lang="fr">{_esc(a["example"]["word"])}</span>'
        f'<span class="glyph-meaning" lang="km">{_esc(a["example"]["km"])}</span>{_meanings(a["example"], langs=("en",))}'
        f'{_audio(renderer, a["example"]["word"], "fr")}</div>'
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
            f'{_notes(s["note"], "glyph-note", fallback=False)}'
            f'<div class="glyph-example lang-{s["lang"]}"><span class="glyph-word" lang="{s["lang"]}">{_esc(s["example"]["word"])}</span>'
            f'<span class="glyph-meaning" lang="km">{_esc(s["example"]["km"])}</span>{_meanings(s["example"], langs=("en",))}'
            f'{_audio(renderer, s["example"]["word"], s["lang"])}</div></article>')
    return "".join(cards)


def _meaning3(meaning: dict | None) -> str:
    """Sens d'un mot d'exemple, dans la langue du profil (fr, en ou km)."""
    return "".join(f'<span class="glyph-meaning for-{lang}" lang="{lang}">{_esc(text)}</span>'
                   for lang, text in (meaning or {}).items() if text)


def _cyrillic_letters(renderer, cyr: dict) -> str:
    cards = []
    for letter in cyr.get("letters", []):
        ex = letter["example"]
        cards.append(
            f'<article class="glyph-card glyph-letter glyph-cyr"><div class="glyph-head">'
            f'<span class="glyph glyph-latin-big" lang="ru">{_esc(letter["upper"])} {_esc(letter["lower"])}</span>'
            f'<span class="glyph-sound translit" lang="ru-Latn">{_esc(letter["sound"])}</span></div>'
            f'<div class="glyph-row lang-ru"><span class="lang-tag" aria-hidden="true">RU</span>'
            f'<span class="glyph-name" lang="ru">{_esc(letter["name"])}</span>{_audio(renderer, letter["name"], "ru")}</div>'
            f'<div class="glyph-example lang-ru"><span class="glyph-word" lang="ru">{_esc(ex["word"])}</span>'
            f'<span class="translit" lang="ru-Latn">{_esc(ex["tr"])}</span>'
            f'{_meaning3({k: ex.get(k) for k in ("fr", "en", "km")})}{_audio(renderer, ex["word"], "ru")}</div>'
            f'{_notes(letter.get("note"), "glyph-note")}</article>')
    return "".join(cards)


def _han_cards(renderer, items: list, with_letters: bool = False) -> str:
    cards = []
    for item in items:
        if with_letters:
            head = (f'<div class="glyph-head"><span class="glyph glyph-latin-big glyph-combo" lang="zh-Latn-pinyin">'
                    f'{_esc(item["letters"])}</span></div>'
                    f'<div class="glyph-example lang-zh"><span class="glyph-word glyph-han" lang="zh">{_esc(item["char"])}</span>'
                    f'<span class="translit" lang="zh-Latn-pinyin">{_esc(item["py"])}</span>'
                    f'{_meaning3(item.get("meaning"))}{_audio(renderer, item["char"], "zh")}</div>')
        else:
            head = (f'<div class="glyph-head"><span class="glyph glyph-han" lang="zh">{_esc(item["char"])}</span>'
                    f'<span class="glyph-sound" lang="zh-Latn-pinyin">{_esc(item["py"])}</span>{_audio(renderer, item["char"], "zh")}</div>'
                    f'<div class="glyph-badges">{_meaning3(item.get("meaning"))}</div>')
        cards.append(f'<article class="glyph-card glyph-zh">{head}{_notes(item.get("note"), "glyph-note")}</article>')
    return "".join(cards)


def _extra_parts(renderer, data: dict) -> str:
    """Parties « Cyrillique » et « Chinois » (masquées avec la langue correspondante)."""
    out = ""
    cyr = data.get("cyrillic")
    if cyr:
        out += (f'<section class="part alpha-part only-ru" id="cyrillique"><header class="part-head">'
                f'<span class="part-num" aria-hidden="true" lang="ru">Я</span><h2>{lbl("cyrillic")}</h2></header>'
                f'{_intro(cyr.get("intro"))}'
                f'{_block("cyr-lettres", "cyr_letters", _cyrillic_letters(renderer, cyr))}</section>')
    zh = data.get("chinese")
    if zh:
        out += (f'<section class="part alpha-part only-zh" id="chinois"><header class="part-head">'
                f'<span class="part-num" aria-hidden="true" lang="zh">中</span><h2>{lbl("chinese")}</h2></header>'
                f'{_intro(zh.get("intro"))}'
                f'{_block("tons", "tones", _han_cards(renderer, zh.get("tones", [])), _notes(zh.get("tones_intro"), "alpha-hint"))}'
                f'{_block("initiales", "initials", _han_cards(renderer, zh.get("initials", []), with_letters=True))}'
                f'{_block("finales", "finals", _han_cards(renderer, zh.get("finals", []), with_letters=True))}'
                f'{_block("caracteres", "characters", _han_cards(renderer, zh.get("characters", [])), _notes(zh.get("characters_intro"), "alpha-hint"))}'
                f'</section>')
    return out


def render(renderer, data: dict | None) -> str | None:
    """Écrit alphabet.html et renvoie son chemin relatif (None si les données sont absentes)."""
    if not data:
        return None
    from .render import page_head
    khmer, latin = data.get("khmer", {}), data.get("latin", {})
    vowels_intro = ""
    if khmer.get("vowels_intro"):
        vi = khmer["vowels_intro"]
        vowels_intro = _notes(vi, "alpha-hint")
    toc = "".join(f'<a class="toc-link" href="#{anchor}">{lbl(key)}</a>' for anchor, key in (
        ("consonnes", "consonants"), ("voyelles", "vowels"), ("chiffres", "digits"),
        ("lettres", "letters"), ("accents", "accents"), ("sons", "sounds")))
    toc += "".join(f'<a class="toc-link {css}" href="#{anchor}">{lbl(key)}</a>' for anchor, key, css in (
        ("cyrillique", "toc_cyrillic", "only-ru"), ("chinois", "toc_chinese", "only-zh"))
        if data.get({"only-ru": "cyrillic", "only-zh": "chinese"}[css]))
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
    # Le profil khmer apprend l'alphabet latin : sa partie passe en premier (feuille de style).
    content = (
        f'<article class="alphabet">'
        f'{page_head(LABELS["title"], LABELS["subtitle"])}'
        f'<nav class="alpha-toc lesson-toc" data-toc aria-label="Sommaire"><div class="toc-links">{toc}</div></nav>'
        f'<div class="alpha-parts">{khmer_part}{latin_part}{_extra_parts(renderer, data)}</div></article>')
    page = renderer._page(root=".", title=f'{LABELS["title"][0]} — {renderer.config.get("site.title", "FR-KH Learning")}',
                          description="Alphabets khmer, latin et cyrillique, et écriture chinoise, avec la prononciation.",
                          body_class="page-alphabet", content=content)
    target = renderer.paths.index.parent / PAGE
    wavutil.atomic_write(target, page.encode("utf-8"))
    return renderer.paths.rel(target)

