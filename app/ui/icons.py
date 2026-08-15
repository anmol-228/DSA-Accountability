"""Small monochrome line icons, drawn at runtime with QPainter.

No external image assets and no icon-font dependency: every icon is a
handful of vector primitives (lines/arcs/circles) drawn into a QPixmap and
wrapped in a QIcon. This keeps the packaged app self-contained and avoids
PyInstaller resource-path issues entirely.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    return pm, painter


def _finish(pm: QPixmap, painter: QPainter) -> QIcon:
    painter.end()
    return QIcon(pm)


def _pen(color: str, width: float) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def gear_icon(color: str, size: int = 18) -> QIcon:
    pm, p = _canvas(size)
    p.setPen(_pen(color, 1.4))
    p.setBrush(Qt.NoBrush)
    c = size / 2
    r_outer, r_inner = size * 0.34, size * 0.16
    p.drawEllipse(QPointF(c, c), r_outer * 0.62, r_outer * 0.62)
    p.drawEllipse(QPointF(c, c), r_inner, r_inner)
    import math
    for i in range(8):
        angle = math.radians(i * 45)
        x1 = c + math.cos(angle) * r_outer * 0.68
        y1 = c + math.sin(angle) * r_outer * 0.68
        x2 = c + math.cos(angle) * r_outer * 0.98
        y2 = c + math.sin(angle) * r_outer * 0.98
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    return _finish(pm, p)


def clock_icon(color: str, size: int = 18) -> QIcon:
    pm, p = _canvas(size)
    p.setPen(_pen(color, 1.4))
    p.setBrush(Qt.NoBrush)
    c = size / 2
    r = size * 0.36
    p.drawEllipse(QPointF(c, c), r, r)
    p.drawLine(QPointF(c, c), QPointF(c, c - r * 0.55))
    p.drawLine(QPointF(c, c), QPointF(c + r * 0.4, c + r * 0.15))
    return _finish(pm, p)


def close_icon(color: str, size: int = 18) -> QIcon:
    pm, p = _canvas(size)
    p.setPen(_pen(color, 1.5))
    margin = size * 0.32
    p.drawLine(QPointF(margin, margin), QPointF(size - margin, size - margin))
    p.drawLine(QPointF(size - margin, margin), QPointF(margin, size - margin))
    return _finish(pm, p)


def expand_icon(color: str, size: int = 18) -> QIcon:
    pm, p = _canvas(size)
    p.setPen(_pen(color, 1.5))
    m = size * 0.28
    # two small corner brackets pointing diagonally, suggesting expand/collapse
    p.drawLine(QPointF(m, size - m), QPointF(m, size - m * 1.9))
    p.drawLine(QPointF(m, size - m), QPointF(m * 1.9, size - m))
    p.drawLine(QPointF(size - m, m), QPointF(size - m, m * 1.9))
    p.drawLine(QPointF(size - m, m), QPointF(size - m * 1.9, m))
    return _finish(pm, p)


def dots_icon(color: str, size: int = 18) -> QIcon:
    pm, p = _canvas(size)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    c = size / 2
    r = size * 0.06
    spacing = size * 0.22
    for dx in (-spacing, 0, spacing):
        p.drawEllipse(QPointF(c + dx, c), r, r)
    return _finish(pm, p)


def flame_icon(color: str, size: int = 16) -> QIcon:
    pm, p = _canvas(size)
    p.setPen(_pen(color, 1.3))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    s = size
    path.moveTo(s * 0.5, s * 0.08)
    path.cubicTo(s * 0.78, s * 0.35, s * 0.7, s * 0.5, s * 0.6, s * 0.42)
    path.cubicTo(s * 0.66, s * 0.58, s * 0.5, s * 0.55, s * 0.48, s * 0.68)
    path.cubicTo(s * 0.36, s * 0.6, s * 0.34, s * 0.72, s * 0.4, s * 0.82)
    path.cubicTo(s * 0.2, s * 0.72, s * 0.22, s * 0.42, s * 0.4, s * 0.28)
    path.cubicTo(s * 0.36, s * 0.4, s * 0.42, s * 0.4, s * 0.5, s * 0.08)
    p.drawPath(path)
    return _finish(pm, p)


def check_icon(color: str, size: int = 12) -> QIcon:
    pm, p = _canvas(size)
    p.setPen(_pen(color, 1.8))
    p.drawLine(QPointF(size * 0.2, size * 0.55), QPointF(size * 0.42, size * 0.78))
    p.drawLine(QPointF(size * 0.42, size * 0.78), QPointF(size * 0.82, size * 0.24))
    return _finish(pm, p)


def write_checkbox_check_asset(path, color: str = "#FFFFFF", size: int = 14) -> None:
    """Renders a small white checkmark to a PNG file at `path`, used by
    QCheckBox::indicator:checked in theme.py's QSS (native QCheckBox has no
    way to paint a checkmark purely via QSS colors/borders — this is the
    one spot in the app that needs a tiny file asset, generated at runtime,
    never hand-shipped)."""
    pm, p = _canvas(size)
    p.setPen(_pen(color, 1.8))
    p.drawLine(QPointF(size * 0.22, size * 0.53), QPointF(size * 0.42, size * 0.74))
    p.drawLine(QPointF(size * 0.42, size * 0.74), QPointF(size * 0.8, size * 0.28))
    p.end()
    pm.save(str(path))


def app_icon(color: str = "#242424", size: int = 32) -> QIcon:
    """Monochrome tray/app icon: a rounded square with a small checkmark,
    replacing the old flat-orange square."""
    pm, p = _canvas(size)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    rect = QRectF(size * 0.08, size * 0.08, size * 0.84, size * 0.84)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.22, size * 0.22)
    p.drawPath(path)

    p.setPen(_pen("#FFFFFF", size * 0.09))
    cx, cy = size * 0.5, size * 0.5
    p.drawLine(QPointF(cx - size * 0.16, cy + size * 0.02),
               QPointF(cx - size * 0.03, cy + size * 0.15))
    p.drawLine(QPointF(cx - size * 0.03, cy + size * 0.15),
               QPointF(cx + size * 0.2, cy - size * 0.14))
    return _finish(pm, p)


def dot_icon(color: str, size: int = 8) -> QIcon:
    pm, p = _canvas(size)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(0, 0, size, size))
    return _finish(pm, p)
