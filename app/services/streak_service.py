"""Honest streak tracking (spec section 42) — activity streak and
on-schedule streak are tracked separately; neither is fabricated."""
from __future__ import annotations

import datetime as _dt
import sqlite3

from app import config


def record_meaningful_activity(conn: sqlite3.Connection, date: _dt.date | None = None) -> None:
    date = date or config.today_local()
    key = date.isoformat()
    row = conn.execute("SELECT * FROM daily_activity WHERE activity_date = ?", (key,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO daily_activity (activity_date, meaningful_activity) VALUES (?, 1)", (key,)
        )
    elif not row["meaningful_activity"]:
        conn.execute("UPDATE daily_activity SET meaningful_activity = 1 WHERE activity_date = ?", (key,))
    conn.commit()


def current_activity_streak(conn: sqlite3.Connection, today: _dt.date | None = None) -> int:
    today = today or config.today_local()
    streak = 0
    cursor = today
    while True:
        row = conn.execute(
            "SELECT meaningful_activity FROM daily_activity WHERE activity_date = ?",
            (cursor.isoformat(),),
        ).fetchone()
        if row is None or not row["meaningful_activity"]:
            break
        streak += 1
        cursor = cursor - _dt.timedelta(days=1)
    return streak


def best_activity_streak(conn: sqlite3.Connection) -> int:
    current = current_activity_streak(conn)
    stored = _get_setting_int(conn, "best_activity_streak", 0)
    best = max(current, stored)
    if best > stored:
        _set_setting_int(conn, "best_activity_streak", best)
    return best


def on_schedule_streak(conn: sqlite3.Connection) -> int:
    """Consecutive curriculum days (from day 1) completed on/before their
    original scheduled date. Breaks at the first late completion."""
    rows = conn.execute(
        "SELECT day_number, original_due_date, completed, completed_at FROM curriculum_days "
        "ORDER BY day_number"
    ).fetchall()
    streak = 0
    for r in rows:
        if not r["completed"]:
            break
        completed_date = _dt.datetime.fromisoformat(r["completed_at"]).date()
        due_date = _dt.date.fromisoformat(r["original_due_date"])
        if completed_date <= due_date:
            streak += 1
        else:
            streak = 0
    return streak


def _get_setting_int(conn: sqlite3.Connection, key: str, default: int) -> int:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return int(row["value"]) if row else default


def _set_setting_int(conn: sqlite3.Connection, key: str, value: int) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
