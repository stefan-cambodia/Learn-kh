"""Interface en ligne de commande : python3 manage.py <commande>."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import __version__, admin, db, srs
from .audio import AudioLibrary
from .audio.providers import TTSError, provider_names
from .config import ConfigError, load_config, setup_logging
from .curriculum import Curriculum
from .generator import GenerationError, LessonService, audio_items
from .lock import AlreadyRunning, ProcessLock
from .quality import summarize
from .render import RenderError
from .langs import CONTENT_LANGS
from .textutil import LANGS, format_date, speech_text

EXIT_OK, EXIT_ERROR, EXIT_BUSY = 0, 1, 2


class App:
    """Contexte partagé par toutes les commandes."""

    def __init__(self, root: str | None = None, quiet: bool = False):
        self.config = load_config(root, create=True)
        self.config.paths.ensure()
        self.log = setup_logging(self.config, quiet=quiet)
        self.conn = db.connect(self.config.paths.database)
        self.library = AudioLibrary(self.config, self.conn, self.log)
        self._service: LessonService | None = None

    @property
    def service(self) -> LessonService:
        if self._service is None:
            self._service = LessonService(self.config, self.conn, self.log, self.library)
        return self._service

    def lock(self) -> ProcessLock:
        return ProcessLock(self.config.paths.lock)

    def close(self) -> None:
        self.conn.close()


def _size(octets: int) -> str:
    return f"{octets / 1048576:.1f} Mo" if octets >= 1048576 else f"{octets / 1024:.0f} Ko"


def _date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"date invalide : {value!r} (format attendu : AAAA-MM-JJ)") from None


def _print_result(result) -> None:
    labels = {"created": "Nouvelle leçon créée", "resumed": "Leçon reprise après interruption",
              "refreshed": "Leçon actualisée", "exists": "La leçon existe déjà"}
    print(f"{labels[result.status]} : n° {result.lesson_number} du {format_date(result.lesson_date)} — « {result.title} »")
    if result.status != "exists":
        print(f"  Durée estimée   : ≈ {max(1, round(result.estimated_seconds / 60))} min")
        print(f"  Audio           : {result.audio_ready} prêt(s), {result.audio_missing} en attente")
        print(f"  Appels TTS      : {result.tts_calls}   |   réutilisations du cache : {result.cache_hits}")
    if result.html_path:
        print(f"  Page            : {result.html_path}")
    for message in result.messages:
        print(f"  Note            : {message}")


# --- Commandes ------------------------------------------------------------------------

def cmd_init(app: App, args) -> int:
    paths = app.config.paths
    print(f"Projet initialisé dans {paths.root}")
    print(f"  Configuration : {paths.rel(paths.config)}")
    print(f"  Base SQLite   : {paths.rel(paths.database)}")
    if not paths.env.is_file():
        print("  Clés API      : copiez .env.example vers .env puis renseignez vos clés")
    units = Curriculum(paths.content, app.log).load()
    print(f"  Programme     : {len(units.units)} unité(s) prête(s)")
    app.service.renderer.render_index()
    print(f"  Site          : {paths.rel(paths.index)}")
    return EXIT_OK


def cmd_generate(app: App, args) -> int:
    with app.lock():
        result = app.service.generate(args.date, force=args.force, with_audio=not args.no_audio)
    _print_result(result)
    return EXIT_OK


def cmd_daily(app: App, args) -> int:
    """Tâche planifiée : sauvegarde, reprise des travaux inachevés, puis leçon du jour."""
    config = app.config
    now = config.now()
    if not args.now and now.time().replace(tzinfo=None) < config.schedule_time():
        app.log.info("Il est %s (%s) : la leçon du jour sera générée à partir de %s.",
                     now.strftime("%H:%M"), config.get("schedule.timezone"), config.get("schedule.time"))
        return EXIT_OK
    today = now.date()
    try:
        lock = app.lock().acquire()
    except AlreadyRunning:
        app.log.info("Une génération est déjà en cours : rien à faire pour cette fois.")
        return EXIT_OK
    try:
        stamp = today.strftime("%Y%m%d")
        if not list(config.paths.backups.glob(f"learning-{stamp}-*.db")):
            target = db.backup_database(app.conn, config.paths.backups, int(config.get("backup.keep", 14)),
                                        stamp=f"{stamp}-{now.strftime('%H%M%S')}")
            app.log.info("Sauvegarde de la base : %s", config.paths.rel(target))

        # Reprise des leçons interrompues (coupure de courant, arrêt de la machine…)
        for row in app.conn.execute(
                "SELECT lesson_date FROM lessons WHERE status != 'complete' AND lesson_date != ? ORDER BY lesson_date",
                (today.isoformat(),)).fetchall():
            _print_result(app.service.generate(row["lesson_date"]))

        existing = app.conn.execute("SELECT status FROM lessons WHERE lesson_date = ?", (today.isoformat(),)).fetchone()
        if existing is None or existing["status"] != "complete":
            _print_result(app.service.generate(today))

        # L'accueil dépend de la date (leçons générées à l'avance) : une régénération par jour suffit.
        if db.get_meta(app.conn, "index_rendered_for", "") != today.isoformat():
            app.service.renderer.render_index()
            db.set_meta(app.conn, "index_rendered_for", today.isoformat())

        # Nouvelle tentative pour les audios en attente, au plus une fois par heure.
        waiting = app.conn.execute("SELECT COUNT(*) FROM lessons WHERE audio_missing > 0").fetchone()[0]
        last = db.get_meta(app.conn, "last_audio_retry", "")
        due = not last or (dt.datetime.fromisoformat(last) + dt.timedelta(minutes=55)) <= now
        if waiting and due and not app.library.run_calls:
            db.set_meta(app.conn, "last_audio_retry", now.isoformat())
            totals = app.service.repair_audio(scope="incomplete")
            if totals["generated"]:
                app.log.info("Audios récupérés : %d généré(s), %d encore en attente.", totals["generated"], totals["missing"])
    finally:
        lock.release()
    return EXIT_OK


def cmd_render(app: App, args) -> int:
    with app.lock():
        if args.all or not args.numbers:
            app.service.sync_languages()
            count = app.service.renderer.render_all()
            print(f"{count} page(s) de leçon et l'index ont été régénérés.")
        else:
            for number in args.numbers:
                print("Page régénérée :", app.service.renderer.render_lesson(number))
            app.service.renderer.render_index()
            app.service.renderer.export_data()
    return EXIT_OK


def cmd_audio(app: App, args) -> int:
    library = app.library
    if args.action == "verify":
        report = library.verify(deep=args.deep)
        print(f"Fichiers valides     : {report['ready']} ({_size(report['bytes'])}, {report['seconds'] / 60:.1f} min)")
        waiting = [m for m in report["missing"] if m["reason"] != "fichier supprimé"]
        deleted = [m for m in report["missing"] if m["reason"] == "fichier supprimé"]
        print(f"En attente           : {len(waiting)}")
        print(f"Supprimés du disque  : {len(deleted)}")
        print(f"Corrompus            : {len(report['corrupt'])}")
        print(f"Non référencés       : {len(report['orphans'])}")
        for item in deleted + report["corrupt"]:
            print(f"  ✗ {item['file']} — {item['reason']}")
        if args.fix and (deleted or report["corrupt"] or waiting):
            with app.lock():
                totals = app.service.repair_audio(scope="all")
            print(f"Réparation : {totals['generated']} fichier(s) régénéré(s), {totals['missing']} encore en attente.")
            return EXIT_OK if not totals["missing"] else EXIT_ERROR
        return EXIT_ERROR if (deleted or report["corrupt"]) else EXIT_OK

    if args.action == "missing":
        report = library.verify()
        items = report["missing"] + report["corrupt"]
        if not items:
            print("Aucun fichier audio manquant ou corrompu.")
            return EXIT_OK
        for item in items:
            print(f"[{item['locale']}] {item['text'][:60]:<60}  {item['reason']}")
        print(f"{len(items)} fichier(s) à générer : « python3 manage.py audio repair »")
        return EXIT_OK

    if args.action == "convert":
        fmt = args.format or app.config.audio_format()
        with app.lock():
            def progress(i, total):
                if i % 200 == 0:
                    print(f"  … {i} / {total}", flush=True)
            report = library.convert(fmt, progress=progress)
            app.service.sync_languages()
            app.service.renderer.render_all()
        print(f"Fichiers convertis en {fmt.upper()} : {report['converted']} "
              f"({_size(report['bytes_before'])} → {_size(report['bytes_after'])}), déjà au format : {report['skipped']}")
        for item in report["failed"]:
            print(f"  ✗ {item['file']} — {item['reason']}")
        if fmt != app.config.audio_format():
            print(f"Pensez à indiquer « \"format\": \"{fmt}\" » dans la rubrique « audio » de config/config.json.")
        return EXIT_ERROR if report["failed"] else EXIT_OK

    if args.action == "repair":
        if args.no_limits:
            app.config.data["tts"]["limits"] = {}
        with app.lock():
            totals = app.service.repair_audio(scope="all", lessons=args.lesson or None)
        print(f"Leçons contrôlées : {totals['lessons']}   |   fichiers endommagés détectés : {totals['damaged']}")
        print(f"Audios générés    : {totals['generated']}   |   prêts : {totals['ready']}   |   en attente : {totals['missing']}")
        print(f"Appels TTS        : {library.run_calls}   |   réutilisations du cache : {library.run_hits}")
        for name, reason in library._down.items():
            if name != "__budget__":
                print(f"  ! {reason}")
        return EXIT_OK

    if args.action == "regen":
        rows = library.find(text=args.text, lang=args.lang, file=args.file, text_hash=args.hash)
        targets = [(r["text"], r["language"]) for r in rows]
        if not targets and args.text and args.lang:
            targets = [(speech_text(args.text), args.lang)]
        if not targets:
            print("Aucun audio ne correspond. Précisez --text et --lang, --file ou --hash.")
            return EXIT_ERROR
        failures = 0
        with app.lock():
            for text, lang in targets:
                ref = library.ensure(text, lang, force=True)
                if ref.ready:
                    print(f"Régénéré : {ref.path}")
                else:
                    failures += 1
                    print(f"Échec ({lang}) « {text[:50]} » : {ref.reason} — l'ancien fichier, s'il existe, est conservé.")
            app.service.renderer.render_all()
        return EXIT_ERROR if failures else EXIT_OK

    if args.action == "prune":
        report = library.verify()
        needed = set()
        include = bool(app.config.get("audio.include_examples", True))
        for row in app.conn.execute("SELECT content_json FROM lessons WHERE content_json != '{}'"):
            for lang, text in audio_items(json.loads(row["content_json"]), include):
                needed.add(library.lookup(text, lang).text_hash)
        from . import alphabet
        for lang, text in alphabet.audio_items(alphabet.load(app.config)):
            needed.add(library.lookup(text, lang).text_hash)
        unused = [dict(r) for r in app.conn.execute("SELECT text_hash, file_path, file_size FROM audio_files")
                  if r["text_hash"] not in needed]
        total = sum(u["file_size"] for u in unused)
        print(f"{len(unused)} audio(s) inutilisé(s) ({_size(total)}), {len(report['orphans'])} fichier(s) non référencé(s).")
        if args.dry_run:
            for item in unused:
                print("  -", item["file_path"])
            for orphan in report["orphans"]:
                print("  -", orphan)
            return EXIT_OK
        with app.lock():
            for item in unused:
                (app.config.paths.root / item["file_path"]).unlink(missing_ok=True)
                app.conn.execute("DELETE FROM audio_files WHERE text_hash = ?", (item["text_hash"],))
            for orphan in report["orphans"]:
                (app.config.paths.root / orphan).unlink(missing_ok=True)
            app.service.renderer.export_data()
        print("Nettoyage terminé.")
        return EXIT_OK
    return EXIT_ERROR


def cmd_stats(app: App, args) -> int:
    conn, config = app.conn, app.config
    stats = app.library.statistics()
    lessons = conn.execute("SELECT COUNT(*) AS n, MAX(lesson_date) AS last FROM lessons WHERE status = 'complete'").fetchone()
    words = conn.execute("SELECT kind, COUNT(*) AS n FROM vocabulary GROUP BY kind").fetchall()
    limits = config.get("tts.limits", {})
    if args.json:
        print(json.dumps({"lessons": lessons["n"], "last_lesson": lessons["last"], "audio": stats,
                          "vocabulary": {r["kind"]: r["n"] for r in words},
                          "progress": srs.summary(conn, config.today().isoformat())}, ensure_ascii=False, indent=2))
        return EXIT_OK
    print("LEÇONS")
    print(f"  Leçons publiées             : {lessons['n']}" + (f" (dernière : {format_date(lessons['last'])})" if lessons["last"] else ""))
    for row in words:
        print(f"  {'Mots appris' if row['kind'] == 'word' else 'Expressions apprises':<27} : {row['n']}")
    print("SYNTHÈSE VOCALE")
    print(f"  Appels TTS effectués        : {stats['tts_calls']} (réussis : {stats['tts_success']}, échoués : {stats['tts_failed']})")
    print(f"  Caractères envoyés          : {stats['tts_chars']}")
    print(f"  Audios réutilisés (cache)   : {stats['cache_hits']}")
    print(f"  Aujourd'hui                 : {stats['today']['calls']} appel(s), {stats['today']['chars']} / {limits.get('max_chars_per_day', '∞')} caractères")
    print(f"  Ce mois-ci                  : {stats['month']['calls']} appel(s), {stats['month']['chars']} / {limits.get('max_chars_per_month', '∞')} caractères")
    print("BIBLIOTHÈQUE AUDIO")
    print(f"  Fichiers WAV                : {stats['files']} ({_size(stats['bytes'])}, {stats['seconds'] / 60:.1f} min d'écoute)")
    print(f"  En attente de génération    : {stats['missing']}")
    for row in stats["per_locale"]:
        print(f"    {row['locale']:<6} {row['provider']:<8} {row['voice']:<26} {row['files']:>5} fichier(s)  {_size(row['bytes']):>9}")
    print("PROGRESSION")
    for item in srs.summary(conn, config.today().isoformat()):
        name = config.profiles().get(item["learner"], {}).get("label", item["learner"])
        print(f"  {item['learner']} ({name}) : {item['total']} éléments suivis, {item['mastered']} acquis, "
              f"{item['due']} à réviser, maîtrise moyenne {item['average']:.0%}")
    return EXIT_OK


def cmd_export(app: App, args) -> int:
    app.service.renderer.export_data()
    target = admin.export_all(app.config, app.conn, Path(args.out) if args.out else None, include_audio=not args.no_audio)
    print(f"Export créé : {target} ({_size(target.stat().st_size)})")
    return EXIT_OK


def cmd_check(app: App, args) -> int:
    report = admin.check_project(app.config, app.conn, app.library, deep=args.deep)
    print(report.render())
    print(f"\nBilan : {report.errors} erreur(s), {report.warnings} point(s) d'attention.")
    return EXIT_ERROR if report.errors else EXIT_OK


def cmd_backup(app: App, args) -> int:
    target = db.backup_database(app.conn, app.config.paths.backups, int(app.config.get("backup.keep", 14)))
    print(f"Sauvegarde créée : {app.config.paths.rel(target)} ({_size(target.stat().st_size)})")
    return EXIT_OK


def cmd_schedule(app: App, args) -> int:
    config = app.config
    if args.action == "show":
        state = admin.schedule_state(config)
        print(f"Heure de génération : {config.get('schedule.time')} ({config.get('schedule.timezone')}) — il est "
              f"{config.now().strftime('%H:%M')} dans ce fuseau.")
        print("État : " + (state["detail"] if state["installed"] else "non installée"))
        print("\nLigne cron (Linux) :\n  " + admin.cron_line(config))
        print("\nTâche planifiée (Windows) :\n  " + " ".join(f'"{a}"' if " " in a else a for a in admin.windows_command(config)))
        print("\nLa tâche s'exécute toutes les quelques minutes et ne fait rien tant que l'heure prévue n'est pas "
              "passée ou que la leçon du jour existe déjà : une machine éteinte à 07h00 rattrape donc à l'allumage.")
        return EXIT_OK
    if args.action == "install":
        print(admin.schedule_install(config, args.method))
        return EXIT_OK
    print(admin.schedule_remove(config))
    return EXIT_OK


def cmd_content(app: App, args) -> int:
    curriculum = Curriculum(app.config.paths.content, app.log).load()
    used = {r["unit_id"]: r["lesson_number"] for r in app.conn.execute(
        "SELECT unit_id, lesson_number FROM lessons WHERE unit_id IS NOT NULL")}
    if args.action == "refresh":
        with app.lock():
            stats = admin.refresh_lessons(app.config, app.conn, curriculum)
            print(f"{stats['lessons']} leçon(s) et {stats['vocabulary']} mot(s) mis à jour d'après content/units.")
            totals = app.service.repair_audio(scope="all")
            count = app.service.renderer.render_all()
        print(f"Audio : {totals['generated']} nouveau(x), {totals['missing']} en attente. {count} page(s) régénérée(s).")
        return EXIT_OK
    if args.action == "list":
        for unit in curriculum.units:
            state = f"leçon {used[unit['id']]}" if unit["id"] in used else "à venir"
            print(f"{unit['id']}  {unit['level']:<14} {unit['title']['fr']:<34} {state}")
        print(f"{len(curriculum.units)} unité(s), dont {len([u for u in curriculum.units if u['id'] not in used])} à venir.")
        return EXIT_OK
    shown = [i for i in curriculum.issues if args.all or i.level != "info"]
    for issue in shown:
        print(issue)
    summary = summarize(curriculum.issues)
    print(f"{len(curriculum.units)} unité(s) valide(s), {len(curriculum.rejected)} écartée(s) — {summary['errors']} erreur(s), "
          f"{summary['warnings']} avertissement(s), {summary['uncertain']} traduction(s) à vérifier"
          + ("" if args.all or not summary["uncertain"] else " (détail avec --all)"))
    return EXIT_ERROR if summary["errors"] else EXIT_OK


def cmd_correct(app: App, args) -> int:
    with app.lock():
        result = admin.correct_text(app.config, app.conn, args.find, args.replace, args.lang, args.lesson, args.dry_run)
        prefix = "[simulation] " if args.dry_run else ""
        print(f"{prefix}{result['occurrences']} occurrence(s) : leçons {result['lessons'] or '—'}, "
              f"{result['vocabulary']} entrée(s) de vocabulaire, unités {result['units'] or '—'}")
        if args.dry_run or not result["occurrences"]:
            return EXIT_OK
        if result["lessons"]:
            totals = app.service.repair_audio(scope="all", lessons=result["lessons"])
            print(f"Pages régénérées ; audio : {totals['generated']} nouveau(x), {totals['missing']} en attente.")
    return EXIT_OK


def cmd_lesson(app: App, args) -> int:
    conn, paths = app.conn, app.config.paths
    if args.action == "list":
        for row in conn.execute("SELECT * FROM lessons ORDER BY lesson_number"):
            print(f"{row['lesson_number']:>4}  {row['lesson_date']}  {row['level']:<14} {row['status']:<9} "
                  f"{row['title_fr']}" + (f"  ({row['audio_missing']} audio(s) en attente)" if row["audio_missing"] else ""))
        return EXIT_OK
    if args.action == "export":
        row = conn.execute("SELECT content_json FROM lessons WHERE lesson_number = ?", (args.number,)).fetchone()
        if row is None:
            print(f"Leçon n° {args.number} introuvable.")
            return EXIT_ERROR
        target = Path(args.file) if args.file else paths.exports / f"lesson-{args.number:03d}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(json.loads(row["content_json"]), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Contenu exporté : {target}\nModifiez ce fichier puis lancez : python3 manage.py lesson import {target}")
        return EXIT_OK
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    with app.lock():
        number = admin.import_lesson(conn, payload)
        totals = app.service.repair_audio(scope="all", lessons=[number])
    print(f"Leçon n° {number} mise à jour ; audio : {totals['generated']} nouveau(x), {totals['missing']} en attente.")
    return EXIT_OK


def cmd_progress(app: App, args) -> int:
    conn, config = app.conn, app.config
    day = config.today().isoformat()
    if args.action == "show":
        for item in srs.summary(conn, day):
            name = config.profiles().get(item["learner"], {}).get("label", item["learner"])
            print(f"{item['learner']} ({name}) : {item['total']} éléments, {item['mastered']} acquis, "
                  f"{item['due']} à réviser, maîtrise moyenne {item['average']:.0%}")
        rows = conn.execute(
            "SELECT v.french_text, v.khmer_text, p.learner, p.review_count, p.next_review, p.mastery_score "
            "FROM learner_progress p JOIN vocabulary v ON v.id = p.vocabulary_id "
            "WHERE p.next_review IS NOT NULL ORDER BY p.next_review, v.id LIMIT ?", (args.limit,)).fetchall()
        if rows:
            print("\nProchaines révisions :")
        for row in rows:
            print(f"  {row['next_review']}  {row['learner']}  {row['french_text']:<28} {row['khmer_text']:<20} "
                  f"({row['review_count']} révision(s), maîtrise {row['mastery_score']:.0%})")
        return EXIT_OK
    words = admin.set_progress(config, conn, args.action, args.learner, args.word)
    verb = "sera revu dès demain" if args.action == "forget" else "est marqué comme acquis"
    print(f"« {words[0]} » ({words[1]}) {verb} pour {args.learner}.")
    return EXIT_OK


def cmd_tts(app: App, args) -> int:
    library, config = app.library, app.config
    if args.action == "status":
        print(f"Fournisseurs disponibles : {', '.join(provider_names())}")
        for lang in config.content_langs():
            spec = library.spec_for(lang)
            try:
                ready, reason = library.provider(spec.provider).configured()
            except TTSError as exc:
                ready, reason = False, str(exc)
            state = "prêt" if ready else f"NON CONFIGURÉ — {reason}"
            print(f"  {spec.locale:<6} {spec.provider:<8} {spec.voice:<26} {spec.sample_rate} Hz, vitesse {spec.speaking_rate:g}  →  {state}")
        stats, limits = library.statistics(), config.get("tts.limits", {})
        print(f"Consommation : {stats['today']['chars']} / {limits.get('max_chars_per_day')} caractères aujourd'hui, "
              f"{stats['month']['chars']} / {limits.get('max_chars_per_month')} ce mois-ci")
        return EXIT_OK
    if args.action == "voices":
        spec = library.spec_for(args.lang)
        name = args.provider or spec.provider
        voices = library.provider(name).list_voices(spec.locale)
        if not voices:
            print(f"Le fournisseur « {name} » ne propose aucune voix pour {spec.locale}.")
            return EXIT_ERROR
        for voice in sorted(voices, key=lambda v: v["name"] or ""):
            mark = "  ← voix configurée" if voice["name"] == spec.voice and name == spec.provider else ""
            print(f"  {voice['name']:<34} {voice['gender']:<8}{mark}")
        print(f"{len(voices)} voix {spec.locale} chez « {name} ».")
        return EXIT_OK
    samples = {"fr": "Bonjour, bienvenue.", "en": "Hello, welcome.", "km": "សួស្តី សូមស្វាគមន៍។",
               "es": "Hola, bienvenido.", "it": "Ciao, benvenuto.", "ru": "Здравствуйте, добро пожаловать.",
               "zh": "你好，欢迎。"}
    failures = 0
    for lang in ([args.lang] if args.lang else config.content_langs()):
        ref = library.ensure(samples[lang], lang)
        if ref.ready:
            print(f"  {library.spec_for(lang).locale} : OK — {ref.path} ({ref.duration:.1f} s, {ref.source})")
        else:
            failures += 1
            print(f"  {library.spec_for(lang).locale} : ÉCHEC — {ref.reason}")
    return EXIT_ERROR if failures else EXIT_OK


def cmd_alphabet(app: App, args) -> int:
    from . import alphabet
    data = alphabet.load(app.config)
    if not data:
        print(f"Données introuvables : {app.config.paths.rel(alphabet.data_path(app.config.paths))}")
        return EXIT_ERROR
    with app.lock():
        if not args.no_audio:
            totals = alphabet.ensure_audio(app.service.library, data)
            print(f"Audio : {totals['ready']} prêt(s), {totals['missing']} manquant(s)")
        page = app.service.renderer.render_alphabet()
        app.service.renderer.render_index()
    print(f"Page écrite : {page}")
    return EXIT_OK


def cmd_serve(app: App, args) -> int:
    if args.no_accounts:
        admin.serve(app.config, args.host, args.port)
    else:
        from . import webapp
        webapp.serve(app.config, args.host, args.port, app.log)
    return EXIT_OK


def _account_password(args, login: str) -> tuple[str, bool]:
    """Mot de passe d'un compte : tiré au hasard (--generate), lu sur l'entrée standard
    (--password-stdin) ou demandé deux fois au clavier, sans l'afficher."""
    from .accounts import generate_password
    if args.generate:
        return generate_password(), True
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\r\n"), False
    import getpass
    first = getpass.getpass(f"Mot de passe pour {login} : ")
    if first != getpass.getpass("Encore une fois : "):
        raise ValueError("les deux mots de passe ne sont pas identiques")
    return first, False


