"""Dialogs: reflection form, simple-task completion, close accountability +
emergency exit, and a lightweight OA/mock session runner.

VISUAL REDESIGN NOTE: restyled for the mono light widget redesign (button
variants, label roles, no emoji/loud color). All functional behavior —
validation rules, pipeline calls, signals — is unchanged from before.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QRadioButton, QTextEdit, QVBoxLayout, QWidget,
)

from app import config
from app.services import pipeline_service
from app.ui.theme import Spacing, get_palette
from app.ui.widgets import (
    Divider, SlimProgressBar, metadata_label, primary_button as _primary_button,
    section_label, tertiary_button as _tertiary_button,
)


def _set_text_if_changed(label: QLabel, text: str) -> None:
    if label.text() != text:
        label.setText(text)


def _title_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "day-indicator")
    lbl.setStyleSheet("font-size: 15pt;")
    lbl.setWordWrap(True)
    return lbl


class ReflectionDialog(QDialog):
    """Mandatory reflection before a LeetCode/revision task is finalized
    (spec section 22). AI-generated text is never substituted for the
    user's own explanation — the Finalize button stays disabled until the
    explanation field is non-trivial."""

    def __init__(self, conn, task_row, problem_row, prefill_code: str = "", parent=None):
        super().__init__(parent)
        self.conn = conn
        self.task_row = task_row
        self.problem_row = problem_row
        self.setWindowTitle(f"LC {problem_row['leetcode_number']} — {problem_row['title']}")
        self.setMinimumWidth(460)
        self._build_ui(prefill_code)

    def _build_ui(self, prefill_code: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.NORMAL)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)

        layout.addWidget(_title_label(f"LC {self.problem_row['leetcode_number']} — {self.problem_row['title']}"))

        layout.addWidget(section_label("YOUR JAVA CODE"))
        self.code_edit = QTextEdit()
        self.code_edit.setPlainText(prefill_code)
        self.code_edit.setMinimumHeight(120)
        self.code_edit.setStyleSheet("font-family: Consolas, monospace;")
        layout.addWidget(self.code_edit)

        layout.addWidget(section_label("PATTERN"))
        self.pattern_edit = QLineEdit()
        layout.addWidget(self.pattern_edit)

        row = QHBoxLayout()
        row.setSpacing(Spacing.NORMAL)
        time_col = QVBoxLayout()
        time_col.addWidget(metadata_label("TIME"))
        self.time_edit = QLineEdit()
        self.time_edit.setPlaceholderText("O(n)")
        time_col.addWidget(self.time_edit)
        space_col = QVBoxLayout()
        space_col.addWidget(metadata_label("SPACE"))
        self.space_edit = QLineEdit()
        self.space_edit.setPlaceholderText("O(1)")
        space_col.addWidget(self.space_edit)
        row.addLayout(time_col)
        row.addLayout(space_col)
        layout.addLayout(row)

        layout.addWidget(section_label("YOUR EXPLANATION"))
        self.explanation_edit = QTextEdit()
        self.explanation_edit.setPlaceholderText("Explain your approach in your own words…")
        self.explanation_edit.textChanged.connect(self._update_finalize_enabled)
        layout.addWidget(self.explanation_edit)

        layout.addWidget(section_label("ASSISTANCE"))
        self.assist_group = QButtonGroup(self)
        assist_row = QHBoxLayout()
        for i, (label, value) in enumerate([
            ("Independently", "independent"), ("Small hint", "small_hint"),
            ("Significant hint", "significant_hint"), ("Studied solution", "studied_solution"),
        ]):
            rb = QRadioButton(label)
            rb.setProperty("value", value)
            if i == 0:
                rb.setChecked(True)
            self.assist_group.addButton(rb)
            assist_row.addWidget(rb)
        layout.addLayout(assist_row)

        layout.addWidget(section_label("CONFIDENCE"))
        self.confidence_group = QButtonGroup(self)
        conf_row = QHBoxLayout()
        for i, (label, value) in enumerate([("Green", "green"), ("Yellow", "yellow"), ("Red", "red")]):
            rb = QRadioButton(label)
            rb.setProperty("value", value)
            if i == 0:
                rb.setChecked(True)
            self.confidence_group.addButton(rb)
            conf_row.addWidget(rb)
        conf_row.addStretch()
        layout.addLayout(conf_row)

        self.finalize_btn = _primary_button("Finalize")
        self.finalize_btn.setEnabled(False)
        self.finalize_btn.clicked.connect(self._on_finalize)
        layout.addWidget(self.finalize_btn)

    def _update_finalize_enabled(self) -> None:
        text = self.explanation_edit.toPlainText().strip()
        self.finalize_btn.setEnabled(len(text) >= 15)  # must be the user's own words, not a stub

    def _selected(self, group: QButtonGroup) -> str:
        return group.checkedButton().property("value")

    def _on_finalize(self) -> None:
        code = self.code_edit.toPlainText().strip()
        if not code:
            QMessageBox.warning(self, "Code required", "Paste or capture your Java solution before finalizing.")
            return
        reflection = {
            "pattern": self.pattern_edit.text().strip() or None,
            "time_complexity": self.time_edit.text().strip() or None,
            "space_complexity": self.space_edit.text().strip() or None,
            "explanation": self.explanation_edit.toPlainText().strip(),
            "assistance_level": self._selected(self.assist_group),
            "confidence": self._selected(self.confidence_group),
        }
        try:
            result = pipeline_service.finalize_leetcode_task(self.conn, self.task_row["id"], code, reflection)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", str(exc))
            return

        msg = "Local Git commit created.\n"
        msg += "GitHub push complete." if result["push"] == "pushed" else "GitHub push queued — will retry."
        if result.get("day_completed"):
            msg += "\n\nCurriculum day complete — next day unlocked."
        QMessageBox.information(self, "Complete", msg)
        self.accept()


class SimpleTaskDialog(QDialog):
    """For concept / repair tasks — a short reflection note only. No code
    field: standalone Java exercises use ExerciseTaskDialog instead, which
    routes learners to VS Code (spec: "the app must not be a code editor")."""

    def __init__(self, conn, task_row, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.task_row = task_row
        self.setWindowTitle(task_row["title"])
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.NORMAL)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)
        layout.addWidget(_title_label(task_row["title"]))

        layout.addWidget(section_label("NOTE — WHAT YOU LEARNED / DID"))
        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(80)
        layout.addWidget(self.note_edit)

        btn = _primary_button("Mark Complete")
        btn.clicked.connect(self._on_complete)
        layout.addWidget(btn)

    def _on_complete(self) -> None:
        note = self.note_edit.toPlainText().strip() or None
        result = pipeline_service.finalize_simple_task(self.conn, self.task_row["id"], note=note)
        if result.get("day_completed"):
            QMessageBox.information(self, "Complete", "Curriculum day complete — next day unlocked.")
        self.accept()


class _ExerciseValidationWorker(QObject):
    """Runs compile + functional tests on a background QThread so a slow
    compile or a hung/looping learner program (protected by build_service's
    own subprocess timeout) never freezes the dialog's UI thread."""

    finished = Signal(object)  # emits an _ExerciseValidation

    def __init__(self, source_path, canonical_filename: str):
        super().__init__()
        self.source_path = source_path
        self.canonical_filename = canonical_filename

    def run(self) -> None:
        from app.services import build_service, exercise_tests

        source = self.source_path.read_text(encoding="utf-8")
        if build_service.is_skeleton_or_empty(source):
            self.finished.emit(_ExerciseValidation(file_ok=True, is_skeleton=True))
            return

        compile_result = build_service.compile_java(self.source_path, self.canonical_filename)
        if not compile_result.success:
            self.finished.emit(_ExerciseValidation(file_ok=True, is_skeleton=False,
                                                     compiled=False, compile_summary=compile_result.summary))
            return

        suite = exercise_tests.run_functional_tests(
            self.canonical_filename, self.canonical_filename, compile_result.build_dir
        )
        self.finished.emit(_ExerciseValidation(file_ok=True, is_skeleton=False, compiled=True, suite=suite))


