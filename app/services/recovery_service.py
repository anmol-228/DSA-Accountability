"""Recovery mode: suggests a catch-up pace without ever skipping or
redistributing days (spec section 45). Sequential gating is untouched —
this only produces a display recommendation."""
from __future__ import annotations

import datetime as _dt
import sqlite3

from app import config
from app.services import progression_service as prog


def is_recovery_mode(conn: sqlite3.Connection, today: _dt.date | None = None) -> bool:
    return prog.schedule_delay_days(conn, today) >= config.RECOVERY_MODE_THRESHOLD_DAYS


def suggested_catchup_plan(conn: sqlite3.Connection, today: _dt.date | None = None) -> list[dict]:
    """Spreads the current delay across upcoming calendar days as a
    recommendation only. E.g. 4 days behind -> today: current + 1 extra,
    tomorrow: 1, day after: current + 1 extra, etc., until caught up."""
    today = today or config.today_local()
    active = prog.get_active_day(conn)
    if active is None:
        return []

    delay = prog.schedule_delay_days(conn, today)
    if delay <= 0:
        return [{"date": today.isoformat(), "suggested_days": [active], "note": "On schedule."}]

    plan = []
    day_cursor = active
    date_cursor = today
    remaining_extra = delay
    while remaining_extra >= 0 and day_cursor <= config.TOTAL_CURRICULUM_DAYS:
        days_today = [day_cursor]
        if remaining_extra > 0:
            days_today.append(day_cursor + 1)
            day_cursor += 1
            remaining_extra -= 1
        plan.append({
            "date": date_cursor.isoformat(),
            "suggested_days": [d for d in days_today if d <= config.TOTAL_CURRICULUM_DAYS],
        })
        day_cursor += 1
        date_cursor += _dt.timedelta(days=1)
        if remaining_extra <= 0:
            break
    return plan
