"""Génération du site statique : pages de leçon, index et exports JSON.

Les gabarits se trouvent dans ``templates/`` (syntaxe ``$variable`` de
``string.Template``) ; ils peuvent être modifiés sans toucher au code.
Le site produit n'utilise aucune ressource externe : il fonctionne hors ligne.
"""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path
from string import Template

from .audio import wavutil
from .config import LEGACY_PROFILES, LEVEL_LABELS
from .textutil import LANGS, fold, format_date, speech_text, to_khmer_digits

# Libellés d'interface : (français, anglais, khmer). Le profil choisi dans la page décide lequel s'affiche.
UI = {
    "tagline": ("Une leçon de moins de dix minutes, chaque jour, en trois langues.",
                "A lesson of less than ten minutes, every day, in three languages.",
                "មេរៀនខ្លីមិនដល់ ១០ នាទី រៀងរាល់ថ្ងៃ ជាបីភាសា។"),
    "lesson": ("Leçon", "Lesson", "មេរៀន"),
    "home": ("Toutes les leçons", "All lessons", "មេរៀនទាំងអស់"),
    "previous": ("Leçon précédente", "Previous lesson", "មេរៀនមុន"),
    "next": ("Leçon suivante", "Next lesson", "មេរៀនបន្ទាប់"),
    "vocabulary": ("Vocabulaire", "Vocabulary", "វាក្យសព្ទ"),
    "expressions": ("Expressions pratiques", "Useful expressions", "ឃ្លាមានប្រយោជន៍"),
    "sentences": ("Phrases de la vie quotidienne", "Everyday sentences", "ប្រយោគក្នុងជីវិតប្រចាំថ្ងៃ"),
    "dialogue": ("Petit dialogue", "Short dialogue", "ការសន្ទនាខ្លី"),
    "review": ("Révision", "Review", "ការរំលឹកមេរៀន"),
    "minutes": ("min", "min", "នាទី"),
    "new": ("nouveau", "new", "ថ្មី"),
    "seen": ("déjà vu", "seen before", "ធ្លាប់រៀន"),
    "uncertain": ("à vérifier", "to be checked", "ត្រូវពិនិត្យ"),
    "uncertain_title": ("Traduction à faire vérifier par un locuteur natif",
                        "Translation to be checked by a native speaker",
                        "ការបកប្រែនេះគួរឱ្យម្ចាស់ភាសាពិនិត្យឡើងវិញ"),
    "example": ("Exemple", "Example", "ឧទាហរណ៍"),
    "tip": ("Le conseil du jour", "Tip of the day", "គន្លឹះថ្ងៃនេះ"),
    "audio_missing": ("Audio pas encore disponible", "Audio not available yet", "មិនទាន់មានសំឡេង"),
    "download": ("Télécharger le fichier WAV", "Download the WAV file", "ទាញយកឯកសារ WAV"),
    "listen_all": ("Écouter tout le dialogue", "Listen to the whole dialogue", "ស្តាប់ការសន្ទនាទាំងមូល"),
    "review_words": ("Mots à revoir", "Words to review", "ពាក្យត្រូវរំលឹក"),
    "review_hint": ("Revoir un mot à intervalles espacés aide à le retenir.",
                    "Reviewing a word at spaced intervals helps you remember it.",
                    "ការរំលឹកឡើងវិញជាប្រចាំជួយឱ្យចាំបានយូរ។"),
    "quick_questions": ("Trois petites questions", "Three quick questions", "សំណួរខ្លីបី"),
    "translation": ("Exercice de traduction", "Translation exercise", "លំហាត់បកប្រែ"),
    "comprehension": ("Question de compréhension", "Comprehension question", "សំណួរយល់ន័យ"),
    "comprehension_hint": ("Relisez le dialogue, puis répondez.", "Read the dialogue again, then answer.",
                           "សូមអានការសន្ទនាម្តងទៀត រួចឆ្លើយ។"),
    "show_answer": ("Voir la réponse", "Show the answer", "មើលចម្លើយ"),
    "done": ("J'ai terminé cette leçon", "I have finished this lesson", "ខ្ញុំរៀនមេរៀននេះចប់ហើយ"),
    "done_mark": ("Terminée", "Done", "រៀនចប់"),
    "search": ("Rechercher une leçon", "Search for a lesson", "ស្វែងរកមេរៀន"),
    "no_result": ("Aucune leçon ne correspond à cette recherche.", "No lesson matches this search.",
                  "រកមិនឃើញមេរៀនទេ។"),
    "all_levels": ("Tous les niveaux", "All levels", "គ្រប់កម្រិត"),
    "last_lesson": ("Dernière leçon", "Last lesson", "មេរៀនចុងក្រោយ"),
    "total_lessons": ("Leçons disponibles", "Lessons available", "ចំនួនមេរៀនសរុប"),
    "current_level": ("Niveau actuel", "Current level", "កម្រិតបច្ចុប្បន្ន"),
    "words_learned": ("Mots et expressions appris", "Words and expressions learned", "ពាក្យ និងឃ្លាដែលបានរៀន"),
    "no_lessons": ("Aucune leçon pour l'instant. Lancez « python3 manage.py generate » pour créer la première.",
                   "No lessons yet. Run “python3 manage.py generate” to create the first one.",
                   "មិនទាន់មានមេរៀននៅឡើយទេ។"),
    "slow": ("Lecture lente", "Slow playback", "អានយឺត"),
    "review_lesson": ("Leçon de révision", "Review lesson", "មេរៀនរំលឹក"),
    "audio_pending": ("audio en attente", "audio pending", "សំឡេងមិនទាន់រួចរាល់"),
    "open": ("Ouvrir la leçon", "Open the lesson", "បើកមេរៀន"),
    "profile": ("Langue de l'apprenant", "Learner's language", "ភាសារបស់អ្នករៀន"),
    "skip": ("Aller au contenu", "Skip to content", "ទៅកាន់មាតិកា"),
    "audio_notice": ("Certains audios ne sont pas encore disponibles : ils seront ajoutés automatiquement.",
                     "Some audio files are not available yet: they will be added automatically.",
                     "សំឡេងខ្លះមិនទាន់មាននៅឡើយទេ។ វានឹងត្រូវបន្ថែមដោយស្វ័យប្រវត្តិ។"),
    "today_lesson": ("Leçon du jour", "Today's lesson", "មេរៀនថ្ងៃនេះ"),
    "latest_lesson": ("Dernière leçon disponible", "Latest lesson available", "មេរៀនចុងក្រោយ"),
    "start": ("Commencer", "Start", "ចាប់ផ្តើម"),
    "today_badge": ("Aujourd'hui", "Today", "ថ្ងៃនេះ"),
    "future_badge": ("À venir", "Upcoming", "នាពេលខាងមុខ"),
    "future_notice": ("Cette leçon est prévue pour plus tard. Vous pouvez la regarder, mais elle n'est pas encore au programme.",
                      "This lesson is planned for later. You can look at it, but it is not on the schedule yet.",
                      "មេរៀននេះសម្រាប់ថ្ងៃខាងមុខ។ អាចមើលបាន ប៉ុន្តែមិនទាន់ដល់ពេលរៀនទេ។"),
    "review_nav": ("Réviser", "Review", "រំលឹក"),
    "home_short": ("Accueil", "Home", "ទំព័រដើម"),
    "size": ("Taille du texte", "Text size", "ទំហំអក្សរ"),
    "due_words": ("à réviser aujourd'hui", "to review today", "ត្រូវរំលឹកថ្ងៃនេះ"),
    "lexicon_nav": ("Lexique", "Glossary", "សទ្ទានុក្រម"),
    "alphabet_nav": ("Alphabets", "Alphabets", "អក្សរ"),
    "all_lessons": ("Toutes les leçons", "All lessons", "មេរៀនទាំងអស់"),
    "sc_review": ("Cartes mémoire et exercice d'écoute", "Flashcards and listening practice", "កាតចងចាំ និងលំហាត់ស្តាប់"),
    "sc_lexicon": ("Tous les mots vus, avec l'audio", "Every word seen so far, with audio",
                   "ពាក្យទាំងអស់ដែលបានរៀន ព្រមទាំងសំឡេង"),
    "sc_alphabet": ("Lettres khmères et latines", "Khmer and Latin letters", "អក្សរខ្មែរ និងអក្សរឡាតាំង"),
    "alphabet_promo": ("Apprendre les alphabets khmer et latin, avec la prononciation",
                       "Learn the Khmer and Latin alphabets, with pronunciation",
                       "រៀនអក្សរខ្មែរ និងអក្សរឡាតាំង ព្រមទាំងការបញ្ចេញសំឡេង"),
    "roleplay": ("Jeu de rôle, je suis :", "Role play, I am:", "លេងតួ ខ្ញុំជា៖"),
    "roleplay_lang": ("en", "in", "ជា"),
    "rp_continue": ("Continuer", "Continue", "បន្ត"),
    "rp_stop": ("Arrêter", "Stop", "ឈប់"),
    "rp_key": ("Espace", "Space", "Space"),
    "quiz": ("Se tester", "Test yourself", "តេស្តខ្លួនឯង"),
    "quiz_hint": ("Mode test : touchez une ligne floutée pour la révéler.",
                  "Test mode: tap a blurred line to reveal it.",
                  "របៀបតេស្ត៖ ចុចលើបន្ទាត់ព្រិលៗ ដើម្បីមើល។"),
    "review_this": ("Réviser les mots de cette leçon", "Review the words of this lesson", "រំលឹកពាក្យក្នុងមេរៀននេះ"),
    "greeting": ("Bonjour !", "Hello!", "សួស្តី!"),
    "footer": ("Site généré automatiquement, consultable hors connexion.",
               "Site generated automatically, available offline.",
               "គេហទំព័រនេះបង្កើតដោយស្វ័យប្រវត្តិ និងប្រើបានដោយគ្មានអ៊ីនធឺណិត។"),
}