def _users_journal(app: App, store, args) -> int:
    """« users journal » : les derniers événements des comptes, du plus récent au plus ancien."""
    from .accounts import CLI_ACTOR, EVENT_GROUPS, EVENT_NAMES
    user_id = None
    if args.login:
        user = store.get_by_login(args.login)
        if user is None:
            print(f"Compte inconnu : {args.login}", file=sys.stderr)
            return EXIT_ERROR
        user_id = user.id
    events = store.list_events(limit=args.limit, user_id=user_id, kinds=EVENT_GROUPS.get(args.type))
    if not events:
        print("Journal vide.")
    for event in events:
        when = dt.datetime.fromtimestamp(event.at, app.config.tzinfo()).strftime("%Y-%m-%d %H:%M")
        what = EVENT_NAMES.get(event.kind, event.kind) + (f" ({event.detail})" if event.detail else "")
        by = "" if not event.actor else "  par la ligne de commande" if event.actor == CLI_ACTOR else f"  par {event.actor}"
        print(f"{when}  {what:<42} {event.login or '(identifiant inconnu)':<22} {event.ip}{by}".rstrip())
    return EXIT_OK


def _users_show(app: App, store, user) -> None:
    """« users show » : le compte, sa progression, ses sessions ouvertes et ses derniers événements."""
    from .account_pages import device_name
    from .accounts import EVENT_NAMES

    def moment(seconds) -> str:
        return dt.datetime.fromtimestamp(seconds, app.config.tzinfo()).strftime("%Y-%m-%d %H:%M")

    detail = store.progress_detail(user.id)
    print(f"Identifiant        : {user.login}")
    print(f"Nom affiché        : {user.name}")
    print(f"Rôle               : {user.role} — {'actif' if user.active else 'désactivé'}"
          + (" — mot de passe provisoire" if user.must_change_password else ""))
    print(f"Langue             : {user.profile}")
    print(f"Créé le            : {user.created_at}")
    print(f"Dernière connexion : {user.last_login_at or 'jamais'}")
    print(f"Progression        : {len(detail['lessons'])} leçon(s) terminée(s), {len(detail['days'])} jour(s) d'activité, "
          f"série en cours {detail['streak']} (meilleure : {detail['best_streak']}), {detail['cards']} carte(s) révisée(s)")
    for lang, item in sorted(detail["langs"].items()):
        print(f"  {lang} : {item['cards']} carte(s), {item['known']} connue(s), {item['due']} à revoir")
    sessions = store.list_sessions(user.id)
    print(f"Sessions ouvertes  : {len(sessions)}")
    for item in sessions:
        print(f"  {device_name(item.user_agent) or 'appareil inconnu':<24} {item.ip:<16} dernière activité : {moment(item.last_seen_at)}")
    events = store.list_events(limit=5, user_id=user.id)
    if events:
        print("Derniers événements :")
        for event in events:
            print(f"  {moment(event.at)}  {EVENT_NAMES.get(event.kind, event.kind)}" + (f" ({event.detail})" if event.detail else ""))


