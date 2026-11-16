"""Base de données SQLite : schéma, connexion, compteurs et sauvegardes."""

from __future__ import annotations

import datetime as dt
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS lessons (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_number      INTEGER NOT NULL UNIQUE,
    lesson_date        TEXT    NOT NULL UNIQUE,
    theme              TEXT    NOT NULL,
    title_fr           TEXT    NOT NULL,
    title_en           TEXT    NOT NULL,
    title_km           TEXT    NOT NULL,
    level              TEXT    NOT NULL,
    kind               TEXT    NOT NULL DEFAULT 'unit',
    unit_id            TEXT,
    estimated_duration INTEGER NOT NULL DEFAULT 0,
    html_path          TEXT,
    content_json       TEXT    NOT NULL,
    status             TEXT    NOT NULL DEFAULT 'draft',
    audio_missing      INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS vocabulary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vocab_key       TEXT    NOT NULL UNIQUE,
    kind            TEXT    NOT NULL DEFAULT 'word',
    french_text     TEXT    NOT NULL,
    english_text    TEXT    NOT NULL,
    khmer_text      TEXT    NOT NULL,
    transliteration TEXT,
    category        TEXT,
    explanation_fr  TEXT,
    explanation_en  TEXT,
    explanation_km  TEXT,
    example_json    TEXT,
    uncertain       INTEGER NOT NULL DEFAULT 0,
    uncertain_note  TEXT,
    unit_id         TEXT,
    first_lesson_id INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_vocabulary (
    lesson_id     INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary(id) ON DELETE CASCADE,
    is_new        INTEGER NOT NULL DEFAULT 1,
    section       TEXT    NOT NULL DEFAULT 'vocabulary',
    position      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (lesson_id, vocabulary_id)
);

CREATE TABLE IF NOT EXISTS audio_files (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    text_hash      TEXT    NOT NULL UNIQUE,
    text           TEXT    NOT NULL,
    language       TEXT    NOT NULL,
    locale         TEXT    NOT NULL,
    provider       TEXT    NOT NULL,
    voice          TEXT    NOT NULL,
    speaking_rate  REAL    NOT NULL DEFAULT 1.0,
    pitch          REAL    NOT NULL DEFAULT 0.0,
    sample_rate    INTEGER NOT NULL,
    engine_version TEXT    NOT NULL DEFAULT '',
    format         TEXT    NOT NULL DEFAULT 'wav/pcm_s16le/mono',
    file_path      TEXT    NOT NULL,
    file_size      INTEGER NOT NULL DEFAULT 0,
    duration       REAL    NOT NULL DEFAULT 0,
    checksum       TEXT,
    status         TEXT    NOT NULL DEFAULT 'missing',
    attempts       INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audio_status ON audio_files(status);
CREATE INDEX IF NOT EXISTS idx_audio_text ON audio_files(language, text);

CREATE TABLE IF NOT EXISTS learner_progress (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    learner        TEXT    NOT NULL,
    vocabulary_id  INTEGER NOT NULL REFERENCES vocabulary(id) ON DELETE CASCADE,
    learning_level INTEGER NOT NULL DEFAULT 0,
    introduced_on  TEXT    NOT NULL,
    last_review    TEXT,
    next_review    TEXT,
    review_count   INTEGER NOT NULL DEFAULT 0,
    mastery_score  REAL    NOT NULL DEFAULT 0,
    UNIQUE (learner, vocabulary_id)
);
CREATE INDEX IF NOT EXISTS idx_progress_due ON learner_progress(next_review);

CREATE TABLE IF NOT EXISTS tts_usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at   TEXT    NOT NULL,
    day         TEXT    NOT NULL,
    provider    TEXT    NOT NULL,
    locale      TEXT    NOT NULL,
    voice       TEXT    NOT NULL,
    characters  INTEGER NOT NULL,
    text_hash   TEXT    NOT NULL,
    success     INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_tts_day ON tts_usage(day);

CREATE TABLE IF NOT EXISTS counters (
    day   TEXT    NOT NULL,
    name  TEXT    NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, name)
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    command     TEXT NOT NULL,
    lesson_date TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    tts_calls   INTEGER NOT NULL DEFAULT 0,
    cache_hits  INTEGER NOT NULL DEFAULT 0,
    errors      INTEGER NOT NULL DEFAULT 0,
    message     TEXT
);
"""


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Mises à niveau des bases créées par une version précédente."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(vocabulary)")}
    if "explanation_en" not in columns:
        conn.execute("ALTER TABLE vocabulary ADD COLUMN explanation_en TEXT")
    # Profils « A » (khmer) et « B » (français) → profils par langue ; le profil anglais
    # reprend le suivi du profil français (même calendrier de révision).
    if conn.execute("SELECT 1 FROM learner_progress WHERE learner IN ('A', 'B') LIMIT 1").fetchone():
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("UPDATE learner_progress SET learner = 'km' WHERE learner = 'A'")
            conn.execute("UPDATE learner_progress SET learner = 'fr' WHERE learner = 'B'")
            conn.execute(
                "INSERT OR IGNORE INTO learner_progress(learner, vocabulary_id, learning_level, introduced_on, last_review, "
                "next_review, review_count, mastery_score) SELECT 'en', vocabulary_id, learning_level, introduced_on, "
                "last_review, next_review, review_count, mastery_score FROM learner_progress WHERE learner = 'fr'")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version' AND CAST(value AS INTEGER) < ?",
                 (str(SCHEMA_VERSION), SCHEMA_VERSION))


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Transaction explicite : tout est validé ensemble, ou rien ne l'est."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def bump(conn: sqlite3.Connection, day: str, name: str, amount: int = 1) -> None:
    conn.execute(
        "INSERT INTO counters(day, name, value) VALUES (?, ?, ?) "
        "ON CONFLICT(day, name) DO UPDATE SET value = value + excluded.value",
        (day, name, amount))


def counter_total(conn: sqlite3.Connection, name: str, day: str | None = None) -> int:
    if day:
        row = conn.execute("SELECT COALESCE(SUM(value), 0) FROM counters WHERE name = ? AND day = ?",
                           (name, day)).fetchone()
    else:
        row = conn.execute("SELECT COALESCE(SUM(value), 0) FROM counters WHERE name = ?", (name,)).fetchone()
    return int(row[0])


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def integrity_ok(conn: sqlite3.Connection) -> tuple[bool, str]:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    return (row[0] == "ok", str(row[0]))


def backup_database(conn: sqlite3.Connection, backups_dir: Path, keep: int = 14,
                    stamp: str | None = None) -> Path:
    """Sauvegarde cohérente (API de sauvegarde SQLite), puis rotation des anciennes copies."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backups_dir / f"learning-{stamp}.db"
    tmp = target.with_suffix(".db.tmp")
    dest = sqlite3.connect(str(tmp))
    try:
        conn.backup(dest)
    finally:
        dest.close()
    tmp.replace(target)
    copies = sorted(backups_dir.glob("learning-*.db"))
    for old in copies[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
    return target
