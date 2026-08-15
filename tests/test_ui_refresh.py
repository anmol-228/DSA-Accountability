"""Regression tests for the periodic-flicker fix (see PROJECT_STATE.md
"Periodic Flicker Fix"). Verifies the UiSnapshot-based dispatch: identical
state produces zero UI mutation, task-only changes produce exactly one
incremental update (no rebuild), and active-day/task-set changes produce
exactly one deliberate rebuild. Runs headless (offscreen) — no real
display needed, no real progress DB touched.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app import config, database
from app.services import curriculum_service, progression_service as prog


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def overlay_window(qapp, tmp_path, monkeypatch):
    db_path = tmp_path / "ui_test.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    database.run_migrations(db_path)
    conn = database.get_connection(db_path)
    curriculum_service.seed_curriculum(conn)
    conn.close()

    from app.ui.main_window import OverlayWindow
    win = OverlayWindow()
    win.compact = False
    win.poll_state()
    yield win
    # NOT win.close() -- that triggers the real close-accountability modal
    # (spec section 11) whenever the day isn't finished, which would block
    # forever waiting for a click that never comes in a headless test.
    win.hide()
    win.deleteLater()


def _complete_all_required(day_number: int):
    conn = database.get_connection()
    try:
        for r in conn.execute(
            "SELECT id FROM tasks WHERE day_number = ? AND required = 1", (day_number,)
        ).fetchall():
            prog.complete_task(conn, r["id"])
    finally:
        conn.close()


def _complete_one_task(day_number: int):
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM tasks WHERE day_number = ? AND required = 1 AND completed = 0 "
            "ORDER BY id LIMIT 1", (day_number,)
        ).fetchone()
        prog.complete_task(conn, row["id"])
    finally:
        conn.close()


# --- core acceptance criterion ------------------------------------------------

def test_identical_state_produces_zero_ui_mutation(overlay_window):
    win = overlay_window
    win.rebuild_count = 0
    win.incremental_count = 0
    win.noop_count = 0

    win.poll_state()
    win.poll_state()
    win.poll_state()

    assert win.rebuild_count == 0
    assert win.incremental_count == 0
    assert win.noop_count == 3


def test_100_identical_polls_are_all_noops(overlay_window):
    win = overlay_window
    win.rebuild_count = 0
    win.incremental_count = 0
    win.noop_count = 0
    widget_count_before = win.content_layout.count()
    geometry_before = win.geometry()

    for _ in range(100):
        win.poll_state()

    assert win.rebuild_count == 0
    assert win.incremental_count == 0
    assert win.noop_count == 100
    assert win.content_layout.count() == widget_count_before  # no widget growth
    assert win.geometry() == geometry_before  # no geometry drift


# --- task completion: incremental only, no rebuild ------------------------------

def test_task_completion_triggers_incremental_update_not_rebuild(overlay_window):
    win = overlay_window
    win.rebuild_count = 0
    win.incremental_count = 0

    _complete_one_task(1)  # day 1 has >1 required task, so it stays active
    win.poll_state()

    assert win.rebuild_count == 0
    assert win.incremental_count == 1


def test_task_row_reused_not_recreated_on_incremental_update(overlay_window):
    win = overlay_window
    conn = database.get_connection()
    task_id = conn.execute(
        "SELECT id FROM tasks WHERE day_number = 1 AND required = 1 ORDER BY id LIMIT 1"
    ).fetchone()["id"]
    conn.close()
    row_before = win._task_rows[task_id]

    _complete_one_task(1)
    win.poll_state()

    row_after = win._task_rows[task_id]
    assert row_before is row_after  # same Python object -- never recreated
    assert row_after._completed is True


# --- active day change: exactly one deliberate rebuild --------------------------

def test_active_day_change_triggers_exactly_one_rebuild(overlay_window):
    win = overlay_window
    win.rebuild_count = 0

    _complete_all_required(1)
    win.poll_state()

    assert win.rebuild_count == 1
    conn = database.get_connection()
    assert prog.get_active_day(conn) == 2
    conn.close()

    # idle again after the day change -- must go fully quiet
    win.rebuild_count = 0
    win.incremental_count = 0
    for _ in range(10):
        win.poll_state()
    assert win.rebuild_count == 0
    assert win.incremental_count == 0


# --- compact/expand cycling stability --------------------------------------------

def test_20_compact_expand_cycles_stable(overlay_window):
    win = overlay_window
    widths = set()
    for i in range(20):
        win._toggle_compact()
        widths.add(win.card.width())
        assert win._scroll_area is None or win._scroll_area.minimumHeight() > 0

    # exactly two distinct widths (compact, expanded), never drifting
    assert widths == {310, 372}


def test_compact_expand_does_not_lose_task_rows(overlay_window):
    win = overlay_window
    conn = database.get_connection()
    required_count = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE day_number = 1 AND required = 1"
    ).fetchone()["c"]
    conn.close()

    win.compact = True
    win.poll_state()
    win.compact = False
    win.poll_state()

    assert len(win._task_rows) == required_count


# --- scroll position preservation across a structural rebuild -------------------

def test_scroll_position_preserved_across_structural_rebuild(overlay_window):
    win = overlay_window
    assert win._scroll_area is not None
    win._scroll_area.setMinimumHeight(100)  # force a small viewport so scrolling is meaningful
    win._scroll_area.setMaximumHeight(100)
    win._scroll_area.verticalScrollBar().setValue(20)
    scroll_value_before = win._scroll_area.verticalScrollBar().value()
    assert scroll_value_before > 0

    # Force a structural rebuild via a genuine state change unrelated to
    # scrolling: complete one task (still incremental normally) -- instead
    # simulate a revision becoming newly required, which changes task_ids.
    from app.services import revision_service
    conn = database.get_connection()
    problem_id = conn.execute("SELECT id FROM problems WHERE leetcode_number = 1480").fetchone()["id"]
    revision_service.schedule_revision(conn, problem_id, "red", config.today_local())
    conn.close()

    win.poll_state()  # revision now due today -> task_ids changes -> rebuild

    assert win._scroll_area is not None
    assert win._scroll_area.verticalScrollBar().value() == scroll_value_before


# --- premium fallback title swap counts as structural -----------------------------

def test_premium_fallback_title_change_triggers_rebuild_not_silent_desync(overlay_window):
    """A task's problem can be swapped (spec section 33 premium fallback)
    without its task_id changing. If that weren't part of the structural
    key, the TaskRow would keep showing the OLD problem title forever."""
    win = overlay_window

    for day in range(1, 8):  # advance until Day 8 (has real LeetCode tasks) is active
        _complete_all_required(day)
    win.poll_state()

    conn = database.get_connection()
    assert prog.get_active_day(conn) == 8
    task = conn.execute(
        "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
        "WHERE t.day_number = 8 AND p.leetcode_number = 1"
    ).fetchone()
    conn.close()

    from app.services import leetcode_service
    conn = database.get_connection()
    leetcode_service.apply_premium_fallback(conn, task["id"], "arrays")
    conn.close()

    win.rebuild_count = 0
    win.poll_state()
    assert win.rebuild_count == 1  # title changed -> must rebuild, not go silently stale
