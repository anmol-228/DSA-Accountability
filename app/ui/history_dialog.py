"""History / calendar view + practice readiness (spec sections 51, 55)."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from app.services import analytics_service, progression_service as prog, streak_service
from app.ui.theme import Spacing, get_palette
from app.ui.widgets import Divider, SlimProgressBar, metadata_label, section_label


class HistoryDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("History")
        self.resize(640, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM, Spacing.MEDIUM)
        layout.setSpacing(Spacing.NORMAL)

        status = prog.get_status(conn)
        title = QLabel(f"{status.completed_days} of 135 days complete")
        title.setProperty("role", "day-indicator")
        title.setStyleSheet("font-size: 16pt;")
        layout.addWidget(title)

        summary_row = QHBoxLayout()
        summary_row.addWidget(metadata_label(f"Schedule delay · {status.schedule_delay_days}d", strong=True))
        summary_row.addWidget(metadata_label(
            f"Activity streak · {streak_service.current_activity_streak(conn)} "
            f"(best {streak_service.best_activity_streak(conn)})"
        ))
        summary_row.addWidget(metadata_label(f"On-schedule streak · {streak_service.on_schedule_streak(conn)}"))
        summary_row.addStretch()
        layout.addLayout(summary_row)
        layout.addWidget(Divider())

        layout.addWidget(section_label("PRACTICE READINESS — not a hiring prediction"))
        readiness = analytics_service.topic_readiness(conn)
        for topic, pct in sorted(readiness.items(), key=lambda kv: -kv[1])[:8]:
            row = QHBoxLayout()
            label = QLabel(topic.replace("_", " ").title())
            label.setFixedWidth(140)
            row.addWidget(label)
            bar = SlimProgressBar(get_palette(), height=6)
            bar.setValue(pct)
            row.addWidget(bar)
            pct_label = metadata_label(f"{pct:.0f}%")
            pct_label.setFixedWidth(36)
            row.addWidget(pct_label)
            layout.addLayout(row)
        layout.addWidget(Divider())

        layout.addWidget(section_label("CURRICULUM DAYS"))
        rows = conn.execute(
            "SELECT day_number, title, original_due_date, completed, completed_at "
            "FROM curriculum_days ORDER BY day_number"
        ).fetchall()

        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels(["Day", "Title", "Original Due", "Completed", "Completed At"])
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        for i, r in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(str(r["day_number"])))
            table.setItem(i, 1, QTableWidgetItem(r["title"]))
            table.setItem(i, 2, QTableWidgetItem(r["original_due_date"]))
            table.setItem(i, 3, QTableWidgetItem("Yes" if r["completed"] else "No"))
            table.setItem(i, 4, QTableWidgetItem(r["completed_at"] or ""))
        table.resizeColumnsToContents()
        layout.addWidget(table)
