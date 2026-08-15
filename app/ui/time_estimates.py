"""Presentational-only time estimates for the study-plan display.

This is purely a display layer: a flat heuristic mapping from task_type to
an estimated number of minutes, used ONLY to render "~50m" style labels.
It never reads or writes the database, never affects completion, gating,
streaks, or any other logic — see app/ui/main_window.py where it's called
strictly for label text.
"""
from __future__ import annotations

import json

PER_TASK_MINUTES = {
    "learn": 7,
    "exercise": 15,
    "leetcode": 25,
    "revision": 15,
    "concept": 10,
    "repair": 20,
}
DEFAULT_SESSION_MINUTES = 60


def estimate_task_minutes(task_row) -> int:
    if task_row["task_type"] in ("oa", "mock"):
        try:
            meta = json.loads(task_row["description"] or "{}")
        except (ValueError, TypeError):
            meta = {}
        return int(meta.get("minutes") or DEFAULT_SESSION_MINUTES)
    return PER_TASK_MINUTES.get(task_row["task_type"], 10)


def estimate_total_minutes(tasks) -> int:
    return sum(estimate_task_minutes(t) for t in tasks)


def format_minutes(total: int) -> str:
    if total <= 0:
        return ""
    if total < 60:
        return f"~{total}m"
    hours, minutes = divmod(total, 60)
    return f"~{hours}h {minutes}m" if minutes else f"~{hours}h"
