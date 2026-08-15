"""Completion-gated curriculum progression.

THE CENTRAL INVARIANT OF THIS ENTIRE APPLICATION:

    active curriculum day = earliest incomplete day in 1..135

The active day is NEVER derived from the calendar. Calendar time moving
forward (including past midnight) does not, by itself, change the active
day. The only thing that advances the active day is verified completion of
all required tasks for the current day. Completing a day immediately
unlocks the next one, even on the same calendar date (same-day catch-up).

This module deliberately does NOT persist a mutable "current day" integer
as its source of truth (see spec section 7 / PROJECT_STATE.md) — it always
derives the active day by scanning curriculum_days.completed. This makes
progress resilient to any inconsistency elsewhere in the database.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
from dataclasses import dataclass

from app import config
from app.services import runtime_env, schedule_service


def get_active_day(conn: sqlite3.Connection) -> int | None:
    """Earliest curriculum day (1..135) that is not yet completed.

    Returns None if all 135 days are completed (POST-PLAN MODE).
    """
    row = conn.execute(
        "SELECT day_number FROM curriculum_days WHERE completed = 0 "
        "ORDER BY day_number ASC LIMIT 1"
    ).fetchone()
    return row["day_number"] if row else None


def is_post_plan_mode(conn: sqlite3.Connection) -> bool:
    return get_active_day(conn) is None


def is_day_locked(conn: sqlite3.Connection, day_number: int) -> bool:
    """A day is locked if it is not the active day and not already completed."""
    active = get_active_day(conn)
    if active is None:
        return False  # post-plan mode: nothing is "locked" in the old sense
    if day_number < active:
        return False  # already completed (or in the past) — not locked
    return day_number > active


def required_tasks_for_day(conn: sqlite3.Connection, day_number: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM tasks WHERE day_number = ? AND required = 1", (day_number,)
    ).fetchall()


def remaining_required_count(conn: sqlite3.Connection, day_number: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE day_number = ? AND required = 1 AND completed = 0",
        (day_number,),
    ).fetchone()
    return row["c"]


def day_is_ready_to_complete(conn: sqlite3.Connection, day_number: int) -> bool:
    """True if every required task for the day is completed.

    A day with zero required tasks is vacuously never auto-completed here —
    callers should not create days with zero required tasks (the curriculum
    seed always attaches at least one).
    """
    total_required = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE day_number = ? AND required = 1", (day_number,)
    ).fetchone()["c"]
    if total_required == 0:
        return False
    return remaining_required_count(conn, day_number) == 0


def complete_task(conn: sqlite3.Connection, task_id: int, actor: str = "user") -> bool:
    """Marks a task completed and, if that finishes the day's required work,
    marks the day complete and unlocks the next day immediately.

    Returns True if this call caused the containing day to become complete.
    """
    runtime_env.assert_connection_access_allowed(conn, config.PRODUCTION_DB_PATH, "complete curriculum task")
    now = config.now_local().isoformat()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        raise ValueError(f"No task with id {task_id}")
    if task["completed"]:
        return False

    conn.execute("UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?", (now, task_id))
    day_completed = maybe_complete_day(conn, task["day_number"], actor=actor)
    conn.commit()
    return day_completed


def maybe_complete_day(conn: sqlite3.Connection, day_number: int, actor: str = "user") -> bool:
    """Checks whether `day_number` now has all required tasks done; if so,
    marks it completed and unlocks day_number + 1. Idempotent."""
    day = conn.execute(
        "SELECT * FROM curriculum_days WHERE day_number = ?", (day_number,)
    ).fetchone()
    if day is None or day["completed"]:
        return False
    if not day_is_ready_to_complete(conn, day_number):
        return False

    now = config.now_local().isoformat()
    conn.execute(
        "UPDATE curriculum_days SET completed = 1, completed_at = ? WHERE day_number = ?",
        (now, day_number),
    )
    conn.execute(
        "INSERT INTO audit_log (ts, actor, action, details) VALUES (?, ?, 'day_completed', ?)",
        (now, actor, f"day {day_number}"),
    )

    next_day = day_number + 1
    if next_day <= config.TOTAL_CURRICULUM_DAYS:
        nxt = conn.execute(
            "SELECT unlocked_at FROM curriculum_days WHERE day_number = ?", (next_day,)
        ).fetchone()
        if nxt is not None and nxt["unlocked_at"] is None:
            conn.execute(
                "UPDATE curriculum_days SET unlocked_at = ? WHERE day_number = ?", (now, next_day)
            )
            conn.execute(
                "INSERT INTO audit_log (ts, actor, action, details) VALUES (?, 'system', 'day_unlocked', ?)",
                (now, f"day {next_day}"),
            )
    return True


def original_due_date(conn: sqlite3.Connection, day_number: int) -> _dt.date:
    row = conn.execute(
        "SELECT original_due_date FROM curriculum_days WHERE day_number = ?", (day_number,)
    ).fetchone()
    if row and row["original_due_date"]:
        return _dt.date.fromisoformat(row["original_due_date"])
    return schedule_service.due_date(conn, day_number)


def reschedule_original_dates(conn: sqlite3.Connection) -> int:
    """Recomputes curriculum_days.original_due_date for all 135 days from
    the user's persisted schedule start date. A data migration for when the
    anchor date itself changes (e.g. the user rescheduling the
    plan) against an already-seeded database. Never touches completed /
    completed_at / unlocked_at — real progress is completely unaffected,
    only the "originally scheduled for" dates used for delay/on-schedule-
    streak display move.

    Guarded by a version derived from the selected date: skips the recompute
    entirely once that exact version has
    already been applied, so this doesn't re-run 135 UPDATEs on every
    single startup, and — more importantly — repeated calls can never
    drift the schedule by re-deriving dates from something other than the
    fixed config constant (there is no "+1 day per call" failure mode
    possible here, since the source is always the persisted start date,
    but the version guard makes that invariant explicit and
    cheap to verify rather than merely true by inspection). Returns the
    number of rows updated (0 if this version was already applied).
    """
    runtime_env.assert_connection_access_allowed(conn, config.PRODUCTION_DB_PATH, "reschedule curriculum")
    start = schedule_service.get_start_date(conn)
    expected_version = schedule_service.version_for(start)
    applied = conn.execute(
        "SELECT value FROM settings WHERE key = 'schedule_version'"
    ).fetchone()
    if applied and applied["value"] == expected_version:
        return 0

    updated = 0
    for day_no in range(1, config.TOTAL_CURRICULUM_DAYS + 1):
        due = (start + _dt.timedelta(days=day_no - 1)).isoformat()
        cur = conn.execute(
            "UPDATE curriculum_days SET original_due_date = ? WHERE day_number = ?",
            (due, day_no),
        )
        updated += cur.rowcount
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('schedule_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (expected_version,),
    )
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('schedule_start_date', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (start.isoformat(),),
    )
    conn.commit()
    return updated


def schedule_delay_days(conn: sqlite3.Connection, today: _dt.date | None = None) -> int:
    """Calendar days the active day is behind its original scheduled date. 0 if not behind / post-plan."""
    active = get_active_day(conn)
    if active is None:
        return 0
    today = today or config.today_local()
    delta = (today - original_due_date(conn, active)).days
    return max(0, delta)


def projected_finish_date(conn: sqlite3.Connection, today: _dt.date | None = None) -> _dt.date:
    """Projected finish assuming ~1 curriculum day completed per calendar day from today onward."""
    today = today or config.today_local()
    completed_count = conn.execute(
        "SELECT COUNT(*) AS c FROM curriculum_days WHERE completed = 1"
    ).fetchone()["c"]
    remaining = config.TOTAL_CURRICULUM_DAYS - completed_count
    if remaining <= 0:
        last = conn.execute(
            "SELECT MAX(completed_at) AS m FROM curriculum_days WHERE completed = 1"
        ).fetchone()["m"]
        if last:
            return _dt.datetime.fromisoformat(last).date()
        return today
    return today + _dt.timedelta(days=remaining - 1)


@dataclass
class ProgressStatus:
    active_day: int | None
    post_plan_mode: bool
    today: _dt.date
    original_due_date: _dt.date | None
    schedule_delay_days: int
    original_target_end: _dt.date
    projected_finish: _dt.date
    completed_days: int
    remaining_required_tasks: int


def get_status(conn: sqlite3.Connection, today: _dt.date | None = None) -> ProgressStatus:
    today = today or config.today_local()
    active = get_active_day(conn)
    completed_days = conn.execute(
        "SELECT COUNT(*) AS c FROM curriculum_days WHERE completed = 1"
    ).fetchone()["c"]
    return ProgressStatus(
        active_day=active,
        post_plan_mode=active is None,
        today=today,
        original_due_date=original_due_date(conn, active) if active else None,
        schedule_delay_days=schedule_delay_days(conn, today),
        original_target_end=schedule_service.target_end_date(conn),
        projected_finish=projected_finish_date(conn, today),
        completed_days=completed_days,
        remaining_required_tasks=remaining_required_count(conn, active) if active else 0,
    )
