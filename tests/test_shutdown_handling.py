"""Regression tests for the shutdown-blocking fix (see PROJECT_STATE.md
"Shutdown Blocking Fix"). A real Windows shutdown/restart/logoff must
never be delayed by the interactive close-accountability modal — nobody
is present to answer it. Runs headless; no real progress DB touched.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app import config, database
from app.services import curriculum_service


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def overlay_window(qapp, tmp_path, monkeypatch):
    db_path = tmp_path / "shutdown_test.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    database.run_migrations(db_path)
    conn = database.get_connection(db_path)
    curriculum_service.seed_curriculum(conn)
    conn.close()

    from app.ui.events import shutdown_state
    shutdown_state.in_progress = False  # tests must never leak state to each other

    from app.ui.main_window import OverlayWindow
    win = OverlayWindow()
    win.compact = False
    win.poll_state()
    yield win
    shutdown_state.in_progress = False
    win.hide()
    win.deleteLater()


def _make_close_event():
    from PySide6.QtGui import QCloseEvent
    return QCloseEvent()


def test_shutdown_in_progress_closes_without_any_modal(overlay_window, monkeypatch):
    """The core bug: during a real OS shutdown, the app must not show a
    dialog nobody can answer. Patches CloseAccountabilityDialog to raise
    if constructed at all, proving the modal path is never reached."""
    from app.ui.events import shutdown_state
    import app.ui.main_window as mw_module

    def _must_not_be_called(*a, **kw):
        raise AssertionError("CloseAccountabilityDialog must not be constructed during shutdown")

    monkeypatch.setattr(mw_module, "CloseAccountabilityDialog", _must_not_be_called)

    shutdown_state.in_progress = True
    event = _make_close_event()
    overlay_window.closeEvent(event)

    assert event.isAccepted()


def test_normal_close_with_incomplete_day_still_shows_modal(overlay_window, monkeypatch):
    """Regression guard the other way: a real user clicking X on an
    incomplete day must still see the accountability prompt — the
    shutdown fix must not silently disable it for ordinary use."""
    from app.ui.events import shutdown_state
    import app.ui.main_window as mw_module

    shutdown_state.in_progress = False
    calls = []

    class FakeDialog:
        def __init__(self, conn, active, remaining, parent=None):
            calls.append((active, remaining))
            self.emergency_exit_confirmed = False

        def exec(self):
            return 0  # simulate "Return to DSA" -- user did not confirm emergency exit

    monkeypatch.setattr(mw_module, "CloseAccountabilityDialog", FakeDialog)

    event = _make_close_event()
    overlay_window.closeEvent(event)

    assert len(calls) == 1  # the modal WAS shown for a genuine user-initiated close
    assert not event.isAccepted()  # and the window correctly stayed open


def test_normal_close_with_confirmed_emergency_exit_closes(overlay_window, monkeypatch):
    from app.ui.events import shutdown_state
    import app.ui.main_window as mw_module

    shutdown_state.in_progress = False

    class FakeDialog:
        def __init__(self, conn, active, remaining, parent=None):
            self.emergency_exit_confirmed = True

        def exec(self):
            return 1

    monkeypatch.setattr(mw_module, "CloseAccountabilityDialog", FakeDialog)

    event = _make_close_event()
    overlay_window.closeEvent(event)

    assert event.isAccepted()


def test_shutdown_flag_defaults_false(overlay_window):
    """Sanity check on the fixture/module itself: nothing leaves the flag
    set between tests, which would silently disable the real feature."""
    from app.ui.events import shutdown_state
    assert shutdown_state.in_progress is False
