"""Camera preview mirroring keeps image and overlay coordinates aligned."""

from __future__ import annotations

import os

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QApplication

from dance_mirror.multimodal.preview import CameraPreviewPacket, HandPreview
from dance_mirror.view.camera_preview import CameraPreview


def _packet() -> CameraPreviewPacket:
    return CameraPreviewPacket(
        frame_bgr=np.asarray(
            [
                [[10, 20, 30], [40, 50, 60]],
                [[70, 80, 90], [100, 110, 120]],
            ],
            dtype=np.uint8,
        ),
        keypoints_px=np.zeros((17, 3), dtype=np.float64),
        scores=np.zeros(17, dtype=np.float64),
        bbox_xyxy=None,
        person_count=1,
        frame_index=0,
        timestamp_s=0.0,
        readiness=0.9,
    )


def test_mirror_flips_image_pixels_and_overlay_coordinates_together() -> None:
    app = QApplication.instance() or QApplication([])
    packet = _packet()
    target = QRectF(0.0, 0.0, 100.0, 100.0)

    plain = CameraPreview(mirror=False)
    mirrored = CameraPreview(mirror=True)

    assert plain._map_xy(packet, target, 0.5, 0.1).x() == 25.0  # noqa: SLF001
    assert mirrored._map_xy(packet, target, 0.5, 0.1).x() == 75.0  # noqa: SLF001
    assert plain._qimage(packet).pixelColor(0, 0).name() == "#1e140a"  # noqa: SLF001
    assert mirrored._qimage(packet).pixelColor(0, 0).name() == "#3c3228"  # noqa: SLF001

    plain.deleteLater()
    mirrored.deleteLater()
    app.processEvents()


def test_hand_skeleton_is_rendered_above_the_frame() -> None:
    app = QApplication.instance() or QApplication([])
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    landmarks = np.zeros((21, 3), dtype=np.float64)
    landmarks[:, 0] = np.linspace(80.0, 240.0, 21)
    landmarks[:, 1] = np.linspace(50.0, 150.0, 21)
    packet = CameraPreviewPacket(
        frame_bgr=frame,
        keypoints_px=np.zeros((17, 3), dtype=np.float64),
        scores=np.zeros(17, dtype=np.float64),
        bbox_xyxy=None,
        person_count=1,
        frame_index=1,
        timestamp_s=0.0,
        readiness=0.9,
        hands=(
            HandPreview(
                side="left",
                name="ok",
                confidence=0.9,
                landmarks_px=landmarks,
            ),
        ),
    )
    preview = CameraPreview(mirror=False)
    preview.set_packet(packet)
    preview.show()
    app.processEvents()
    image = preview.grab().toImage()
    colored_pixels = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.blue() > 180 and color.green() > 120 and color.red() < 150:
                colored_pixels += 1
    assert colored_pixels > 50
    preview.deleteLater()
    app.processEvents()
