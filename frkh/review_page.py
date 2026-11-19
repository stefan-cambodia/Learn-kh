"""Page « Réviser » : cartes mémoire du vocabulaire et des expressions des leçons publiées.

Les données sont intégrées à la page (aucune requête réseau, fonctionne hors ligne) ;
le navigateur ne retient que les leçons dont la date est passée, et garde la
progression de chaque apprenant dans son stockage local (méthode de Leitner).
"""

from __future__ import annotations

import json

from .audio import wavutil
from .langs import translit
from .textutil import LANGS, speech_text

PAGE = "revision.html"

# Libellés : (français, anglais, khmer).
TEXT = {
    "title": ("Réviser", "Review", "រំលឹកមេរៀន"),
    "kicker": ("Cartes mémoire", "Flashcards", "កាតចងចាំ"),
    "intro": ("Une série de 20 cartes tirées des leçons passées. Les mots que vous connaissez mal reviennent plus souvent.",
              "A set of 20 cards from past lessons. Words you don't know well come back more often.",
              "កាត២០សន្លឹកពីមេរៀនដែលបានរៀនរួច។ ពាក្យដែលមិនទាន់ចាំច្បាស់ នឹងត្រលប់មកញឹកញាប់ជាង។"),
    "nojs": ("Cette page a besoin de JavaScript.", "This page needs JavaScript.", "ទំព័រនេះត្រូវការ JavaScript។"),
}


def _bi(key: str) -> str:
    from .render import multi
    return multi(TEXT[key])


def collect(renderer) -> list[dict]:
    cards: list[dict] = []
    seen: set[tuple[str, str]] = set()
    rows = renderer.conn.execute(
        "SELECT lesson_number, lesson_date, content_json, html_path FROM lessons "
        "WHERE status = 'complete' ORDER BY lesson_number").fetchall()
    for row in rows:
        content = json.loads(row["content_json"])
        for kind in ("vocabulary", "expressions"):
            for entry in content.get(kind, []):
                key = (entry.get("fr", ""), entry.get("km", ""))
                if not all(entry.get(lang) for lang in LANGS) or key in seen:
                    continue
                seen.add(key)
                audio = {}
                langs = [lang for lang in renderer.config.content_langs() if entry.get(lang)]
                for lang in langs:
                    ref = renderer.library.lookup(speech_text(entry[lang]), lang)
                    if ref.ready:
                        audio[lang] = ref.path
                card = {
                    "id": f'{entry["fr"]}|{entry["km"]}', "n": row["lesson_number"], "d": row["lesson_date"],
                    "k": "w" if kind == "vocabulary" else "e",
                    "fr": entry["fr"], "en": entry["en"], "km": entry["km"], "tr": entry.get("tr", ""),
                    "a": audio, "href": row["html_path"] or f'lessons/lesson-{row["lesson_number"]:03d}.html',
                }
                for lang in langs:
                    card[lang] = entry[lang]
                    reading = translit(entry, lang)
                    if reading and lang != "km":
                        card[f"{lang}_tr"] = reading
                cards.append(card)
    return cards


def render(renderer) -> str:
    from .render import ICONS
    cards = collect(renderer)
    payload = json.dumps(cards, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    content = (
        f'<article class="review-page">'
        f'<nav class="lesson-nav" aria-label="Navigation"><a class="nav-link nav-home" data-nav href="./index.html">'
        f'{ICONS["home"]}{_home()}</a></nav>'
        f'<header class="lesson-head"><p class="kicker">{_bi("kicker")}</p>'
        f'<h1 class="tri-title">{"".join(f'<span class="t-{lang}" lang="{lang}">{text}</span>' for lang, text in zip(LANGS, TEXT["title"]))}</h1>'
        f'<p class="alpha-subtitle">{_bi("intro")}</p></header>'
        f'<noscript><p class="empty">{_bi("nojs")}</p></noscript>'
        f'<div id="review-app" class="review-app js-only"></div>'
        f'<script type="application/json" id="review-data">{payload}</script>'
        f'<script src="./js/review.js?v={renderer._asset_version()}" defer></script>'
        f'</article>')
    page = renderer._page(root=".", title=f'{TEXT["title"][0]} — {renderer.config.get("site.title", "FR-KH Learning")}',
                          description="Cartes mémoire du vocabulaire des leçons, dans toutes les langues.",
                          body_class="page-review", content=content)
    target = renderer.paths.index.parent / PAGE
    wavutil.atomic_write(target, page.encode("utf-8"))
    return renderer.paths.rel(target)


def _home() -> str:
    from .render import ui
    return ui("home")