@dataclass
class _ExerciseValidation:
    file_ok: bool
    is_skeleton: bool = False
    compiled: bool | None = None
    compile_summary: str = ""
    suite: object = None  # exercise_tests.TestSuiteResult

    @property
    def ready_to_finalize(self) -> bool:
        if not self.file_ok or self.is_skeleton or not self.compiled:
            return False
        if self.suite is None:
            return False
        if not self.suite.defined:
            return True  # no test spec registered for this exercise -- compile pass is the bar
        return self.suite.all_passed


class ExerciseTaskDialog(QDialog):
    """Standalone Java exercise: NEVER an inline code editor. The learner
    writes code in VS Code; this dialog opens the canonical file there,
    watches it for saves, and runs compile + functional-test validation
    automatically, exactly mirroring the LeetCode flow's separation of
    "where you write code" from "where you get held accountable"."""

    VALIDATION_DEBOUNCE_MS = 500

    def __init__(self, conn, task_row, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.task_row = task_row
        self.setWindowTitle(task_row["title"])
        self.setMinimumWidth(460)

        from app.services import pipeline_service as _pipeline, code_sync_service
        repo_root = _pipeline.get_dsa135_repo(conn)
        self.repo_root = repo_root
        self.canonical_filename = task_row["canonical_filename"]
        self.source_path = code_sync_service.exercise_file_path(
            repo_root, task_row["day_number"], self.canonical_filename
        )
        code_sync_service.write_exercise_skeleton_if_missing(self.source_path, self.canonical_filename)

        self._validation: _ExerciseValidation | None = None
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._start_validation)
        self._thread: QThread | None = None
        self._worker: _ExerciseValidationWorker | None = None

        self._build_ui()
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(str(self.source_path))
        self._watcher.fileChanged.connect(self._on_file_changed)

        self._start_validation()  # validate whatever is on disk right now

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.NORMAL)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)

        layout.addWidget(_title_label(self.task_row["title"]))
        layout.addWidget(section_label("JAVA EXERCISE"))

        layout.addWidget(metadata_label("FILE", strong=True))
        file_label = QLabel(self.source_path.name)
        file_label.setProperty("role", "body")
        layout.addWidget(file_label)
        rel = self._relative_path_label()
        rel_label = metadata_label(rel)
        layout.addWidget(rel_label)

        open_row = QHBoxLayout()
        open_vscode_btn = _primary_button("Open in VS Code")
        open_vscode_btn.clicked.connect(self._on_open_vscode)
        open_row.addWidget(open_vscode_btn)
        open_folder_btn = _tertiary_button("Open Folder")
        open_folder_btn.clicked.connect(self._on_open_folder)
        open_row.addWidget(open_folder_btn)
        layout.addLayout(open_row)

        layout.addWidget(Divider())
        layout.addWidget(section_label("VALIDATION"))

        self.file_status = self._status_row(layout, "File")
        self.compile_status = self._status_row(layout, "Compilation")
        self.tests_status = self._status_row(layout, "Tests")

        self.hint_label = QLabel("Save your program in VS Code. Validation runs automatically.")
        self.hint_label.setProperty("role", "metadata")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self.detail_label = QLabel("")
        self.detail_label.setProperty("role", "metadata")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        layout.addWidget(Divider())
        layout.addWidget(section_label("WHAT I LEARNED"))
        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(70)
        layout.addWidget(self.note_edit)

        self.finalize_btn = _primary_button("Finalize Exercise")
        self.finalize_btn.setEnabled(False)
        self.finalize_btn.clicked.connect(self._on_finalize)
        layout.addWidget(self.finalize_btn)

    def _relative_path_label(self) -> str:
        try:
            return str(self.source_path.relative_to(self.repo_root)).replace("\\", " / ")
        except ValueError:
            return str(self.source_path)

    def _status_row(self, layout: QVBoxLayout, label_text: str) -> QLabel:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setProperty("role", "body")
        row.addWidget(label)
        row.addStretch()
        value = QLabel("Waiting")
        value.setProperty("role", "metadata-strong")
        row.addWidget(value)
        wrap = QWidget()
        wrap.setLayout(row)
        layout.addWidget(wrap)
        return value

    # --- file watching --------------------------------------------------------------

    def _on_open_vscode(self) -> None:
        from app.services import vscode_service
        ok, message = vscode_service.open_file_in_vscode(self.source_path, self.repo_root)
        if not ok:
            QMessageBox.warning(self, "VS Code", message)

    def _on_open_folder(self) -> None:
        from app.services import vscode_service
        ok, message = vscode_service.open_folder_in_vscode(self.source_path.parent)
        if not ok:
            QMessageBox.warning(self, "Open Folder", message)

    def _on_file_changed(self, path: str) -> None:
        # Many editors save via write-to-temp-then-rename, which can drop
        # the path from QFileSystemWatcher's list even though the file
        # still exists under the same name -- re-add it so future saves
        # keep being detected.
        if self.source_path.exists() and str(self.source_path) not in self._watcher.files():
            self._watcher.addPath(str(self.source_path))
        self._debounce_timer.start(self.VALIDATION_DEBOUNCE_MS)  # restarts on every rapid save

    # --- validation --------------------------------------------------------------------

    def _start_validation(self) -> None:
        if not self.source_path.exists():
            self._render_validation(_ExerciseValidation(file_ok=False))
            return
        _set_text_if_changed(self.file_status, "Detected")

        self._thread = QThread(self)
        self._worker = _ExerciseValidationWorker(self.source_path, self.canonical_filename)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._render_validation)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _render_validation(self, validation: _ExerciseValidation) -> None:
        self._validation = validation

        if not validation.file_ok:
            _set_text_if_changed(self.file_status, "Not started")
            _set_text_if_changed(self.compile_status, "Waiting")
            _set_text_if_changed(self.tests_status, "Waiting")
            self.detail_label.setText("")
            self.finalize_btn.setEnabled(False)
            return

        _set_text_if_changed(self.file_status, "Detected")

        if validation.is_skeleton:
            _set_text_if_changed(self.compile_status, "Waiting")
            _set_text_if_changed(self.tests_status, "Waiting")
            self.detail_label.setText("This still looks like the starter skeleton — write your solution and save.")
            self.finalize_btn.setEnabled(False)
            return

        if not validation.compiled:
            _set_text_if_changed(self.compile_status, "Failed")
            _set_text_if_changed(self.tests_status, "Waiting")
            self.detail_label.setText(f"Compilation failed\n\n{validation.compile_summary}\n\n"
                                       f"Fix the code in VS Code and save again.")
            self.finalize_btn.setEnabled(False)
            return

        _set_text_if_changed(self.compile_status, "Passed")
        suite = validation.suite
        if suite is None or not suite.defined:
            _set_text_if_changed(self.tests_status, "N/A")
            self.detail_label.setText("No automated test cases for this exercise — compiled successfully.")
        elif suite.all_passed:
            _set_text_if_changed(self.tests_status, f"{suite.passed} / {suite.total} passed")
            self.detail_label.setText("Ready to finalize.")
        else:
            _set_text_if_changed(self.tests_status, f"{suite.passed} / {suite.total} passed")
            failures = [r for r in suite.results if not r.passed]
            first = failures[0]
            timeout_note = " (timed out)" if first.timed_out else ""
            self.detail_label.setText(
                f"Failed: {first.description}{timeout_note}\n"
                f"Expected: {first.expected}\nReceived: {first.actual}"
            )

        self.finalize_btn.setEnabled(validation.ready_to_finalize)

    def _on_finalize(self) -> None:
        if not (self._validation and self._validation.ready_to_finalize):
            return
        note = self.note_edit.toPlainText().strip()
        if len(note) < 5:
            QMessageBox.warning(self, "Note required", "Add a short note on what you learned first.")
            return
        from app.services import pipeline_service as _pipeline
        try:
            result = _pipeline.finalize_exercise_task(self.conn, self.task_row["id"], note, self.repo_root)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", str(exc))
            return
        if not result["commit"]:
            QMessageBox.warning(self, "Commit failed", result.get("commit_error") or "Local commit failed.")
            return
        msg = "Local Git commit created.\n"
        msg += "GitHub push complete." if result["push"] == "pushed" else "GitHub push queued — will retry."
        if result.get("day_completed"):
            msg += "\n\nCurriculum day complete — next day unlocked."
        QMessageBox.information(self, "Complete", msg)
        self.accept()

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)


