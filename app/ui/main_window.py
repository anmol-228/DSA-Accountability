"""The always-on-top compact/expanded overlay (spec section 9).

REFRESH ARCHITECTURE (flicker fix, see PROJECT_STATE.md "Periodic Flicker
Fix"): the 4-second timer no longer unconditionally destroys and rebuilds
all content. Instead `poll_state()` builds a cheap, comparable `UiSnapshot`
from the database and dispatches:

  - identical snapshot           -> do nothing at all (no widget touched)
  - same structural_key, diff    -> update only the specific widgets whose
                                     value changed (task checkmarks,
                                     progress bar, labels) in place
  - different structural_key     -> the one legitimate case for a full
                                     rebuild: active day changed, the
                                     required task set changed (e.g. a
                                     revision became due), or compact mode
                                     was toggled

`structural_key` = (active_day, post_plan_mode, compact, task_ids,
task_titles) — anything outside that tuple is treated as an incremental
value and never triggers widget destruction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QVBoxLayout, QWidget,
)

from app import config, database
from app.services import (
    curriculum_service,
    progression_service as prog,
    revision_service,
    streak_service,
)
from app.ui import icons, time_estimates
from app.ui.dialogs import (
    CloseAccountabilityDialog, ExerciseTaskDialog, ReflectionDialog, SessionRunnerDialog,
    SimpleTaskDialog,
)
from app.ui.events import bus as ui_event_bus, shutdown_state
from app.ui.theme import Spacing, get_palette
from app.ui.widgets import (
    Divider, ScheduleIndicator, SlimProgressBar, TaskRow, apply_card_shadow, section_label,
)

COMPACT_WIDTH = 310
EXPANDED_WIDTH = 372
TASK_LIST_MAX_HEIGHT = 340

SECTION_MAP = {
    "learn": "LEARN",
    "exercise": "PRACTICE",
    "leetcode": "PRACTICE",
    "revision": "REVISION",
    "concept": "CORE CS",
    "oa": "OA",
    "mock": "MOCK",
    "repair": "WRAP UP",
}
SECTION_DISPLAY_ORDER = ["LEARN", "PRACTICE", "REVISION", "CORE CS", "OA", "MOCK", "WRAP UP"]


def _group_by_section(tasks: list) -> dict[str, list]:
    grouped: dict[str, list] = {name: [] for name in SECTION_DISPLAY_ORDER}
    for t in tasks:
        grouped[SECTION_MAP.get(t["task_type"], "WRAP UP")].append(t)
    return grouped


def _format_month_day(d) -> str:
    """Portable 'Mon D' formatting (no leading zero) — %-d is a Unix-only
    strftime directive and would raise on Windows, the only target
    platform for this app."""
    return f"{d:%b} {d.day}"


def _set_text_if_changed(label: QLabel, text: str) -> None:
    if label.text() != text:
        label.setText(text)


@dataclass(frozen=True)
class UiSnapshot:
    active_day: int | None
    post_plan_mode: bool
    compact: bool
    task_ids: tuple[int, ...]
    task_titles: tuple[str, ...]      # part of structural key too: a premium-fallback
                                       # swap changes a task's problem/title without
                                       # changing its id, and that must still rebuild.
    task_completed: tuple[bool, ...]  # incremental only
    done_count: int
    total_count: int
    percent: int
    schedule_delay_days: int
    streak: int
    best_streak: int
    projected_finish_str: str
    target_finish_str: str
    next_task_title: str | None
    deferred_queue_count: int
    day_title: str
    est_minutes_str: str

    @property
    def structural_key(self):
        return (self.active_day, self.post_plan_mode, self.compact, self.task_ids, self.task_titles)


class OverlayWindow(QWidget):
    def __init__(self, on_open_settings=None, on_open_history=None):
        super().__init__()
        self.on_open_settings = on_open_settings
        self.on_open_history = on_open_history
        self.settings = QSettings("DSAAccountability", "Overlay")
        self.compact = self.settings.value("compact", True, type=bool)
        self._drag_pos: QPoint | None = None
        self.palette_tokens = get_palette()  # Mono Light is the sole active theme for now

        self._last_snapshot: UiSnapshot | None = None
        self._task_rows: dict[int, TaskRow] = {}
        self._scroll_area: QScrollArea | None = None
        # Instrumentation for regression tests / diagnosis (spec section 42) —
        # cheap counters, always on, never logged/printed by default.
        self.rebuild_count = 0
        self.incremental_count = 0
        self.noop_count = 0

        self.setObjectName("overlayRoot")
        # Explicit, stable title so external tooling (single-instance
        # bring-to-front, support diagnostics) can reliably find this
        # window -- it previously had no title at all.
        self.setWindowTitle("DSA Accountability")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumWidth(COMPACT_WIDTH + 2 * Spacing.MAJOR)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(Spacing.MAJOR, Spacing.MAJOR, Spacing.MAJOR, Spacing.MAJOR)

        self.card = QFrame()
        self.card.setObjectName("overlayCard")
        self.card.setProperty("role", "card")
        apply_card_shadow(self.card, self.palette_tokens)  # created once, never recreated
        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(Spacing.MEDIUM, Spacing.NORMAL, Spacing.MEDIUM, Spacing.MEDIUM)
        card_layout.setSpacing(Spacing.SMALL)

        self._build_header(card_layout)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(Spacing.SMALL)
        card_layout.addWidget(self.content)

        self._restore_geometry()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.poll_state)
        self.refresh_timer.start(4000)

        # Cross-thread nudge from the localhost API (e.g. a LeetCode Accepted
        # event) — connected with default AutoConnection, which Qt resolves
        # to a queued connection automatically since the emitting thread
        # differs from this object's (GUI) thread. No direct cross-thread
        # widget access happens anywhere.
        ui_event_bus.state_changed.connect(self.poll_state)

        self.poll_state()

    # --- chrome / drag handling -------------------------------------------------

    def _build_header(self, parent_layout: QVBoxLayout) -> None:
        header = QWidget()
        header.setFixedHeight(24)
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)

        app_label = QLabel("DSA ACCOUNTABILITY")
        app_label.setProperty("role", "app-label")
        row.addWidget(app_label)
        row.addStretch()

        menu_btn = QLabel()
        menu_btn.setPixmap(icons.dots_icon(self.palette_tokens.text_tertiary, 18).pixmap(18, 18))
        menu_btn.setFixedSize(24, 24)
        menu_btn.setAlignment(Qt.AlignCenter)
        menu_btn.setCursor(Qt.PointingHandCursor)
        menu_btn.mousePressEvent = self._open_header_menu
        row.addWidget(menu_btn)

        parent_layout.addWidget(header)
        header.mousePressEvent = self._titlebar_press
        header.mouseMoveEvent = self._titlebar_move

    def _open_header_menu(self, event) -> None:
        menu = QMenu(self)
        toggle_action = menu.addAction("Collapse" if not self.compact else "Expand")
        history_action = menu.addAction("History")
        settings_action = menu.addAction("Settings")
        menu.addSeparator()
        close_action = menu.addAction("Close")

        chosen = menu.exec(self.mapToGlobal(event.position().toPoint() if hasattr(event, "position")
                                             else event.pos()))
        if chosen == toggle_action:
            self._toggle_compact()
        elif chosen == history_action and self.on_open_history:
            self.on_open_history()
        elif chosen == settings_action and self.on_open_settings:
            self.on_open_settings()
        elif chosen == close_action:
            self.close()

    def _titlebar_press(self, event) -> None:
        self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _titlebar_move(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _toggle_compact(self) -> None:
        self.compact = not self.compact
        self.settings.setValue("compact", self.compact)
        # `compact` is part of structural_key, so this alone guarantees the
        # next poll_state() performs exactly one deliberate rebuild.
        self.poll_state()

    def _restore_geometry(self) -> None:
        pos = self.settings.value("pos")
        if pos is not None:
            self.move(pos)
        else:
            self.move(80, 80)

    def moveEvent(self, event) -> None:
        self.settings.setValue("pos", self.pos())
        super().moveEvent(event)

    # --- snapshot / dispatch -------------------------------------------------------

    def _build_snapshot(self, conn) -> UiSnapshot:
        status = prog.get_status(conn)
        if status.post_plan_mode:
            return UiSnapshot(
                active_day=None, post_plan_mode=True, compact=self.compact,
                task_ids=(), task_titles=(), task_completed=(),
                done_count=0, total_count=0, percent=0,
                schedule_delay_days=0, streak=0, best_streak=0,
                projected_finish_str="", target_finish_str="",
                next_task_title=None, deferred_queue_count=0,
                day_title="", est_minutes_str="",
            )

        active = status.active_day
        # Idempotent bookkeeping, not a UI operation: only inserts new
        # required-today revision tasks when genuinely due (spec section 10 —
        # polling/computation is fine, it's UI reconstruction that isn't).
        revision_service.generate_required_today(conn, active, status.today)
        day = curriculum_service.get_day(conn, active)
        tasks = curriculum_service.get_tasks_for_day(conn, active)
        required = [t for t in tasks if t["required"]]
        remaining = [t for t in required if not t["completed"]]
        done_count = len(required) - len(remaining)
        total_count = len(required)
        percent = round(100 * done_count / total_count) if total_count else 0

        streak = streak_service.current_activity_streak(conn)
        best = streak_service.best_activity_streak(conn)
        deferred = revision_service.deferred_queue(conn, status.today)
        est = time_estimates.format_minutes(time_estimates.estimate_total_minutes(required))

        return UiSnapshot(
            active_day=active, post_plan_mode=False, compact=self.compact,
            task_ids=tuple(t["id"] for t in required),
            task_titles=tuple(t["title"] for t in required),
            task_completed=tuple(bool(t["completed"]) for t in required),
            done_count=done_count, total_count=total_count, percent=percent,
            schedule_delay_days=status.schedule_delay_days, streak=streak, best_streak=best,
            projected_finish_str=_format_month_day(status.projected_finish),
            target_finish_str=_format_month_day(status.original_target_end),
            next_task_title=remaining[0]["title"] if remaining else None,
            deferred_queue_count=len(deferred),
            day_title=day["title"], est_minutes_str=est,
        )

    def poll_state(self) -> None:
        """The ONLY entry point for the timer, the cross-thread event bus,
        and every user action that might have changed state (task dialog
        closed, compact toggled). Does zero UI work when nothing changed."""
        conn = database.get_connection()
        try:
            snapshot = self._build_snapshot(conn)
            if snapshot == self._last_snapshot:
                self.noop_count += 1
                return

            structural_changed = (
                self._last_snapshot is None
                or snapshot.structural_key != self._last_snapshot.structural_key
            )
            if structural_changed:
                self._rebuild(conn, snapshot)
                self.rebuild_count += 1
            else:
                self._apply_incremental(snapshot)
                self.incremental_count += 1
            self._last_snapshot = snapshot
        finally:
            conn.close()

    # Back-compat alias — existing call sites / QA scripts call `.refresh()`.
    refresh = poll_state

    # --- structural rebuild (only path allowed to touch geometry) ------------------

    def _clear_content(self) -> None:
        """Removes every widget from content_layout immediately (not just
        scheduling deletion) so consecutive rebuilds can never leave a
        stale widget overlapping the newly built layout."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._task_rows = {}
        self._scroll_area = None

    def _rebuild(self, conn, snapshot: UiSnapshot) -> None:
        saved_scroll_value = None
        if self._scroll_area is not None:
            saved_scroll_value = self._scroll_area.verticalScrollBar().value()

        self._clear_content()
        self.card.setFixedWidth(COMPACT_WIDTH if self.compact else EXPANDED_WIDTH)

        if snapshot.post_plan_mode:
            self._render_post_plan_mode()
            self._settle_layout()
            return

        self._render_day_header(snapshot)
        self._render_progress(snapshot)

        if self.compact:
            self._render_compact_body(snapshot)
        else:
            self._render_task_sections(conn, snapshot)
            self._render_expanded_footer(conn, snapshot)

        self._settle_layout()

        if saved_scroll_value is not None and self._scroll_area is not None:
            self._scroll_area.verticalScrollBar().setValue(saved_scroll_value)

    def _settle_layout(self) -> None:
        """Forces synchronous geometry recomputation top-down before
        resizing the window. Only called from _rebuild() — i.e. at most
        once per genuine structural change, never on an unconditional
        timer tick (that was the root cause of the periodic flicker; see
        PROJECT_STATE.md)."""
        self.content.updateGeometry()
        self.content.layout().activate()
        self.card.updateGeometry()
        self.card.layout().activate()
        self.layout().activate()
        self.adjustSize()

    def _render_post_plan_mode(self) -> None:
        title = QLabel("All 135 days complete")
        title.setProperty("role", "day-indicator")
        subtitle = QLabel("Post-plan mode — nothing left to unlock.")
        subtitle.setProperty("role", "metadata")
        subtitle.setWordWrap(True)
        self.content_layout.addWidget(title)
        self.content_layout.addWidget(subtitle)

    def _render_day_header(self, snapshot: UiSnapshot) -> None:
        top_row = QHBoxLayout()
        day_label = QLabel(f"DAY {snapshot.active_day:02d} / {config.TOTAL_CURRICULUM_DAYS}")
        day_label.setProperty("role", "day-indicator")
        top_row.addWidget(day_label)
        top_row.addStretch()
        self._percent_label = QLabel(f"{snapshot.percent}%")
        self._percent_label.setProperty("role", "metadata-strong")
        top_row.addWidget(self._percent_label)
        top_wrap = QWidget()
        top_wrap.setLayout(top_row)
        self.content_layout.addWidget(top_wrap)

        topic_label = QLabel(snapshot.day_title)
        topic_label.setProperty("role", "topic")
        topic_label.setWordWrap(True)
        self.content_layout.addWidget(topic_label)

        if not self.compact and snapshot.est_minutes_str:
            est_label = QLabel(snapshot.est_minutes_str)
            est_label.setProperty("role", "metadata")
            self.content_layout.addWidget(est_label)

    def _render_progress(self, snapshot: UiSnapshot) -> None:
        row = QHBoxLayout()
        self._progress_text_label = QLabel(
            f"{snapshot.done_count} of {snapshot.total_count} complete" if snapshot.total_count
            else "Nothing required"
        )
        self._progress_text_label.setProperty("role", "metadata")
        row.addWidget(self._progress_text_label)
        row.addStretch()
        wrap = QWidget()
        wrap.setLayout(row)
        self.content_layout.addWidget(wrap)

        self._progress_bar = SlimProgressBar(self.palette_tokens)
        self._progress_bar.setValue(
            100 * snapshot.done_count / snapshot.total_count if snapshot.total_count else 0
        )
        self.content_layout.addWidget(self._progress_bar)

    def _render_task_sections(self, conn, snapshot: UiSnapshot) -> None:
        required = curriculum_service.get_tasks_for_day(conn, snapshot.active_day)
        required = [t for t in required if t["required"]]

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, Spacing.SMALL, 0, 0)
        scroll_layout.setSpacing(Spacing.NORMAL)

        grouped = _group_by_section(required)
        any_section = False
        for section_name in SECTION_DISPLAY_ORDER:
            items = grouped[section_name]
            if not items:
                continue
            any_section = True
            header_row = QHBoxLayout()
            count_label = section_label(f"{section_name} · {len(items)} ITEM{'S' if len(items) != 1 else ''}")
            header_row.addWidget(count_label)
            header_row.addStretch()
            est = time_estimates.format_minutes(time_estimates.estimate_total_minutes(items))
            if est:
                est_label = QLabel(est)
                est_label.setProperty("role", "metadata")
                header_row.addWidget(est_label)
            header_wrap = QWidget()
            header_wrap.setLayout(header_row)
            scroll_layout.addWidget(header_wrap)
            scroll_layout.addWidget(Divider())

            for t in items:
                row = TaskRow(t["title"], bool(t["completed"]), self.palette_tokens)
                row.clicked.connect(lambda t=t: self._open_task_dialog(t["id"]))
                scroll_layout.addWidget(row)
                self._task_rows[t["id"]] = row

        if not any_section:
            empty = QLabel("Nothing required today.")
            empty.setProperty("role", "metadata")
            scroll_layout.addWidget(empty)

        scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(scroll_content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # Deliberately NOT overriding sizePolicy to Maximum here: that
        # policy tells the layout engine "prefer to shrink, sizeHint is
        # only a ceiling" — that previously caused the task list to
        # visibly collapse across repeated toggles. Default policy plus an
        # explicit min/max pair gives a stable, correct height.
        natural_height = scroll_content.sizeHint().height()
        target_height = min(natural_height, TASK_LIST_MAX_HEIGHT)
        scroll.setMinimumHeight(target_height)
        scroll.setMaximumHeight(TASK_LIST_MAX_HEIGHT)
        self.content_layout.addWidget(scroll)
        self._scroll_area = scroll

    def _render_compact_body(self, snapshot: UiSnapshot) -> None:
        next_row = QVBoxLayout()
        next_row.addWidget(section_label("NEXT"))
        self._next_label = QLabel(snapshot.next_task_title or "All required tasks done — nice.")
        self._next_label.setProperty("role", "body")
        self._next_label.setWordWrap(True)
        next_row.addWidget(self._next_label)
        next_wrap = QWidget()
        next_wrap.setLayout(next_row)
        self.content_layout.addWidget(next_wrap)

        footer = QHBoxLayout()
        self._schedule_indicator = ScheduleIndicator(self.palette_tokens)
        self._schedule_indicator.set_status(snapshot.schedule_delay_days)
        footer.addWidget(self._schedule_indicator)
        footer.addStretch()
        self._streak_label = QLabel(f"Streak {snapshot.streak}")
        self._streak_label.setProperty("role", "metadata")
        footer.addWidget(self._streak_label)
        footer_wrap = QWidget()
        footer_wrap.setLayout(footer)
        self.content_layout.addWidget(footer_wrap)

        self._best_label = None
        self._finish_label = None
        self._revision_queue_label = None

    def _render_expanded_footer(self, conn, snapshot: UiSnapshot) -> None:
        self.content_layout.addWidget(Divider())

        schedule_row = QHBoxLayout()
        self._schedule_indicator = ScheduleIndicator(self.palette_tokens)
        self._schedule_indicator.set_status(snapshot.schedule_delay_days)
        schedule_row.addWidget(self._schedule_indicator)
        schedule_row.addStretch()
        schedule_wrap = QWidget()
        schedule_wrap.setLayout(schedule_row)
        self.content_layout.addWidget(schedule_wrap)

        self._finish_label = QLabel(self._finish_text(snapshot))
        self._finish_label.setProperty("role", "metadata")
        self.content_layout.addWidget(self._finish_label)

        self._revision_queue_label = QLabel(f"Revision queue · {snapshot.deferred_queue_count} pending")
        self._revision_queue_label.setProperty("role", "metadata")
        self._revision_queue_label.setVisible(snapshot.deferred_queue_count > 0)
        self.content_layout.addWidget(self._revision_queue_label)

        streak_row = QHBoxLayout()
        self._streak_label = QLabel(f"Streak  {snapshot.streak} days")
        self._streak_label.setProperty("role", "metadata-strong")
        self._best_label = QLabel(f"Best  {snapshot.best_streak}")
        self._best_label.setProperty("role", "metadata")
        streak_row.addWidget(self._streak_label)
        streak_row.addStretch()
        streak_row.addWidget(self._best_label)
        streak_wrap = QWidget()
        streak_wrap.setLayout(streak_row)
        self.content_layout.addWidget(streak_wrap)

        next_day = snapshot.active_day + 1
        if next_day <= config.TOTAL_CURRICULUM_DAYS:
            hint = QLabel(f"Finish Day {snapshot.active_day:02d} to unlock Day {next_day:02d}")
            hint.setProperty("role", "metadata")
            hint.setWordWrap(True)
            self.content_layout.addWidget(hint)

        self._next_label = None

        footer_btns = QHBoxLayout()
        history_btn = QLabel("History")
        history_btn.setProperty("role", "metadata-strong")
        history_btn.setCursor(Qt.PointingHandCursor)
        if self.on_open_history:
            history_btn.mousePressEvent = lambda e: self.on_open_history()
        settings_btn = QLabel("Settings")
        settings_btn.setProperty("role", "metadata-strong")
        settings_btn.setCursor(Qt.PointingHandCursor)
        if self.on_open_settings:
            settings_btn.mousePressEvent = lambda e: self.on_open_settings()
        footer_btns.addWidget(history_btn)
        footer_btns.addStretch()
        footer_btns.addWidget(settings_btn)
        footer_wrap = QWidget()
        footer_wrap.setLayout(footer_btns)
        self.content_layout.addWidget(footer_wrap)

    @staticmethod
    def _finish_text(snapshot: UiSnapshot) -> str:
        if snapshot.schedule_delay_days > 0:
            return f"Projected finish · {snapshot.projected_finish_str}"
        return f"Target finish · {snapshot.target_finish_str}"

    # --- incremental update (no widget creation/destruction, ever) -----------------

    def _apply_incremental(self, snapshot: UiSnapshot) -> None:
        for task_id, completed in zip(snapshot.task_ids, snapshot.task_completed):
            row = self._task_rows.get(task_id)
            if row is not None:
                row.set_completed(completed)  # itself a no-op if unchanged

        if hasattr(self, "_percent_label"):
            _set_text_if_changed(self._percent_label, f"{snapshot.percent}%")
        if hasattr(self, "_progress_text_label"):
            text = (f"{snapshot.done_count} of {snapshot.total_count} complete"
                    if snapshot.total_count else "Nothing required")
            _set_text_if_changed(self._progress_text_label, text)
        if hasattr(self, "_progress_bar"):
            new_value = 100 * snapshot.done_count / snapshot.total_count if snapshot.total_count else 0
            self._progress_bar.setValue(new_value)  # SlimProgressBar.update() only repaints on real change

        if getattr(self, "_schedule_indicator", None) is not None:
            self._schedule_indicator.set_status(snapshot.schedule_delay_days)

        if getattr(self, "_next_label", None) is not None:
            _set_text_if_changed(
                self._next_label, snapshot.next_task_title or "All required tasks done — nice."
            )

        if getattr(self, "_streak_label", None) is not None:
            text = f"Streak {snapshot.streak}" if self.compact else f"Streak  {snapshot.streak} days"
            _set_text_if_changed(self._streak_label, text)
        if getattr(self, "_best_label", None) is not None:
            _set_text_if_changed(self._best_label, f"Best  {snapshot.best_streak}")
        if getattr(self, "_finish_label", None) is not None:
            _set_text_if_changed(self._finish_label, self._finish_text(snapshot))
        if getattr(self, "_revision_queue_label", None) is not None:
            _set_text_if_changed(
                self._revision_queue_label, f"Revision queue · {snapshot.deferred_queue_count} pending"
            )
            if self._revision_queue_label.isVisible() != (snapshot.deferred_queue_count > 0):
                self._revision_queue_label.setVisible(snapshot.deferred_queue_count > 0)

    def _open_task_dialog(self, task_id: int) -> None:
        conn = database.get_connection()
        try:
            task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if task_row is None or task_row["completed"]:
                return
            if task_row["task_type"] in ("leetcode", "revision"):
                problem = conn.execute(
                    "SELECT * FROM problems WHERE id = ?", (task_row["problem_id"],)
                ).fetchone()
                dlg = ReflectionDialog(conn, task_row, problem, parent=self)
                dlg.exec()
            elif task_row["task_type"] in ("oa", "mock"):
                problems = conn.execute(
                    "SELECT p.* FROM task_problem_links l JOIN problems p ON l.problem_id = p.id "
                    "WHERE l.task_id = ?", (task_row["id"],),
                ).fetchall()
                meta = json.loads(task_row["description"] or "{}")
                minutes = meta.get("minutes", 60)
                dlg = SessionRunnerDialog(conn, task_row, problems, minutes, parent=self)
                dlg.exec()
            elif task_row["task_type"] == "exercise":
                dlg = ExerciseTaskDialog(conn, task_row, parent=self)
                dlg.exec()
            else:
                dlg = SimpleTaskDialog(conn, task_row, parent=self)
                dlg.exec()
        finally:
            conn.close()
        # Whatever just happened (task completed, day completed, or the
        # dialog was cancelled with nothing changed) is exactly what
        # poll_state() already knows how to handle correctly and minimally.
        self.poll_state()

    # --- close accountability (spec section 11) ------------------------------------

    def closeEvent(self, event) -> None:
        if shutdown_state.in_progress:
            # A real Windows shutdown/restart/logoff, not a user clicking
            # the X. Nobody is present to answer the close-accountability
            # modal, and blocking an OS session end is explicitly a
            # non-goal for this app (see PROJECT_STATE.md "Shutdown
            # Blocking Fix") — just let the window close.
            event.accept()
            return
        conn = database.get_connection()
        try:
            active = prog.get_active_day(conn)
            if active is None:
                event.accept()
                return
            remaining = prog.remaining_required_count(conn, active)
            if remaining == 0:
                self.hide()
                event.ignore()
                return
            dlg = CloseAccountabilityDialog(conn, active, remaining, parent=self)
            dlg.exec()
            if dlg.emergency_exit_confirmed:
                event.accept()
            else:
                event.ignore()
        finally:
            conn.close()
