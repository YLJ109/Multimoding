"""Native skeleton preview used when WebEngine is unavailable."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from dance_mirror.domain.skeleton import EDGES
from dance_mirror.motion.retarget import RetargetedSkeleton
from dance_mirror.view.design_tokens import palette_for

JOINT_KEYS: tuple[str, ...] = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


class SkeletonPreview(QWidget):
    """Draw two 2D projections as a low-cost fallback renderer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 360)
        self._theme_mode = "light"
        self._reference: RetargetedSkeleton | None = None
        self._user: RetargetedSkeleton | None = None

    def set_reference(self, skeleton: RetargetedSkeleton) -> None:
        self._reference = skeleton
        self.update()

    def set_theme_mode(self, theme: str) -> None:
        self._theme_mode = "dark" if str(theme).lower() == "dark" else "light"
        self.update()

    def set_user(self, skeleton: RetargetedSkeleton) -> None:
        self._user = skeleton
        self.update()

    def clear_user(self) -> None:
        self._user = None
        self.update()

    def paintEvent(self, event: object) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = palette_for(self._theme_mode)
        painter.fillRect(self.rect(), QColor(palette.background))
        left = QRectF(0, 0, self.width() / 2, self.height())
        right = QRectF(self.width() / 2, 0, self.width() / 2, self.height())
        self._draw_skeleton(painter, left, self._reference, QColor(palette.skeleton_left))
        self._draw_skeleton(painter, right, self._user, QColor(palette.skeleton_right))
        painter.setPen(QColor(palette.muted))
        painter.drawText(18, 24, "标准动作")
        painter.drawText(self.width() // 2 + 18, 24, "你的动作")

    def _draw_skeleton(
        self,
        painter: QPainter,
        viewport: QRectF,
        skeleton: RetargetedSkeleton | None,
        color: QColor,
    ) -> None:
        if skeleton is None:
            painter.setPen(QColor(palette_for(self._theme_mode).skeleton_empty))
            painter.drawText(viewport.center(), "等待骨架数据")
            return
        points: dict[str, QPointF] = {}
        for name in JOINT_KEYS:
            x, y, _z = skeleton.joints[name]
            px = viewport.left() + viewport.width() * (0.5 + x * 0.28)
            py = viewport.top() + viewport.height() * (0.52 - y * 0.28)
            points[name] = QPointF(px, py)
        painter.setPen(QPen(color, 2.0))
        for first, second in EDGES:
            first_name = JOINT_KEYS[first]
            second_name = JOINT_KEYS[second]
            painter.drawLine(points[first_name], points[second_name])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for point in points.values():
            painter.drawEllipse(point, 3.0, 3.0)