class EmergencyExitDialog(QDialog):
    """Press-and-hold ~5 seconds to confirm. Never a single accidental click."""

    HOLD_MS = 5000

    def __init__(self, day_number: int, remaining: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Emergency Exit")
        self.setMinimumWidth(380)
        self.confirmed = False
        self._elapsed = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.NORMAL)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)

        msg = QLabel(
            f"Day {day_number} still has {remaining} required task(s) incomplete.\n"
            "Press and hold the button below for 5 seconds to confirm."
        )
        msg.setProperty("role", "body")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("Optional reason")
        layout.addWidget(self.reason_edit)

        self.progress = SlimProgressBar(get_palette(), height=6)
        layout.addWidget(self.progress)

        self.hold_btn = QPushButton("Hold to confirm emergency exit")
        self.hold_btn.setProperty("variant", "primary")
        self.hold_btn.pressed.connect(self._start_hold)
        self.hold_btn.released.connect(self._cancel_hold)
        layout.addWidget(self.hold_btn)

        cancel_btn = _tertiary_button("Return to DSA")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _start_hold(self) -> None:
        self._elapsed = 0
        self._timer.start(50)

    def _cancel_hold(self) -> None:
        self._timer.stop()
        self.progress.setValue(0)

    def _tick(self) -> None:
        self._elapsed += 50
        self.progress.setValue(100 * self._elapsed / self.HOLD_MS)
        if self._elapsed >= self.HOLD_MS:
            self._timer.stop()
            self.confirmed = True
            self.accept()

    def reason(self) -> str | None:
        return self.reason_edit.text().strip() or None


