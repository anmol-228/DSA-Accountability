"""A single process-wide Qt signal used to let background threads (the
localhost API server thread) ask the GUI thread to poll state promptly,
instead of waiting for the next periodic timer tick.

Safe by construction: `bus` is a QObject created on the GUI thread (import
happens there first, during app startup). When a different thread calls
`bus.state_changed.emit()`, Qt automatically delivers it via a queued
connection to any GUI-thread slot connected to it — this is the standard,
documented-safe way to notify a Qt GUI thread from a worker thread. No
QWidget method is ever called directly from a non-GUI thread.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class _UiEventBus(QObject):
    state_changed = Signal()


bus = _UiEventBus()


class _ShutdownState:
    """Set True when Windows is ending the session (shutdown/restart/
    logoff) via QApplication.commitDataRequest, BEFORE any window's
    closeEvent fires. OverlayWindow.closeEvent checks this and skips the
    close-accountability modal in that case — the app must never block or
    delay an OS shutdown (that was an explicit non-goal from day one; see
    PROJECT_STATE.md "Shutdown Blocking Fix"). A modal dialog with nobody
    present to answer it is exactly what caused Windows to report this app
    as "preventing shutdown"."""
    in_progress = False


shutdown_state = _ShutdownState()
