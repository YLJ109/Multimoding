"""Qt camera preview with polished body, face, and hand overlays."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from dance_mirror.domain.skeleton import EDGES
from dance_mirror.multimodal.face import face_connections
from dance_mirror.multimodal.gesture import (
    face_expression_name_zh,
    gesture_name_zh,
    hand_edges,
    hand_side_name_zh,
)
from dance_mirror.multimodal.preview import CameraPreviewPacket, HandPreview
from dance_mirror.view.design_tokens import palette_for

_PREVIEW_SIZES = {
    "collapsed": (0, 0),
    "small": (260, 146),
    "medium": (320, 180),
    "large": (380, 214),
}

_HUD_HEIGHT = 30.0

_LEFT_JOINTS = {1, 3, 5, 7, 9, 11, 13, 15}
_RIGHT_JOINTS = {2, 4, 6, 8, 10, 12, 14, 16}
# Maps a hand side label to the design-token attribute carrying its accent color.
_HAND_SIDES = {"left": "hud_hand_left", "right": "hud_hand_right", "unknown": "hud_hand_unknown"}
_FACE_EDGES = face_connections()
_HAND_EDGES = hand_edges()


@dataclass(frozen=True, slots=True)
class PreviewState:
    """Small state snapshot useful for diagnostics and tests."""

    connected: bool = False
    size_mode: str = "medium"
    person_count: int = 0
    readiness: float = 0.0
    frame_index: int = -1
    hand_count: int = 0
    face_visible: bool = False


@dataclass(slots=True)
class OverlayOptions:
    """Per-page visibility controls for the camera overlay."""

    body: bool = True
    face: bool = True
    hands: bool = True
    bbox: bool = True
    hud: bool = True
    labels: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {
            "body": bool(self.body),
            "face": bool(self.face),
            "hands": bool(self.hands),
            "bbox": bool(self.bbox),
            "hud": bool(self.hud),
            "labels": bool(self.labels),
        }


class CameraPreview(QWidget):
    """Draw a downscaled BGR frame and its multimodal vector overlays."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        size_mode: str = "medium",
        mirror: bool = True,
    ) -> None:
        super().__init__(parent)
        self._packet: CameraPreviewPacket | None = None
        self._size_mode = size_mode if size_mode in _PREVIEW_SIZES else "medium"
        self._theme_mode = "light"
        self._mirror = bool(mirror)
        self._privacy_masked = False
        self._placeholder = "摄像头未连接"
        self._overlays = OverlayOptions()
        self.setMinimumSize(180, 102)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_size()

    @property
    def size_mode(self) -> str:
        return self._size_mode

    @property
    def state(self) -> PreviewState:
        packet = self._packet
        return PreviewState(
            connected=packet is not None,
            size_mode=self._size_mode,
            person_count=packet.person_count if packet is not None else 0,
            readiness=packet.readiness if packet is not None else 0.0,
            frame_index=packet.frame_index if packet is not None else -1,
            hand_count=len(packet.hands) if packet is not None else 0,
            face_visible=bool(
                packet is not None and packet.face_landmarks_px.shape[0] > 0
            ),
        )

    def set_packet(self, packet: CameraPreviewPacket) -> None:
        self._packet = packet
        self._privacy_masked = packet.privacy_masked
        self.update()

    def clear(self) -> None:
        self._packet = None
        self.update()

    def set_size_mode(self, mode: str) -> None:
        if mode not in _PREVIEW_SIZES:
            mode = "medium"
        self._size_mode = mode
        self._apply_size()
        self.setVisible(mode != "collapsed")
        self.update()

    def set_mirror(self, enabled: bool) -> None:
        self._mirror = bool(enabled)
        self.update()

    def set_theme_mode(self, theme: str) -> None:
        self._theme_mode = "dark" if str(theme).lower() == "dark" else "light"
        self.update()

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    def set_overlay_options(
        self,
        *,
        body: bool | None = None,
        face: bool | None = None,
        hands: bool | None = None,
        bbox: bool | None = None,
        hud: bool | None = None,
        labels: bool | None = None,
    ) -> None:
        if body is not None:
            self._overlays.body = bool(body)
        if face is not None:
            self._overlays.face = bool(face)
        if hands is not None:
            self._overlays.hands = bool(hands)
        if bbox is not None:
            self._overlays.bbox = bool(bbox)
        if hud is not None:
            self._overlays.hud = bool(hud)
        if labels is not None:
            self._overlays.labels = bool(labels)
        self.update()
        self._apply_size()

    def _apply_size(self) -> None:
        width, height = _PREVIEW_SIZES[self._size_mode]
        if width <= 0:
            self.setFixedSize(1, 1)
            return
        self.setFixedSize(width, round(height + self._hud_height()))

    def _hud_height(self) -> float:
        return _HUD_HEIGHT if self._overlays.hud else 0.0

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        panel = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        palette = palette_for(self._theme_mode)
        painter.setPen(QPen(QColor(palette.camera_border), 1.0))
        painter.setBrush(QColor(palette.camera_background))
        painter.drawRoundedRect(panel, 7.0, 7.0)
        packet = self._packet
        if packet is None:
            painter.setPen(QColor(palette.camera_placeholder))
            painter.drawText(panel, Qt.AlignmentFlag.AlignCenter, self._placeholder)
            return

        image = self._qimage(packet)
        frame_panel = QRectF(
            panel.left(),
            panel.top(),
            panel.width(),
            max(1.0, panel.height() - self._hud_height()),
        )
        target = self._aspect_fit(packet, frame_panel.adjusted(2, 2, -2, -2))
        painter.setClipRect(target)
        painter.drawImage(target, image)
        if self._overlays.face:
            self._draw_face(painter, packet, target, palette)
        if self._overlays.body:
            self._draw_body(painter, packet, target, palette)
        if self._overlays.bbox:
            self._draw_boxes(painter, packet, target, palette)
        if self._overlays.hands:
            self._draw_hands(painter, packet, target, palette)
        painter.setClipping(False)
        if self._overlays.hud:
            self._draw_hud(painter, packet, panel, palette)
        if self._privacy_masked:
            painter.setBrush(QColor(palette.hud_privacy_fill))
            painter.setPen(QPen(QColor(palette.hud_privacy_stroke), 1.2))
            painter.drawRoundedRect(frame_panel.adjusted(2, 2, -2, -2), 6.0, 6.0)

    def _qimage(self, packet: CameraPreviewPacket) -> QImage:
        source = packet.frame_bgr[:, ::-1] if self._mirror else packet.frame_bgr
        frame = np.ascontiguousarray(source[:, :, ::-1])
        height, width, _ = frame.shape
        image = QImage(
            frame.data,
            width,
            height,
            int(frame.strides[0]),
            QImage.Format.Format_RGB888,
        )
        return image.copy()

    def _aspect_fit(self, packet: CameraPreviewPacket, bounds: QRectF) -> QRectF:
        frame_height, frame_width = packet.frame_bgr.shape[:2]
        source_ratio = frame_width / max(frame_height, 1)
        if bounds.width() / max(bounds.height(), 1.0) > source_ratio:
            height = bounds.height()
            width = height * source_ratio
        else:
            width = bounds.width()
            height = width / max(source_ratio, 1e-6)
        return QRectF(
            bounds.center().x() - width / 2.0,
            bounds.center().y() - height / 2.0,
            width,
            height,
        )

    def _map_xy(
        self,
        packet: CameraPreviewPacket,
        target: QRectF,
        x: float,
        y: float,
    ) -> QPointF:
        height, width = packet.frame_bgr.shape[:2]
        normalized_x = float(x) / max(width, 1)
        normalized_y = float(y) / max(height, 1)
        if self._mirror:
            normalized_x = 1.0 - normalized_x
        return QPointF(
            target.left() + normalized_x * target.width(),
            target.top() + normalized_y * target.height(),
        )

    def _mapped_point(
        self,
        packet: CameraPreviewPacket,
        target: QRectF,
        index: int,
    ) -> QPointF:
        return self._map_xy(
            packet,
            target,
            packet.keypoints_px[index, 0],
            packet.keypoints_px[index, 1],
        )

    def _draw_face(
        self,
        painter: QPainter,
        packet: CameraPreviewPacket,
        target: QRectF,
        palette: object,
    ) -> None:
        points = packet.face_landmarks_px
        if points.shape[0] == 0:
            return
        mapped = [
            self._map_xy(packet, target, float(point[0]), float(point[1]))
            for point in points
        ]
        painter.setPen(
            QPen(
                QColor(palette.hud_face_edge),
                1.05,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        for first, second in _FACE_EDGES:
            painter.drawLine(mapped[first], mapped[second])
        painter.setBrush(QColor(palette.hud_face_dot))
        painter.setPen(Qt.PenStyle.NoPen)
        for index in (1, 2, 4, 5, 6, 9, 10, 13, 14, 33, 61, 133, 152, 263, 291, 362):
            painter.drawEllipse(mapped[index], 1.25, 1.25)

    def _draw_body(
        self,
        painter: QPainter,
        packet: CameraPreviewPacket,
        target: QRectF,
        palette: object,
    ) -> None:
        points = [self._mapped_point(packet, target, index) for index in range(17)]
        for first, second in EDGES:
            confidence = min(float(packet.scores[first]), float(packet.scores[second]))
            if confidence < 0.25:
                continue
            painter.setPen(
                QPen(
                    QColor(palette.hud_bone_shadow),
                    5.0,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(points[first], points[second])
            painter.setPen(
                QPen(
                    self._joint_color(first, confidence, packet.readiness),
                    2.4,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(points[first], points[second])
        for index, point in enumerate(points):
            confidence = float(packet.scores[index])
            radius = 4.2 if confidence >= 0.5 else 2.8
            painter.setPen(QPen(QColor(palette.hud_joint_outline), 1.2))
            painter.setBrush(self._joint_color(index, confidence, packet.readiness))
            painter.drawEllipse(point, radius, radius)

    def _draw_hands(
        self,
        painter: QPainter,
        packet: CameraPreviewPacket,
        target: QRectF,
        palette: object,
    ) -> None:
        for hand in packet.hands:
            color = QColor(getattr(palette, _HAND_SIDES.get(hand.side, "hud_hand_unknown")))
            mapped = [
                self._map_xy(
                    packet,
                    target,
                    float(point[0]),
                    float(point[1]),
                )
                for point in hand.landmarks_px
            ]
            painter.setPen(
                QPen(
                    QColor(palette.hud_bone_shadow),
                    6.0,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            for first, second in _HAND_EDGES:
                painter.drawLine(mapped[first], mapped[second])
            halo = QColor(color)
            halo.setAlpha(85)
            painter.setPen(QPen(halo, 5.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for first, second in _HAND_EDGES:
                painter.drawLine(mapped[first], mapped[second])
            painter.setPen(QPen(color, 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for first, second in _HAND_EDGES:
                painter.drawLine(mapped[first], mapped[second])
            painter.setPen(QPen(QColor(palette.hud_joint_outline), 0.9))
            painter.setBrush(color)
            for index, point in enumerate(mapped):
                radius = 3.8 if index in {4, 8, 12, 16, 20} else 2.8
                painter.drawEllipse(point, radius, radius)
            if self._overlays.labels:
                label = f"{hand_side_name_zh(hand.side)} · {gesture_name_zh(hand.name)}"
                anchor = mapped[0]
                badge = QRectF(anchor.x() - 3, anchor.y() + 5, 72, 18)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette.hud_badge_bg))
                painter.drawRoundedRect(badge, 4.0, 4.0)
                painter.setPen(color.lighter(145))
                painter.drawText(badge.adjusted(5, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter, label)

    def _draw_boxes(
        self,
        painter: QPainter,
        packet: CameraPreviewPacket,
        target: QRectF,
        palette: object,
    ) -> None:
        if packet.bbox_xyxy is not None:
            self._draw_box(
                painter,
                packet,
                target,
                packet.bbox_xyxy,
                QColor(palette.hud_bbox_person),
                "人物",
                palette,
            )
        if packet.face_bbox_xyxy is not None:
            self._draw_box(
                painter,
                packet,
                target,
                packet.face_bbox_xyxy,
                QColor(palette.hud_bbox_face),
                face_expression_name_zh(packet.face_expression) if packet.face_expression else "人脸",
                palette,
            )

    def _draw_box(
        self,
        painter: QPainter,
        packet: CameraPreviewPacket,
        target: QRectF,
        bbox: tuple[float, float, float, float],
        color: QColor,
        label: str,
        palette: object,
    ) -> None:
        x1, y1, x2, y2 = bbox
        height, width = packet.frame_bgr.shape[:2]
        del height, width
        first = self._map_xy(packet, target, float(x1), float(y1))
        second = self._map_xy(packet, target, float(x2), float(y2))
        left = min(first.x(), second.x())
        top = min(first.y(), second.y())
        right = max(first.x(), second.x())
        bottom = max(first.y(), second.y())
        box = QRectF(
            left,
            top,
            right - left,
            bottom - top,
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 1.4, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(box, 4.0, 4.0)
        if self._overlays.labels:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 190))
            painter.drawRoundedRect(
                QRectF(box.left(), max(target.top(), box.top() - 18.0), min(86.0, box.width()), 17.0),
                3.0,
                3.0,
            )
            painter.setPen(QColor(palette.hud_badge_text))
            painter.drawText(
                QRectF(box.left() + 4, max(target.top(), box.top() - 18.0), 82, 17),
                Qt.AlignmentFlag.AlignVCenter,
                label,
            )

    def _joint_color(self, index: int, confidence: float, readiness: float) -> QColor:
        if confidence < 0.25:
            return QColor(palette_for(self._theme_mode).muted)
        if readiness >= 0.78:
            return QColor(palette_for(self._theme_mode).success)
        if readiness >= 0.5:
            return QColor(palette_for(self._theme_mode).warning)
        if index in _LEFT_JOINTS:
            return QColor(palette_for(self._theme_mode).hud_joint_left)
        if index in _RIGHT_JOINTS:
            return QColor(palette_for(self._theme_mode).hud_joint_right)
        return QColor(palette_for(self._theme_mode).hud_joint_empty)

    def _draw_hud(
        self,
        painter: QPainter,
        packet: CameraPreviewPacket,
        panel: QRectF,
        palette: object,
    ) -> None:
        badge = QRectF(
            panel.left() + 4.0,
            panel.bottom() - _HUD_HEIGHT + 3.0,
            max(1.0, panel.width() - 8.0),
            _HUD_HEIGHT - 6.0,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.hud_badge_bg))
        painter.drawRoundedRect(badge, 5.0, 5.0)
        painter.setPen(QColor(palette.hud_text))
        text = (
            f"准备度 {packet.readiness * 100:3.0f}%  ·  人物 {packet.person_count}  ·  "
            f"手部 {len(packet.hands)}"
        )
        if packet.face_landmarks_px.shape[0]:
            text += f"  ·  {face_expression_name_zh(packet.face_expression)}"
        painter.drawText(badge.adjusted(7, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter, text)


def packet_from_bgr(
    frame: object,
    *,
    keypoints_px: object,
    scores: object,
    bbox_xyxy: tuple[float, float, float, float] | None,
    person_count: int,
    frame_index: int,
    timestamp_s: float,
    readiness: float,
    privacy_masked: bool = False,
    hands: tuple[HandPreview, ...] = (),
    face_landmarks_px: object | None = None,
    face_bbox_xyxy: tuple[float, float, float, float] | None = None,
    face_expression: str = "",
    eye_open: float = 0.0,
    mouth_open: float = 0.0,
    **kwargs: object,
) -> CameraPreviewPacket:
    """Compatibility helper for workers that already prepared overlay data."""
    del kwargs
    from dance_mirror.multimodal.preview import packet_from_bgr as build_packet

    return build_packet(
        frame,
        keypoints_px=keypoints_px,
        scores=scores,
        bbox_xyxy=bbox_xyxy,
        person_count=person_count,
        frame_index=frame_index,
        timestamp_s=timestamp_s,
        readiness=readiness,
        privacy_masked=privacy_masked,
        hands=hands,
        face_landmarks_px=face_landmarks_px,
        face_bbox_xyxy=face_bbox_xyxy,
        face_expression=face_expression,
        eye_open=eye_open,
        mouth_open=mouth_open,
    )
