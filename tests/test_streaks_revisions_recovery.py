import datetime as dt

from app.services import (
    progression_service as prog,
    recovery_service,
    revision_service,
    streak_service,
)


def _complete_all_required(conn, day_number):
    rows = conn.execute(
        "SELECT id FROM tasks WHERE day_number = ? AND required = 1", (day_number,)
    ).fetchall()
    for r in rows:
        prog.complete_task(conn, r["id"])


# --- streaks -----------------------------------------------------------------

def test_activity_streak_breaks_on_gap(seeded_conn):
    conn = seeded_conn
    streak_service.record_meaningful_activity(conn, dt.date(2026, 8, 11))
    streak_service.record_meaningful_activity(conn, dt.date(2026, 8, 12))
    # gap on the 13th
    streak_service.record_meaningful_activity(conn, dt.date(2026, 8, 14))
    assert streak_service.current_activity_streak(conn, dt.date(2026, 8, 14)) == 1
    assert streak_service.current_activity_streak(conn, dt.date(2026, 8, 12)) == 2


def test_opening_app_alone_is_not_meaningful_activity(seeded_conn):
    # No record_meaningful_activity call made -> streak stays 0.
    assert streak_service.current_activity_streak(seeded_conn, dt.date(2026, 8, 11)) == 0


def test_on_schedule_streak_breaks_on_late_completion(seeded_conn):
    conn = seeded_conn
    # Day 1 completed on time (due 2026-08-15)
    for r in conn.execute("SELECT id FROM tasks WHERE day_number = 1 AND required = 1"):
        prog.complete_task(conn, r["id"])
    conn.execute("UPDATE curriculum_days SET completed_at = ? WHERE day_number = 1",
                 (dt.datetime(2026, 8, 15, 20, 0).isoformat(),))
    # Day 2 completed late (due 2026-08-16, completed 08-18)
    for r in conn.execute("SELECT id FROM tasks WHERE day_number = 2 AND required = 1"):
        prog.complete_task(conn, r["id"])
    conn.execute("UPDATE curriculum_days SET completed_at = ? WHERE day_number = 2",
                 (dt.datetime(2026, 8, 18, 9, 0).isoformat(),))
    conn.commit()
    assert streak_service.on_schedule_streak(conn) == 0  # broke at day 2


# --- revisions ------------------------------------------------------------------

def test_revision_schedule_default_intervals(seeded_conn):
    conn = seeded_conn
    problem = conn.execute("SELECT id FROM problems WHERE leetcode_number = 1").fetchone()
    ids = revision_service.schedule_revision(conn, problem["id"], "green", dt.date(2026, 8, 11))
    rows = conn.execute(
        "SELECT due_date FROM revision_schedule WHERE id IN (%s) ORDER BY due_date" % ",".join("?" * len(ids)),
        ids,
    ).fetchall()
    due_dates = [r["due_date"] for r in rows]
    assert due_dates == ["2026-08-13", "2026-08-18", "2026-09-01", "2026-09-25"]


def test_revision_schedule_red_intervals(seeded_conn):
    conn = seeded_conn
    problem = conn.execute("SELECT id FROM problems WHERE leetcode_number = 1").fetchone()
    ids = revision_service.schedule_revision(conn, problem["id"], "red", dt.date(2026, 8, 11))
    assert len(ids) == 5  # D+1, D+3, D+7, D+21, D+45


def test_revision_workload_cap_two_per_day(seeded_conn):
    conn = seeded_conn
    # Day 100 has 2 fixed leetcode tasks -> cap should be 2
    problems = [conn.execute("SELECT id FROM problems WHERE leetcode_number = ?", (n,)).fetchone()["id"]
                for n in (1, 121, 53, 88, 283)]
    for pid in problems:
        revision_service.schedule_revision(conn, pid, "green", dt.date(2026, 8, 1))
    created = revision_service.generate_required_today(conn, 100, dt.date(2026, 8, 15))
    assert len(created) <= 2


def test_revision_required_today_blocks_day_completion(seeded_conn):
    conn = seeded_conn
    problem = conn.execute("SELECT id FROM problems WHERE leetcode_number = 1").fetchone()
    revision_service.schedule_revision(conn, problem["id"], "green", dt.date(2026, 8, 1))
    created = revision_service.generate_required_today(conn, 1, dt.date(2026, 8, 15))
    assert len(created) >= 1
    # Day 1's normal tasks are complete but the generated revision isn't -> day not complete
    for r in conn.execute("SELECT id FROM tasks WHERE day_number = 1 AND generated = 0 AND required = 1"):
        prog.complete_task(conn, r["id"])
    assert prog.get_active_day(conn) == 1
    for task_id in created:
        prog.complete_task(conn, task_id)
    assert prog.get_active_day(conn) == 2


# --- recovery mode ------------------------------------------------------------

def test_recovery_mode_threshold(seeded_conn):
    conn = seeded_conn
    assert recovery_service.is_recovery_mode(conn, dt.date(2026, 8, 16)) is False  # 1 day behind
    assert recovery_service.is_recovery_mode(conn, dt.date(2026, 8, 18)) is True  # 3 days behind


def test_recovery_plan_preserves_sequential_gating(seeded_conn):
    conn = seeded_conn
    plan = recovery_service.suggested_catchup_plan(conn, dt.date(2026, 8, 19))  # 4 days behind
    all_days = [d for entry in plan for d in entry["suggested_days"]]
    assert all_days == sorted(all_days)  # never skips ahead out of order
    assert all_days[0] == 1


def test_recovery_catchup_by_completing_multiple_days(seeded_conn):
    conn = seeded_conn
    _complete_all_required(conn, 1)
    _complete_all_required(conn, 2)
    _complete_all_required(conn, 3)
    assert prog.get_active_day(conn) == 4
    # delay recalculated against day 4's original date relative to "today"
    assert prog.schedule_delay_days(conn, dt.date(2026, 8, 15)) == 0
