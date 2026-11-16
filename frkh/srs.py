"""Répétition espacée : révisions prévues 1, 3, 7, 14 et 30 jours après l'apprentissage.

Chaque mot possède, pour chaque profil d'apprenant (fr, en, km), une fiche dans ``learner_progress``.
Une leçon ne dure que dix minutes : chaque jour, on ne révise donc qu'un petit
nombre de mots, choisis à tour de rôle dans chaque échéance (les mots d'hier,
ceux d'il y a 3 jours, 7 jours…). Seules les révisions réellement présentées
font progresser le score de maîtrise.
"""

from __future__ import annotations

import datetime as dt
import math

LEARNERS = ("fr", "en", "km")


def _d(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _plus(day: str, days: int) -> str:
    return (_d(day) + dt.timedelta(days=days)).isoformat()


def stage_on(introduced_on: str, day: str, intervals: list[int]) -> int:
    """Nombre d'échéances atteintes à la date ``day`` (0 = rien à réviser encore)."""
    elapsed = (_d(day) - _d(introduced_on)).days
    return sum(1 for interval in intervals if elapsed >= interval)


def introduce(conn, vocabulary_id: int, day: str, intervals: list[int], learners=LEARNERS) -> None:
    """Crée la fiche de suivi d'un mot nouveau pour chaque apprenant."""
    for learner in learners:
        conn.execute(
            "INSERT OR IGNORE INTO learner_progress(learner, vocabulary_id, learning_level, introduced_on, "
            "last_review, next_review, review_count, mastery_score) VALUES (?, ?, 0, ?, ?, ?, 0, 0)",
            (learner, vocabulary_id, day, day, _plus(day, intervals[0])))


def due_items(conn, day: str, intervals: list[int], limit: int, exclude: set[int] | None = None) -> list[dict]:
    """Mots à réviser aujourd'hui, pris à tour de rôle dans chaque échéance."""
    exclude = exclude or set()
    rows = conn.execute(
        "SELECT p.*, v.kind FROM learner_progress p JOIN vocabulary v ON v.id = p.vocabulary_id "
        "WHERE p.next_review IS NOT NULL AND p.next_review <= ? ORDER BY p.vocabulary_id", (day,)).fetchall()
    by_vocab: dict[int, dict] = {}
    for row in rows:
        if row["vocabulary_id"] in exclude:
            continue
        stage = max(1, stage_on(row["introduced_on"], day, intervals))
        item = by_vocab.setdefault(row["vocabulary_id"], {
            "vocabulary_id": row["vocabulary_id"], "kind": row["kind"], "stage": stage,
            "review_count": row["review_count"], "due_for": [], "introduced_on": row["introduced_on"]})
        item["due_for"].append(row["learner"])
        item["stage"] = min(item["stage"], stage)
        item["review_count"] = min(item["review_count"], row["review_count"])
    buckets: dict[int, list[dict]] = {}
    for item in by_vocab.values():
        buckets.setdefault(item["stage"], []).append(item)
    for items in buckets.values():
        items.sort(key=lambda i: (i["review_count"], 0 if i["kind"] == "word" else 1, i["vocabulary_id"]))
    selected: list[dict] = []
    while len(selected) < limit and any(buckets.values()):
        for stage in sorted(buckets):
            if buckets[stage] and len(selected) < limit:
                selected.append(buckets[stage].pop(0))
    return selected


def record_review(conn, vocabulary_id: int, day: str, intervals: list[int]) -> None:
    """Enregistre une révision effectivement présentée dans la leçon du jour."""
    rows = conn.execute(
        "SELECT * FROM learner_progress WHERE vocabulary_id = ? AND next_review IS NOT NULL AND next_review <= ?",
        (vocabulary_id, day)).fetchall()
    enough = math.ceil(len(intervals) * 0.6)
    for row in rows:
        stage = max(1, stage_on(row["introduced_on"], day, intervals))
        count = row["review_count"] + 1
        if stage < len(intervals):
            next_review = _plus(row["introduced_on"], intervals[stage])
            if next_review <= day:
                next_review = _plus(day, 1)
        elif count >= enough:
            next_review = None            # cycle terminé : le mot est considéré comme acquis
        else:
            next_review = _plus(day, intervals[-1])
        conn.execute(
            "UPDATE learner_progress SET learning_level = ?, review_count = ?, last_review = ?, next_review = ?, "
            "mastery_score = ? WHERE id = ?",
            (stage, count, day, next_review, round(min(1.0, count / len(intervals)), 2), row["id"]))


def forget(conn, learner: str, vocabulary_id: int, day: str, intervals: list[int]) -> int:
    """Remet un mot à zéro pour un apprenant : il sera revu dès demain."""
    cur = conn.execute(
        "UPDATE learner_progress SET learning_level = 0, review_count = 0, mastery_score = 0, introduced_on = ?, "
        "last_review = ?, next_review = ? WHERE learner = ? AND vocabulary_id = ?",
        (day, day, _plus(day, intervals[0]), learner, vocabulary_id))
    return cur.rowcount


def master(conn, learner: str, vocabulary_id: int, day: str, intervals: list[int]) -> int:
    """Marque un mot comme acquis pour un apprenant : il ne sera plus proposé en révision."""
    cur = conn.execute(
        "UPDATE learner_progress SET learning_level = ?, mastery_score = 1, last_review = ?, next_review = NULL "
        "WHERE learner = ? AND vocabulary_id = ?", (len(intervals), day, learner, vocabulary_id))
    return cur.rowcount


def summary(conn, day: str) -> list[dict]:
    out = []
    for learner in LEARNERS:
        row = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(mastery_score >= 0.8), 0) AS mastered, "
            "COALESCE(SUM(next_review IS NOT NULL AND next_review <= ?), 0) AS due, "
            "COALESCE(AVG(mastery_score), 0) AS average FROM learner_progress WHERE learner = ?",
            (day, learner)).fetchone()
        out.append({"learner": learner, "total": row["total"], "mastered": row["mastered"], "due": row["due"],
                    "average": round(row["average"], 2)})
    return out
