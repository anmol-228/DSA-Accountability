import datetime as dt

import pytest

from app import config
from app.services import curriculum_service, progression_service as prog, schedule_service


def _complete_all_required(conn, day_number):
    rows = conn.execute(
        "SELECT id FROM tasks WHERE day_number = ? AND required = 1", (day_number,)
    ).fetchall()
    for r in rows:
        prog.complete_task(conn, r["id"])


# --- Curriculum shape -------------------------------------------------------

def test_exactly_135_days(seeded_conn):
    n = seeded_conn.execute("SELECT COUNT(*) c FROM curriculum_days").fetchone()["c"]
    assert n == 135


def test_all_135_original_dates_consecutive_and_correct(seeded_conn):
    """Final production repair pass acceptance criterion: Day 1 =
    2026-08-15, Day 135 = 2026-12-27, every day in between exactly
    consecutive -- not just spot-checked at the two endpoints."""
    rows = seeded_conn.execute(
        "SELECT day_number, original_due_date FROM curriculum_days ORDER BY day_number"
    ).fetchall()
    assert len(rows) == 135
    assert dt.date.fromisoformat(rows[0]["original_due_date"]) == dt.date(2026, 8, 15)
    assert dt.date.fromisoformat(rows[-1]["original_due_date"]) == dt.date(2026, 12, 27)
    for i, r in enumerate(rows):
        assert r["day_number"] == i + 1
        expected = dt.date(2026, 8, 15) + dt.timedelta(days=i)
        assert dt.date.fromisoformat(r["original_due_date"]) == expected


def test_before_canonical_start_delay_is_zero_not_negative(seeded_conn):
    """A fresh install queried before the canonical start date (e.g. this
    repair itself, performed before the 2026-08-15 start) must
    show 0 delay -- never a negative delay or 'ahead of schedule' framing."""
    status = prog.get_status(seeded_conn, today=dt.date(2026, 8, 14))
    assert status.active_day == 1
    assert status.schedule_delay_days == 0


def test_on_canonical_start_day_incomplete_day1_has_zero_delay(seeded_conn):
    status = prog.get_status(seeded_conn, today=dt.date(2026, 8, 15))
    assert status.active_day == 1
    assert status.schedule_delay_days == 0


def test_reschedule_original_dates_is_idempotent_across_repeated_calls(seeded_conn):
    """Calling reschedule_original_dates() again (e.g. on every app
    startup) must never shift the schedule further -- Day 1 stays
    2026-08-15 no matter how many times it's called, guarded by
    the persisted date-derived schedule version."""
    seeded_conn.execute("DELETE FROM settings WHERE key = 'schedule_version'")
    seeded_conn.commit()
    first = prog.reschedule_original_dates(seeded_conn)
    assert first == 135  # fresh DB, no schedule_version yet -> real recompute
    assert prog.original_due_date(seeded_conn, 1) == dt.date(2026, 8, 15)
    second = prog.reschedule_original_dates(seeded_conn)
    assert second == 0  # version already applied -> no-op, not another 135-row update
    assert prog.original_due_date(seeded_conn, 1) == dt.date(2026, 8, 15)
    assert prog.original_due_date(seeded_conn, 135) == dt.date(2026, 12, 27)


@pytest.mark.parametrize(
    "start",
    [dt.date(2026, 8, 15), dt.date(2027, 1, 1), dt.date(2027, 6, 15)],
)
def test_user_selected_start_date_produces_exactly_135_consecutive_days(conn, start):
    schedule_service.set_start_date(conn, start)
    curriculum_service.seed_curriculum(conn)
    rows = conn.execute(
        "SELECT day_number, original_due_date FROM curriculum_days ORDER BY day_number"
    ).fetchall()
    assert len(rows) == 135
    assert dt.date.fromisoformat(rows[0]["original_due_date"]) == start
    assert dt.date.fromisoformat(rows[-1]["original_due_date"]) == start + dt.timedelta(days=134)
    assert all(
        dt.date.fromisoformat(row["original_due_date"]) == start + dt.timedelta(days=index)
        for index, row in enumerate(rows)
    )


def test_day_1_original_date(seeded_conn):
    assert prog.original_due_date(seeded_conn, 1) == dt.date(2026, 8, 15)


def test_day_135_original_date(seeded_conn):
    assert prog.original_due_date(seeded_conn, 135) == dt.date(2026, 12, 27)


def test_unique_day_ids(seeded_conn):
    rows = seeded_conn.execute("SELECT day_number FROM curriculum_days").fetchall()
    nums = [r["day_number"] for r in rows]
    assert len(nums) == len(set(nums))
    assert sorted(nums) == list(range(1, 136))


def test_all_tasks_reference_valid_days(seeded_conn):
    bad = seeded_conn.execute(
        "SELECT t.id FROM tasks t LEFT JOIN curriculum_days d ON t.day_number = d.day_number "
        "WHERE d.day_number IS NULL"
    ).fetchall()
    assert bad == []


