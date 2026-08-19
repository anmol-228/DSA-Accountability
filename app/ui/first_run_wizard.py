"""Interactive first-run configuration for a new, portable installation."""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app import config
from app.services import (
    git_service,
    onboarding_service,
    pairing_service,
    pipeline_service,
    startup_service,
)
from app.ui.theme import Spacing
from app.ui.widgets import Divider, StatusChip, primary_button, secondary_button


def run_checks(conn) -> list[tuple[str, bool, str]]:
    """Return genuine prerequisite/configuration checks without mutating state."""
    java = shutil.which("java")
    javac = shutil.which("javac")
    git = shutil.which("git")
    code = shutil.which("code")
    repo = pipeline_service.get_dsa135_repo(conn)
    repo_exists = git_service.is_repo(repo)
    token_present = conn.execute(
        "SELECT 1 FROM settings WHERE key = 'pairing_token'"
    ).fetchone() is not None
    return [
        ("Database", True, "Ready"),
        ("Java runtime", java is not None, "Ready" if java else "Not found on PATH"),
        ("Java compiler", javac is not None, "Ready" if javac else "Not found on PATH"),
        ("Git", git is not None, "Ready" if git else "Not found on PATH"),
        ("VS Code", code is not None, "Ready" if code else "Optional — not found"),
        ("Learner repo", repo_exists, "Existing Git repo" if repo_exists else "Will create"),
        ("Chrome extension", token_present, "Token ready — pair once" if token_present else "Token not generated"),
        ("Windows startup", True, "On" if startup_service.is_startup_enabled() else "Off"),
    ]


class FirstRunWizard(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("DSA Accountability — First Run Setup")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)
        layout.setSpacing(Spacing.NORMAL)

        welcome = QLabel("Welcome to DSA Accountability")
        welcome.setProperty("role", "day-indicator")
        welcome.setStyleSheet("font-size: 17pt;")
        layout.addWidget(welcome)
        subtitle = QLabel(
            "Choose your own Day 1 and learner repository. The 135-day curriculum "
            "ends 134 calendar days after your selected date."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addWidget(Divider())

        layout.addWidget(QLabel("Start date (Curriculum Day 1)"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        today = config.today_local()
        self.start_date_edit.setDate(QDate(today.year, today.month, today.day))
        self.start_date_edit.dateChanged.connect(self._update_target_label)
        layout.addWidget(self.start_date_edit)
        self.target_label = QLabel()
        self.target_label.setProperty("role", "metadata")
        layout.addWidget(self.target_label)
        self._update_target_label()

        layout.addWidget(QLabel("Learner repository folder"))
        repo_row = QHBoxLayout()
        self.repo_edit = QLineEdit(str(config.DEFAULT_DSA135_REPO))
        repo_row.addWidget(self.repo_edit)
        browse = secondary_button("Browse")
        browse.clicked.connect(self._browse_repo)
        repo_row.addWidget(browse)
        layout.addLayout(repo_row)
        repo_help = QLabel(
            "Choose an existing Git repository or an empty/new folder. The app will "
            "initialize local Git when needed; the folder name is configurable."
        )
        repo_help.setProperty("role", "metadata")
        repo_help.setWordWrap(True)
        layout.addWidget(repo_help)

        layout.addWidget(QLabel("GitHub remote URL (optional)"))
        self.remote_edit = QLineEdit()
        self.remote_edit.setPlaceholderText("https://github.com/you/your-learning-repo.git")
        layout.addWidget(self.remote_edit)

        self.autopush_cb = QCheckBox("Automatically push completed work when a remote is configured")
        self.autopush_cb.setChecked(True)
        layout.addWidget(self.autopush_cb)
        self.startup_cb = QCheckBox("Launch DSA Accountability when I sign into Windows")
        self.startup_cb.setChecked(False)
        layout.addWidget(self.startup_cb)
        layout.addWidget(Divider())

        # Token must exist BEFORE run_checks() evaluates the "Chrome
        # extension" line below -- otherwise that check sees no token row
        # yet and reports "Token not generated" in the very same dialog
        # that displays a real, just-created token a few widgets down
        # (contradictory-state bug, found and fixed 2026-08-16; ported
        # forward from the flexible-engine branch where it was first found
        # -- this bug predates and is unrelated to that branch's UI model).
        token = pairing_service.get_or_create_token(conn)

        for label, ok, detail in run_checks(conn):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch()
            row.addWidget(StatusChip(detail, kind="success" if ok else "warning"))
            layout.addLayout(row)

        layout.addWidget(Divider())
        layout.addWidget(QLabel("Chrome extension pairing token (keep private)"))
        token_label = QLabel(token)
        token_label.setProperty("role", "metadata-strong")
        token_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        token_label.setWordWrap(True)
        layout.addWidget(token_label)
        chrome_help = QLabel(
            "After setup: open chrome://extensions, enable Developer mode, choose Load "
            "unpacked, select this release's chrome-extension folder, then paste the token "
            "in the extension popup and click Save & Test Connection."
        )
        chrome_help.setProperty("role", "metadata")
        chrome_help.setWordWrap(True)
        layout.addWidget(chrome_help)

        continue_btn = primary_button("Save setup and continue")
        continue_btn.clicked.connect(self._save_and_accept)
        continue_btn.setDefault(True)
        layout.addWidget(continue_btn)

    def _selected_start_date(self) -> dt.date:
        value = self.start_date_edit.date()
        return dt.date(value.year(), value.month(), value.day())

    def _update_target_label(self) -> None:
        start = self._selected_start_date()
        target = start + dt.timedelta(days=config.TOTAL_CURRICULUM_DAYS - 1)
        self.target_label.setText(f"Day 135 target date: {target.isoformat()}")

    def _browse_repo(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select learner repository folder")
        if chosen:
            self.repo_edit.setText(chosen)

    def _save_and_accept(self) -> None:
        try:
            onboarding_service.configure_first_run(
                self.conn,
                start_date=self._selected_start_date(),
                learner_repo=Path(self.repo_edit.text().strip()),
                remote_url=self.remote_edit.text(),
                auto_push=self.autopush_cb.isChecked(),
                startup_enabled=self.startup_cb.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001 - show actionable setup failure
            QMessageBox.warning(self, "Setup could not be saved", str(exc))
            return
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
