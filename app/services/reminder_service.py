"""Reminders. Default behavior: exactly one notification per app launch
(i.e. once per PC sign-in, if autostart is enabled) — never a recurring
nag — and nothing at all once the active day's required work is done.

A time-of-day checkpoint mode (`due_reminder`, spec section 46) also exists
for anyone who wants multiple reminders per day instead, but it is opt-in
and OFF by default (see `checkpoint_reminders_enabled`). It fires at most
once per configured checkpoint per calendar day, tracked via the
`reminders` table, so re-checking it every minute can never spam."""
from __future__ import annotations

import datetime as _dt
import sqlite3

from app import config
from app.services import progression_service as prog

CHECKPOINT_MESSAGES = {
    "10:00": "Day {day} is waiting. {n} required task(s).",
    "16:00": "DSA Day {day} is still incomplete. {n} task(s) remaining.",
    "20:00": "Your active DSA day is still unfinished. {n} required task(s) remain.",
}


def checkpoint_reminders_enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM settings WHERE key = 'checkpoint_reminders_enabled'").fetchone()
    return row is not None and row["value"] == "1"


def startup_reminder(conn: sqlite3.Connection) -> dict | None:
    """Call once per app launch. Returns a message only if there is
    genuinely required work left today; None if the day is already
    complete (or post-plan mode) — never nags about finished work."""
    active = prog.get_active_day(conn)
    if active is None:
        return None
    remaining = prog.remaining_required_count(conn, active)
    if remaining == 0:
        return None
    return {
        "day": active,
        "remaining": remaining,
        "message": f"Day {active} has {remaining} required task(s) waiting.",
    }


def reminder_times(conn: sqlite3.Connection) -> list[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = 'reminder_times'").fetchone()
    if row:
        import json
        return json.loads(row["value"])
    return list(config.DEFAULT_REMINDER_TIMES)


def is_snoozed(conn: sqlite3.Connection, now: _dt.datetime | None = None) -> bool:
    now = now or config.now_local()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'snoozed_until'"
    ).fetchone()
    if not row or not row["value"]:
        return False
    return _dt.datetime.fromisoformat(row["value"]) > now


def snooze(conn: sqlite3.Connection, minutes: int) -> None:
    until = (config.now_local() + _dt.timedelta(minutes=minutes)).isoformat()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('snoozed_until', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (until,),
    )
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('snooze_uses', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)"
    )
    conn.commit()


def due_reminder(conn: sqlite3.Connection, checkpoint: str, now: _dt.datetime | None = None) -> dict | None:
    """Returns a reminder payload only if `checkpoint` (e.g. '10:00') is one
    of the configured reminder times, it hasn't already fired today, the
    active day is still incomplete, and the user hasn't snoozed past now.

    Caller is expected to invoke this once per minute at most; the
    checkpoint match plus the once-per-day dedup below is what prevents
    repeated firing within the same checkpoint minute or across retries.
    """
    now = now or config.now_local()
    if checkpoint not in reminder_times(conn):
        return None
    if is_snoozed(conn, now):
        return None

    today = now.date().isoformat()
    already_fired = conn.execute(
        "SELECT 1 FROM reminders WHERE scheduled_time = ? AND fired_at LIKE ?",
        (checkpoint, f"{today}%"),
    ).fetchone()
    if already_fired:
        return None

    active = prog.get_active_day(conn)
    if active is None:
        return None
    remaining = prog.remaining_required_count(conn, active)
    if remaining == 0:
        return None

    template = CHECKPOINT_MESSAGES.get(checkpoint, "DSA Day {day} still has {n} task(s) remaining.")
    message = template.format(day=active, n=remaining)
    conn.execute(
        "INSERT INTO reminders (scheduled_time, fired_at, day_number, message) VALUES (?, ?, ?, ?)",
        (checkpoint, now.isoformat(), active, message),
    )
    conn.commit()
    return {"day": active, "remaining": remaining, "message": message}
