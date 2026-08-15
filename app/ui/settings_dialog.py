"""Settings panel (spec section 68). Grouped into sections matching a
modern Windows settings panel layout. All behavior unchanged — presentation
only."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

from app import build_info, config
from app.services import (
    backup_service, export_service, git_service, integration_test_service, pairing_service,
    pipeline_service, schedule_service, startup_service,
)
from app.ui.theme import Spacing
from app.ui.widgets import (
    Divider, secondary_button as _secondary_button, section_label,
    tertiary_button as _tertiary_button,
)


class SettingsDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.resize(500, 640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)
        layout.setSpacing(Spacing.NORMAL)
        scroll.setWidget(body)

        # --- SYSTEM -----------------------------------------------------------
        layout.addWidget(section_label("SYSTEM"))
        schedule_start = schedule_service.get_start_date(conn)
        schedule_end = schedule_service.target_end_date(conn)
        schedule_label = QLabel(
            f"Schedule: Day 1 {schedule_start.isoformat()} · Day 135 {schedule_end.isoformat()}"
        )
        schedule_label.setProperty("role", "metadata")
        schedule_label.setWordWrap(True)
        layout.addWidget(schedule_label)
        self.startup_cb = QCheckBox("Launch when I sign into Windows")
        self.startup_cb.setChecked(startup_service.is_startup_enabled())
        self.startup_cb.toggled.connect(self._on_startup_toggled)
        layout.addWidget(self.startup_cb)
        layout.addWidget(Divider())

        # --- INTEGRATIONS -------------------------------------------------------
        layout.addWidget(section_label("INTEGRATIONS"))
        self.autopush_cb = QCheckBox("Automatic GitHub push")
        row = conn.execute("SELECT value FROM settings WHERE key = 'auto_push_enabled'").fetchone()
        self.autopush_cb.setChecked(row is None or row["value"] == "1")
        self.autopush_cb.toggled.connect(self._on_autopush_toggled)
        layout.addWidget(self.autopush_cb)

        layout.addWidget(QLabel("Learner repository path"))
        repo_row = QHBoxLayout()
        self.repo_edit = QLineEdit(str(pipeline_service.get_dsa135_repo(conn)))
        repo_row.addWidget(self.repo_edit)
        browse_btn = _secondary_button("Browse")
        browse_btn.clicked.connect(self._browse_repo)
        repo_row.addWidget(browse_btn)
        layout.addLayout(repo_row)

        save_repo_btn = _tertiary_button("Save repo path")
        save_repo_btn.clicked.connect(self._save_repo_path)
        layout.addWidget(save_repo_btn)

        remote_btn = _tertiary_button("Configure GitHub remote URL")
        remote_btn.clicked.connect(self._configure_remote)
        layout.addWidget(remote_btn)

        token_btns = QHBoxLayout()
        regen_btn = _tertiary_button("Regenerate pairing token...")
        regen_btn.setAutoDefault(False)
        regen_btn.setDefault(False)
        regen_btn.clicked.connect(self._regenerate_token)
        token_btns.addWidget(regen_btn)
        self._show_token_btn = _tertiary_button("Show pairing token")
        self._show_token_btn.clicked.connect(self._toggle_token_visible)
        token_btns.addWidget(self._show_token_btn)
        self._copy_token_btn = _tertiary_button("Copy")
        self._copy_token_btn.clicked.connect(self._copy_token)
        self._copy_token_btn.setEnabled(False)  # nothing real to copy until shown
        token_btns.addWidget(self._copy_token_btn)
        layout.addLayout(token_btns)

        # Hidden by default -- a pairing token is a credential (anyone
        # who has it can call every authenticated localhost endpoint) and
        # was previously always shown in plain text on every Settings
        # open, including in screenshots taken during earlier debugging.
        # setTextInteractionFlags makes it mouse-selectable (a plain QLabel
        # otherwise has no selection/copy at all -- there was no way to
        # actually get the token out of this dialog before), and the
        # explicit Copy button covers it more reliably than relying on a
        # click-drag selection.
        self._token_visible = False
        self.token_label = QLabel("Current token · ••••••••••••••••••••")
        self.token_label.setProperty("role", "metadata")
        self.token_label.setWordWrap(True)
        self.token_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.token_label)
        layout.addWidget(Divider())

        # --- DATA -----------------------------------------------------------------
        layout.addWidget(section_label("DATA"))
        backup_btn = _tertiary_button("Backup now")
        backup_btn.clicked.connect(self._backup_now)
        layout.addWidget(backup_btn)

        export_row = QHBoxLayout()
        for label, fmt in [("Export JSON", "json"), ("Export CSV", "csv"), ("Export Markdown", "md")]:
            btn = _secondary_button(label)
            btn.clicked.connect(lambda _checked, f=fmt: self._export(f))
            export_row.addWidget(btn)
        layout.addLayout(export_row)

        logs_btn = _tertiary_button("Open logs folder")
        logs_btn.clicked.connect(lambda: __import__("os").startfile(str(config.LOGS_DIR)))
        layout.addWidget(logs_btn)
        layout.addWidget(Divider())

        # --- DIAGNOSTICS ------------------------------------------------------------
        layout.addWidget(section_label("DIAGNOSTICS"))
        test_status = integration_test_service.status(conn)
        self._test_status_label = QLabel(self._format_test_status(test_status))
        self._test_status_label.setProperty("role", "metadata")
        self._test_status_label.setWordWrap(True)
        layout.addWidget(self._test_status_label)

        run_test_btn = _tertiary_button("Run Live LeetCode Integration Test")
        run_test_btn.clicked.connect(self._run_live_integration_test)
        layout.addWidget(run_test_btn)

        stop_test_btn = _tertiary_button("Stop Integration Test Mode")
        stop_test_btn.clicked.connect(self._stop_live_integration_test)
        layout.addWidget(stop_test_btn)

        finalize_test_btn = _tertiary_button("Finalize & Push Test Result")
        finalize_test_btn.clicked.connect(self._finalize_live_integration_test)
        layout.addWidget(finalize_test_btn)
        layout.addWidget(Divider())

        # --- ABOUT ---------------------------------------------------------------
        layout.addWidget(section_label("ABOUT"))
        build_label = QLabel(build_info.display_text())
        build_label.setProperty("role", "metadata")
        build_label.setWordWrap(True)
        build_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(build_label)
        layout.addStretch()

    def _format_test_status(self, s: dict) -> str:
        if not s["active"]:
            return "Live integration test: not armed."
        return (
            f"Live integration test: ARMED for LC{s['leetcode_number']} \"{s['title']}\" "
            f"(slug: {s['slug']}). Open that problem on leetcode.com now — a real session "
            f"will start automatically. This never touches curriculum progress."
        )

    def _run_live_integration_test(self) -> None:
        QMessageBox.information(
            self, "Live LeetCode Integration Test",
            "This validates the real Chrome extension -> desktop -> Git/GitHub pipeline "
            "end-to-end without touching curriculum progress (no task/day completion, no "
            "streak, no revision, no readiness change). Archives to an isolated "
            ".integration-test folder and (if you push) an isolated temporary repository/branch "
            "-- never your configured learner-repository working tree or curriculum files.\n\n"
            "Pick a FREE LeetCode problem you have not already solved for the curriculum. "
            "Do not paste a solution here -- you'll write and submit it yourself on leetcode.com."
        )
        slug, ok = QInputDialog.getText(
            self, "Problem slug",
            "LeetCode URL slug (the part after /problems/, e.g. \"reverse-integer\"):"
        )
        if not ok or not slug.strip():
            return
        number_str, ok = QInputDialog.getText(self, "Problem number", "LeetCode problem number (e.g. 7):")
        if not ok or not number_str.strip().isdigit():
            QMessageBox.warning(self, "Invalid input", "Problem number must be a plain integer.")
            return
        title, ok = QInputDialog.getText(self, "Problem title", "LeetCode problem title (e.g. \"Reverse Integer\"):")
        if not ok or not title.strip():
            return

        source_repo = pipeline_service.get_dsa135_repo(self.conn)
        try:
            isolated_repo = integration_test_service.start(
                self.conn, slug.strip(), int(number_str.strip()), title.strip(), source_repo=source_repo,
            )
        except Exception as exc:  # noqa: BLE001 - surface clone/network/config failures clearly
            QMessageBox.warning(self, "Could not arm test", str(exc))
            return
        self._test_status_label.setText(self._format_test_status(integration_test_service.status(self.conn)))
        QMessageBox.information(
            self, "Armed",
            f"Test mode armed for LC{number_str.strip()} \"{title.strip()}\" in disposable repo:\n"
            f"{isolated_repo}\n\n"
            "Open that problem on leetcode.com now. The extension's normal page-open "
            "notification will start a real tracked session for it."
        )

    def _stop_live_integration_test(self) -> None:
        integration_test_service.stop(self.conn)
        self._test_status_label.setText(self._format_test_status(integration_test_service.status(self.conn)))

    def _finalize_live_integration_test(self) -> None:
        test_status = integration_test_service.status(self.conn)
        session_id = test_status.get("session_id")
        if not session_id:
            QMessageBox.warning(self, "No test session", "No armed integration-test session with a captured event yet.")
            return
        event = self.conn.execute(
            "SELECT id FROM leetcode_events WHERE session_id = ? AND is_fresh = 1 ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if event is None:
            QMessageBox.warning(self, "No fresh Accepted event",
                                 "No fresh Accepted event recorded yet for the armed test session. "
                                 "Submit your solution on leetcode.com first.")
            return
        note, ok = QInputDialog.getText(self, "Test note", "Short note (e.g. \"real submission, monaco_global capture\"):")
        if not ok:
            return
        result = pipeline_service.finalize_integration_test(self.conn, event["id"], note or "(no note)")
        lines = [f"{k}: {v}" for k, v in result.items()]
        QMessageBox.information(self, "Integration test result", "\n".join(lines))

    def _on_startup_toggled(self, checked: bool) -> None:
        try:
            startup_service.enable_startup() if checked else startup_service.disable_startup()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Startup", f"Could not update startup setting: {exc}")

    def _on_autopush_toggled(self, checked: bool) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES ('auto_push_enabled', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("1" if checked else "0",),
        )
        self.conn.commit()

    def _browse_repo(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select learner repository folder")
        if path:
            self.repo_edit.setText(path)

    def _save_repo_path(self) -> None:
        path = Path(self.repo_edit.text().strip())
        pipeline_service.set_dsa135_repo(self.conn, path)
        git_service.ensure_repo(path)
        QMessageBox.information(self, "Saved", f"Learner repo set to {path}")

    def _configure_remote(self) -> None:
        url, ok = QInputDialog.getText(
            self,
            "GitHub Remote",
            "Remote URL (https://github.com/you/your-learning-repo.git):",
        )
        if ok and url.strip():
            repo = pipeline_service.get_dsa135_repo(self.conn)
            git_service.ensure_repo(repo)
            git_service.add_remote(repo, url.strip())
            QMessageBox.information(self, "Saved", f"Remote 'origin' set to {url.strip()}")

    def _toggle_token_visible(self) -> None:
        self._token_visible = not self._token_visible
        if self._token_visible:
            token = pairing_service.get_or_create_token(self.conn)
            self.token_label.setText(f"Current token · {token}")
            self._show_token_btn.setText("Hide pairing token")
        else:
            self.token_label.setText("Current token · ••••••••••••••••••••")
            self._show_token_btn.setText("Show pairing token")
        self._copy_token_btn.setEnabled(self._token_visible)

    def _copy_token(self) -> None:
        token = pairing_service.get_or_create_token(self.conn)
        QApplication.clipboard().setText(token)
        QMessageBox.information(self, "Copied", "Pairing token copied to clipboard.")

    def _regenerate_token(self) -> None:
        # Final production repair pass: regeneration was previously one
        # un-confirmed click away, which is how the desktop token drifted
        # from what was pasted into Chrome at least once this project's
        # history (see docs/PRODUCTION_STABILIZATION_2026-08-12.md,
        # "Pairing token forensics"). Defaults to Cancel so a stray Enter
        # key press can never trigger it.
        box = QMessageBox(self)
        box.setWindowTitle("Regenerate pairing token?")
        box.setText(
            "This will disconnect the Chrome extension and require pairing again.\n\n"
            "Regenerate?"
        )
        cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
        regen_btn = box.addButton("Regenerate", QMessageBox.DestructiveRole)
        box.setDefaultButton(cancel_btn)
        box.exec()
        if box.clickedButton() is not regen_btn:
            return

        token = pairing_service.regenerate_token(self.conn)
        if self._token_visible:
            self.token_label.setText(f"Current token · {token}")
        QMessageBox.information(self, "Token regenerated", "Re-pair the Chrome extension with the new token.")

    def _backup_now(self) -> None:
        path = backup_service.backup_now()
        QMessageBox.information(self, "Backup", f"Backup written to:\n{path}")

    def _export(self, fmt: str) -> None:
        default_name = f"dsa_export.{fmt if fmt != 'md' else 'md'}"
        path_str, _ = QFileDialog.getSaveFileName(self, "Export", default_name)
        if not path_str:
            return
        path = Path(path_str)
        if fmt == "json":
            export_service.export_json(self.conn, path)
        elif fmt == "csv":
            export_service.export_csv(self.conn, path)
        else:
            export_service.export_markdown(self.conn, path)
        QMessageBox.information(self, "Exported", f"Written to {path}")
