"""Focus timers for study sessions (spec section 48)."""
from __future__ import annotations

import sqlite3

from app import config

STRUGGLE_GUIDANCE_MINUTES = {"easy": (15, 20), "medium": (25, 35)}


def start_study_session(conn: sqlite3.Connection, task_id: int | None, problem_id: int | None) -> int:
    now = config.now_local().isoformat()
    cur = conn.execute(
        "INSERT INTO study_sessions (task_id, problem_id, started_at) VALUES (?, ?, ?)",
        (task_id, problem_id, now),
    )
    conn.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


def end_study_session(conn: sqlite3.Connection, session_id: int) -> int:
    row = conn.execute("SELECT started_at FROM study_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise ValueError(f"No study session {session_id}")
    now = config.now_local()
    started = config.now_local().fromisoformat(row["started_at"])
    duration = int((now - started).total_seconds())
    conn.execute(
        "UPDATE study_sessions SET ended_at = ?, duration_seconds = ? WHERE id = ?",
        (now.isoformat(), duration, session_id),
    )
    conn.commit()
    return duration


def total_study_minutes(conn: sqlite3.Connection, since_date: str | None = None) -> int:
    if since_date:
        row = conn.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) s FROM study_sessions "
            "WHERE started_at >= ?", (since_date,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COALESCE(SUM(duration_seconds), 0) s FROM study_sessions").fetchone()
    return row["s"] // 60