class CloseAccountabilityDialog(QDialog):
    def __init__(self, conn, day_number: int, remaining: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.day_number = day_number
        self.remaining = remaining
        self.emergency_exit_confirmed = False
        self.setWindowTitle("Active DSA Day Not Complete")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.NORMAL)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)

        layout.addWidget(_title_label("Today's active day isn't finished yet"))
        body = QLabel(
            f"Day {day_number} cannot advance until the required work is finished.\n\n"
            f"Remaining: {remaining} required task(s)"
        )
        body.setProperty("role", "body")
        body.setWordWrap(True)
        layout.addWidget(body)

        return_btn = _primary_button("Return to DSA")
        return_btn.clicked.connect(self.reject)
        layout.addWidget(return_btn)

        emergency_btn = _tertiary_button("Emergency Exit")
        emergency_btn.clicked.connect(self._open_emergency_exit)
        layout.addWidget(emergency_btn)

    def _open_emergency_exit(self) -> None:
        dlg = EmergencyExitDialog(self.day_number, self.remaining, self)
        if dlg.exec() == QDialog.Accepted and dlg.confirmed:
            now = config.now_local().isoformat()
            self.conn.execute(
                "INSERT INTO emergency_exits (ts, day_number, remaining_tasks, reason) VALUES (?, ?, ?, ?)",
                (now, self.day_number, self.remaining, dlg.reason()),
            )
            self.conn.execute(
                "INSERT INTO audit_log (ts, actor, action, details) VALUES (?, 'user', 'emergency_exit', ?)",
                (now, f"day {self.day_number}, {self.remaining} remaining, reason={dlg.reason()}"),
            )
            self.conn.commit()
            self.emergency_exit_confirmed = True
            self.accept()


