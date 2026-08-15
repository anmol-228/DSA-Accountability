"""Per-user calendar schedule, separate from reference curriculum content."""
from __future__ import annotations

import datetime as dt
import sqlite3

from app import config
from app.services import runtime_env

START_DATE_KEY = "schedule_start_date"
VERSION_KEY = "schedule_version"
SCHEDULE_FORMAT_VERSION = 1


def _validate_day(day_number: int) -> None:
    if not 1 <= day_number <= config.TOTAL_CURRICULUM_DAYS:
        raise ValueError(
            f"curriculum day must be 1..{config.TOTAL_CURRICULUM_DAYS}, got {day_number}"
        )


def parse_start_date(value: dt.date | str) -> dt.date:
    if isinstance(value, dt.datetime):
        value = value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("start date must use YYYY-MM-DD") from exc


def version_for(start_date: dt.date | str) -> str:
    return f"start-{parse_start_date(start_date).isoformat()}-v{SCHEDULE_FORMAT_VERSION}"


def configured_start_date(conn: sqlite3.Connection) -> dt.date | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (START_DATE_KEY,)).fetchone()
    if row and row["value"]:
        return parse_start_date(row["value"])

    # Backward compatibility for existing installations: infer the anchor from
    # their already-seeded Day 1 row. This preserves their schedule exactly.
    try:
        row = conn.execute(
            "SELECT original_due_date FROM curriculum_days WHERE day_number = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row and row["original_due_date"]:
        return parse_start_date(row["original_due_date"])
    return None


def get_start_date(conn: sqlite3.Connection) -> dt.date:
    """Return the configured anchor, defaulting only for non-onboarded helpers.

    The first-run UI always persists an explicit choice before seeding. The
    fallback keeps low-level library/tests usable and is the current local date,
    never a developer-specific constant.
    """
    return configured_start_date(conn) or config.today_local()


def due_date(conn: sqlite3.Connection, day_number: int) -> dt.date:
    _validate_day(day_number)
    return get_start_date(conn) + dt.timedelta(days=day_number - 1)


def target_end_date(conn: sqlite3.Connection) -> dt.date:
    return due_date(conn, config.TOTAL_CURRICULUM_DAYS)


def set_start_date(conn: sqlite3.Connection, start_date: dt.date | str) -> int:
    """Persist a schedule anchor and align existing day rows without progress loss."""
    runtime_env.assert_connection_access_allowed(
        conn, config.PRODUCTION_DB_PATH, "configure curriculum schedule"
    )
    start = parse_start_date(start_date)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (START_DATE_KEY, start.isoformat()),
    )
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (VERSION_KEY, version_for(start)),
    )

    updated = 0
    try:
        for day_number in range(1, config.TOTAL_CURRICULUM_DAYS + 1):
            result = conn.execute(
                "UPDATE curriculum_days SET original_due_date = ? WHERE day_number = ?",
                ((start + dt.timedelta(days=day_number - 1)).isoformat(), day_number),
            )
            updated += result.rowcount
    except sqlite3.OperationalError:
        # Migrations may exist while curriculum rows have not yet been seeded.
        pass
    conn.commit()
    return updated


def ensure_existing_installation_setting(conn: sqlite3.Connection) -> dt.date | None:
    """Persist an inferred legacy anchor without changing any due date."""
    existing = conn.execute("SELECT value FROM settings WHERE key = ?", (START_DATE_KEY,)).fetchone()
    if existing:
        return parse_start_date(existing["value"])
    start = configured_start_date(conn)
    if start is None:
        return None
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        (START_DATE_KEY, start.isoformat()),
    )
    conn.commit()
    return start