POS_LABELS = {
    "nom": ("nom", "noun", "នាម"), "verbe": ("verbe", "verb", "កិរិយាសព្ទ"),
    "adjectif": ("adjectif", "adjective", "គុណនាម"), "adverbe": ("adverbe", "adverb", "កិរិយាវិសេសន៍"),
    "pronom": ("pronom", "pronoun", "សព្វនាម"), "interjection": ("interjection", "interjection", "ឧទានសព្ទ"),
    "nombre": ("nombre", "number", "លេខ"), "preposition": ("préposition", "preposition", "ធ្នាក់"),
    "conjonction": ("conjonction", "conjunction", "ឈ្នាប់"), "particule": ("particule", "particle", "និបាត"),
    "interrogatif": ("mot interrogatif", "question word", "ពាក្យសំណួរ"), "expression": ("expression", "expression", "ឃ្លា"),
}

# Nom de chaque langue, dans chaque langue d'interface.
LANG_NAMES = {
    "fr": {"fr": "français", "en": "French", "km": "ភាសាបារាំង"},
    "en": {"fr": "anglais", "en": "English", "km": "ភាសាអង់គ្លេស"},
    "km": {"fr": "khmer", "en": "Khmer", "km": "ភាសាខ្មែរ"},
}

LANG_INFO = {
    "fr": {"tag": "FR", "listen": "Écouter en français"},
    "en": {"tag": "EN", "listen": "Listen in English"},
    "km": {"tag": "KH", "listen": "ស្តាប់ជាភាសាខ្មែរ"},
}

