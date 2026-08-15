"""Reusable, hand-painted presentational widgets shared across the app.

Custom-painted rather than QSS-image-based so nothing depends on bundled
image assets or PyInstaller resource paths (see icons.py for the same
reasoning applied to icons).
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QWidget

from app.ui.theme import Font, Palette, Radius


def apply_card_shadow(widget: QWidget, palette: Palette, blur: int = 28, y_offset: int = 8) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(palette.shadow))
    widget.setGraphicsEffect(effect)


def primary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("variant", "primary")
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def secondary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def tertiary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("variant", "tertiary")
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def icon_button(icon: QIcon, size: int = 28, icon_size: int = 16, tooltip: str = "") -> QPushButton:
    btn = QPushButton()
    btn.setProperty("variant", "icon")
    btn.setIcon(icon)
    btn.setIconSize(QSize(icon_size, icon_size))
    btn.setFixedSize(size, size)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "section-heading")
    return lbl


def metadata_label(text: str, strong: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "metadata-strong" if strong else "metadata")
    return lbl


class Divider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "divider")
        self.setFixedHeight(1)


class SlimProgressBar(QWidget):
    """A flat, rounded, minimal progress bar — deliberately not QProgressBar
    so no platform chrome (native groove/border/animated stripes) leaks
    through."""

    def __init__(self, palette: Palette, height: int = 5, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._value = 0  # 0..100
        self.setFixedHeight(height)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def setValue(self, value: float) -> None:
        self._value = max(0.0, min(100.0, value))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        radius = rect.height() / 2

        track = QPainterPath()
        track.addRoundedRect(rect, radius, radius)
        painter.fillPath(track, QColor(self._palette.border))

        if self._value > 0:
            fill_width = rect.width() * (self._value / 100.0)
            fill_rect = QRectF(0, 0, fill_width, rect.height())
            fill = QPainterPath()
            fill.addRoundedRect(fill_rect, radius, radius)
            painter.fillPath(fill, QColor(self._palette.btn_dark))
        painter.end()


class TaskRow(QWidget):
    """A single task line: custom rounded checkbox + label, full-row hover
    highlight, click-anywhere-to-open behavior. Completed rows render
    muted/disabled and don't respond to clicks."""

    clicked = Signal()

    def __init__(self, text: str, completed: bool, palette: Palette, parent=None):
        super().__init__(parent)
        self._text = text
        self._completed = completed
        self._palette = palette
        self._hover = False
        self.setToolTip(text)
        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor if not completed else Qt.ArrowCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_completed(self, completed: bool) -> None:
        """Updates checked state in place — no widget recreation. No-ops
        if the value is already correct, so callers can invoke this on
        every poll without triggering unnecessary repaints."""
        if completed == self._completed:
            return
        self._completed = completed
        self.setCursor(Qt.PointingHandCursor if not completed else Qt.ArrowCursor)
        self._hover = False
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        if not self._completed:
            self._hover = True
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._completed and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._palette
        rect = QRectF(self.rect())

        if self._hover:
            hover_path = QPainterPath()
            hover_path.addRoundedRect(rect.adjusted(0, 0, 0, 0), Radius.TASK_HOVER, Radius.TASK_HOVER)
            painter.fillPath(hover_path, QColor(p.hover))

        box_size = 16
        box_y = (rect.height() - box_size) / 2
        box_rect = QRectF(10, box_y, box_size, box_size)
        box_path = QPainterPath()
        box_path.addRoundedRect(box_rect, 4, 4)

        if self._completed:
            painter.fillPath(box_path, QColor(p.btn_dark))
            painter.setPen(QColor(p.btn_dark_text))
            pen = painter.pen()
            pen.setWidthF(1.6)
            painter.setPen(pen)
            cx, cy = box_rect.center().x(), box_rect.center().y()
            painter.drawLine(int(cx - 3.5), int(cy), int(cx - 1), int(cy + 2.8))
            painter.drawLine(int(cx - 1), int(cy + 2.8), int(cx + 4), int(cy - 3.2))
        else:
            painter.setPen(QColor(p.text_tertiary))
            painter.setBrush(QColor(p.surface))
            painter.drawPath(box_path)

        text_rect = QRectF(10 + box_size + 10, 0, rect.width() - box_size - 30, rect.height())
        painter.setPen(QColor(p.text_tertiary if self._completed else p.text_primary))
        font = QFont()
        font.setPointSizeF(Font.TASK)
        painter.setFont(font)
        elided = painter.fontMetrics().elidedText(self._text, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.end()


class ScheduleIndicator(QWidget):
    """Dot + text schedule status ("On schedule" / "N days behind").
    `set_status()` only touches the label/stylesheet when the delay value
    actually differs from last time — built specifically so a background
    poll can call it every cycle without ever repainting when nothing
    changed."""

    def __init__(self, palette: Palette, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._delay_days: int | None = None  # sentinel forces first real update to apply
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._dot = QLabel("●")
        self._text = QLabel("")
        self._text.setProperty("role", "metadata-strong")
        layout.addWidget(self._dot)
        layout.addWidget(self._text)

    def set_status(self, delay_days: int) -> None:
        if delay_days == self._delay_days:
            return
        self._delay_days = delay_days
        p = self._palette
        if delay_days > 0:
            self._dot.setStyleSheet(f"color: {p.warning}; font-size: 9px;")
            text = f"{delay_days} day{'s' if delay_days != 1 else ''} behind"
        else:
            self._dot.setStyleSheet(f"color: {p.success}; font-size: 9px;")
            text = "On schedule"
        if self._text.text() != text:
            self._text.setText(text)


class StatusChip(QLabel):
    """A small rounded pill for compact status text (e.g. LeetCode task
    state, GitHub sync state) — restrained, monochrome, never a loud
    colored badge."""

    def __init__(self, text: str, kind: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "chip")
        self.setProperty("kind", kind)
        self.setAlignment(Qt.AlignCenter)