class SessionRunnerDialog(QDialog):
    """Lightweight OA/mock session runner (spec section 64): countdown
    timer, problem list with LeetCode links, no hints or notes visible
    until the review phase, then a manual finish."""

    def __init__(self, conn, task_row, problems: list, minutes: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.task_row = task_row
        self.remaining_seconds = minutes * 60
        self.setWindowTitle(task_row["title"])
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.NORMAL)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)

        layout.addWidget(_title_label(task_row["title"]))

        self.timer_label = QLabel()
        self.timer_label.setStyleSheet("font-size: 22pt; font-weight: 700;")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self._update_timer_label()
        layout.addWidget(self.timer_label)

        layout.addWidget(section_label("PROBLEMS"))
        problem_list = QListWidget()
        for p in problems:
            problem_list.addItem(QListWidgetItem(f"LC {p['leetcode_number']} — {p['title']}"))
        layout.addWidget(problem_list)

        layout.addWidget(section_label("RESULTS / NOTES — REVIEW PHASE"))
        self.results_edit = QTextEdit()
        layout.addWidget(self.results_edit)

        finish_btn = _primary_button("Finish Session")
        finish_btn.clicked.connect(self._on_finish)
        layout.addWidget(finish_btn)

        self.qtimer = QTimer(self)
        self.qtimer.timeout.connect(self._tick)
        self.qtimer.start(1000)
        self.started_at = config.now_local()

    def _update_timer_label(self) -> None:
        m, s = divmod(max(0, self.remaining_seconds), 60)
        self.timer_label.setText(f"{m:02d}:{s:02d}")

    def _tick(self) -> None:
        self.remaining_seconds -= 1
        self._update_timer_label()
        if self.remaining_seconds <= 0:
            self.qtimer.stop()
            self.timer_label.setText("Time's up")

    def _on_finish(self) -> None:
        self.qtimer.stop()
        note = self.results_edit.toPlainText().strip() or None
        result = pipeline_service.finalize_simple_task(self.conn, self.task_row["id"], note=note)
        if result.get("day_completed"):
            QMessageBox.information(self, "Complete", "Curriculum day complete — next day unlocked.")
        self.accept()
