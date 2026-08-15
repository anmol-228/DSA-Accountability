"""Practice Readiness dashboard (spec section 51).

Explicitly NOT a "chance of getting hired" score — just a transparent,
locally-computed blend of completion, independence, confidence, and
revision recency per topic.
"""
from __future__ import annotations

import sqlite3

CONFIDENCE_WEIGHT = {"green": 1.0, "yellow": 0.6, "red": 0.3}
ASSISTANCE_WEIGHT = {"independent": 1.0, "small_hint": 0.85, "significant_hint": 0.6, "studied_solution": 0.4}


def topic_readiness(conn: sqlite3.Connection) -> dict[str, float]:
    """Returns {topic: percentage 0-100}. Formula per topic, averaged over
    every reflection recorded for a problem in that topic:

        score = 0.4 * confidence_weight
              + 0.3 * assistance_weight
              + 0.3 * completion_rate_for_topic

    completion_rate_for_topic = required leetcode/revision tasks completed
    / required leetcode/revision tasks total, for that topic's curriculum
    days.
    """
    topics = [r["topic"] for r in conn.execute("SELECT DISTINCT topic FROM curriculum_days")]
    result: dict[str, float] = {}

    for topic in topics:
        day_numbers = [r["day_number"] for r in conn.execute(
            "SELECT day_number FROM curriculum_days WHERE topic = ?", (topic,)
        )]
        if not day_numbers:
            result[topic] = 0.0
            continue
        placeholders = ",".join("?" * len(day_numbers))

        totals = conn.execute(
            f"SELECT COUNT(*) c FROM tasks WHERE day_number IN ({placeholders}) "
            "AND task_type IN ('leetcode', 'revision') AND required = 1",
            day_numbers,
        ).fetchone()["c"]
        done = conn.execute(
            f"SELECT COUNT(*) c FROM tasks WHERE day_number IN ({placeholders}) "
            "AND task_type IN ('leetcode', 'revision') AND required = 1 AND completed = 1",
            day_numbers,
        ).fetchone()["c"]
        completion_rate = (done / totals) if totals else 0.0

        reflections = conn.execute(
            f"SELECT r.confidence, r.assistance_level FROM reflections r "
            f"JOIN tasks t ON r.task_id = t.id WHERE t.day_number IN ({placeholders})",
            day_numbers,
        ).fetchall()
        if reflections:
            avg_conf = sum(CONFIDENCE_WEIGHT.get(r["confidence"], 0.5) for r in reflections) / len(reflections)
            avg_assist = sum(ASSISTANCE_WEIGHT.get(r["assistance_level"], 0.5) for r in reflections) / len(reflections)
        else:
            avg_conf, avg_assist = 0.0, 0.0

        score = 0.4 * avg_conf + 0.3 * avg_assist + 0.3 * completion_rate
        result[topic] = round(score * 100, 1)

    return result