PART_MINUTES = {"vocabulary": 3, "expressions": 2, "sentences": 2, "dialogue": 2, "review": 1}

ICONS = {
    "download": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v10m0 0-4-4m4 4 4-4M5 19h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "mute": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4zm12.5 0 5 6m0-6-5 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "prev": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "next": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "home": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    "search": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 16l4.5 4.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "house": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10.5 12 4l8 6.5V19a1.5 1.5 0 0 1-1.5 1.5H14v-6h-4v6H5.5A1.5 1.5 0 0 1 4 19z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
    "eye": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
    "book": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5zM5 19.5A1.5 1.5 0 0 0 6.5 21H19" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
    "flame": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.2 1.2-3.6 2.4-4.6.2 1.6 1 2.6 2.1 2.9C11 8.9 11 6 12 3z" fill="currentColor"/></svg>',
    "cards": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="13" height="15" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 3h10.5A2.5 2.5 0 0 1 21 5.5V17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    "clock": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
}


class RenderError(Exception):
    pass


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def multi(texts, tag: str = "span", attrs: str = "") -> str:
    """Texte dans chaque langue d'interface : la feuille de style n'affiche que celui du profil actif.

    ``texts`` : {"fr": …, "en": …, "km": …} ou tuple (fr, en, km). Une langue absente reprend le français.
    """
    if not isinstance(texts, dict):
        texts = dict(zip(LANGS, texts))
    out = []
    for lang in LANGS:
        value = texts.get(lang) or texts.get("fr") or ""
        out.append(f'<{tag} class="ui-{lang}" lang="{lang}"{attrs}>{esc(value)}</{tag}>')
    return "".join(out)


def ui(key: str, tag: str = "span") -> str:
    """Libellé d'interface, dans les trois langues."""
    return multi(UI[key], tag=tag)


def ui_text(key: str, lang: str = "fr") -> str:
    """Libellé brut dans une langue (attributs title, aria-label…)."""
    return UI[key][LANGS.index(lang)]


def num_label(n) -> str:
    """Nombre en chiffres latins (français, anglais) et en chiffres khmers."""
    return multi({"fr": str(n), "en": str(n), "km": to_khmer_digits(n)})


def minutes_label(n: int) -> str:
    return multi({"fr": f"≈ {n} min", "en": f"≈ {n} min", "km": f"≈ {to_khmer_digits(n)} នាទី"})


def date_label(value, weekday: bool = True) -> str:
    return multi({lang: format_date(value, lang, weekday=weekday) for lang in LANGS})


def for_profiles(profiles, all_profiles=LANGS) -> str:
    """Classes qui réservent un élément à certains profils (« not-km » : masqué pour le profil khmer)."""
    return " ".join(f"not-{p}" for p in all_profiles if p not in profiles)


def scoped_notes(note: dict | None, css: str = "note", tag: str = "p") -> str:
    """Une explication par profil : chaque profil lit celle de sa langue.

    Sans version anglaise, le profil anglais lit la version française.
    """
    if not note or not any(note.get(lang) for lang in LANGS):
        return ""
    parts = []
    for lang in LANGS:
        text = note.get(lang)
        if not text:
            continue
        scope = f"for-{lang}"
        if lang == "fr" and not note.get("en"):
            scope = "not-km"
        parts.append(f'<{tag} class="{css} {scope}" lang="{lang}">{esc(text)}</{tag}>')
    return "".join(parts)


