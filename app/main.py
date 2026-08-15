"""Entry point: wires database, curriculum seeding, the localhost API
server, the always-on-top overlay, a system tray icon, and periodic
reminders together."""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
from pathlib import Path

# Allows `python app\main.py` to work directly (not just `python -m app.main`)
# by putting the project root on sys.path before the `app.*` imports below
# resolve. When imported normally (PyInstaller bundle, `-m app.main`),
# __package__ is already "app" and this is a no-op.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from app import build_info, config, database
from app.api.local_server import LocalAPIServer
from app.services import (
    curriculum_service,
    github_sync_service,
    integration_test_service,
    pipeline_service,
    progression_service,
    reminder_service,
    schedule_service,
    single_instance,
)
from app.ui import icons
from app.ui.events import shutdown_state
from app.ui.first_run_wizard import FirstRunWizard
from app.ui.history_dialog import HistoryDialog
from app.ui.main_window import OverlayWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.theme import build_qss, get_palette

def _emergency_log(message: str) -> None:
    """Writes to a location that's writable regardless of anything about
    %LOCALAPPDATA%\\DSAAccountability being ready yet -- %TEMP% always
    exists for a logged-in user. Exists because a real autostart-launched
    process was observed this session showing stale/wrong UI data with
    ZERO corresponding entry in the normal app.log, meaning something
    failed or diverged before or during the normal logging.basicConfig
    path -- and that evidence was lost before it could be inspected.
    This never raises itself, even if writing fails.
    """
    try:
        import datetime
        p = Path(os.environ.get("TEMP", ".")) / "DSAAccountability_emergency.log"
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} pid={os.getpid()} argv={sys.argv} {message}\n")
    except Exception:  # noqa: BLE001 - this function must never itself crash startup
        pass


class _EmergencyFallbackFileHandler(logging.FileHandler):
    """Python's logging module deliberately swallows errors raised while
    emitting a record (Handler.handleError), printing a traceback to
    sys.stderr as its only trace -- but a PyInstaller --windowed build has
    sys.stderr = None, so handleError's own `if sys.stderr:` guard makes
    that swallow completely silent. A real autostart-launched process was
    observed alive, responsive, and correctly serving API requests, yet
    app.log had ZERO lines from it -- consistent with exactly this: the
    FileHandler opened fine (no exception during logging.basicConfig
    itself) but a later write failed (e.g. a transient sharing violation
    against a process that had just released app.log) and vanished
    without a trace. Routing handleError to the emergency log -- which
    never goes through the logging module itself -- makes that failure
    mode provable instead of invisible."""

    def handleError(self, record: logging.LogRecord) -> None:
        try:
            import traceback
            _emergency_log(
                "logging FileHandler failed to emit a record: "
                f"{record.getMessage()!r}\n{traceback.format_exc()}"
            )
        except Exception:  # noqa: BLE001
            pass


config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
_log_handler = _EmergencyFallbackFileHandler(str(config.LOGS_DIR / "app.log"))
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger("dsa.main")

GITHUB_RETRY_INTERVAL_MS = 3 * 60 * 1000  # periodic drain check; per-row backoff decides what actually retries


