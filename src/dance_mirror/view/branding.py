"""Runtime-drawn application icon.

Keeps the app self-contained (no external asset, works offline) while giving the
title bar, taskbar, and dialogs a consistent brand mark that follows the theme.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from dance_mirror.view.design_tokens import palette_for

_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _draw_mark(painter: QPainter, size: int) -> None:
    palette = palette_for("dark")
    radius = size * 0.24

    gradient = QLinearGradient(0.0, 0.0, float(size), float(size))
    gradient.setColorAt(0.0, QColor(palette.primary))
    gradient.setColorAt(1.0, QColor(palette.focus))
    badge = QPainterPath()
    badge.addRoundedRect(QRectF(0.0, 0.0, float(size), float(size)), radius, radius)
    painter.fillPath(badge, QBrush(gradient))

    pen = QPen(QColor(palette.hud_text))
    pen.setWidthF(max(1.0, size * 0.062))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QColor(palette.hud_text))

    head_radius = size * 0.086
    head = QPointF(size * 0.5, size * 0.262)
    painter.drawEllipse(head, head_radius, head_radius)

    neck = QPointF(size * 0.5, size * 0.365)
    hip = QPointF(size * 0.5, size * 0.60)
    painter.drawLine(neck, hip)
    painter.drawLine(neck, QPointF(size * 0.232, size * 0.452))  # left arm raised
    painter.drawLine(neck, QPointF(size * 0.768, size * 0.392))  # right arm higher
    painter.drawLine(hip, QPointF(size * 0.342, size * 0.808))  # left leg
    painter.drawLine(hip, QPointF(size * 0.668, size * 0.788))  # right leg


def application_icon() -> QIcon:
    """Return a multi-resolution icon for the window and taskbar."""
    icon = QIcon()
    for size in _ICON_SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _draw_mark(painter, size)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
