"""Page « Traduire » : traducteur entre les sept langues du site, à l'écrit et à l'oral.

Entrée : texte tapé, ou dictée au micro (reconnaissance vocale du navigateur).
Sortie : texte traduit, translittération (khmer, russe, chinois) et lecture à voix haute.

Contrairement au reste du site, cette page a besoin d'Internet : la traduction passe par
le service gratuit de Google Traduction (sans clé), avec MyMemory en secours ; la voix
utilise celle de Google Traduction, ou à défaut une voix installée dans l'appareil.
Le code est dans ``js/translate.js``. Aucun historique n'est conservé.
"""

from __future__ import annotations

import json

from .audio import wavutil
from .langs import LANG_META

PAGE = "traduction.html"

# Libellés : (français, anglais, khmer).
TEXT = {
    "title": ("Traduire", "Translate", "បកប្រែ"),
    "intro": ("Tapez ou dites une phrase : elle est traduite, écrite et lue à voix haute.",
              "Type or say a sentence: it is translated, written out and read aloud.",
              "វាយ ឬនិយាយឃ្លាមួយ៖ វានឹងត្រូវបកប្រែ សរសេរ និងអានឮៗ។"),
    "online": ("Cette page a besoin d'une connexion Internet.",
               "This page needs an Internet connection.",
               "ទំព័រនេះត្រូវការអ៊ីនធឺណិត។"),
    "from": ("De", "From", "ពី"),
    "to": ("Vers", "To", "ទៅ"),
    "swap": ("Inverser les langues", "Swap languages", "ប្តូរភាសា"),
    "source": ("Texte à traduire", "Text to translate", "អត្ថបទដែលត្រូវបកប្រែ"),
    "mic": ("Parler", "Speak", "និយាយ"),
    "clear": ("Effacer", "Clear", "លុប"),
    "go": ("Traduire", "Translate", "បកប្រែ"),
    "result": ("Traduction", "Translation", "ការបកប្រែ"),
    "speak": ("Écouter", "Listen", "ស្តាប់"),
    "copy": ("Copier", "Copy", "ចម្លង"),
    "nojs": ("Cette page a besoin de JavaScript.", "This page needs JavaScript.", "ទំព័រនេះត្រូវការ JavaScript។"),
    "credit": ("Traduction automatique : Google Traduction (ou MyMemory). Elle peut contenir des erreurs.",
               "Machine translation: Google Translate (or MyMemory). It may contain mistakes.",
               "ការបកប្រែដោយម៉ាស៊ីន៖ Google Translate (ឬ MyMemory)។ អាចមានកំហុស។"),
}
PLACEHOLDER = ("Tapez ici, ou touchez « Parler »…", "Type here, or tap “Speak”…", "វាយនៅទីនេះ ឬចុច «និយាយ»…")

ICON_MIC = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" fill="none" '
            'stroke="currentColor" stroke-width="2"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>')
ICON_SPEAKER = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="none" '
                'stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" '
                'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>')
ICON_SWAP = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7h12m0 0-3.5-3.5M19 7l-3.5 3.5M17 17H5m0 0 3.5-3.5M5 17l3.5 3.5" '
             'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
ICON_WIFI = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 9.5a12.5 12.5 0 0 1 17 0M6.5 13a8 8 0 0 1 11 0M9.5 16.3a3.8 3.8 0 0 1 5 0" '
             'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="19.3" r="1.3" fill="currentColor"/></svg>')
ICON_COPY = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2.5" fill="none" '
             'stroke="currentColor" stroke-width="2"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" '
             'fill="none" stroke="currentColor" stroke-width="2"/></svg>')


def _bi(key: str) -> str:
    from .render import multi
    return multi(TEXT[key])


def render(renderer) -> str:
    from .render import esc, page_head
    langs = list(renderer.config.content_langs())
    options = "".join(
        f'<option value="{lang}">{esc(LANG_META[lang]["tag"])} · {esc(LANG_META[lang]["native"])}</option>' for lang in langs)
    meta = {lang: {"locale": LANG_META[lang]["locale"], "native": LANG_META[lang]["native"],
                   "names": LANG_META[lang]["names"]} for lang in langs}
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    online = f'<p class="tr-online">{ICON_WIFI}{_bi("online")}</p>'
    placeholders = " ".join(f'data-placeholder-{lang}="{esc(text)}"' for lang, text in zip(("fr", "en", "km"), PLACEHOLDER))
    content = (
        f'<article class="translate-page">'
        f'{page_head(TEXT["title"], TEXT["intro"], online)}'
        f'<noscript><p class="empty">{_bi("nojs")}</p></noscript>'
        f'<div class="tr-app js-only" id="tr-app">'
        f'<div class="tr-langs">'
        f'<label class="tr-lang"><span class="tr-lang-label">{_bi("from")}</span>'
        f'<select id="tr-from">{options}</select></label>'
        f'<button type="button" class="tr-swap" id="tr-swap" title="{esc(TEXT["swap"][0])}" aria-label="{esc(TEXT["swap"][0])}">'
        f'{ICON_SWAP}</button>'
        f'<label class="tr-lang"><span class="tr-lang-label">{_bi("to")}</span>'
        f'<select id="tr-to">{options}</select></label></div>'
        f'<div class="tr-panes">'
        f'<section class="tr-pane tr-in" id="tr-in" aria-label="{esc(TEXT["source"][0])}">'
        f'<textarea id="tr-text" rows="4" maxlength="2000" spellcheck="true" '
        f'placeholder="{esc(PLACEHOLDER[0])}" {placeholders}></textarea>'
        f'<p class="translit tr-translit" id="tr-src-translit" hidden></p>'
        f'<div class="tr-actions">'
        f'<button type="button" class="tr-btn tr-mic" id="tr-mic" aria-pressed="false">{ICON_MIC}{_bi("mic")}</button>'
        f'<button type="button" class="tr-btn tr-ghost" id="tr-clear">{_bi("clear")}</button>'
        f'<button type="button" class="tr-btn tr-go" id="tr-go">{_bi("go")}</button></div></section>'
        f'<section class="tr-pane tr-out" id="tr-out" aria-label="{esc(TEXT["result"][0])}">'
        f'<p class="tr-pane-label">{_bi("result")}</p>'
        f'<p class="tr-result" id="tr-result" aria-live="polite"></p>'
        f'<p class="translit tr-translit" id="tr-result-translit" hidden></p>'
        f'<div class="tr-actions">'
        f'<button type="button" class="tr-btn tr-speak" id="tr-speak" disabled>{ICON_SPEAKER}{_bi("speak")}</button>'
        f'<button type="button" class="tr-btn tr-ghost" id="tr-copy" disabled>{ICON_COPY}{_bi("copy")}</button></div></section>'
        f'</div>'
        f'<p class="tr-status" id="tr-status" role="status" aria-live="polite" hidden></p>'
        f'<p class="tr-credit">{_bi("credit")}</p>'
        f'</div>'
        f'<script type="application/json" id="tr-data">{payload}</script>'
        f'<script src="./js/translate.js?v={renderer._asset_version()}" defer></script>'
        f'</article>')
    page = renderer._page(root=".", title=f'{TEXT["title"][0]} — {renderer.config.get("site.title", "FR-KH Learning")}',
                          description="Traducteur écrit et vocal entre le français, l'anglais, le khmer, l'espagnol, "
                                      "l'italien, le russe et le chinois.",
                          body_class="page-translate", content=content)
    target = renderer.paths.index.parent / PAGE
    wavutil.atomic_write(target, page.encode("utf-8"))
    return renderer.paths.rel(target)