def main() -> int:
    _emergency_log("main() entered")
    minimized = "--minimized" in sys.argv

    # Single-instance guard runs BEFORE any database/UI work -- two
    # processes opening the same SQLite file, binding two different
    # localhost API ports, and duplicating the startup reminder was a real
    # risk from autostart + a manual launch overlapping (production
    # stabilization pass, section 32). No DB connection is opened at all
    # if another instance already owns the lock.
    acquired = single_instance.acquire()
    _emergency_log(f"single_instance.acquire() -> {acquired}")
    if not acquired:
        logger.info("Another instance is already running; bringing it forward and exiting.")
        single_instance.bring_existing_instance_forward()
        return 0

    database.init_db()
    conn = database.get_connection()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(build_qss(get_palette()))

    first_run_row = conn.execute(
        "SELECT value FROM settings WHERE key = 'first_run_complete'"
    ).fetchone()
    if first_run_row is None:
        wizard = FirstRunWizard(conn)
        if wizard.exec() == 0:
            conn.close()
            single_instance.release()
            return 0
    else:
        # Existing installations predate configurable schedules. Infer and
        # persist their already-seeded Day 1 without changing a single date.
        schedule_service.ensure_existing_installation_setting(conn)

    curriculum_service.seed_curriculum(conn)
    curriculum_service.backfill_canonical_filenames(conn)
    progression_service.reschedule_original_dates(conn)
    if integration_test_service.clear_on_startup(conn):
        logger.warning("Cleared stale live-integration-test state and disposable repo on startup")

    # One-time-per-launch diagnostic snapshot (spec: production
    # stabilization pass, section 4/68/22/90). Never logs the raw token --
    # only presence and a non-reversible sha256[:8] fingerprint, so a
    # future "token changed after reboot" report can be checked against
    # this log's history without ever having exposed the secret itself.
    # Also makes "which DB/paths/repo/port did this launch actually use"
    # provable after the fact.
    first_run_present = conn.execute(
        "SELECT 1 FROM settings WHERE key = 'first_run_complete'"
    ).fetchone() is not None
    token_row = conn.execute(
        "SELECT value FROM settings WHERE key = 'pairing_token'"
    ).fetchone()
    token_fingerprint = hashlib.sha256(token_row["value"].encode()).hexdigest()[:8] if token_row else None
    repo_row = conn.execute(
        "SELECT value FROM settings WHERE key = 'dsa135_repo_path'"
    ).fetchone()
    logger.info(
        "startup: pid=%s frozen=%s exe=%s resource_root=%s data_root=%s db=%s "
        "first_run_complete=%s pairing_token_fingerprint=%s repo_path=%s minimized=%s "
        "build_version=%s build_commit=%s build_dirty=%s built_at=%s",
        os.getpid(), config.IS_FROZEN, sys.executable, config.RESOURCE_ROOT,
        config.DATA_DIR.parent, config.DB_PATH,
        first_run_present, token_fingerprint, repo_row["value"] if repo_row else None, minimized,
        build_info.get_build_info()["version"], build_info.get_build_info()["commit"],
        build_info.get_build_info()["dirty"], build_info.get_build_info()["built_at"],
    )

    def _on_session_ending(session_manager) -> None:
        """Windows sends WM_QUERYENDSESSION on shutdown/restart/logoff;
        Qt surfaces it as commitDataRequest BEFORE any window's
        closeEvent fires. Mark it so the overlay skips its interactive
        close-accountability modal (nobody is present to answer it during
        a real OS shutdown) and never delays or blocks the session end."""
        shutdown_state.in_progress = True
        session_manager.release()

    app.commitDataRequest.connect(_on_session_ending)

    api_server = LocalAPIServer()
    api_server.start()
    logger.info("Local API started on port %s", api_server.port)

    conn.close()

    def open_settings() -> None:
        c = database.get_connection()
        try:
            SettingsDialog(c, parent=window).exec()
        finally:
            c.close()

    def open_history() -> None:
        c = database.get_connection()
        try:
            HistoryDialog(c, parent=window).exec()
        finally:
            c.close()

    window = OverlayWindow(on_open_settings=open_settings, on_open_history=open_history)
    if not minimized:
        window.show()

    tray = QSystemTrayIcon(icons.app_icon())
    tray.setToolTip("DSA Accountability")
    menu = QMenu()
    show_action = menu.addAction("Show / Hide")
    show_action.triggered.connect(lambda: window.hide() if window.isVisible() else window.show())
    quit_action = menu.addAction("Quit DSA Accountability")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.show() if reason == QSystemTrayIcon.Trigger else None)
    tray.show()

    def show_startup_reminder() -> None:
        """Fires at most ONCE per app launch (i.e. once per PC sign-in if
        autostart is enabled) — never on a recurring timer — and only if
        there's genuinely required work left today."""
        c = database.get_connection()
        try:
            due = reminder_service.startup_reminder(c)
            if due:
                tray.showMessage("DSA Accountability", due["message"], QSystemTrayIcon.Information, 8000)
        finally:
            c.close()

    QTimer.singleShot(3000, show_startup_reminder)

    def _drain_github_queue_in_background() -> None:
        """Runs github_sync_service.drain_due_pushes off the GUI thread --
        it shells out to real `git push`, which can take seconds (up to a
        60s timeout) and must never freeze the overlay. Safe to call
        repeatedly: each row has its own backoff window, so most calls do
        nothing. Fixes the previously-dead process_queue() gap (production
        stabilization pass, section 25-29) -- a push that failed with a
        retryable error used to stay 'pending' forever with nothing ever
        retrying it automatically."""
        def _worker() -> None:
            c = database.get_connection()
            try:
                repo_path = pipeline_service.get_dsa135_repo(c)
                result = github_sync_service.drain_due_pushes(c, repo_path)
                if result["pushed"] or result["still_pending"]:
                    logger.info("GitHub retry drain: %s", result)
            except Exception:  # noqa: BLE001 - background maintenance, never crash the app
                logger.exception("GitHub retry drain failed")
            finally:
                c.close()
        threading.Thread(target=_worker, daemon=True).start()

    QTimer.singleShot(5000, _drain_github_queue_in_background)
    github_retry_timer = QTimer()
    github_retry_timer.timeout.connect(_drain_github_queue_in_background)
    github_retry_timer.start(GITHUB_RETRY_INTERVAL_MS)

    exit_code = app.exec()
    api_server.stop()
    return exit_code


if __name__ == "__main__":
    _emergency_log("process reached __main__, about to call main()")
    try:
        exit_code = main()
    except Exception:
        import traceback
        _emergency_log("UNCAUGHT EXCEPTION in main():\n" + traceback.format_exc())
        raise
    _emergency_log(f"main() returned exit_code={exit_code}")
    sys.exit(exit_code)