def cmd_users(app: App, args) -> int:
    from .accounts import CLI_ACTOR, AccountError, Accounts
    store = Accounts(app.config)
    try:
        if args.action == "list":
            users = store.list_users()
            if not users:
                print("Aucun compte. Créez l'administrateur : python3 manage.py users add <identifiant> --role admin")
            for user in users:
                done = store.progress_summary(user.id)["lessons"]
                print(f"{user.login:<20} {user.role:<6} {'actif' if user.active else 'désactivé':<10} {user.profile}  "
                      f"{done:>3} leçon(s)  dernière connexion : {user.last_login_at or 'jamais':<20}  {user.name}")
            return EXIT_OK
        if args.action == "journal":
            return _users_journal(app, store, args)
        if args.action == "add":
            password, generated = _account_password(args, args.login)
            user = store.create_user(args.login, args.name or args.login, password, role=args.role, profile=args.profile,
                                     must_change_password=generated)
            store.record_event("user_created", user=user, actor=CLI_ACTOR)
            print(f"Compte créé : {user.login} ({user.role})")
            if generated:
                print(f"Mot de passe provisoire : {password}  (à changer à la première connexion)")
            return EXIT_OK
        user = store.get_by_login(args.login)
        if user is None:
            print(f"Compte inconnu : {args.login}", file=sys.stderr)
            return EXIT_ERROR
        if args.action == "show":
            _users_show(app, store, user)
        elif args.action == "password":
            password, generated = _account_password(args, user.login)
            store.set_password(user.id, password, must_change_password=generated)
            store.record_event("password_reset", user=user, actor=CLI_ACTOR)
            print(f"Mot de passe de {user.login} changé ; ses sessions sont fermées.")
            if generated:
                print(f"Mot de passe provisoire : {password}  (à changer à la prochaine connexion)")
        elif args.action == "role":
            if store.update_user(user.id, role=args.role).role != user.role:
                store.record_event("role_changed", user=user, actor=CLI_ACTOR, detail=args.role)
            print(f"{user.login} : rôle « {args.role} ».")
        elif args.action in ("enable", "disable"):
            if store.update_user(user.id, active=args.action == "enable").active != user.active:
                store.record_event("user_enabled" if args.action == "enable" else "user_disabled", user=user, actor=CLI_ACTOR)
            print(f"{user.login} : compte {'activé' if args.action == 'enable' else 'désactivé'}.")
        elif args.action == "logout":
            closed = store.revoke_user_sessions(user.id)
            if closed:
                store.record_event("sessions_closed", user=user, actor=CLI_ACTOR, detail=closed)
            print(f"{user.login} : {closed} session(s) fermée(s).")
        elif args.action == "import-progress":
            count = store.import_shared_progress(user.id)
            store.record_event("progress_imported", user=user, actor=CLI_ACTOR)
            print(f"{user.login} : {count} rubrique(s) de l'ancienne progression partagée reprise(s).")
        elif args.action == "delete":
            if not args.yes:
                print(f"Ajoutez --yes pour supprimer définitivement {user.login} et sa progression.", file=sys.stderr)
                return EXIT_ERROR
            store.delete_user(user.id)
            store.record_event("user_deleted", user=user, actor=CLI_ACTOR)
            print(f"Compte supprimé : {user.login}")
        return EXIT_OK
    except AccountError as exc:
        print(f"Refusé : {exc}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        store.close()


# --- Analyse des arguments ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage.py", description="FR-KH Learning — leçons quotidiennes français / anglais / khmer.")
    parser.add_argument("--version", action="version", version=f"FR-KH Learning {__version__}")
    parser.add_argument("--root", help="dossier du projet (par défaut : celui de manage.py)")
    sub = parser.add_subparsers(dest="command", metavar="commande", required=True)

    sub.add_parser("init", help="préparer le projet (dossiers, base, configuration, index)").set_defaults(func=cmd_init)

    p = sub.add_parser("generate", help="générer la leçon du jour, ou celle d'une date donnée")
    p.add_argument("--date", type=_date, help="date de la leçon (AAAA-MM-JJ) ; aujourd'hui par défaut")
    p.add_argument("--force", action="store_true", help="repasser sur une leçon existante (audio et page), sans la dupliquer")
    p.add_argument("--no-audio", action="store_true", help="ne pas appeler la synthèse vocale pour cette exécution")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("daily", help="tâche planifiée : sauvegarde, reprises, leçon du jour")
    p.add_argument("--now", action="store_true", help="ne pas attendre l'heure configurée")
    p.add_argument("--quiet", action="store_true", help="n'afficher que les avertissements et les erreurs")
    p.set_defaults(func=cmd_daily)

    p = sub.add_parser("render", help="régénérer des pages HTML (et l'index)")
    p.add_argument("numbers", nargs="*", type=int, metavar="N", help="numéros de leçon")
    p.add_argument("--all", action="store_true", help="toutes les leçons")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("audio", help="contrôler et réparer la bibliothèque audio")
    a = p.add_subparsers(dest="action", metavar="action", required=True)
    v = a.add_parser("verify", help="vérifier tous les fichiers audio")
    v.add_argument("--deep", action="store_true", help="comparer aussi l'empreinte du contenu")
    v.add_argument("--fix", action="store_true", help="régénérer ce qui manque ou est corrompu")
    a.add_parser("missing", help="lister les audios manquants ou corrompus")
    r = a.add_parser("repair", help="régénérer uniquement les audios manquants ou corrompus")
    r.add_argument("--lesson", type=int, action="append", metavar="N", help="limiter à une leçon (répétable)")
    r.add_argument("--no-limits", action="store_true", help="ignorer les plafonds de consommation (rattrapage en masse)")
    c = a.add_parser("convert", help="convertir la bibliothèque audio en MP3 ou en WAV, sans appel au fournisseur")
    c.add_argument("--format", choices=("mp3", "wav"), help="format visé (par défaut : audio.format de la configuration)")
    g = a.add_parser("regen", help="régénérer un audio précis")
    g.add_argument("--text", help="texte prononcé")
    g.add_argument("--lang", choices=CONTENT_LANGS, help="langue du texte")
    g.add_argument("--file", help="chemin ou nom du fichier audio")
    g.add_argument("--hash", help="début de l'empreinte SHA-256")
    pr = a.add_parser("prune", help="supprimer les audios qui ne servent plus à aucune leçon")
    pr.add_argument("--dry-run", action="store_true", help="montrer sans supprimer")
    p.set_defaults(func=cmd_audio)

    p = sub.add_parser("stats", help="statistiques : appels TTS, cache, volume audio, progression")
    p.add_argument("--json", action="store_true", help="sortie JSON")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("export", help="exporter toutes les leçons (archive ZIP autonome)")
    p.add_argument("--out", help="dossier de destination (par défaut : exports/)")
    p.add_argument("--no-audio", action="store_true", help="ne pas inclure les fichiers WAV")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("check", help="vérification générale du projet")
    p.add_argument("--deep", action="store_true", help="contrôle approfondi des fichiers audio")
    p.set_defaults(func=cmd_check)

    sub.add_parser("backup", help="sauvegarder la base SQLite").set_defaults(func=cmd_backup)

    p = sub.add_parser("schedule", help="planification quotidienne (cron, systemd ou Windows)")
    p.add_argument("action", choices=("show", "install", "remove"))
    p.add_argument("--method", choices=("auto", "cron", "systemd", "windows"), default="auto")
    p.set_defaults(func=cmd_schedule)

    p = sub.add_parser("content", help="programme pédagogique (unités de content/units)")
    p.add_argument("action", choices=("check", "list", "refresh"),
                   help="check : vérifier ; list : lister ; refresh : reporter les unités modifiées dans les leçons déjà générées")
    p.add_argument("--all", action="store_true", help="afficher aussi les traductions signalées à vérifier")
    p.set_defaults(func=cmd_content)

    p = sub.add_parser("correct", help="corriger un texte dans les leçons, le vocabulaire et les unités")
    p.add_argument("--find", required=True, help="texte fautif")
    p.add_argument("--replace", required=True, help="texte corrigé")
    p.add_argument("--lang", choices=CONTENT_LANGS + ("tr", "zh_tr", "ru_tr"),
                   help="limiter à une langue (tr = translittération du khmer, zh_tr = pinyin)")
    p.add_argument("--lesson", type=int, help="limiter à une leçon")
    p.add_argument("--dry-run", action="store_true", help="montrer sans modifier")
    p.set_defaults(func=cmd_correct)

    p = sub.add_parser("lesson", help="lister, exporter ou réimporter le contenu d'une leçon")
    a = p.add_subparsers(dest="action", metavar="action", required=True)
    a.add_parser("list", help="lister les leçons")
    e = a.add_parser("export", help="exporter le contenu d'une leçon pour le corriger à la main")
    e.add_argument("number", type=int)
    e.add_argument("file", nargs="?")
    i = a.add_parser("import", help="réimporter un contenu corrigé")
    i.add_argument("file")
    p.set_defaults(func=cmd_lesson)

    p = sub.add_parser("progress", help="suivi de la répétition espacée")
    a = p.add_subparsers(dest="action", metavar="action", required=True)
    s = a.add_parser("show", help="résumé et prochaines révisions")
    s.add_argument("--limit", type=int, default=20)
    for name, text in (("forget", "remettre un mot à zéro (à revoir dès demain)"), ("master", "marquer un mot comme acquis")):
        f = a.add_parser(name, help=text)
        f.add_argument("--learner", choices=("fr", "en", "km", "all", "A", "B", "both"), required=True,
                       help="profil : fr, en, km, ou all pour les trois (A et B : anciens noms de km et fr)")
        f.add_argument("--word", required=True, help="mot en français, anglais ou khmer")
    p.set_defaults(func=cmd_progress)

    p = sub.add_parser("tts", help="synthèse vocale : état, voix disponibles, essai")
    a = p.add_subparsers(dest="action", metavar="action", required=True)
    a.add_parser("status", help="fournisseurs, voix configurées et consommation")
    v = a.add_parser("voices", help="lister les voix proposées pour une langue")
    v.add_argument("--lang", choices=CONTENT_LANGS, required=True)
    v.add_argument("--provider", help="fournisseur à interroger (par défaut : celui de la langue)")
    t = a.add_parser("test", help="synthétiser une phrase d'essai")
    t.add_argument("--lang", choices=CONTENT_LANGS)
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("alphabet", help="module Alphabets : générer les audios et la page alphabet.html")
    p.add_argument("--no-audio", action="store_true", help="ne pas appeler la synthèse vocale")
    p.set_defaults(func=cmd_alphabet)

    p = sub.add_parser("serve", help="serveur web avec comptes utilisateurs (connexion, progression par compte)")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 pour ouvrir au réseau local")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-accounts", action="store_true", help="ancien serveur sans comptes : site ouvert, progression partagée")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("users", help="comptes du serveur : lister, créer, mot de passe, rôle, suppression, journal")
    a = p.add_subparsers(dest="action", metavar="action", required=True)
    a.add_parser("list", help="lister les comptes")
    a.add_parser("show", help="détail d'un compte : progression, sessions ouvertes, derniers événements").add_argument("login")
    u = a.add_parser("journal", help="journal des comptes : connexions, échecs, opérations")
    u.add_argument("login", nargs="?", help="limiter à un compte")
    u.add_argument("--type", choices=("logins", "failures", "accounts"), help="connexions, échecs ou opérations sur les comptes")
    u.add_argument("--limit", type=int, default=50, metavar="N", help="nombre de lignes (50 par défaut)")

    def password_options(parser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--generate", action="store_true", help="tirer un mot de passe provisoire, à changer à la connexion")
        group.add_argument("--password-stdin", action="store_true", help="lire le mot de passe sur l'entrée standard")

    u = a.add_parser("add", help="créer un compte")
    u.add_argument("login", help="identifiant (lettres minuscules, chiffres, point, tiret)")
    u.add_argument("--name", help="nom affiché (par défaut : l'identifiant)")
    u.add_argument("--role", choices=("user", "admin"), default="user")
    u.add_argument("--profile", choices=LANGS, help="langue de l'apprenant (par défaut : celle du site)")
    password_options(u)
    u = a.add_parser("password", help="changer le mot de passe d'un compte (ses sessions sont fermées)")
    u.add_argument("login")
    password_options(u)
    u = a.add_parser("role", help="changer le rôle d'un compte")
    u.add_argument("login")
    u.add_argument("role", choices=("user", "admin"))
    for name, text in (("enable", "réactiver un compte"), ("disable", "désactiver un compte (connexion impossible)"),
                       ("logout", "fermer toutes les sessions d'un compte"),
                       ("import-progress", "reprendre dans un compte la progression partagée de l'ancien serveur")):
        a.add_parser(name, help=text).add_argument("login")
    u = a.add_parser("delete", help="supprimer un compte et sa progression")
    u.add_argument("login")
    u.add_argument("--yes", action="store_true", help="confirmer la suppression")
    p.set_defaults(func=cmd_users)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")   # consoles Windows
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        app = App(args.root, quiet=getattr(args, "quiet", False))
    except ConfigError as exc:
        print(f"Erreur de configuration : {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        return args.func(app, args)
    except AlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_BUSY
    except (GenerationError, RenderError, ConfigError, TTSError, ValueError, RuntimeError, OSError) as exc:
        app.log.error("%s", exc)
        return EXIT_ERROR
    except KeyboardInterrupt:
        app.log.warning("Interrompu : la prochaine exécution reprendra là où celle-ci s'est arrêtée.")
        return 130
    except Exception:
        # Erreur imprévue : la trace complète part dans logs/errors.log, utile pour une tâche planifiée.
        app.log.exception("Erreur inattendue pendant la commande « %s »", args.command)
        return EXIT_ERROR
    finally:
        app.close()
