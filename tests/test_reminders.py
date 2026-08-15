import datetime as dt

from app.services import progression_service as prog, reminder_service


def _complete_all_required(conn, day_number):
    rows = conn.execute(
        "SELECT id FROM tasks WHERE day_number = ? AND required = 1", (day_number,)
    ).fetchall()
    for r in rows:
        prog.complete_task(conn, r["id"])


# --- startup_reminder (the default behavior) ---------------------------------

def test_startup_reminder_fires_when_day_incomplete(seeded_conn):
    due = reminder_service.startup_reminder(seeded_conn)
    assert due is not None
    assert due["day"] == 1
    assert due["remaining"] > 0


def test_startup_reminder_still_fires_for_newly_unlocked_day(seeded_conn):
    """Completing Day 1 immediately unlocks Day 2 (by design, for same-day
    catch-up), and Day 2 has its own required tasks — so a reminder should
    still mention Day 2, not go silent, until ALL 135 days are truly done."""
    _complete_all_required(seeded_conn, 1)
    due = reminder_service.startup_reminder(seeded_conn)
    assert due is not None
    assert due["day"] == 2


def test_startup_reminder_silent_in_post_plan_mode(seeded_conn):
    for day in range(1, 136):
        _complete_all_required(seeded_conn, day)
    assert prog.is_post_plan_mode(seeded_conn)
    due = reminder_service.startup_reminder(seeded_conn)
    assert due is None


# --- due_reminder (opt-in checkpoint mode) — regression test for the spam bug --

def test_due_reminder_none_on_non_checkpoint_minute(seeded_conn):
    """This is the exact bug the user hit: calling due_reminder every
    minute must NOT return a reminder for arbitrary minutes that aren't a
    configured checkpoint — only the fallback message masked this before."""
    now = dt.datetime(2026, 8, 11, 10, 37)  # not 10:00, 16:00, or 20:00
    due = reminder_service.due_reminder(seeded_conn, now.strftime("%H:%M"), now)
    assert due is None


def test_due_reminder_fires_exactly_once_per_checkpoint_per_day(seeded_conn):
    now = dt.datetime(2026, 8, 11, 10, 0)
    first = reminder_service.due_reminder(seeded_conn, "10:00", now)
    assert first is not None
    second = reminder_service.due_reminder(seeded_conn, "10:00", now)
    assert second is None  # already fired for this checkpoint today


def test_due_reminder_fires_again_next_day(seeded_conn):
    day1 = dt.datetime(2026, 8, 11, 10, 0)
    day2 = dt.datetime(2026, 8, 12, 10, 0)
    assert reminder_service.due_reminder(seeded_conn, "10:00", day1) is not None
    assert reminder_service.due_reminder(seeded_conn, "10:00", day2) is not None


def test_due_reminder_silent_only_in_post_plan_mode(seeded_conn):
    for day in range(1, 136):
        _complete_all_required(seeded_conn, day)
    now = dt.datetime(2026, 8, 11, 10, 0)
    assert reminder_service.due_reminder(seeded_conn, "10:00", now) is None


def test_snooze_suppresses_due_reminder(seeded_conn):
    from app import config
    reminder_service.snooze(seeded_conn, 15)
    now = config.now_local()
    assert reminder_service.due_reminder(seeded_conn, now.strftime("%H:%M"), now) is None