class SiteRenderer:
    def __init__(self, config, conn, library, logger: logging.Logger | None = None):
        self.config = config
        self.conn = conn
        self.library = library
        self.paths = config.paths
        self.log = logger or logging.getLogger("frkh.render")
        self._templates: dict[str, Template] = {}
        self._missing = 0

    # --- gabarits -------------------------------------------------------------------
    def _tpl(self, name: str) -> Template:
        if name not in self._templates:
            path = self.paths.templates / f"{name}.html"
            try:
                self._templates[name] = Template(path.read_text(encoding="utf-8"))
            except OSError as exc:
                raise RenderError(f"gabarit introuvable : templates/{name}.html ({exc})") from exc
        return self._templates[name]

    def _fill(self, name: str, /, **values) -> str:
        try:
            return self._tpl(name).substitute(**values)
        except KeyError as exc:
            raise RenderError(f"templates/{name}.html utilise une variable inconnue : {exc}") from exc
        except ValueError as exc:
            raise RenderError(f"templates/{name}.html : syntaxe invalide ({exc}) — écrire $$ pour un « $ » littéral") from exc

    def _page(self, *, root: str, title: str, description: str, body_class: str, content: str) -> str:
        profiles = self.config.profiles()
        buttons = "".join(
            f'<button type="button" data-profile-choice="{key}" lang="{key}" aria-pressed="false" '
            f'title="{esc(LANG_NAMES[key][key].capitalize())}">{esc(spec["label"])}</button>'
            for key, spec in profiles.items())
        profiles_json = json.dumps({key: spec["learns"] for key, spec in profiles.items()}, separators=(",", ":"))
        return self._fill(
            "base", root=root, page_title=esc(title), page_description=esc(description), body_class=body_class,
            default_profile=esc(self.config.default_profile()), profile_buttons=buttons,
            profiles_json=profiles_json.replace("</", "<\\/"),
            site_title=esc(self.config.get("site.title", "FR-KH Learning")),
            ui_profile=esc(UI["profile"][0]), ui_slow=ui("slow"), ui_skip=ui("skip"), ui_footer=ui("footer"),
            ui_home=ui("home"), ui_alphabet=ui("alphabet_nav"), ui_review=ui("review_nav"), ui_lexicon=ui("lexicon_nav"), icon_book=ICONS["book"],
            ui_size_title=esc(UI["size"][0]), app_name=esc(self._app_name()),
            ui_home_short=ui("home_short"), ui_alphabet_short=ui("alphabet_nav"), icon_house=ICONS["house"],
            icon_cards=ICONS["cards"], version=self._asset_version(), root_attr=root, timezone=esc(self.config.get("schedule.timezone", "Asia/Phnom_Penh")),
            content=content)

    def _asset_version(self) -> str:
        """Numéro de version des fichiers CSS et JS : force le navigateur à recharger après une mise à jour."""
        stamp = 0
        for rel in ("css/style.css", "js/app.js", "js/review.js"):
            try:
                stamp = max(stamp, int((self.paths.root / rel).stat().st_mtime))
            except OSError:
                pass
        return str(stamp)

    # --- briques d'affichage -----------------------------------------------------------
    def _audio(self, text: str, lang: str, root: str) -> str:
        ref = self.library.lookup(speech_text(text), lang)
        if not ref.ready:
            self._missing += 1
            return self._fill("partials/audio_missing", lang=lang, icon=ICONS["mute"], label=ui("audio_missing"),
                              reason=esc(UI["audio_missing"][0]))
        src = f"{root}/{ref.path}"
        return self._fill("partials/audio", lang=lang, src=esc(src), filename=esc(Path(ref.path).name),
                          label=esc(f"{LANG_INFO[lang]['listen']} : {text}"),
                          download_title=esc(UI["download"][0]), icon_download=ICONS["download"])

    def _rows(self, entry: dict, root: str, *, audio: bool = True, compact: bool = False) -> str:
        rows = []
        for lang in LANGS:
            text = entry.get(lang)
            if not text:
                continue
            translit = ""
            if lang == "km" and entry.get("tr"):
                translit = f'<p class="translit not-km" lang="km-Latn">{esc(entry["tr"])}</p>'
            rows.append(self._fill("partials/lang_row", lang=lang, tag=LANG_INFO[lang]["tag"], text=esc(text),
                                   translit=translit, audio=self._audio(text, lang, root) if audio else ""))
        return f'<div class="tri{" tri-compact" if compact else ""}">{"".join(rows)}</div>'

    @staticmethod
    def _note(note: dict | None) -> str:
        return scoped_notes(note)

    @staticmethod
    def _badges(entry: dict, show_state: bool = True) -> str:
        badges = []
        pos = entry.get("pos")
        if pos in POS_LABELS:
            badges.append(f'<span class="badge badge-pos">{multi(POS_LABELS[pos])}</span>')
        if show_state and "is_new" in entry:
            key = "new" if entry["is_new"] else "seen"
            badges.append(f'<span class="badge badge-{key}">{ui(key)}</span>')
        if entry.get("uncertain"):
            title = entry.get("uncertain_note") or UI["uncertain_title"][0]
            badges.append(f'<span class="badge badge-uncertain" title="{esc(title)}">{ui("uncertain")}</span>')
        return "".join(badges)

    def _entry(self, entry: dict, root: str, anchor: str, *, with_example: bool = True) -> str:
        example = ""
        if with_example and entry.get("example"):
            example = (f'<div class="example"><p class="example-label">{ui("example")}</p>'
                       f'{self._rows(entry["example"], root, compact=True)}</div>')
        situation = ""
        if entry.get("situation"):
            situation = f'<p class="situation">{multi(entry["situation"])}</p>'
        uncertain = ""
        if entry.get("uncertain") and entry.get("uncertain_note"):
            uncertain = f'<p class="uncertain-note not-km" lang="fr">{esc(entry["uncertain_note"])}</p>'
        return self._fill("partials/entry", anchor=anchor, badges=self._badges(entry), situation=situation,
                          rows=self._rows(entry, root), note=self._note(entry.get("note")) + uncertain,
                          example=example, extra_class=" is-uncertain" if entry.get("uncertain") else "")

    @staticmethod
    def _character_name(name: dict, fallback: str) -> str:
        latin = name.get("latin") or fallback
        return multi({"fr": latin, "en": latin, "km": name.get("km") or latin})

    @staticmethod
    def _level(level: str) -> dict:
        return LEVEL_LABELS.get(level, {"fr": level, "en": level, "km": level})

    def _studied(self, profile: str) -> str:
        """« en khmer et en anglais », « in Khmer and French », « ជាភាសាបារាំង និងភាសាអង់គ្លេស »."""
        names = [LANG_NAMES[lang][profile] for lang in self.config.profiles()[profile]["learns"]]
        if profile == "fr":
            return " et ".join(f"en {n}" for n in names)
        if profile == "en":
            return "in " + " and ".join(names)
        return "ជា" + " និង".join(names)

    def _question_prompt(self, q: dict) -> str:
        texts = {
            "fr": lambda w: f"Comment dit-on « <strong>{w}</strong> » {self._studied('fr')} ?",
            "en": lambda w: f"How do you say “<strong>{w}</strong>” {self._studied('en')}?",
            "km": lambda w: f"តើពាក្យ « <strong>{w}</strong> » {self._studied('km')}ថាដូចម្តេច?",
        }
        return "".join(f'<p class="prompt for-{p}" lang="{p}">{texts[p](esc(q.get(p, "")))}</p>'
                       for p in self.config.profiles())

    def _translate_hint(self) -> str:
        texts = {"fr": f"Traduisez {self._studied('fr')} :", "en": f"Translate {self._studied('en')}:",
                 "km": f"សូមបកប្រែ{self._studied('km')}៖"}
        return multi(texts)

    def _section(self, key: str, number: int, body: str) -> str:
        minutes = PART_MINUTES[key]
        time = minutes_label(minutes)
        return self._fill("partials/section", key=key, number=number, title=ui(key), time=time, body=body)

    def _answer(self, body: str) -> str:
        return f'<details class="answer"><summary>{ui("show_answer")}</summary><div class="answer-body">{body}</div></details>'

    # --- page de leçon -----------------------------------------------------------------------
    def render_lesson(self, number: int, content: dict | None = None) -> str:
        row = self.conn.execute("SELECT * FROM lessons WHERE lesson_number = ?", (number,)).fetchone()
        if row is None:
            raise RenderError(f"leçon n° {number} introuvable")
        content = content or json.loads(row["content_json"])
        root = ".."
        characters = self.config.characters()
        sections = []
        self._missing = 0

        cards = "".join(self._entry(e, root, f"mot-{i}") for i, e in enumerate(content["vocabulary"], 1))
        sections.append(self._section("vocabulary", 1, f'<div class="cards">{cards}</div>'))
        cards = "".join(self._entry(e, root, f"expression-{i}") for i, e in enumerate(content["expressions"], 1))
        sections.append(self._section("expressions", 2, f'<div class="cards">{cards}</div>'))
        cards = "".join(self._entry(e, root, f"phrase-{i}") for i, e in enumerate(content["sentences"], 1))
        sections.append(self._section("sentences", 3, f'<div class="cards cards-wide">{cards}</div>'))

        dialogue = content["dialogue"]
        lines = []
        for i, line in enumerate(dialogue["lines"], 1):
            speaker = line.get("speaker", "A")
            name = characters.get(speaker, {}).get("name", {})
            lines.append(self._fill(
                "partials/dialogue_line", speaker=speaker.lower(), index=i,
                initial=esc((name.get("latin") or speaker)[:1].upper()),
                name=self._character_name(name, speaker),
                rows=self._rows(line, root, compact=True)))
        setting = dialogue.get("setting") or {}
        play_all = "".join(
            f'<button type="button" class="chip chip-{lang}" data-play-all="{lang}">{LANG_INFO[lang]["tag"]}</button>'
            for lang in LANGS)
        roles = "".join(
            f'<button type="button" class="chip chip-role" data-role="{who.lower()}">'
            f'{self._character_name(characters.get(who, {}).get("name", {}), who)}</button>'
            for who in ("A", "B"))
        # Langues du jeu de rôle : celles que le profil étudie.
        rp_langs = "".join(
            f'<button type="button" class="chip chip-{lang} not-{lang}" data-rp-lang="{lang}">{LANG_INFO[lang]["tag"]}</button>'
            for lang in LANGS)
        roleplay = (f'<div class="roleplay js-only" data-roleplay><span>{ui("roleplay")}</span>{roles}'
                    f'<span class="rp-lang-label">{ui("roleplay_lang")}</span>{rp_langs}</div>'
                    f'<div class="roleplay-bar" id="roleplay-bar" hidden role="status"><p class="rp-msg" id="rp-msg"></p>'
                    f'<div class="rp-actions"><button type="button" class="fc-btn" id="rp-continue">{ui("rp_continue")} <kbd>{ui("rp_key")}</kbd></button>'
                    f'<button type="button" class="chip" id="rp-stop">{ui("rp_stop")}</button></div></div>')
        body = (f'<div class="setting">{self._rows(setting, root, audio=False, compact=True)}</div>'
                f'<div class="play-all js-only"><span>{ui("listen_all")}</span>{play_all}</div>'
                f'{roleplay}<ol class="dialogue">{"".join(lines)}</ol>')
        sections.append(self._section("dialogue", 4, body))
        sections.append(self._section("review", 5, self._review(content, root)))

        tip = ""
        if content.get("tip"):
            tip = self._fill("partials/tip", title=ui("tip"), body=self._note(content["tip"]))

        title = "".join(f'<span class="t-{lang}" lang="{lang}">{esc(content["title"][lang])}</span>' for lang in LANGS)
        level = self._level(content["level"])
        minutes = max(1, round(content.get("estimated_seconds", row["estimated_duration"]) / 60))
        meta = [
            f'<li class="meta-date">{date_label(content["date"])}</li>',
            f'<li class="meta-level level-{esc(content["level"])}">{multi(level)}</li>',
            f'<li class="meta-time">{ICONS["clock"]}{minutes_label(minutes)}</li>',
        ]
        if content.get("kind") == "review":
            meta.append(f'<li class="meta-review">{ui("review_lesson")}</li>')
        meta.append(f'<li class="meta-quiz js-only"><button type="button" class="quiz-toggle" id="quiz-toggle" aria-pressed="false" '
                    f'title="{esc(UI["quiz_hint"][0])}">{ICONS["eye"]}{ui("quiz")}</button></li>')
        kicker = multi({"fr": f"Leçon {number}", "en": f"Lesson {number}", "km": f"មេរៀនទី {to_khmer_digits(number)}"})

        notice = ""
        if self._missing:
            notice = f'<p class="notice" role="status">{ICONS["mute"]}<span>{ui("audio_notice")}</span></p>'
        future_notice = (f'<p class="notice notice-future js-only" id="future-notice" hidden>{ICONS["clock"]}'
                         f'<span>{ui("future_notice")}</span></p>')
        review_link = (f'<p class="review-this"><a class="review-this-link" data-nav href="{root}/revision.html#lecon={number}">'
                       f'{ICONS["cards"]}{ui("review_this")}</a></p>')
        body = self._fill("lesson", number=number, date_iso=esc(content["date"]), future_notice=future_notice,
                          review_link=review_link, quiz_hint=ui("quiz_hint"),
                          nav=self._nav(number), nav_bottom=self._nav(number), kicker=kicker,
                          title=title, meta="".join(meta), notice=notice, tip=tip, sections="".join(sections),
                          done=ui("done"), done_mark=ui("done_mark"), icon_check=ICONS["check"])
        page = self._page(root=root, title=f"Leçon {number} — {content['title']['fr']} · {self.config.get('site.title')}",
                          description=f"Leçon {number} : {content['title']['fr']} / {content['title']['en']}",
                          body_class="page-lesson", content=body)
        target = self.paths.lessons / f"lesson-{number:03d}.html"
        wavutil.atomic_write(target, page.encode("utf-8"))
        return self.paths.rel(target)

    def _nav(self, number: int) -> str:
        def exists(n: int) -> bool:
            return bool(self.conn.execute(
                "SELECT 1 FROM lessons WHERE lesson_number = ? AND content_json != '{}'", (n,)).fetchone())

        def link(n: int, key: str, cls: str, icon_first: bool) -> str:
            label, icon = ui(key), ICONS["prev" if icon_first else "next"]
            if not exists(n):
                return f'<span class="nav-link {cls} is-disabled" aria-disabled="true">{icon if icon_first else ""}{label}{"" if icon_first else icon}</span>'
            return (f'<a class="nav-link {cls}" data-nav rel="{"prev" if icon_first else "next"}" href="lesson-{n:03d}.html">'
                    f'{icon if icon_first else ""}{label}{"" if icon_first else icon}</a>')

        home = f'<a class="nav-link nav-home" data-nav href="../index.html">{ICONS["home"]}{ui("home")}</a>'
        return link(number - 1, "previous", "nav-prev", True) + home + link(number + 1, "next", "nav-next", False)

    def _review(self, content: dict, root: str) -> str:
        review = content.get("review", {})
        blocks = []
        words = review.get("words") or []
        if words:
            chips = []
            for word in words:
                due_for = {LEGACY_PROFILES.get(p, p) for p in word.get("due_for") or LANGS}
                scope = for_profiles(due_for)
                scope = f" {scope}" if scope else ""
                days = word.get("days")
                badge = ""
                if days:
                    badge = (f'<span class="badge badge-days">'
                             f'{multi({"fr": f"J+{days}", "en": f"D+{days}", "km": f"{to_khmer_digits(days)} ថ្ងៃ"})}</span>')
                chips.append(f'<li class="recall{scope}">{badge}{self._rows(word, root, compact=True)}</li>')
            blocks.append(f'<div class="block"><h3>{ui("review_words")}</h3><p class="hint">{ui("review_hint")}</p>'
                          f'<ul class="recall-list">{"".join(chips)}</ul></div>')

        questions = review.get("questions") or []
        if questions:
            items = []
            for q in questions:
                prompt = self._question_prompt(q)
                items.append(f'<li>{prompt}{self._answer(self._rows(q, root, compact=True))}</li>')
            blocks.append(f'<div class="block"><h3>{ui("quick_questions")}</h3><ol class="questions">{"".join(items)}</ol></div>')

        translation = review.get("translation")
        if translation:
            prompt = (f'<p class="hint">{self._translate_hint()}</p>'
                      + "".join(f'<p class="prompt prompt-big for-{p}" lang="{p}">{esc(translation.get(p, ""))}</p>'
                                for p in self.config.profiles()))
            blocks.append(f'<div class="block"><h3>{ui("translation")}</h3>{prompt}'
                          f'{self._answer(self._rows(translation, root, compact=True))}</div>')

        comp = review.get("comprehension")
        if comp:
            blocks.append(f'<div class="block"><h3>{ui("comprehension")}</h3><p class="hint">{ui("comprehension_hint")}</p>'
                          f'{self._rows(comp["question"], root, audio=False, compact=True)}'
                          f'{self._answer(self._rows(comp["answer"], root, audio=False, compact=True))}</div>')
        return "".join(blocks)

    def render_neighbours(self, number: int) -> None:
        """Met à jour les liens « précédente / suivante » des leçons voisines."""
        for n in (number - 1, number + 1):
            row = self.conn.execute("SELECT status FROM lessons WHERE lesson_number = ?", (n,)).fetchone()
            if row and row["status"] == "complete":
                self.render_lesson(n)

    def render_all(self) -> int:
        count = 0
        for row in self.conn.execute(
                "SELECT lesson_number FROM lessons WHERE content_json != '{}' ORDER BY lesson_number").fetchall():
            html_path = self.render_lesson(row["lesson_number"])
            self.conn.execute("UPDATE lessons SET html_path = ? WHERE lesson_number = ?", (html_path, row["lesson_number"]))
            count += 1
        self.render_index()
        self.render_alphabet()
        self.export_data()
        return count

    def render_alphabet(self) -> str | None:
        """Page « Alphabets » (alphabet.html) : n'appelle jamais la synthèse vocale."""
        from . import alphabet
        return alphabet.render(self, alphabet.load(self.config))

    # --- index ---------------------------------------------------------------------------------
    def _published(self) -> list:
        return self.conn.execute(
            "SELECT * FROM lessons WHERE status = 'complete' ORDER BY lesson_date DESC, lesson_number DESC").fetchall()

    def render_index(self) -> str:
        rows = self._published()
        cards = []
        for row in rows:
            content = json.loads(row["content_json"])
            level = self._level(row["level"])
            words = content.get("vocabulary", []) + content.get("expressions", [])
            date = row["lesson_date"]
            y, m, d = date.split("-")
            search = " ".join([
                str(row["lesson_number"]), f"#{row['lesson_number']}", f"lecon {row['lesson_number']}",
                f"lesson {row['lesson_number']}", date, f"{d}/{m}/{y}", f"{d}-{m}-{y}", f"{int(d)}/{int(m)}/{y}",
                format_date(date, "fr"), format_date(date, "en"), format_date(date, "km"),
                row["theme"], row["theme"].replace("-", " "), row["title_fr"], row["title_en"], row["title_km"],
                level["fr"], level["en"], level["km"], row["level"],
                " ".join(f"{w['fr']} {w['en']} {w['km']}" for w in words),
            ])
            preview = "".join(
                f'<li><span lang="fr">{esc(w["fr"])}</span><span lang="en">{esc(w["en"])}</span>'
                f'<span lang="km">{esc(w["km"])}</span></li>' for w in content.get("vocabulary", []))
            flags = ""
            if row["kind"] == "review":
                flags += f'<span class="badge badge-review">{ui("review_lesson")}</span>'
            if row["audio_missing"]:
                flags += (f'<span class="badge badge-pending" title="{row["audio_missing"]} audio(s)">'
                          f'{ICONS["mute"]}{ui("audio_pending")}</span>')
            minutes = max(1, round(row["estimated_duration"] / 60))
            title = "".join(f'<span class="t-{lang}" lang="{lang}">{esc(row["title_" + lang])}</span>' for lang in LANGS)
            cards.append(self._fill(
                "partials/lesson_card", number=row["lesson_number"],
                state=" is-future" if row["lesson_date"] > self.config.today().isoformat() else "", href=esc(row["html_path"] or f"lessons/lesson-{row['lesson_number']:03d}.html"),
                search=esc(fold(search)), level=esc(row["level"]), title=title,
                number_label=num_label(row["lesson_number"]),
                date=date_label(date), date_iso=date,
                level_label=multi(level),
                theme=esc(row["theme"].replace("-", " ")),
                minutes=minutes_label(minutes),
                flags=flags, preview=preview, done_mark=ui("done_mark"), icon_check=ICONS["check"], open=esc(UI["open"][0])))

        # Les leçons générées à l'avance ne comptent qu'à partir de leur date.
        today = self.config.today().isoformat()
        past = [r for r in rows if r["lesson_date"] <= today]
        learned_words: set[str] = set()
        for r in past:
            content = json.loads(r["content_json"])
            for w in content.get("vocabulary", []) + content.get("expressions", []):
                learned_words.add(fold(w.get("fr", "")))
        learned = len(learned_words)
        if past:
            last = past[0]
            last_date = date_label(last["lesson_date"], weekday=False)
            level_label = multi(self._level(last["level"]))
        else:
            last_date = level_label = '<span>—</span>'
        stats = "".join(self._fill("partials/stat", label=label, value=value) for label, value in (
            (ui("total_lessons"), num_label(len(past))),
            (ui("current_level"), level_label),
            (ui("words_learned"), num_label(learned)),
        ))
        present = [lvl for lvl in LEVEL_LABELS if any(r["level"] == lvl for r in rows)]
        filters = f'<button type="button" class="chip is-active" data-level="">{ui("all_levels")}</button>' + "".join(
            f'<button type="button" class="chip" data-level="{lvl}">{multi(LEVEL_LABELS[lvl])}</button>'
            for lvl in present)
        body = self._fill(
            "index", site_title=esc(self.config.get("site.title", "FR-KH Learning")), tagline=ui("tagline"),
            stats=stats, search_label=ui("search"), icon_search=ICONS["search"],
            placeholder_fr=esc("Numéro, date, thème ou mot en français, anglais ou khmer…"),
            placeholder_en=esc("Number, date, topic or word in French, English or Khmer…"),
            placeholder_km=esc("លេខ កាលបរិច្ឆេទ ប្រធានបទ ឬពាក្យ…"),
            filters=filters, lessons="".join(cards), no_result=ui("no_result"),
            alphabet_link=(f'<a class="alpha-promo" data-nav href="alphabet.html"><span class="alpha-promo-glyphs" aria-hidden="true">'
                           f'<span lang="km">ក ខ គ</span> A B C</span><span class="alpha-promo-text">'
                           f'{ui("alphabet_promo")}'
                           f'</span></a>'),
            empty=f'<p class="empty">{ui("no_lessons")}</p>' if not rows else "",
            greeting=self._greeting(), shortcuts=self._shortcuts(), all_lessons=ui("all_lessons"),
            card_index=self._card_index(rows), icon_cards=ICONS["cards"], due_words=ui("due_words"),
            today_label=ui("today_lesson"), latest_label=ui("latest_lesson"), start=ui("start"),
            today_badge=ui("today_badge"), future_badge=ui("future_badge"), icon_next=ICONS["next"],
            icon_flame=ICONS["flame"])
        page = self._page(root=".", title=str(self.config.get("site.title", "FR-KH Learning")),
                          description="Leçons quotidiennes de français, d'anglais et de khmer — Daily French, English and Khmer lessons.",
                          body_class="page-index", content=body)
        wavutil.atomic_write(self.paths.index, page.encode("utf-8"))
        self.render_review()
        self.render_lexicon()
        self.render_manifest()
        return self.paths.rel(self.paths.index)

    def render_lexicon(self) -> str:
        """Page « Lexique » (lexique.html) : tous les mots et expressions, avec recherche et audio."""
        from . import lexicon_page
        return lexicon_page.render(self)

    def _app_name(self) -> str:
        """Nom court sous l'icône de l'écran d'accueil du téléphone."""
        return str(self.config.get("site.short_name", "") or "FR-ENG-KH")

    def render_manifest(self) -> str:
        """manifest.webmanifest : nom, icônes et couleurs pour « Ajouter à l'écran d'accueil »."""
        manifest = {
            "name": str(self.config.get("site.title", "FR-KH Learning")),
            "short_name": self._app_name(),
            "description": "Leçons quotidiennes de français, d'anglais et de khmer.",
            "lang": "fr", "start_url": "index.html", "scope": "./", "display": "standalone",
            "background_color": "#f5f2ec", "theme_color": "#1d2230",
            "icons": [
                {"src": "css/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "css/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
        target = self.paths.root / "manifest.webmanifest"
        wavutil.atomic_write(target, json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))
        return self.paths.rel(target)

    def _card_index(self, rows) -> str:
        """Identifiants et dates des cartes de révision : l'accueil compte les mots à réviser."""
        seen, cards = set(), []
        for row in sorted(rows, key=lambda r: r["lesson_number"]):
            content = json.loads(row["content_json"])
            for entry in content.get("vocabulary", []) + content.get("expressions", []):
                key = f'{entry.get("fr", "")}|{entry.get("km", "")}'
                if key not in seen and all(entry.get(lang) for lang in LANGS):
                    seen.add(key)
                    cards.append([key, row["lesson_date"]])
        return json.dumps(cards, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    def _greeting(self) -> str:
        return ui("greeting")

    def _shortcuts(self) -> str:
        tiles = (("revision.html", "review", ICONS["cards"], "review_nav", "sc_review"),
                 ("lexique.html", "lexicon", ICONS["book"], "lexicon_nav", "sc_lexicon"),
                 ("alphabet.html", "alphabet", '<span lang="km">ក</span>', "alphabet_nav", "sc_alphabet"))
        return "".join(
            f'<a class="shortcut shortcut-{key}" data-nav href="{href}"><span class="shortcut-icon" aria-hidden="true">{icon}</span>'
            f'<span class="shortcut-text"><span class="shortcut-title">{ui(title)}</span>'
            f'<span class="shortcut-desc">{ui(desc)}</span></span></a>'
            for href, key, icon, title, desc in tiles)

    def render_review(self) -> str:
        """Page « Réviser » (revision.html) : cartes mémoire du vocabulaire des leçons publiées."""
        from . import review_page
        return review_page.render(self)

    # --- exports JSON -------------------------------------------------------------------------------
    def export_data(self) -> None:
        """data/lessons.json, data/vocabulary.json et data/audio-library.json (aucun secret n'y figure)."""
        lessons = []
        for row in self.conn.execute("SELECT * FROM lessons WHERE status = 'complete' ORDER BY lesson_number"):
            lessons.append({
                "number": row["lesson_number"], "date": row["lesson_date"], "theme": row["theme"], "level": row["level"],
                "kind": row["kind"], "unit_id": row["unit_id"],
                "title": {"fr": row["title_fr"], "en": row["title_en"], "km": row["title_km"]},
                "estimated_duration_seconds": row["estimated_duration"], "html_path": row["html_path"],
                "audio_missing": row["audio_missing"], "created_at": row["created_at"],
                "content": json.loads(row["content_json"]),
            })
        vocabulary = []
        progress: dict[int, dict] = {}
        for p in self.conn.execute("SELECT * FROM learner_progress"):
            progress.setdefault(p["vocabulary_id"], {})[p["learner"]] = {
                "learning_level": p["learning_level"], "review_count": p["review_count"],
                "last_review": p["last_review"], "next_review": p["next_review"], "mastery_score": p["mastery_score"]}
        for row in self.conn.execute("SELECT * FROM vocabulary ORDER BY id"):
            vocabulary.append({
                "id": row["id"], "kind": row["kind"], "french": row["french_text"], "english": row["english_text"],
                "khmer": row["khmer_text"], "transliteration": row["transliteration"], "category": row["category"],
                "explanation_fr": row["explanation_fr"], "explanation_en": row["explanation_en"],
                "explanation_km": row["explanation_km"],
                "uncertain": bool(row["uncertain"]), "unit_id": row["unit_id"], "progress": progress.get(row["id"], {})})
        audio = [{
            "hash": row["text_hash"], "text": row["text"], "language": row["language"], "locale": row["locale"],
            "provider": row["provider"], "voice": row["voice"], "speaking_rate": row["speaking_rate"],
            "sample_rate": row["sample_rate"], "format": row["format"], "file": row["file_path"],
            "size": row["file_size"], "duration": row["duration"], "status": row["status"],
            "created_at": row["created_at"],
        } for row in self.conn.execute("SELECT * FROM audio_files ORDER BY locale, file_path")]
        for name, payload in (("lessons.json", lessons), ("vocabulary.json", vocabulary), ("audio-library.json", audio)):
            data = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
            wavutil.atomic_write(self.paths.data / name, data)