# --- Progression gating: THE core invariant ---------------------------------

def test_fresh_install_day1_is_active(seeded_conn):
    assert prog.get_active_day(seeded_conn) == 1


def test_calendar_advance_does_not_advance_active_day(seeded_conn):
    """Fresh install Aug 16 (a day after canonical start) with zero progress
    must still show Day 1 active — calendar time never auto-advances."""
    assert prog.get_active_day(seeded_conn) == 1
    status = prog.get_status(seeded_conn, today=dt.date(2026, 8, 16))
    assert status.active_day == 1
    assert status.schedule_delay_days == 1


def test_incomplete_day_stays_active_days_later(seeded_conn):
    status = prog.get_status(seeded_conn, today=dt.date(2026, 8, 19))
    assert status.active_day == 1
    assert status.schedule_delay_days == 4


def test_completing_day1_immediately_unlocks_day2(seeded_conn):
    _complete_all_required(seeded_conn, 1)
    assert prog.get_active_day(seeded_conn) == 2


def test_completing_day1_unlocks_day2_regardless_of_calendar_date(seeded_conn):
    assert prog.get_status(seeded_conn, today=dt.date(2026, 9, 1)).active_day == 1
    _complete_all_required(seeded_conn, 1)
    assert prog.get_status(seeded_conn, today=dt.date(2026, 9, 1)).active_day == 2


def test_completing_day2_same_calendar_date_unlocks_day3(seeded_conn):
    _complete_all_required(seeded_conn, 1)
    assert prog.get_active_day(seeded_conn) == 2
    _complete_all_required(seeded_conn, 2)
    assert prog.get_active_day(seeded_conn) == 3


def test_no_skipping_future_days(seeded_conn):
    """Even if calendar is far in the future, days can't be skipped — only
    sequential completion advances the active day."""
    status = prog.get_status(seeded_conn, today=dt.date(2026, 9, 1))
    assert status.active_day == 1
    assert prog.is_day_locked(seeded_conn, 2) is True
    assert prog.is_day_locked(seeded_conn, 135) is True


def test_day_locked_status(seeded_conn):
    assert prog.is_day_locked(seeded_conn, 1) is False  # active day is never "locked"
    assert prog.is_day_locked(seeded_conn, 2) is True
    _complete_all_required(seeded_conn, 1)
    assert prog.is_day_locked(seeded_conn, 1) is False  # completed, not locked
    assert prog.is_day_locked(seeded_conn, 2) is False  # now active


def test_partial_completion_does_not_complete_day(seeded_conn):
    rows = seeded_conn.execute(
        "SELECT id FROM tasks WHERE day_number = 1 AND required = 1"
    ).fetchall()
    assert len(rows) > 1
    prog.complete_task(seeded_conn, rows[0]["id"])
    assert prog.get_active_day(seeded_conn) == 1
    assert prog.remaining_required_count(seeded_conn, 1) == len(rows) - 1


def test_all_135_days_completable_and_post_plan_mode(seeded_conn):
    for day in range(1, 136):
        assert prog.get_active_day(seeded_conn) == day
        _complete_all_required(seeded_conn, day)
    assert prog.get_active_day(seeded_conn) is None
    assert prog.is_post_plan_mode(seeded_conn) is True


def test_complete_task_idempotent(seeded_conn):
    row = seeded_conn.execute(
        "SELECT id FROM tasks WHERE day_number = 1 AND required = 1 LIMIT 1"
    ).fetchone()
    assert prog.complete_task(seeded_conn, row["id"]) is False  # day 1 has >1 required task
    # completing the same task again should be a no-op, not raise or double-count
    result = prog.complete_task(seeded_conn, row["id"])
    assert result is False


# --- Projected finish --------------------------------------------------------

def test_projected_finish_on_schedule_pace(seeded_conn):
    # Nothing completed yet, today = start date -> 135 remaining -> finish = start + 134 = Dec 27
    status = prog.get_status(seeded_conn, today=dt.date(2026, 8, 15))
    assert status.projected_finish == dt.date(2026, 12, 27)


def test_projected_finish_moves_later_when_behind(seeded_conn):
    # Still 135 remaining but today has moved forward -> finish pushes out
    status = prog.get_status(seeded_conn, today=dt.date(2026, 8, 19))
    assert status.projected_finish == dt.date(2026, 12, 31)  # +4 days


def test_projected_finish_moves_earlier_on_catchup(seeded_conn):
    _complete_all_required(seeded_conn, 1)
    _complete_all_required(seeded_conn, 2)
    # 2 days completed "today" -> 133 remaining from today
    status = prog.get_status(seeded_conn, today=dt.date(2026, 8, 15))
    assert status.projected_finish == dt.date(2026, 8, 15) + dt.timedelta(days=132)


def test_original_target_end_never_changes(seeded_conn):
    _complete_all_required(seeded_conn, 1)
    status = prog.get_status(seeded_conn, today=dt.date(2026, 9, 1))
    assert status.original_target_end == dt.date(2026, 12, 27)
