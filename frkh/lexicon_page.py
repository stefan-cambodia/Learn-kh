"""Page « Lexique » : tous les mots et expressions des leçons publiées, avec recherche et audio.

Le navigateur masque les entrées des leçons dont la date n'est pas encore arrivée
(leçons générées à l'avance). Les boutons audio sont légers (``data-src``) : la page
reste rapide même avec plusieurs centaines d'entrées.
"""

from __future__ import annotations

import json

from .audio import wavutil
from .textutil import LANGS, fold, speech_text, to_khmer_digits

PAGE = "lexique.html"

TEXT = {
    "title": ("Lexique", "សទ្ទានុក្រម"),
    "kicker": ("Tous les mots vus", "ពាក្យទាំងអស់ដែលបានរៀន"),
    "intro": ("Les mots et expressions des leçons passées, du plus récent au plus ancien. Cherchez dans les trois langues.",
              "ពាក្យ និងឃ្លាពីមេរៀនដែលបានរៀនរួច ពីថ្មីទៅចាស់។ អាចស្វែងរកជាបីភាសា។"),
    "search": ("Rechercher un mot", "ស្វែងរកពាក្យ"),
    "placeholder": ("Mot en français, anglais ou khmer…", "ពាក្យជាភាសាបារាំង អង់គ្លេស ឬខ្មែរ…"),
    "all": ("Tout", "ទាំងអស់"),
    "words": ("Mots", "ពាក្យ"),
    "expressions": ("Expressions", "ឃ្លា"),
    "none": ("Aucun mot ne correspond à cette recherche.", "រកមិនឃើញពាក្យទេ។"),
    "lesson": ("Leçon", "មេរៀនទី"),
}
LISTEN = {"fr": "Écouter en français", "en": "Listen in English", "km": "ស្តាប់ជាភាសាខ្មែរ"}


def _bi(key: str, tag: str = "span") -> str:
    from .render import bilingual
    return bilingual(*TEXT[key], tag=tag)


def render(renderer) -> str:
    from .render import ICONS, esc, ui
    icon_play = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.2v13.6L19.5 12z"/></svg>'
    rows = renderer.conn.execute(
        "SELECT lesson_number, lesson_date, content_json, html_path FROM lessons "
        "WHERE status = 'complete' ORDER BY lesson_number DESC").fetchall()
    items, seen = [], set()
    for row in rows:
        content = json.loads(row["content_json"])
        href = row["html_path"] or f'lessons/lesson-{row["lesson_number"]:03d}.html'
        for kind, anchor in (("vocabulary", "mot"), ("expressions", "expression")):
            for i, entry in enumerate(content.get(kind, []), 1):
                key = (entry.get("fr", ""), entry.get("km", ""))
                if key in seen or not all(entry.get(lang) for lang in LANGS):
                    continue
                seen.add(key)
                cells = []
                for lang in LANGS:
                    ref = renderer.library.lookup(speech_text(entry[lang]), lang)
                    button = (f'<button type="button" class="play" data-src="{esc(ref.path)}" '
                              f'aria-label="{esc(LISTEN[lang])} : {esc(entry[lang])}">{icon_play}</button>') if ref.ready else ""
                    translit = (f'<span class="translit">{esc(entry["tr"])}</span>'
                                if lang == "km" and entry.get("tr") else "")
                    cells.append(f'<div class="lex-cell lang-{lang}"><span class="lex-text"><span lang="{lang}">'
                                  f'{esc(entry[lang])}</span>{translit}</span>{button}</div>')
                search = fold(" ".join([entry["fr"], entry["en"], entry["km"], entry.get("tr", "")]))
                n = row["lesson_number"]
                items.append(
                    f'<li class="lex-item" data-date="{esc(row["lesson_date"])}" data-kind="{"w" if kind == "vocabulary" else "e"}" '
                    f'data-search="{esc(search)}">{"".join(cells)}'
                    f'<a class="lex-lesson" data-nav href="{esc(href)}#{anchor}-{i}" title="{TEXT["lesson"][0]} {n}">'
                    f'<span class="ui-fr">{TEXT["lesson"][0]} {n}</span><span class="ui-km" lang="km">{TEXT["lesson"][1]} {to_khmer_digits(n)}</span></a></li>')
    chips = "".join(
        f'<button type="button" class="chip{" is-active" if value == "" else ""}" data-kind="{value}">{_bi(key)}</button>'
        for value, key in (("", "all"), ("w", "words"), ("e", "expressions")))
    content = (
        f'<article class="lexicon-page">'
        f'<nav class="lesson-nav" aria-label="Navigation"><a class="nav-link nav-home" data-nav href="./index.html">'
        f'{ICONS["home"]}{ui("home")}</a></nav>'
        f'<header class="lesson-head"><p class="kicker">{_bi("kicker")}</p>'
        f'<h1 class="tri-title"><span class="t-fr" lang="fr">{TEXT["title"][0]}</span>'
        f'<span class="t-km" lang="km">{TEXT["title"][1]}</span></h1>'
        f'<p class="alpha-subtitle">{_bi("intro")}</p></header>'
        f'<section class="finder"><label class="search" for="lex-search"><span class="search-label">{_bi("search")}</span>'
        f'<span class="search-field">{ICONS["search"]}<input type="search" id="lex-search" autocomplete="off" spellcheck="false" '
        f'placeholder="{esc(TEXT["placeholder"][0])}" data-placeholder-fr="{esc(TEXT["placeholder"][0])}" '
        f'data-placeholder-km="{esc(TEXT["placeholder"][1])}"></span></label>'
        f'<div class="filters js-only" role="group" id="lex-filters">{chips}</div></section>'
        f'<p class="result-count" id="lex-count" aria-live="polite"></p>'
        f'<ul class="lex-list" id="lexicon">{"".join(items)}</ul>'
        f'<p class="empty" id="lex-none" hidden>{_bi("none")}</p>'
        f'</article>')
    page = renderer._page(root=".", title=f'{TEXT["title"][0]} — {renderer.config.get("site.title", "FR-KH Learning")}',
                          description="Tous les mots et expressions des leçons, en français, anglais et khmer, avec audio.",
                          body_class="page-lexicon", content=content)
    target = renderer.paths.index.parent / PAGE
    wavutil.atomic_write(target, page.encode("utf-8"))
    return renderer.paths.rel(target)
