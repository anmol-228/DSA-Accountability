"""Spaced revision engine with a daily workload cap (spec sections 38-41).

Only revisions explicitly promoted to `required_today` block curriculum-day
completion; everything else sits in the queue as deferred overflow.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3

from app import config


def schedule_revision(conn: sqlite3.Connection, problem_id: int, confidence: str,
                       base_date: _dt.date | None = None) -> list[int]:
    base_date = base_date or config.today_local()
    intervals = (config.REVISION_INTERVALS_RED if confidence == "red"
                 else config.REVISION_INTERVALS_DEFAULT)
    now = config.now_local().isoformat()
    ids = []
    for stage, days in enumerate(intervals):
        due = (base_date + _dt.timedelta(days=days)).isoformat()
        cur = conn.execute(
            "INSERT INTO revision_schedule (problem_id, due_date, interval_stage, "
            "confidence_at_schedule, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (problem_id, due, stage, confidence, now),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


def _revision_cap_for_day(conn: sqlite3.Connection, day_number: int) -> int:
    day = conn.execute("SELECT * FROM curriculum_days WHERE day_number = ?", (day_number,)).fetchone()
    if day is None:
        return 0
    if day["is_oa_day"] or day["is_mock_day"]:
        urgent_red = conn.execute(
            "SELECT COUNT(*) c FROM revision_schedule WHERE status = 'pending' "
            "AND confidence_at_schedule = 'red' AND due_date <= ?",
            (config.today_local().isoformat(),),
        ).fetchone()["c"]
        return 1 if urgent_red > 0 else 0

    fixed_count = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE day_number = ? AND required = 1 "
        "AND task_type IN ('leetcode','oa','mock') AND generated = 0",
        (day_number,),
    ).fetchone()["c"]
    if fixed_count >= 3:
        return 1
    return config.MAX_GENERATED_REVISIONS_PER_DAY


def generate_required_today(conn: sqlite3.Connection, day_number: int,
                             today: _dt.date | None = None) -> list[int]:
    """Promotes up to the day's cap of due revisions to required_today and
    attaches a gating `tasks` row for each. Idempotent per day."""
    today = today or config.today_local()
    already = conn.execute(
        "SELECT COUNT(*) c FROM revision_schedule WHERE generated_for_day = ? "
        "AND status IN ('required_today', 'completed')",
        (day_number,),
    ).fetchone()["c"]
    cap = _revision_cap_for_day(conn, day_number)
    slots = max(0, cap - already)
    if slots == 0:
        return []

    due = conn.execute(
        "SELECT * FROM revision_schedule WHERE status = 'pending' AND due_date <= ? "
        "ORDER BY (confidence_at_schedule = 'red') DESC, due_date ASC LIMIT ?",
        (today.isoformat(), slots),
    ).fetchall()

    created_task_ids = []
    for r in due:
        problem = conn.execute("SELECT * FROM problems WHERE id = ?", (r["problem_id"],)).fetchone()
        # Interval-stage suffix disambiguates same-problem revision rows: a
        # single Red-confidence solve schedules several future stages
        # (1/3/7/21/45 days out), and if two land due the same day and both
        # get promoted, an undisambiguated title would render two
        # visually-identical task rows for the same problem.
        title = (
            f"Revision - LC {problem['leetcode_number']} {problem['title']} (stage {r['interval_stage']})"
            if problem else "Revision"
        )
        task_cur = conn.execute(
            "INSERT INTO tasks (day_number, task_type, title, problem_id, required, generated) "
            "VALUES (?, 'revision', ?, ?, 1, 1)",
            (day_number, title, r["problem_id"]),
        )
        task_id = task_cur.lastrowid
        conn.execute(
            "UPDATE revision_schedule SET status = 'required_today', generated_for_day = ?, "
            "task_id = ? WHERE id = ?",
            (day_number, task_id, r["id"]),
        )
        created_task_ids.append(task_id)
    conn.commit()
    return created_task_ids


def complete_revision(conn: sqlite3.Connection, revision_id: int, new_confidence: str) -> None:
    now = config.now_local().isoformat()
    rev = conn.execute("SELECT * FROM revision_schedule WHERE id = ?", (revision_id,)).fetchone()
    if rev is None:
        raise ValueError(f"No revision_schedule row {revision_id}")
    conn.execute(
        "UPDATE revision_schedule SET status = 'completed', completed_at = ? WHERE id = ?",
        (now, revision_id),
    )
    conn.commit()
    # Schedule the next stage based on the freshly-reported confidence.
    schedule_revision(conn, rev["problem_id"], new_confidence, config.today_local())


def deferred_queue(conn: sqlite3.Connection, today: _dt.date | None = None) -> list[sqlite3.Row]:
    today = today or config.today_local()
    return conn.execute(
        "SELECT rs.*, p.leetcode_number, p.title FROM revision_schedule rs "
        "JOIN problems p ON rs.problem_id = p.id "
        "WHERE rs.status = 'pending' AND rs.due_date <= ? ORDER BY rs.due_date",
        (today.isoformat(),),
    ).fetchall()
